"""Подбор состава, капитана и трансферов.

Алгоритм (идея перенесена из optimizer.py старого проекта, адаптирована под
официальные правила FPL и платные трансферы):
1. Перебираем комбинации OUT-игроков (1..K, K = бесплатные трансферы + 1 платный).
2. Для каждой комбинации ищем лучших IN-кандидатов на тех же позициях с учётом
   бюджета и лимита 3 игрока из клуба.
3. Для каждого получившегося состава считаем лучший старт-11 и капитана.
4. Выбираем вариант с максимальным приростом xP за вычетом штрафа за платные трансферы.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from . import config
from .models import Player, Position, Recommendation, TransferOption, TransferUrgency

# ------------------------------------------------------------------
# Выбор стартового состава
# ------------------------------------------------------------------


def find_best_starting_11(squad: list[Player]) -> tuple[list[Player], list[Player], str, float]:
    """Возвращает (старт-11, скамейка, расстановка, суммарный xP_next)."""
    gks = [p for p in squad if p.position == Position.GK]
    defs = sorted((p for p in squad if p.position == Position.DEF), key=lambda p: p.xp_next, reverse=True)
    mids = sorted((p for p in squad if p.position == Position.MID), key=lambda p: p.xp_next, reverse=True)
    fwds = sorted((p for p in squad if p.position == Position.FWD), key=lambda p: p.xp_next, reverse=True)

    if not gks:
        return [], [], "0-0-0-0", 0.0

    best_gk = max(gks, key=lambda p: p.xp_next)
    best_score = -1.0
    best_lineup: list[Player] = []
    best_formation = ""

    for n_def, n_mid, n_fwd in config.VALID_FORMATIONS:
        if n_def > len(defs) or n_mid > len(mids) or n_fwd > len(fwds):
            continue
        outfield = defs[:n_def] + mids[:n_mid] + fwds[:n_fwd]
        score = best_gk.xp_next + sum(p.xp_next for p in outfield)
        if score > best_score:
            best_score = score
            best_lineup = [best_gk] + outfield
            best_formation = f"1-{n_def}-{n_mid}-{n_fwd}"

    lineup_ids = {p.fpl_id for p in best_lineup}
    bench_gk = [g for g in gks if g.fpl_id not in lineup_ids]
    bench_outfield = sorted(
        (p for p in squad if p.fpl_id not in lineup_ids and p.position != Position.GK),
        key=lambda p: p.xp_next,
        reverse=True,
    )
    bench = bench_gk + bench_outfield

    return best_lineup, bench, best_formation, best_score


# ------------------------------------------------------------------
# Выбор капитана
# ------------------------------------------------------------------


def select_captain(starting_11: list[Player]) -> tuple[Player | None, Player | None]:
    """Капитан = игрок с максимальным xP_next, скорректированным на позицию и форму."""
    if not starting_11:
        return None, None

    def _captain_score(p: Player) -> float:
        pos_bonus = {Position.GK: 0.6, Position.DEF: 0.8, Position.MID: 1.0, Position.FWD: 1.05}[p.position]

        form_bonus = 1.0
        if p.per90_minutes >= 3:
            season_avg = p.total_points / p.per90_minutes if p.per90_minutes > 0 else 0
            if season_avg > 0:
                ratio = p.form / season_avg
                if ratio > 1.3:
                    form_bonus = 1.15
                elif ratio > 1.1:
                    form_bonus = 1.05

        return p.xp_next * pos_bonus * form_bonus

    ranked = sorted(starting_11, key=_captain_score, reverse=True)
    return ranked[0], (ranked[1] if len(ranked) > 1 else None)


# ------------------------------------------------------------------
# Перебор трансферов
# ------------------------------------------------------------------


def _club_counts(squad: list[Player]) -> Counter:
    return Counter(p.club_name for p in squad)


def _candidates_for_position(
    position: Position,
    all_players: list[Player],
    exclude_ids: set[int],
    top_n: int = config.TOP_CANDIDATES,
) -> list[Player]:
    eligible = [
        p for p in all_players
        if p.position == position
        and p.fpl_id not in exclude_ids
        and p.is_available
        and p.minutes >= config.MIN_MINUTES_FOR_CANDIDATE
    ]
    eligible.sort(key=lambda p: p.xp_next, reverse=True)
    return eligible[:top_n]


def optimize_transfers(
    current_squad: list[Player],
    all_players: list[Player],
    budget: float,
    free_transfers: int,
    max_paid_transfers: int = config.MAX_PAID_TRANSFERS,
) -> Recommendation:
    """Ищет лучшую комбинацию из 0..(free_transfers + max_paid_transfers) трансферов."""
    current_ids = {p.fpl_id for p in current_squad}
    max_transfers = max(1, free_transfers + max_paid_transfers)

    base_lineup, base_bench, base_formation, base_score = find_best_starting_11(current_squad)

    # net_score = xP старт-11 минус штраф за платные трансферы
    best_net_score = base_score
    best_combo: list[tuple[Player, Player]] = []
    best_squad = current_squad
    best_hits = 0

    for k in range(1, max_transfers + 1):
        hits = max(0, k - free_transfers)
        hit_penalty = hits * config.TRANSFER_HIT_COST

        for out_combo in combinations(current_squad, k):
            out_set = {p.fpl_id for p in out_combo}
            out_positions = [p.position for p in out_combo]
            freed_budget = budget + sum(p.price for p in out_combo)

            remaining = [p for p in current_squad if p.fpl_id not in out_set]
            remaining_ids = {p.fpl_id for p in remaining}
            remaining_clubs = _club_counts(remaining)

            position_candidates = [
                _candidates_for_position(pos, all_players, remaining_ids | current_ids)
                for pos in out_positions
            ]

            if any(not cands for cands in position_candidates):
                continue

            if k == 1:
                in_combos = [(c,) for c in position_candidates[0]]
            elif k == 2:
                in_combos = [
                    (a, b) for a in position_candidates[0] for b in position_candidates[1]
                    if a.fpl_id != b.fpl_id
                ]
            else:
                in_combos = [
                    (a, b, c)
                    for a in position_candidates[0]
                    for b in position_candidates[1]
                    for c in position_candidates[2]
                    if len({a.fpl_id, b.fpl_id, c.fpl_id}) == 3
                ]

            for in_combo in in_combos:
                total_cost = sum(p.price for p in in_combo)
                if total_cost > freed_budget:
                    continue

                trial_clubs = Counter(remaining_clubs)
                for p in in_combo:
                    trial_clubs[p.club_name] += 1
                if any(cnt > config.MAX_PER_CLUB for cnt in trial_clubs.values()):
                    continue

                trial_squad = remaining + list(in_combo)
                _, _, _, trial_score = find_best_starting_11(trial_squad)
                net_score = trial_score - hit_penalty

                if net_score > best_net_score:
                    best_net_score = net_score
                    best_combo = list(zip(out_combo, in_combo))
                    best_squad = trial_squad
                    best_hits = hits

    if best_net_score - base_score < config.SKIP_THRESHOLD:
        best_combo = []
        best_squad = current_squad
        best_hits = 0

    lineup, bench, formation, total_xp = find_best_starting_11(best_squad)
    captain, vice = select_captain(lineup)

    transfers: list[TransferOption] = []
    for idx, (p_out, p_in) in enumerate(best_combo):
        single_squad = [p for p in current_squad if p.fpl_id != p_out.fpl_id] + [p_in]
        _, _, _, single_score = find_best_starting_11(single_squad)
        gain_next = single_score - base_score
        gain_5 = p_in.xp_5 - p_out.xp_5
        is_free = idx < free_transfers

        if gain_next > config.URGENCY_MANDATORY:
            urgency = TransferUrgency.MANDATORY
        elif gain_next > config.URGENCY_RECOMMENDED:
            urgency = TransferUrgency.RECOMMENDED
        else:
            urgency = TransferUrgency.OPTIONAL

        transfers.append(
            TransferOption(
                player_out=p_out,
                player_in=p_in,
                urgency=urgency,
                gain_next=round(gain_next, 1),
                gain_5=round(gain_5, 1),
                is_free=is_free,
                reason=_generate_reason(p_out, p_in, gain_next),
            )
        )

    new_budget = budget - sum(t.player_in.price - t.player_out.price for t in transfers)

    return Recommendation(
        transfers=transfers,
        starting_11=lineup,
        bench=bench,
        formation=formation,
        captain=captain,
        vice_captain=vice,
        total_xp=round(total_xp, 1),
        xp_gain=round(best_net_score - base_score, 1),
        budget_after=round(new_budget, 1),
        free_transfers_available=free_transfers,
        hits_used=best_hits,
        hits_cost=best_hits * config.TRANSFER_HIT_COST,
    )


def _generate_reason(p_out: Player, p_in: Player, gain: float) -> str:
    parts: list[str] = []
    if not p_out.is_available:
        parts.append("травма/дисквалификация")
    if p_in.form > p_out.form and p_in.form > 5.0:
        parts.append(f"{p_in.web_name} в хорошей форме")
    if gain > 2.0:
        parts.append("заметный прирост ожидаемых очков")
    elif gain > 0.5:
        parts.append("небольшое улучшение")
    return ", ".join(parts) if parts else "оптимизация прогноза"
