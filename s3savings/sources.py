"""Object listings from an inventory-style CSV or from ListObjectsV2."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

COLUMNS = ["bucket", "key", "size", "last_modified_date", "storage_class"]


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class ObjectRecord:
    bucket: str
    key: str
    size: int
    last_modified: datetime
    storage_class: str


def read_inventory_csv(path: Path) -> Iterator[ObjectRecord]:
    """CSV with a header row naming COLUMNS. Bad rows stop the run."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise InputError(f"{path}: missing columns {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            try:
                size = int(row["size"])
                modified = datetime.fromisoformat(row["last_modified_date"].replace("Z", "+00:00"))
            except (TypeError, ValueError) as exc:
                raise InputError(f"{path}:{line}: {exc}") from exc
            if size < 0 or modified.tzinfo is None:
                raise InputError(f"{path}:{line}: negative size or timestamp without offset")
            yield ObjectRecord(row["bucket"], row["key"], size, modified, row["storage_class"])


def list_bucket(s3, bucket: str) -> Iterator[ObjectRecord]:
    """Every object in the bucket, following ContinuationToken."""
    kwargs = {"Bucket": bucket}
    while True:
        page = s3.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            yield ObjectRecord(
                bucket=bucket,
                key=obj["Key"],
                size=int(obj["Size"]),
                last_modified=obj["LastModified"],
                # No default: a missing class would silently skew the estimate.
                storage_class=obj["StorageClass"],
            )
        if not page.get("IsTruncated"):
            return
        kwargs["ContinuationToken"] = page["NextContinuationToken"]
