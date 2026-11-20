"""Estimate monthly savings per bucket for two options:

1. move STANDARD objects to Intelligent-Tiering (IT);
2. a lifecycle rule that moves them to Standard-IA after N days.

Object age (from LastModified) stands in for "time since last access",
which a listing can't tell us. That makes these numbers an upper bound.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from s3savings.prices import Prices
from s3savings.sources import ObjectRecord

GIB = Decimal(2**30)
ZERO = Decimal("0")
THOUSAND = Decimal(1000)

BANDS = ["small", "recent", "cooling", "cold"]


@dataclass
class Band:
    objects: int = 0
    bytes: int = 0


@dataclass
class BucketEstimate:
    bucket: str
    standard_monthly: Decimal = ZERO
    it_monthly: Decimal = ZERO
    ia_monthly: Decimal = ZERO
    it_transitions: int = 0
    ia_transitions: int = 0
    skipped_other_class: int = 0
    bands: dict[str, Band] = field(default_factory=lambda: {b: Band() for b in BANDS})

    @property
    def it_savings(self) -> Decimal:
        return self.standard_monthly - self.it_monthly

    @property
    def ia_savings(self) -> Decimal:
        return self.standard_monthly - self.ia_monthly


def one_time_cost(transitions: int, prices: Prices) -> Decimal:
    return Decimal(transitions) / THOUSAND * prices.transition_per_1000


def _band(size: int, age: int, p: Prices) -> str:
    if size < p.it_min_monitored_bytes:
        return "small"
    if age < p.it_infrequent_after_days:
        return "recent"
    if age < p.it_archive_instant_after_days:
        return "cooling"
    return "cold"


def estimate(records: Iterable[ObjectRecord], prices: Prices, as_of: date) -> list[BucketEstimate]:
    p = prices
    out: dict[str, BucketEstimate] = {}

    for r in records:
        est = out.setdefault(r.bucket, BucketEstimate(r.bucket))
        if r.storage_class != "STANDARD":
            # Already in another class; nothing to recommend here.
            est.skipped_other_class += 1
            continue

        age = (as_of - r.last_modified.date()).days
        if age < 0:
            raise ValueError(f"s3://{r.bucket}/{r.key} is modified after --as-of {as_of}")

        gb = Decimal(r.size) / GIB
        standard = gb * p.standard
        est.standard_monthly += standard

        band = _band(r.size, age, p)
        est.bands[band].objects += 1
        est.bands[band].bytes += r.size

        # Intelligent-Tiering: small objects stay at the frequent price with no fee.
        if band == "small":
            est.it_monthly += gb * p.it_frequent
        else:
            tier = {
                "recent": p.it_frequent,
                "cooling": p.it_infrequent,
                "cold": p.it_archive_instant,
            }[band]
            est.it_monthly += gb * tier + p.it_monitoring_per_1000 / THOUSAND
            est.it_transitions += 1

        # Standard-IA bills at least 128 KiB, so small objects would cost more.
        eligible = age >= p.ia_transition_after_days and r.size >= p.ia_min_billable_bytes
        if eligible:
            est.ia_monthly += gb * p.standard_ia
            est.ia_transitions += 1
        else:
            est.ia_monthly += standard

    if not out:
        raise ValueError("no objects in input")
    return sorted(out.values(), key=lambda e: (-max(e.it_savings, e.ia_savings), e.bucket))
