from datetime import UTC, datetime
from pathlib import Path

import pytest

from s3savings.prices import PriceError, load_prices
from s3savings.sources import InputError, list_bucket, read_inventory_csv
from tests.fakes import FakeS3

ROOT = Path(__file__).parent.parent
PRICES_TEXT = (ROOT / "config" / "prices.yaml").read_text(encoding="utf-8")


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --- live listing ---------------------------------------------------------------


def test_list_bucket_follows_continuation_token():
    when = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {"Key": f"k{i}", "Size": i, "LastModified": when, "StorageClass": "STANDARD"}
        for i in range(5)
    ]
    s3 = FakeS3({"b-example-com": rows}, page_size=2)
    records = list(list_bucket(s3, "b-example-com"))
    assert [r.key for r in records] == ["k0", "k1", "k2", "k3", "k4"]
    assert [c["ContinuationToken"] for c in s3.calls] == [None, "2", "4"]


def test_missing_storage_class_is_an_error():
    rows = [{"Key": "k", "Size": 1, "LastModified": datetime(2026, 1, 1, tzinfo=UTC)}]
    with pytest.raises(KeyError):
        list(list_bucket(FakeS3({"b": rows}), "b"))


# --- CSV ------------------------------------------------------------------------


def test_csv_missing_column(tmp_path):
    p = write(tmp_path, "i.csv", "bucket,key,size\nb,k,1\n")
    with pytest.raises(InputError, match="missing columns"):
        list(read_inventory_csv(p))


@pytest.mark.parametrize(
    "row",
    [
        "b,k,abc,2026-01-01T00:00:00Z,STANDARD",
        "b,k,-5,2026-01-01T00:00:00Z,STANDARD",
        "b,k,5,not-a-date,STANDARD",
        "b,k,5,2026-01-01T00:00:00,STANDARD",  # no offset
    ],
)
def test_csv_bad_row_names_the_line(tmp_path, row):
    p = write(tmp_path, "i.csv", "bucket,key,size,last_modified_date,storage_class\n" + row + "\n")
    with pytest.raises(InputError, match=r"i\.csv:2"):
        list(read_inventory_csv(p))


# --- prices ---------------------------------------------------------------------


def test_default_prices_load():
    p = load_prices(ROOT / "config" / "prices.yaml")
    assert str(p.standard) == "0.023"
    assert p.it_min_monitored_bytes == 131072


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ('standard: "0.023"', 'standard: "-1"', "negative"),
        ('standard: "0.023"', 'standard: "cheap"', "not a number"),
        ("ia_transition_after_days: 30", "ia_transition_after_days: 7", ">= 30"),
        ("it_archive_instant_after_days: 90", "it_archive_instant_after_days: 10", "increase"),
        ("currency: USD", "currency: EUR", "USD"),
        ('  standard_ia: "0.0125"\n', "", "standard_ia"),
    ],
)
def test_bad_prices_rejected(tmp_path, old, new, match):
    assert old in PRICES_TEXT
    p = write(tmp_path, "p.yaml", PRICES_TEXT.replace(old, new))
    with pytest.raises(PriceError, match=match):
        load_prices(p)
