"""Расчёт ожидаемых очков (xP) по официальным правилам FPL.

Подход (идея перенесена из старого проекта Fantasy-AI-bot, адаптирована под
официальный скоринг FPL и реальные поля FPL API):
1. Декомпозиция по событиям: голы, передачи, клиншит, сейвы, DEFCON, карточки.
2. Байесовское сглаживание малых выборок (per-90 ставки подтягиваются к
   позиционным средним по АПЛ).
3. Опциональное уточнение вероятности клиншита через букмекерские коэффициенты
   (The Odds API); при отсутствии данных — через статистику FPL (xG/xA команд).
"""

from __future__ import annotations

import math

from . import config
from .models import Fixture, MatchOdds, Player, Position, Team

PRIORS = config.POSITIONAL_PRIORS


def _shrink(observed: float, prior: float, n_90s: float, k: float) -> float:
    return (n_90s * observed + k * prior) / (n_90s + k)


def _shrunk_xg(p: Player) -> float:
    return _shrink(p.xg_per90, PRIORS[p.position.value]["xg"], p.per90_minutes, config.SHRINK_K_ATTACK)


def _shrunk_xa(p: Player) -> float:
    return _shrink(p.xa_per90, PRIORS[p.position.value]["xa"], p.per90_minutes, config.SHRINK_K_ATTACK)


def _shrunk_saves(p: Player) -> float:
    return _shrink(p.saves_per90, PRIORS["GK"]["saves"], p.per90_minutes, config.SHRINK_K_GK)


def _shrunk_bonus(p: Player) -> float:
    return _shrink(p.bonus_per90, PRIORS[p.position.value]["bonus"], p.per90_minutes, config.SHRINK_K_BONUS)


def _shrunk_yellow(p: Player) -> float:
    return _shrink(p.yellow_per90, PRIORS[p.position.value]["yellow"], p.per90_minutes, config.SHRINK_K_CARDS)


def _shrunk_defcon(p: Player) -> float:
    prior = PRIORS[p.position.value].get("defcon", 0.0)
    return _shrink(p.defensive_contribution_per_90, prior, p.per90_minutes, config.SHRINK_K_DEFCON)


def prob_clean_sheet(opponent_xg: float) -> float:
    """P(клиншит) = exp(-lambda), lambda = ожидаемые голы соперника (Пуассон)."""
    return math.exp(-max(opponent_xg, 0.0))


def _form_modifier(player: Player) -> float:
    """Форма относительно среднесезонной результативности игрока. 0.88..1.12."""
    if player.per90_minutes < 3 or player.form <= 0:
        return 1.0
    season_avg = player.total_points / player.per90_minutes if player.per90_minutes > 0 else 0
    if season_avg <= 0:
        return 1.0
    ratio = max(0.5, min(2.0, player.form / season_avg))
    if ratio <= 1.0:
        return 0.88 + (ratio - 0.5) * (1.0 - 0.88) / (1.0 - 0.5)
    return 1.0 + (ratio - 1.0) * (1.12 - 1.0) / (2.0 - 1.0)


def _fdr_modifier(price_tier: str, fdr: int) -> float:
    tier_map = config.FDR_MODIFIERS.get(price_tier, config.FDR_MODIFIERS["mid"])
    fdr = max(2, min(5, fdr))
    return tier_map.get(fdr, 1.0)


def compute_team_xga(players: list[Player]) -> dict[int, float]:
    """Оценка xGA/90 команды по лучшему вратарю (минимум 450 минут)."""
    best: dict[int, tuple[float, int]] = {}
    for p in players:
        if p.position == Position.GK and p.team_id and p.minutes >= 450:
            cur = best.get(p.team_id)
            if cur is None or p.minutes > cur[1]:
                best[p.team_id] = (p.xgc_per90, p.minutes)
    return {tid: v[0] for tid, v in best.items()}


def compute_team_xgf(players: list[Player]) -> dict[int, float]:
    """Оценка xGF/90 команды — сумма xG полевых игроков, делённая на число матчей."""
    totals: dict[int, float] = {}
    max_minutes: dict[int, int] = {}
    for p in players:
        if p.team_id and p.minutes > 0:
            totals[p.team_id] = totals.get(p.team_id, 0.0) + p.expected_goals
            max_minutes[p.team_id] = max(max_minutes.get(p.team_id, 0), p.minutes)
    result: dict[int, float] = {}
    for tid, total_xg in totals.items():
        matches = max_minutes.get(tid, 900) / 90
        result[tid] = total_xg / matches if matches > 0 else 1.35
    return result


