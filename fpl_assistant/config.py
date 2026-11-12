"""Конфигурация: константы, официальные правила скоринга FPL, переменные окружения."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def _load_dotenv(path: Path) -> None:
    """Минимальный загрузчик .env (без внешних зависимостей)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")

# --- Команда пользователя ---
FPL_TEAM_ID = int(os.environ.get("FPL_TEAM_ID", "7335846"))

# --- FPL API ---
FPL_API_BASE = "https://fantasy.premierleague.com/api"
FPL_REQUEST_TIMEOUT = 20

# --- The Odds API (опционально) ---
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_SPORT = "soccer_epl"
ODDS_REGIONS = "uk"

# --- Состав и бюджет (официальные правила FPL) ---
SQUAD_SIZE = 15
SQUAD_COMPOSITION = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
TOTAL_BUDGET = 100.0

# Допустимые стартовые расстановки: (DEF, MID, FWD), GK всегда 1
VALID_FORMATIONS: list[tuple[int, int, int]] = [
    (3, 5, 2),
    (3, 4, 3),
    (4, 4, 2),
    (4, 3, 3),
    (4, 5, 1),
    (5, 3, 2),
    (5, 4, 1),
    (5, 2, 3),
]

# --- Трансферы ---
MAX_PAID_TRANSFERS = 1  # сколько платных (-4) трансферов сверх бесплатных допускаем за один прогон
TRANSFER_HIT_COST = 4
FREE_TRANSFER_CAP = 5  # лимит накопления бесплатных трансферов (правило с 2024/25)

# --- Официальный скоринг FPL ---
GOAL_POINTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
CLEAN_SHEET_POINTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
ASSIST_POINTS = 3
SAVE_POINTS_PER_3 = 1
GOALS_CONCEDED_PENALTY_PER_2 = -1  # GK/DEF
YELLOW_CARD_POINTS = -1
RED_CARD_POINTS = -3
OWN_GOAL_POINTS = -2
PENALTY_MISS_POINTS = -2
PENALTY_SAVE_POINTS = 5
APPEARANCE_POINTS_SUB = 1   # < 60 минут
APPEARANCE_POINTS_FULL = 2  # >= 60 минут

# Defensive contribution (DEFCON), добавлено с сезона 2025/26
DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}
DEFCON_POINTS = 2

# --- Байесовское сглаживание малых выборок ---
SHRINK_K_ATTACK = 5.0
SHRINK_K_GK = 8.0
SHRINK_K_BONUS = 8.0
SHRINK_K_CARDS = 10.0
SHRINK_K_DEFCON = 6.0

# Позиционные приоры (среднее по АПЛ на 90 минут)
POSITIONAL_PRIORS = {
    "GK":  {"xg": 0.00, "xa": 0.00, "saves": 3.0, "bonus": 0.05, "yellow": 0.04, "defcon": 0.0},
    "DEF": {"xg": 0.04, "xa": 0.06, "bonus": 0.12, "yellow": 0.12, "defcon": 6.0},
    "MID": {"xg": 0.10, "xa": 0.10, "bonus": 0.15, "yellow": 0.10, "defcon": 5.0},
    "FWD": {"xg": 0.25, "xa": 0.08, "bonus": 0.15, "yellow": 0.08, "defcon": 2.0},
}

# --- Модификаторы по сложности соперника (FDR) и месту проведения матча ---
FDR_MODIFIERS = {
    "premium": {2: 1.08, 3: 1.00, 4: 0.95, 5: 0.90},
    "mid":     {2: 1.10, 3: 1.00, 4: 0.93, 5: 0.85},
    "budget":  {2: 1.15, 3: 1.00, 4: 0.90, 5: 0.80},
}
HOME_MOD = 1.05
AWAY_MOD = 0.95

# --- Порог срочности трансфера (прирост xP за ближайший тур) ---
URGENCY_MANDATORY = 3.0
URGENCY_RECOMMENDED = 1.0
SKIP_THRESHOLD = 0.5  # если лучший вариант даёт меньше — трансферы не рекомендуются

# Сколько лучших кандидатов на позицию рассматривать при переборе
TOP_CANDIDATES = 8

# Минимум сыгранных минут за сезон, чтобы считаться кандидатом на трансфер
MIN_MINUTES_FOR_CANDIDATE = 450

# FPL element_type -> наша позиция
FPL_POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
