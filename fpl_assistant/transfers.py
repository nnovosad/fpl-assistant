"""Вычисление доступных бесплатных трансферов из публичной истории команды.

Официальный эндпоинт /my-team/{id}/ (с actual лимитом трансферов) требует логина.
Вместо него симулируем накопление бесплатных трансферов (FT) по формуле FPL
(старт с 1 перед туром 2, +1 за неиспользованный тур, потолок 5), используя
только публичные данные: /entry/{id}/history/.
"""

from __future__ import annotations

from . import config


def calculate_free_transfers(history: dict, upto_event: int) -> int:
    """Считает количество FT, доступных на тур (upto_event + 1).

    `history` — результат FPLClient.get_history(team_id).
    `upto_event` — номер последнего уже сыгранного тура (обычно get_current_event()).
    """
    chip_events_transfer = {
        c["event"] for c in history.get("chips", []) if c.get("name") in ("wildcard", "freehit")
    }
    by_event = {row["event"]: row for row in history.get("current", [])}

    ft = 1
    for gw in range(2, upto_event + 1):
        row = by_event.get(gw)
        if row is None:
            continue

        if gw in chip_events_transfer:
            used_free = 0  # трансферы в этот тур были бесплатными (wildcard/free hit)
        else:
            made = row.get("event_transfers", 0)
            cost = row.get("event_transfers_cost", 0)
            hits = cost // config.TRANSFER_HIT_COST
            used_free = max(0, made - hits)

        ft = max(ft - used_free, 0)
        ft = min(ft + 1, config.FREE_TRANSFER_CAP)

    return ft
