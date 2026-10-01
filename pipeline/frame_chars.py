"""List what is placed on the main timeline within a frame range."""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_swf(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"CWS":
        return raw[:8] + zlib.decompress(raw[8:])
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("swf")
    ap.add_argument("--from", dest="f0", type=int, default=6200)
    ap.add_argument("--to", dest="f1", type=int, default=6316)
    args = ap.parse_args()

    # character id -> kind
    kind: dict[int, str] = {}
    for p in (ROOT / "work" / "scripts" / "texts").glob("*.txt"):
        kind[int(p.stem)] = "TEXT"
    sym = ROOT / "work" / "scripts" / "symbolClass" / "symbols.csv"
    names: dict[int, str] = {}
    if sym.exists():
        for line in sym.read_text(encoding="utf-8").splitlines():
            if ";" in line:
                a, b = line.split(";", 1)
                try:
                    names[int(a)] = b.strip().strip('"')
                except ValueError:
                    pass

    data = load_swf(args.swf)
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4

    frame = 0
    out: list[tuple[int, int, int]] = []
    while pos < len(data):
        code_len = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if code == 0:
            break
        body = data[pos : pos + length]
        if code == 1:
            frame += 1
        elif code == 26 and len(body) >= 3:  # PlaceObject2
            flags = body[0]
            depth = struct.unpack_from("<H", body, 1)[0]
            if flags & 0x02:  # has character
                cid = struct.unpack_from("<H", body, 3)[0]
                out.append((frame, depth, cid))
        elif code == 70 and len(body) >= 4:  # PlaceObject3
            flags = body[0]
            depth = struct.unpack_from("<H", body, 1)[0]
            p = 3
            if flags & 0x10:
                p += 2
            if flags & 0x04:  # has class name string
                # skip className
                end = body.index(b"\x00", p)
                p = end + 1
            if flags & 0x02:
                cid = struct.unpack_from("<H", body, p)[0]
                out.append((frame, depth, cid))
        pos += length

    print(f"frame {args.f0}..{args.f1}")
    for f, depth, cid in out:
        if args.f0 <= f <= args.f1:
            k = kind.get(cid, "")
            nm = names.get(cid, "")
            print(f"  f{f:>5} depth={depth:>4} char={cid:<6} {k:<5} {nm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
