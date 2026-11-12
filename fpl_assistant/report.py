"""Форматирование текстового отчёта на русском языке."""

from __future__ import annotations

from .models import Player, Recommendation

POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def _player_line(p: Player, extra: str = "") -> str:
    return f"  {p.web_name:<18} {p.position.value:<3} {p.club_name:<4} {p.price:>5.1f}M  xP={p.xp_next:>5.1f}{extra}"


def format_squad_section(title: str, squad: list[Player]) -> str:
    lines = [title]
    for p in sorted(squad, key=lambda x: (POS_ORDER[x.position.value], -x.xp_next)):
        lines.append(_player_line(p))
    return "\n".join(lines)


def format_report(
    team_name: str,
    gw_current: int,
    gw_next: int,
    current_squad: list[Player],
    current_budget_bank: float,
    recommendation: Recommendation,
) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"FPL-ассистент — команда «{team_name}»")
    lines.append(f"Текущий (сыгранный) тур: {gw_current}  →  Планируем на тур: {gw_next}")
    lines.append("=" * 70)

    lines.append("")
    lines.append(format_squad_section(f"Текущий состав (тур {gw_current}):", current_squad))
    lines.append(f"\nБанк: {current_budget_bank:.1f}M")

    lines.append("")
    lines.append(f"Доступно бесплатных трансферов на тур {gw_next}: {recommendation.free_transfers_available}")

    lines.append("")
    if not recommendation.transfers:
        lines.append("Рекомендация: трансферы не требуются — состав уже оптимален.")
    else:
        lines.append(f"Рекомендуемые трансферы (суммарный прирост xP: {recommendation.xp_gain:+.1f}):")
        for t in recommendation.transfers:
            cost_label = "бесплатно" if t.is_free else f"платно (-{4} очка)"
            lines.append(
                f"  [{t.urgency.value}] {t.player_out.web_name} ({t.player_out.club_name}) "
                f"→ {t.player_in.web_name} ({t.player_in.club_name}), {cost_label}"
            )
            lines.append(
                f"      прирост xP: тур +{t.gain_next:.1f} / 5 туров +{t.gain_5:.1f}  —  {t.reason}"
            )
        if recommendation.hits_used:
            lines.append(f"  Итоговый штраф за платные трансферы: -{recommendation.hits_cost} очков")
        lines.append(f"  Бюджет после трансферов: {recommendation.budget_after:.1f}M")

    lines.append("")
    lines.append(f"Рекомендуемый старт-11 ({recommendation.formation}), прогноз очков: {recommendation.total_xp:.1f}")
    lines.append(format_squad_section("", recommendation.starting_11))

    if recommendation.bench:
        lines.append("")
        lines.append(format_squad_section("Скамейка запасных (по приоритету выхода):", recommendation.bench))

    lines.append("")
    if recommendation.captain:
        lines.append(f"Капитан:       {recommendation.captain.web_name}  (xP={recommendation.captain.xp_next:.1f})")
    if recommendation.vice_captain:
        lines.append(f"Вице-капитан:  {recommendation.vice_captain.web_name}  (xP={recommendation.vice_captain.xp_next:.1f})")

    lines.append("=" * 70)
    return "\n".join(lines)
