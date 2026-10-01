"""Recursively classify the leaf characters under a sprite."""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAGS = {
    2: "DefineShape", 22: "DefineShape2", 32: "DefineShape3", 83: "DefineShape4",
    6: "DefineBits", 21: "DefineBitsJPEG2", 35: "DefineBitsJPEG3", 90: "DefineBitsJPEG4",
    20: "DefineBitsLossless", 36: "DefineBitsLossless2", 11: "DefineText",
    33: "DefineText2", 37: "DefineEditText", 39: "DefineSprite", 7: "DefineButton",
    34: "DefineButton2", 10: "DefineFont", 48: "DefineFont2", 75: "DefineFont3",
}
PLACE = {4: "PlaceObject", 26: "PlaceObject2", 70: "PlaceObject3"}


def load_swf(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"CWS":
        return raw[:8] + zlib.decompress(raw[8:])
    return raw


def iter_tags(data: bytes, start: int, end: int):
    pos = start
    while pos < end:
        code_len = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        body = data[pos : pos + length]
        yield code, body
        pos += length
        if code == 0:
            break


def place_char_id(code: int, body: bytes) -> int | None:
    if code == 4:
        return struct.unpack_from("<H", body, 0)[0]
    if code == 26:
        flags = body[0]
        if flags & 0x02:
            return struct.unpack_from("<H", body, 3)[0]
        return None
    if code == 70:
        flags1 = body[0]
        flags2 = body[1]
        p = 4
        if flags2 & 0x02:  # has class name
            p = body.index(b"\x00", p) + 1
        if flags1 & 0x02:
            return struct.unpack_from("<H", body, p)[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("swf")
    ap.add_argument("roots", nargs="+", type=int)
    args = ap.parse_args()

    data = load_swf(args.swf)
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4  # frame rate + frame count
    end_len = len(data)

    defs: dict[int, tuple[str, bytes]] = {}
    for code, body in iter_tags(data, pos, end_len):
        if code == 0:
            break
        if code in TAGS and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            defs[cid] = (TAGS[code], body)

    def walk(cid: int, depth: int, seen: set[int]) -> None:
        kind, body = defs.get(cid, ("?", b""))
        pad = "  " * depth
        if kind != "DefineSprite":
            print(f"{pad}- {cid} {kind}")
            return
        if cid in seen:
            print(f"{pad}- {cid} DefineSprite (recursive)")
            return
        seen.add(cid)
        frame = 0
        sub = list(iter_tags(body, 4, len(body)))
        print(f"{pad}+ sprite {cid}")
        for code, sbody in sub:
            if code in PLACE:
                child = place_char_id(code, sbody)
                if child is not None:
                    walk(child, depth + 1, seen)

    for r in args.roots:
        walk(r, 0, set())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
