"""Report which fonts each DefineText / DefineEditText tag uses."""
from __future__ import annotations

import argparse
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path


class Bits:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.byte = pos
        self.bit = 0

    def align(self) -> None:
        if self.bit:
            self.bit = 0
            self.byte += 1

    def u(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.data[self.byte] >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit = 0
                self.byte += 1
        return v

    def si(self, n: int) -> int:
        if n == 0:
            return 0
        v = self.u(n)
        if v & (1 << (n - 1)):
            v -= 1 << n
        return v

    def rect(self) -> None:
        n = self.u(5)
        self.si(n)
        self.si(n)
        self.si(n)
        self.si(n)
        self.align()

    def matrix(self) -> None:
        if self.u(1):  # hasScale
            n = self.u(5)
            self.si(n)
            self.si(n)
        if self.u(1):  # hasRotate
            n = self.u(5)
            self.si(n)
            self.si(n)
        n = self.u(5)  # translate
        self.si(n)
        self.si(n)
        self.align()


def load_swf(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"CWS":
        return raw[:8] + zlib.decompress(raw[8:])
    return raw


def parse_text(cid: int, body: bytes) -> tuple[list[int], list[int]]:
    """Return (fontIds, textHeights) referenced by a DefineText/DefineText2 tag."""
    b = Bits(body, 2)  # skip characterId
    b.rect()
    b.matrix()
    glyph_bits = b.data[b.byte]
    b.byte += 1
    advance_bits = b.data[b.byte]
    b.byte += 1
    fonts: list[int] = []
    heights: list[int] = []
    while b.byte < len(body):
        flags = b.data[b.byte]
        b.byte += 1
        if flags == 0:
            break
        if flags & 0x80:
            if flags & 0x08:
                font_id = struct.unpack_from("<H", body, b.byte)[0]
                b.byte += 2
                if font_id not in fonts:
                    fonts.append(font_id)
            if flags & 0x04:
                b.byte += 3 if not (cid == 33) else 0
                b.byte += 4 if cid == 33 else 0
            if flags & 0x02:
                b.byte += 2
            if flags & 0x01:
                b.byte += 2
            if flags & 0x10:
                h = struct.unpack_from("<H", body, b.byte)[0]
                b.byte += 2
                if h not in heights:
                    heights.append(h)
        else:
            count = flags
            total_bits = count * (glyph_bits + advance_bits)
            b.byte += (total_bits + 7) // 8
    return fonts, heights


def parse_edit_text(body: bytes) -> list[int]:
    b = Bits(body, 2)
    b.rect()
    flags = struct.unpack_from("<H", body, b.byte)[0]
    pos = b.byte + 2
    fonts: list[int] = []
    if flags & 0x8000:
        raise ValueError("useOutlines")
    if flags & 0x0080:
        fonts.append(struct.unpack_from("<H", body, pos)[0])
    return fonts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("swf")
    args = ap.parse_args()

    data = load_swf(args.swf)
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4

    per_text: dict[int, list[int]] = {}
    font_counter: Counter[int] = Counter()
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
        if code in (11, 33):
            try:
                fonts, heights = parse_text(code, body)
            except Exception:  # noqa: BLE001
                fonts, heights = [], []
            cid = struct.unpack_from("<H", body, 0)[0]
            per_text[cid] = fonts
            for f in fonts:
                font_counter[f] += 1
        elif code == 37:
            try:
                fonts = parse_edit_text(body)
            except Exception:  # noqa: BLE001
                fonts = []
            cid = struct.unpack_from("<H", body, 0)[0]
            per_text[cid] = fonts
            for f in fonts:
                font_counter[f] += 1
        pos += length

    print(f"text tags: {len(per_text)}")
    print("--- fonts used by text tags ---")
    for fid, n in font_counter.most_common():
        print(f"  font {fid:>5}: {n} texts")
    by_font: dict[int, list[int]] = defaultdict(list)
    for cid, fonts in per_text.items():
        for f in fonts:
            by_font[f].append(cid)
    out = Path(args.swf).with_suffix(".textfonts.txt")
    with out.open("w", encoding="utf-8") as fh:
        for fid, cids in sorted(by_font.items()):
            fh.write(f"font {fid}: {sorted(cids)}\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
