from datetime import UTC, datetime
from pathlib import Path

from s3savings.cli import main
from tests.fakes import FakeS3

FIXTURE = str(Path(__file__).parent / "fixtures" / "inventory.csv")


def test_inventory_report(capsys):
    assert main(["--inventory", FIXTURE, "--as-of", "2026-11-20"]) == 0
    out = capsys.readouterr().out
    assert "**Prices are illustrative placeholders**" in out
    assert "- STANDARD storage today: $23.07 per month across 2 bucket(s)." in out
    assert "- Intelligent-Tiering: about **$19.03 per month** saved." in out
    assert "Standard-IA after 30 days: about **$10.52 per month** saved." in out
    assert "| media-example-com | $23.00 | $19.00 | $0.00 | $10.50 | $0.00 |" in out
    assert (
        "| logs-example-com | 1 / 0.00 GiB | 1 / 1.00 GiB | 1 / 1.00 GiB | 1 / 1.00 GiB | 1 |"
        in out
    )
    assert "AWS behaviour, re-verify" in out


def test_live_bucket_mode(tmp_path):
    when = datetime(2026, 1, 1, tzinfo=UTC)
    s3 = FakeS3(
        {
            "b-example-com": [
                {"Key": "x", "Size": 2**30, "LastModified": when, "StorageClass": "STANDARD"}
            ]
        }
    )
    out = tmp_path / "r.md"
    code = main(["--bucket", "b-example-com", "--as-of", "2026-11-20", "--output", str(out)], s3=s3)
    assert code == 0
    assert "| b-example-com |" in out.read_text(encoding="utf-8")


def test_bad_input_exits_non_zero(tmp_path, capsys):
    bad = tmp_path / "i.csv"
    bad.write_text("nope\n", encoding="utf-8")
    out = tmp_path / "r.md"
    assert main(["--inventory", str(bad), "--output", str(out)]) == 1
    assert not out.exists()
    assert "missing columns" in capsys.readouterr().err


def test_empty_bucket_exits_non_zero(capsys):
    assert main(["--bucket", "empty-example-com"], s3=FakeS3({"empty-example-com": []})) == 1
    assert "no objects" in capsys.readouterr().err
