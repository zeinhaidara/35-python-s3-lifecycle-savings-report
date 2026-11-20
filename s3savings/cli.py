"""python -m s3savings --inventory objects.csv | --bucket NAME [--bucket NAME ...]"""

from __future__ import annotations

import argparse
import itertools
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from s3savings.estimate import estimate
from s3savings.prices import load_prices
from s3savings.report import to_markdown
from s3savings.sources import list_bucket, read_inventory_csv

DEFAULT_PRICES = Path(__file__).resolve().parent.parent / "config" / "prices.yaml"


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Estimate S3 storage class savings (read-only).")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--inventory", type=Path, help="inventory-style CSV with a header row")
    src.add_argument("--bucket", action="append", help="list this bucket live (repeatable)")
    p.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    p.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(UTC).date())
    p.add_argument("--output", type=Path)
    return p.parse_args(argv)


def main(argv=None, s3=None) -> int:
    args = parse_args(argv)
    try:
        prices = load_prices(args.prices)
        if args.inventory:
            records = read_inventory_csv(args.inventory)
        else:
            if s3 is None:
                import boto3

                s3 = boto3.client("s3")
            records = itertools.chain.from_iterable(list_bucket(s3, b) for b in args.bucket)
        text = to_markdown(estimate(records, prices, args.as_of), prices, args.as_of)
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0
