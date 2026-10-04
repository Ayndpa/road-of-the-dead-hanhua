"""Pull the latest ParaTranz CSVs down from the platform.

``data/paratranz`` (game 1, project 20958) and ``data/paratranz2`` (game 2,
project 20962) mirror the platform files.  This script refreshes them from the
API, file by file, keeping the platform's own ``key,original,translation,context``
CSV layout (CRLF, no BOM) so the build reads exactly what is on ParaTranz:

    GET /projects/{id}/files/{fileId}/translation

Usage:
    $env:PARATRANZ_TOKEN = "<token>"
    uv run python pipeline/paratranz/pull_translations.py [--project 20962] [--file voice.csv] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://paratranz.cn/api"

# project id -> local folder
PROJECTS: dict[str, Path] = {
    "20958": ROOT / "data" / "paratranz",
    "20962": ROOT / "data" / "paratranz2",
}

FILES = ["as3.csv", "menu.csv", "stream.csv", "ui.csv", "voice.csv"]


def _token() -> str:
    return os.environ.get("PARATRANZ_TOKEN") or os.environ.get("PT_TOKEN") or ""


def api_get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": token})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def render_csv(rows: list[dict]) -> bytes:
    """``key,original,translation,context`` in the platform's own format."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    for row in rows:
        writer.writerow([
            row.get("key") or "",
            row.get("original") or "",
            row.get("translation") or "",
            row.get("context") or "",
        ])
    return buf.getvalue().encode("utf-8")


def pull_file(pid: str, fid: int, name: str, path: Path, token: str, dry_run: bool) -> None:
    rows = api_get(f"{API}/projects/{pid}/files/{fid}/translation", token)
    data = render_csv(rows)
    translated = sum(1 for r in rows if (r.get("translation") or "").strip())
    if dry_run:
        print(f"  {name}: {len(rows)} keys ({translated} translated), "
              f"{len(data)} bytes [dry-run]")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  {name}: {len(rows)} keys ({translated} translated) -> {path.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", action="append", choices=sorted(PROJECTS),
                    help="only this project id (repeatable); default: all")
    ap.add_argument("--file", action="append",
                    help="only this csv file name, e.g. voice.csv (repeatable)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = _token()
    if not token:
        raise SystemExit("set PARATRANZ_TOKEN (or PT_TOKEN) to your ParaTranz API token")

    for pid in args.project or sorted(PROJECTS):
        folder = PROJECTS[pid]
        remote = {f["name"]: f["id"] for f in api_get(f"{API}/projects/{pid}/files", token)}
        print(f"\n== project {pid} ({folder.relative_to(ROOT)})")
        for name in args.file or FILES:
            if name not in remote:
                print(f"  {name}: no matching platform file, skipped")
            else:
                pull_file(pid, remote[name], name, folder / name, token, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
