"""Точка входа: подбор трансферов и капитана для вашей команды в официальном FPL.

Запуск:
    python main.py

ID команды берётся из переменной окружения FPL_TEAM_ID (.env) или аргумента командной строки:
    python main.py 7335846
"""

from __future__ import annotations

import logging
import sys

from fpl_assistant import config, optimizer, scoring
from fpl_assistant.fpl_api import FPLClient
from fpl_assistant.odds_client import OddsClient, normalize_team_name
from fpl_assistant.report import format_report
from fpl_assistant.transfers import calculate_free_transfers

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def _resolve_team_id() -> int:
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except ValueError:
            pass
    return config.FPL_TEAM_ID


def main() -> None:
    team_id = _resolve_team_id()
    client = FPLClient()

    print("Загружаю данные FPL...")
    players_by_id = client.get_players()
    teams = client.get_teams()
    fixtures = client.get_fixtures()

    gw_current = client.get_current_event()
    gw_next = client.get_next_event()

    entry = client.get_entry(team_id)
    team_name = f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip() \
        or entry.get("name", str(team_id))

    picks_data = client.get_picks(team_id, gw_current)
    bank = picks_data["entry_history"]["bank"] / 10.0

    current_squad = [
        players_by_id[pick["element"]]
        for pick in picks_data["picks"]
        if pick["element"] in players_by_id
    ]

    history = client.get_history(team_id)
    free_transfers = calculate_free_transfers(history, upto_event=gw_current)

    print("Считаю прогноз очков (xP) по официальным правилам FPL...")
    all_players = list(players_by_id.values())

    match_odds = {}
    odds_client = OddsClient()
    if odds_client.is_enabled:
        print("Запрашиваю коэффициенты The Odds API...")
        teams_by_name = {normalize_team_name(t.name): t.fpl_id for t in teams.values()}
        match_odds = odds_client.fetch_match_odds(teams_by_name)
        if not match_odds:
            print("  (не удалось сопоставить коэффициенты — используем статистику FPL)")

    scoring.calculate_all_xp(all_players, fixtures, teams, next_gw=gw_next, match_odds=match_odds)

    print("Подбираю трансферы и капитана...")
    recommendation = optimizer.optimize_transfers(
        current_squad=current_squad,
        all_players=all_players,
        budget=bank,
        free_transfers=free_transfers,
    )

    report = format_report(
        team_name=team_name,
        gw_current=gw_current,
        gw_next=gw_next,
        current_squad=current_squad,
        current_budget_bank=bank,
        recommendation=recommendation,
    )
    print()
    print(report)


if __name__ == "__main__":
    main()
