"""Markdown report. No I/O."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from s3savings.estimate import BANDS, ZERO, BucketEstimate, one_time_cost
from s3savings.prices import Prices


def money(v: Decimal) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def gib(n: int) -> str:
    return f"{n / 2**30:,.2f} GiB"


def to_markdown(estimates: list[BucketEstimate], prices: Prices, as_of: date) -> str:
    total_it = sum((e.it_savings for e in estimates), ZERO)
    total_ia = sum((e.ia_savings for e in estimates), ZERO)
    total_now = sum((e.standard_monthly for e in estimates), ZERO)

    lines = [
        f"# S3 storage class savings estimate ({as_of})",
        "",
        "> **Prices are illustrative placeholders** from the price table, not current",
        "> AWS prices. Age is taken from LastModified, not last access, so savings",
        "> are an upper bound. Retrieval fees are not included.",
        "",
        "## Summary",
        "",
        f"- STANDARD storage today: {money(total_now)} per month across "
        f"{len(estimates)} bucket(s).",
        f"- Intelligent-Tiering: about **{money(total_it)} per month** saved.",
        f"- Lifecycle to Standard-IA after {prices.ia_transition_after_days} days: about "
        f"**{money(total_ia)} per month** saved.",
        "",
        "## Per bucket (monthly)",
        "",
        "| Bucket | STANDARD now | IT savings | IT one-time | IA savings | IA one-time |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for e in estimates:
        lines.append(
            f"| {e.bucket} | {money(e.standard_monthly)} | {money(e.it_savings)} | "
            f"{money(one_time_cost(e.it_transitions, prices))} | {money(e.ia_savings)} | "
            f"{money(one_time_cost(e.ia_transitions, prices))} |"
        )

    lines += [
        "",
        "## STANDARD objects by age and size",
        "",
        f"Objects / size. `small` < {prices.it_min_monitored_bytes:,} bytes; otherwise by age: "
        f"`recent` < {prices.it_infrequent_after_days} days, "
        f"`cooling` < {prices.it_archive_instant_after_days} days, `cold` older.",
        "",
        "| Bucket | " + " | ".join(BANDS) + " | Other classes (skipped) |",
        "|---|" + "---:|" * (len(BANDS) + 1),
    ]
    for e in estimates:
        cells = [f"{e.bands[b].objects} / {gib(e.bands[b].bytes)}" for b in BANDS]
        lines.append(f"| {e.bucket} | " + " | ".join(cells) + f" | {e.skipped_other_class} |")

    lines += [
        "",
        "## Rules applied (AWS behaviour, re-verify)",
        "",
        f"- Objects under {prices.it_min_monitored_bytes:,} bytes (`small`) are not tiered by "
        "Intelligent-Tiering and pay no monitoring fee, so they show no IT savings.",
        f"- Standard-IA bills objects as at least {prices.ia_min_billable_bytes:,} bytes, so "
        "`small` objects are left out of the IA option.",
        f"- IA transition only after {prices.ia_transition_after_days} days in STANDARD.",
        "- Standard-IA charges a 30-day minimum; objects deleted soon after transition "
        "cost more than shown. Not modelled.",
    ]
    return "\n".join(lines) + "\n"
