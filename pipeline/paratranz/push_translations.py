"""Push the local ParaTranz CSVs back to the platform, overwriting the old data.

The repository's ``data/paratranz`` (game 1, project 20958) and ``data/paratranz2``
(game 2, project 20962) folders hold the authoritative keys, originals and
translations.  This script brings the matching ParaTranz project in line with the
local state, file by file:

  1. ``POST /projects/{id}/files/{fileId}`` -- re-upload the local CSV as the
     source, which adds keys that only exist locally and refreshes the originals
     (non-incremental, so the file's key set is exactly the local one);
  2. ``PUT  /projects/{id}/strings`` with ``{op: "edit", items: [...]}`` -- set
     the translation of every string whose platform value differs from the local
     CSV, matched by the string's key.

The platform's own "Import Translation" endpoint rejects this CSV layout
(``text.translation`` has no default on insert), so translations are written
through the strings API instead.

Usage:
    $env:PARATRANZ_TOKEN = "<token>"
    uv run python pipeline/paratranz/push_translations.py [--project 20962] [--file voice.csv] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://paratranz.cn/api"

# project id -> local folder
PROJECTS: dict[str, Path] = {
    "20958": ROOT / "data" / "paratranz",
    "20962": ROOT / "data" / "paratranz2",
}

FILES = ["as3.csv", "menu.csv", "stream.csv", "ui.csv", "voice.csv"]
BATCH = 200


def _token() -> str:
    return os.environ.get("PARATRANZ_TOKEN") or os.environ.get("PT_TOKEN") or ""


def api_get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": token})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----ParaTranzBoundary" + uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv; charset=utf-8\r\n\r\n"
    ).encode("utf-8")
    return head + content + f"\r\n--{boundary}--\r\n".encode("utf-8"), \
        f"multipart/form-data; boundary={boundary}"


def api_post_source(pid: str, fid: int, filename: str, content: bytes, token: str):
    body, content_type = _multipart(filename, content)
    req = urllib.request.Request(
        f"{API}/projects/{pid}/files/{fid}", data=body, method="POST",
        headers={"Authorization": token, "Content-Type": content_type},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_edit_strings(pid: str, items: list[dict], token: str):
    data = json.dumps({"op": "edit", "items": items}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/projects/{pid}/strings", data=data, method="PUT",
        headers={"Authorization": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        text = resp.read().decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def read_local(path: Path) -> dict[str, str]:
    """``{key: translation}`` from a ParaTranz CSV (header rows are optional)."""
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip():
                continue
            if row[0].strip().lower() in {"key", "keyvalue", "键值", "键"}:
                continue
            out[row[0]] = row[2] if len(row) > 2 else ""
    return out


def push_file(pid: str, fid: int, name: str, path: Path, token: str, dry_run: bool) -> None:
    content = path.read_bytes()
    local = read_local(path)
    if dry_run:
        print(f"  {name}: {len(local)} local keys, {path.stat().st_size} bytes "
              f"-> file {fid} [dry-run]")
        return

    src = api_post_source(pid, fid, name, content, token)
    rev = src.get("revision", {}) if isinstance(src, dict) else {}
    print(f"  {name}: source synced (insert={rev.get('insert')} update={rev.get('update')} "
          f"remove={rev.get('remove')})")

    rows = api_get(f"{API}/projects/{pid}/files/{fid}/translation", token)
    changed = [
        {"id": r["id"], "translation": local[r["key"]]}
        for r in rows if r["key"] in local and (r.get("translation") or "") != local[r["key"]]
    ]
    total = 0
    for i in range(0, len(changed), BATCH):
        total += len(api_edit_strings(pid, changed[i:i + BATCH], token))
    print(f"  {name}: translations updated {total} / {len(rows)}")


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
        print(f"\n== project {pid} ({folder})")
        for name in args.file or FILES:
            local = folder / name
            if not local.exists():
                print(f"  {name}: local file missing, skipped")
            elif name not in remote:
                print(f"  {name}: no matching platform file, skipped")
            else:
                push_file(pid, remote[name], name, local, token, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
