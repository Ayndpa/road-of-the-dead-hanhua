"""Parallel ranged HTTP downloader (no proxy).

Azure CDN single streams are throttled; many range requests in parallel
usually saturate the link.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LOCK = threading.Lock()
DONE = [0]


def head_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers["Content-Length"])


def fetch(url: str, start: int, end: int, path: str, retries: int = 6) -> int:
    n = 0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                with open(path, "r+b") as f:
                    f.seek(start)
                    while True:
                        buf = r.read(1 << 20)
                        if not buf:
                            break
                        f.write(buf)
                        n += len(buf)
                        with LOCK:
                            DONE[0] += len(buf)
            return n
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1} for [{start}-{end}]: {exc}", flush=True)
            time.sleep(1.5)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--chunk-mb", type=float, default=8)
    args = ap.parse_args()

    total = head_size(args.url)
    chunk = int(args.chunk_mb * 1024 * 1024)
    ranges = [(s, min(s + chunk - 1, total - 1)) for s in range(0, total, chunk)]
    with open(args.out, "wb") as f:
        f.truncate(total)
    print(f"total={total / 1e6:.1f}MB parts={len(ranges)} threads={args.threads}", flush=True)

    t0 = time.time()
    stop = threading.Event()

    def report() -> None:
        while not stop.wait(3):
            el = time.time() - t0
            print(
                f"  {DONE[0] / 1e6:7.1f}/{total / 1e6:.1f}MB "
                f"({100 * DONE[0] / total:5.1f}%) {DONE[0] / 1e6 / el:5.1f}MB/s",
                flush=True,
            )

    th = threading.Thread(target=report, daemon=True)
    th.start()
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = [ex.submit(fetch, args.url, s, e, args.out) for s, e in ranges]
        for fu in futs:
            fu.result()
    stop.set()
    el = time.time() - t0
    print(f"done {total / 1e6:.1f}MB in {el:.1f}s ({total / 1e6 / el:.1f}MB/s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
