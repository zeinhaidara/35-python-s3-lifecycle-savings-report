from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from s3savings.estimate import estimate, one_time_cost
from s3savings.prices import load_prices
from s3savings.sources import ObjectRecord, read_inventory_csv

ROOT = Path(__file__).parent.parent
PRICES = load_prices(ROOT / "config" / "prices.yaml")
AS_OF = date(2026, 11, 20)
GIB = 2**30
D = Decimal


def by_bucket():
    rows = read_inventory_csv(ROOT / "tests" / "fixtures" / "inventory.csv")
    return {e.bucket: e for e in estimate(rows, PRICES, AS_OF)}


def obj(size, modified, cls="STANDARD", bucket="b-example-com"):
    return ObjectRecord(
        bucket, "k", size, datetime.fromisoformat(modified + "T00:00:00+00:00"), cls
    )


def test_age_and_size_bands():
    logs = by_bucket()["logs-example-com"]
    assert {b: (v.objects, v.bytes) for b, v in logs.bands.items()} == {
        "small": (1, 1000),
        "recent": (1, GIB),
        "cooling": (1, GIB),
        "cold": (1, GIB),
    }
    assert logs.skipped_other_class == 1  # the GLACIER object


def test_intelligent_tiering_savings_by_tier():
    logs = by_bucket()["logs-example-com"]
    fee = D("0.0025") / 1000
    # recent stays at 0.023, cooling -> 0.0125, cold -> 0.004; each pays a fee
    expected = (
        (D("0.023") - D("0.023") - fee)
        + (D("0.023") - D("0.0125") - fee)
        + (D("0.023") - D("0.004") - fee)
    )
    assert logs.it_savings == expected == D("0.0294925")
    assert logs.it_transitions == 3  # the small object is not moved


def test_standard_ia_savings_skip_young_and_small():
    logs = by_bucket()["logs-example-com"]
    # only the 45-day and 200-day objects qualify
    assert logs.ia_savings == 2 * (D("0.023") - D("0.0125")) == D("0.021")
    assert logs.ia_transitions == 2


def test_small_object_alone_saves_nothing():
    [e] = estimate([obj(1000, "2020-01-01")], PRICES, AS_OF)
    assert e.it_savings == 0
    assert e.ia_savings == 0
    assert e.it_transitions == e.ia_transitions == 0


def test_ia_boundary_is_inclusive_at_30_days():
    [at_29] = estimate([obj(GIB, "2026-10-22")], PRICES, AS_OF)
    [at_30] = estimate([obj(GIB, "2026-10-21")], PRICES, AS_OF)
    assert at_29.ia_transitions == 0
    assert at_30.ia_transitions == 1


def test_object_exactly_128_kib_is_eligible():
    [e] = estimate([obj(131072, "2026-01-01")], PRICES, AS_OF)
    assert e.ia_transitions == 1 and e.it_transitions == 1
    [e] = estimate([obj(131071, "2026-01-01")], PRICES, AS_OF)
    assert e.ia_transitions == 0 and e.it_transitions == 0


def test_buckets_sorted_by_biggest_saving():
    rows = read_inventory_csv(ROOT / "tests" / "fixtures" / "inventory.csv")
    names = [e.bucket for e in estimate(rows, PRICES, AS_OF)]
    assert names == ["media-example-com", "logs-example-com"]


def test_one_time_transition_cost():
    assert one_time_cost(2000, PRICES) == D("0.02")


def test_future_modified_date_fails():
    with pytest.raises(ValueError, match="after --as-of"):
        estimate([obj(GIB, "2026-12-01")], PRICES, AS_OF)


def test_empty_input_fails():
    with pytest.raises(ValueError, match="no objects"):
        estimate([], PRICES, AS_OF)


def test_datetimes_must_be_aware():
    # sanity check on the helper used above
    assert obj(1, "2026-01-01").last_modified.tzinfo == UTC
