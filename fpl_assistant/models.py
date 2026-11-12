"""Датаклассы: игроки, команды, матчи, рекомендации."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Position(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


class TransferUrgency(str, Enum):
    MANDATORY = "ОБЯЗАТЕЛЬНО"
    RECOMMENDED = "РЕКОМЕНДУЕТСЯ"
    OPTIONAL = "НЕОБЯЗАТЕЛЬНО"


@dataclass
class Team:
    fpl_id: int
    name: str
    short_name: str
    strength_attack_home: int = 0
    strength_attack_away: int = 0
    strength_defence_home: int = 0
    strength_defence_away: int = 0


@dataclass
class Fixture:
    id: int
    gameweek: int
    home_team_id: int
    away_team_id: int
    home_difficulty: int  # FDR 1-5
    away_difficulty: int
    finished: bool = False


@dataclass
class Player:
    """Игрок официального FPL (все поля — из bootstrap-static)."""

    def __hash__(self) -> int:
        return hash(self.fpl_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Player):
            return NotImplemented
        return self.fpl_id == other.fpl_id

    fpl_id: int
    web_name: str
    full_name: str
    team_id: int
    club_name: str
    position: Position
    price: float  # в миллионах (now_cost / 10)
    status: str = "a"  # a=available, i=injured, d=doubtful, s=suspended, u=unavailable
    chance_of_playing: int | None = None
    news: str = ""

    minutes: int = 0
    starts: int = 0
    form: float = 0.0
    total_points: int = 0

    expected_goals: float = 0.0
    expected_assists: float = 0.0
    expected_goals_conceded: float = 0.0
    saves: int = 0
    bonus: int = 0
    bps: int = 0
    goals_conceded: int = 0
    clean_sheets: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    penalties_saved: int = 0
    defensive_contribution_per_90: float = 0.0

    # Рассчитанные прогнозные очки (xP)
    xp_next: float = 0.0   # на ближайший тур
    xp_5: float = 0.0      # на ближайшие 5 туров

    @property
    def per90_minutes(self) -> float:
        return self.minutes / 90.0 if self.minutes > 0 else 0.0

    @property
    def xg_per90(self) -> float:
        return self.expected_goals / self.per90_minutes if self.per90_minutes >= 0.5 else 0.0

    @property
    def xa_per90(self) -> float:
        return self.expected_assists / self.per90_minutes if self.per90_minutes >= 0.5 else 0.0

    @property
    def saves_per90(self) -> float:
        return self.saves / self.per90_minutes if self.per90_minutes >= 1.0 else 0.0

    @property
    def xgc_per90(self) -> float:
        return self.expected_goals_conceded / self.per90_minutes if self.per90_minutes >= 1.0 else 0.0

    @property
    def bonus_per90(self) -> float:
        return self.bonus / self.per90_minutes if self.per90_minutes >= 1.0 else 0.0

    @property
    def yellow_per90(self) -> float:
        return self.yellow_cards / self.per90_minutes if self.per90_minutes >= 1.0 else 0.0

    @property
    def starts_ratio(self) -> float:
        """Доля матчей, в которых игрок выходил в старте (0-1)."""
        games = self.minutes / 90.0
        return self.starts / games if games >= 1.0 else 0.0

    @property
    def is_available(self) -> bool:
        return self.status in ("a", "d")

    @property
    def availability_factor(self) -> float:
        """Вероятность того, что игрок сыграет 60+ минут в ближайшем туре."""
        if self.status in ("i", "s", "u"):
            return 0.0
        if self.status == "n":  # not registered / loan
            return 0.0

        physical = 1.0
        if self.chance_of_playing is not None:
            physical = self.chance_of_playing / 100.0

        if self.minutes < 90:
            nailed = 0.10
        elif self.minutes < 450:
            nailed = min(0.55, self.minutes / 900)
        else:
            nailed = max(0.35, min(1.0, self.starts_ratio))

        return physical * nailed

    @property
    def price_tier(self) -> str:
        if self.price > 10.0:
            return "premium"
        if self.price >= 6.0:
            return "mid"
        return "budget"


@dataclass
class MatchOdds:
    """Коэффициенты матча, пересчитанные в ожидаемые голы (xG)."""
    home_team_id: int
    away_team_id: int
    home_xg: float
    away_xg: float
    home_cs_prob: float
    away_cs_prob: float


@dataclass
class TransferOption:
    player_out: Player
    player_in: Player
    urgency: TransferUrgency
    gain_next: float
    gain_5: float
    is_free: bool = True
    reason: str = ""


@dataclass
class Recommendation:
    transfers: list[TransferOption]
    starting_11: list[Player]
    bench: list[Player]
    formation: str
    captain: Player | None = None
    vice_captain: Player | None = None
    total_xp: float = 0.0
    xp_gain: float = 0.0
    budget_after: float = 0.0
    free_transfers_available: int = 1
    hits_used: int = 0
    hits_cost: int = 0
