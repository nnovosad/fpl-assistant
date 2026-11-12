"""Синхронный клиент официального FPL API."""

from __future__ import annotations

import logging

import requests

from . import config
from .models import Fixture, Player, Position, Team

logger = logging.getLogger(__name__)


class FPLClient:
    """Клиент публичного API fantasy.premierleague.com (без логина)."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._bootstrap_cache: dict | None = None
        self._fixtures_cache: list | None = None

    # ------------------------------------------------------------------
    # Низкоуровневые запросы
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict | list:
        url = f"{config.FPL_API_BASE}{path}"
        logger.info("GET %s", url)
        resp = self._session.get(url, timeout=config.FPL_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _bootstrap(self) -> dict:
        if self._bootstrap_cache is None:
            self._bootstrap_cache = self._get("/bootstrap-static/")
        return self._bootstrap_cache

    def _fixtures_raw(self) -> list:
        if self._fixtures_cache is None:
            self._fixtures_cache = self._get("/fixtures/")
        return self._fixtures_cache

    # ------------------------------------------------------------------
    # Общие данные
    # ------------------------------------------------------------------

    def get_teams(self) -> dict[int, Team]:
        teams: dict[int, Team] = {}
        for t in self._bootstrap()["teams"]:
            teams[t["id"]] = Team(
                fpl_id=t["id"],
                name=t["name"],
                short_name=t["short_name"],
                strength_attack_home=t.get("strength_attack_home", 1100),
                strength_attack_away=t.get("strength_attack_away", 1100),
                strength_defence_home=t.get("strength_defence_home", 1100),
                strength_defence_away=t.get("strength_defence_away", 1100),
            )
        return teams

    def get_fixtures(self) -> list[Fixture]:
        fixtures: list[Fixture] = []
        for f in self._fixtures_raw():
            if f.get("event") is None:
                continue
            fixtures.append(
                Fixture(
                    id=f["id"],
                    gameweek=f["event"],
                    home_team_id=f["team_h"],
                    away_team_id=f["team_a"],
                    home_difficulty=f.get("team_h_difficulty", 3),
                    away_difficulty=f.get("team_a_difficulty", 3),
                    finished=f.get("finished", False),
                )
            )
        return fixtures

    def get_players(self) -> dict[int, Player]:
        teams = self.get_teams()
        players: dict[int, Player] = {}
        for raw in self._bootstrap()["elements"]:
            pos = config.FPL_POSITION_MAP.get(raw["element_type"], "MID")
            team = teams.get(raw["team"])
            players[raw["id"]] = Player(
                fpl_id=raw["id"],
                web_name=raw.get("web_name", ""),
                full_name=f"{raw.get('first_name', '')} {raw.get('second_name', '')}".strip(),
                team_id=raw["team"],
                club_name=team.short_name if team else "",
                position=Position(pos),
                price=raw.get("now_cost", 0) / 10.0,
                status=raw.get("status", "a"),
                chance_of_playing=raw.get("chance_of_playing_next_round"),
                news=raw.get("news", ""),
                minutes=int(raw.get("minutes", 0)),
                starts=int(raw.get("starts", 0)),
                form=float(raw.get("form") or 0),
                total_points=int(raw.get("total_points", 0)),
                expected_goals=float(raw.get("expected_goals") or 0),
                expected_assists=float(raw.get("expected_assists") or 0),
                expected_goals_conceded=float(raw.get("expected_goals_conceded") or 0),
                saves=int(raw.get("saves", 0)),
                bonus=int(raw.get("bonus", 0)),
                bps=int(raw.get("bps", 0)),
                goals_conceded=int(raw.get("goals_conceded", 0)),
                clean_sheets=int(raw.get("clean_sheets", 0)),
                yellow_cards=int(raw.get("yellow_cards", 0)),
                red_cards=int(raw.get("red_cards", 0)),
                penalties_saved=int(raw.get("penalties_saved", 0)),
                defensive_contribution_per_90=float(raw.get("defensive_contribution_per_90") or 0),
            )
        return players

    def get_current_event(self) -> int:
        for ev in self._bootstrap()["events"]:
            if ev.get("is_current"):
                return ev["id"]
        # fallback: последний завершённый
        finished = [ev["id"] for ev in self._bootstrap()["events"] if ev.get("finished")]
        return max(finished) if finished else 1

    def get_next_event(self) -> int:
        for ev in self._bootstrap()["events"]:
            if ev.get("is_next"):
                return ev["id"]
        return self.get_current_event() + 1

    # ------------------------------------------------------------------
    # Данные конкретной команды пользователя
    # ------------------------------------------------------------------

    def get_entry(self, team_id: int) -> dict:
        return self._get(f"/entry/{team_id}/")

    def get_picks(self, team_id: int, event: int) -> dict:
        return self._get(f"/entry/{team_id}/event/{event}/picks/")

    def get_history(self, team_id: int) -> dict:
        """Возвращает {'current': [...], 'past': [...], 'chips': [...]}."""
        return self._get(f"/entry/{team_id}/history/")
