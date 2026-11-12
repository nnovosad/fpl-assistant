"""Клиент The Odds API: букмекерские коэффициенты -> ожидаемые голы (xG) команд.

Используется как необязательное уточнение прогноза клиншитов. Если ключ не задан
или запрос не удался — вызывающий код должен откатиться на статистику FPL
(см. scoring.py, параметр match_odds=None/отсутствие пары в словаре).
"""

from __future__ import annotations

import logging

import requests

from . import config
from .models import MatchOdds

logger = logging.getLogger(__name__)

# Ручное сопоставление имён клубов FPL -> The Odds API (там, где не совпадают).
_NAME_OVERRIDES = {
    "man city": "manchester city",
    "man utd": "manchester united",
    "spurs": "tottenham hotspur",
    "newcastle": "newcastle united",
    "nott'm forest": "nottingham forest",
    "leeds": "leeds united",
    "wolves": "wolverhampton wanderers",
    "west ham": "west ham united",
    "brighton": "brighton and hove albion",
    "leicester": "leicester city",
    "ipswich town": "ipswich town",
    "hull city": "hull city",
    "coventry city": "coventry city",
}


def normalize_team_name(name: str) -> str:
    """Приводит название клуба к единому виду для сопоставления FPL <-> Odds API."""
    key = name.lower().strip()
    return _NAME_OVERRIDES.get(key, key)


class OddsClient:
    """Клиент The Odds API (h2h-коэффициенты EPL)."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else config.ODDS_API_KEY
        self._session = requests.Session()

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def fetch_match_odds(self, teams_by_name: dict[str, int]) -> dict[tuple[int, int], MatchOdds]:
        """Возвращает {(home_team_id, away_team_id): MatchOdds} для предстоящих матчей.

        `teams_by_name` — нормализованное имя клуба FPL -> fpl team id.
        При любой ошибке (нет ключа, лимит запросов, сеть) возвращает пустой словарь.
        """
        if not self.is_enabled:
            return {}

        url = f"{config.ODDS_API_BASE}/sports/{config.ODDS_SPORT}/odds/"
        params = {
            "apiKey": self.api_key,
            "regions": config.ODDS_REGIONS,
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        try:
            resp = self._session.get(url, params=params, timeout=config.FPL_REQUEST_TIMEOUT)
            resp.raise_for_status()
            matches = resp.json()
        except requests.RequestException as exc:
            logger.warning("The Odds API недоступен, используем статистику FPL: %s", exc)
            return {}

        result: dict[tuple[int, int], MatchOdds] = {}
        for m in matches:
            home_name = normalize_team_name(m.get("home_team", ""))
            away_name = normalize_team_name(m.get("away_team", ""))
            home_id = teams_by_name.get(home_name)
            away_id = teams_by_name.get(away_name)
            if home_id is None or away_id is None:
                continue

            odds = self._best_h2h_odds(m)
            if odds is None:
                continue
            p_home, p_draw, p_away = odds

            home_xg, away_xg = self._odds_to_xg(p_home, p_draw, p_away)
            result[(home_id, away_id)] = MatchOdds(
                home_team_id=home_id,
                away_team_id=away_id,
                home_xg=home_xg,
                away_xg=away_xg,
                home_cs_prob=_poisson_zero(away_xg),
                away_cs_prob=_poisson_zero(home_xg),
            )
        return result

    @staticmethod
    def _best_h2h_odds(match: dict) -> tuple[float, float, float] | None:
        """Усредняет коэффициенты h2h по всем букмекерам и убирает маржу."""
        home_team = match.get("home_team", "")
        away_team = match.get("away_team", "")
        home_prices, draw_prices, away_prices = [], [], []

        for bm in match.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name, price = outcome.get("name"), outcome.get("price")
                    if not price:
                        continue
                    if name == home_team:
                        home_prices.append(price)
                    elif name == away_team:
                        away_prices.append(price)
                    elif name == "Draw":
                        draw_prices.append(price)

        if not home_prices or not away_prices or not draw_prices:
            return None

        home_odds = sum(home_prices) / len(home_prices)
        draw_odds = sum(draw_prices) / len(draw_prices)
        away_odds = sum(away_prices) / len(away_prices)

        inv = [1 / home_odds, 1 / draw_odds, 1 / away_odds]
        total = sum(inv)
        p_home, p_draw, p_away = (v / total for v in inv)  # убираем маржу букмекера
        return p_home, p_draw, p_away

    @staticmethod
    def _odds_to_xg(p_home: float, p_draw: float, p_away: float) -> tuple[float, float]:
        """Грубая оценка ожидаемых голов команд через Пуассон-сетку по P(H/D/A)."""
        best_diff = None
        best_pair = (1.35, 1.2)
        for home_xg in [x / 10 for x in range(3, 36)]:
            for away_xg in [x / 10 for x in range(3, 36)]:
                ph, pd, pa = _match_result_probs(home_xg, away_xg)
                diff = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_pair = (home_xg, away_xg)
        return best_pair


def _poisson_pmf(k: int, lam: float) -> float:
    import math
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _poisson_zero(lam: float) -> float:
    return _poisson_pmf(0, max(lam, 0.0))


def _match_result_probs(home_xg: float, away_xg: float, max_goals: int = 8) -> tuple[float, float, float]:
    p_home = p_draw = p_away = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson_pmf(h, home_xg) * _poisson_pmf(a, away_xg)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
    return p_home, p_draw, p_away
