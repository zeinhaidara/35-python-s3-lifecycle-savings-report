"""Load the user-editable price table. Defaults are illustrative placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

# AWS won't transition to Standard-IA before 30 days. AWS behaviour, re-verify.
AWS_MIN_DAYS_BEFORE_IA = 30


class PriceError(ValueError):
    pass


@dataclass(frozen=True)
class Prices:
    standard: Decimal
    standard_ia: Decimal
    it_frequent: Decimal
    it_infrequent: Decimal
    it_archive_instant: Decimal
    it_monitoring_per_1000: Decimal
    transition_per_1000: Decimal
    it_min_monitored_bytes: int
    it_infrequent_after_days: int
    it_archive_instant_after_days: int
    ia_min_billable_bytes: int
    ia_transition_after_days: int


def load_prices(path: Path) -> Prices:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        gb = raw["per_gb_month"]
        rules = raw["rules"]
        if raw["currency"] != "USD":
            raise PriceError("only USD is supported")
        p = Prices(
            standard=_money(gb["standard"]),
            standard_ia=_money(gb["standard_ia"]),
            it_frequent=_money(gb["it_frequent"]),
            it_infrequent=_money(gb["it_infrequent"]),
            it_archive_instant=_money(gb["it_archive_instant"]),
            it_monitoring_per_1000=_money(raw["it_monitoring_per_1000_objects"]),
            transition_per_1000=_money(raw["transition_per_1000_requests"]),
            it_min_monitored_bytes=int(rules["it_min_monitored_bytes"]),
            it_infrequent_after_days=int(rules["it_infrequent_after_days"]),
            it_archive_instant_after_days=int(rules["it_archive_instant_after_days"]),
            ia_min_billable_bytes=int(rules["ia_min_billable_bytes"]),
            ia_transition_after_days=int(rules["ia_transition_after_days"]),
        )
    except (KeyError, TypeError) as exc:
        raise PriceError(f"{path}: missing or malformed entry {exc}") from exc

    if p.ia_transition_after_days < AWS_MIN_DAYS_BEFORE_IA:
        raise PriceError(f"ia_transition_after_days must be >= {AWS_MIN_DAYS_BEFORE_IA}")
    if not 0 < p.it_infrequent_after_days < p.it_archive_instant_after_days:
        raise PriceError("Intelligent-Tiering tier days must increase")
    return p


def _money(value) -> Decimal:
    # Prices are strings in YAML so they parse exactly.
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise PriceError(f"not a number: {value!r}") from exc
    if d < 0:
        raise PriceError(f"price must not be negative: {value!r}")
    return d