def _expected_points_for_match(
    player: Player,
    opponent_xg_match: float,
    p_cs: float,
    is_home: bool,
    fdr: int,
) -> float:
    """Ожидаемые официальные FPL-очки игрока за один матч."""
    p_plays = player.availability_factor
    if p_plays <= 0:
        return 0.0

    pos = player.position.value
    pts = 0.0

    # --- Появление на поле ---
    # p_plays уже учитывает вероятность сыграть 60+; доля "вышел, но заменён рано"
    # учтена грубо через (1 - p_plays) * небольшую вероятность появления на замену.
    pts += p_plays * config.APPEARANCE_POINTS_FULL

    # --- Голы ---
    pts += _shrunk_xg(player) * config.GOAL_POINTS[pos]

    # --- Передачи ---
    pts += _shrunk_xa(player) * config.ASSIST_POINTS

    # --- Клиншит (только если вышел на 60+ минут) ---
    cs_pts = config.CLEAN_SHEET_POINTS[pos]
    if cs_pts:
        pts += p_cs * cs_pts

    # --- Вратарь: сейвы и пропущенные голы ---
    if pos == "GK":
        pts += _shrunk_saves(player) / 3.0 * config.SAVE_POINTS_PER_3
        pts += (opponent_xg_match / 2.0) * config.GOALS_CONCEDED_PENALTY_PER_2

    # --- Защитник: пропущенные голы тоже штрафуют ---
    if pos == "DEF":
        pts += (opponent_xg_match / 2.0) * config.GOALS_CONCEDED_PENALTY_PER_2

    # --- Defensive contribution (DEFCON) ---
    threshold = config.DEFCON_THRESHOLD.get(pos)
    if threshold:
        rate = _shrunk_defcon(player)
        prob_reach = min(1.0, rate / threshold) if threshold > 0 else 0.0
        pts += prob_reach * config.DEFCON_POINTS

    # --- Бонусы (оценка по исторической частоте) ---
    pts += _shrunk_bonus(player)

    # --- Жёлтые карточки ---
    pts += _shrunk_yellow(player) * config.YELLOW_CARD_POINTS

    # --- Модификаторы: форма, сложность соперника, свой/чужой стадион, явка ---
    form_mod = _form_modifier(player)
    fdr_mod = _fdr_modifier(player.price_tier, fdr)
    home_mod = config.HOME_MOD if is_home else config.AWAY_MOD

    # Появление уже учтено как отдельное слагаемое через p_plays выше;
    # остальные события масштабируем вероятностью выйти на замену по той же логике.
    attacking_part = pts - p_plays * config.APPEARANCE_POINTS_FULL
    pts = p_plays * config.APPEARANCE_POINTS_FULL + attacking_part * form_mod * fdr_mod * home_mod * p_plays

    return max(pts, 0.0)


def calculate_xp(
    player: Player,
    fixtures: list[Fixture],
    teams: dict[int, Team],
    team_xga: dict[int, float],
    team_xgf: dict[int, float],
    league_avg_xg: float = 1.35,
    match_odds: dict[tuple[int, int], MatchOdds] | None = None,
) -> float:
    """Суммарные ожидаемые очки игрока по списку туров fixtures."""
    if not player.team_id or player.minutes < 90:
        return 0.0

    total = 0.0
    for fix in fixtures:
        if fix.home_team_id == player.team_id:
            is_home, fdr, opp_id = True, fix.home_difficulty, fix.away_team_id
        elif fix.away_team_id == player.team_id:
            is_home, fdr, opp_id = False, fix.away_difficulty, fix.home_team_id
        else:
            continue

        odds = match_odds.get((fix.home_team_id, fix.away_team_id)) if match_odds else None
        if odds:
            opp_xg_match = odds.away_xg if is_home else odds.home_xg
            p_cs = odds.home_cs_prob if is_home else odds.away_cs_prob
        else:
            my_xga = team_xga.get(player.team_id, 1.35)
            opp_xgf = team_xgf.get(opp_id, 1.35)
            opp_xg_match = opp_xgf * (my_xga / league_avg_xg)
            opp_xg_match *= config.AWAY_MOD if is_home else config.HOME_MOD
            p_cs = prob_clean_sheet(opp_xg_match)

        total += _expected_points_for_match(player, opp_xg_match, p_cs, is_home, fdr)

    return total


def calculate_all_xp(
    players: list[Player],
    fixtures: list[Fixture],
    teams: dict[int, Team],
    next_gw: int,
    short_horizon: int = 1,
    long_horizon: int = 5,
    match_odds: dict[tuple[int, int], MatchOdds] | None = None,
) -> None:
    """Считает xp_next / xp_5 для всех игроков (мутирует players на месте)."""
    team_xga = compute_team_xga(players)
    team_xgf = compute_team_xgf(players)

    short_fixtures = [f for f in fixtures if next_gw <= f.gameweek < next_gw + short_horizon]
    long_fixtures = [f for f in fixtures if next_gw <= f.gameweek < next_gw + long_horizon]

    for p in players:
        p.xp_next = round(calculate_xp(p, short_fixtures, teams, team_xga, team_xgf, match_odds=match_odds), 2)
        p.xp_5 = round(calculate_xp(p, long_fixtures, teams, team_xga, team_xgf, match_odds=match_odds), 2)
