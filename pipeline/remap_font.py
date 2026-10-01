"""Repoint text tags from one embedded font to another.

The game's title logo shares font id 20 with the localised menu/HUD text.  We
keep font 20 (the original decorative face) so the logo is untouched, and move
every *other* text using font 20 to an unused font slot that later gets a CJK
face.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

KEEP: set[int] = set()  # char ids that must keep the old font


def load_swf_raw(path: str) -> tuple[bytes, bool]:
    raw = Path(path).read_bytes()
    if raw[:3] == b"CWS":
        return raw[:8] + zlib.decompress(raw[8:]), True
    return raw, False


def write_swf_fws(data: bytes, out: str) -> None:
    body = bytearray(data)
    body[0:3] = b"FWS"
    struct.pack_into("<I", body, 4, len(body))
    # recompute header (rect etc. unchanged)
    Path(out).write_bytes(bytes(body))


class Bits:
    def __init__(self, body: bytes, pos: int):
        self.b = body
        self.byte = pos
        self.bit = 0

    def align(self) -> None:
        if self.bit:
            self.bit = 0
            self.byte += 1

    def u(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.byte] >> (7 - self.bit)) & 1)
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
        for _ in range(4):
            self.si(n)
        self.align()

    def matrix(self) -> None:
        if self.u(1):
            n = self.u(5)
            self.si(n)
            self.si(n)
        if self.u(1):
            n = self.u(5)
            self.si(n)
            self.si(n)
        n = self.u(5)
        self.si(n)
        self.si(n)
        self.align()


def text_font_offsets(body: bytes, code: int) -> list[int]:
    """Byte offsets of every UI16 fontId inside a DefineText/DefineText2 body."""
    b = Bits(body, 2)
    b.rect()
    b.matrix()
    glyph_bits = body[b.byte]
    b.byte += 1
    advance_bits = body[b.byte]
    b.byte += 1
    offsets: list[int] = []
    while b.byte < len(body):
        flags = body[b.byte]
        b.byte += 1
        if flags == 0:
            break
        if flags & 0x80:
            if flags & 0x08:
                offsets.append(b.byte)
                b.byte += 2
            if flags & 0x04:
                b.byte += 4 if code == 33 else 3
            if flags & 0x02:
                b.byte += 2
            if flags & 0x01:
                b.byte += 2
            if flags & 0x10:
                b.byte += 2
        else:
            total = flags * (glyph_bits + advance_bits)
            b.byte += (total + 7) // 8
    return offsets


def edit_text_font_offset(body: bytes) -> int | None:
    b = Bits(body, 2)
    b.rect()
    flags = struct.unpack_from("<H", body, b.byte)[0]
    if flags & 0x0080:
        return b.byte + 2
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--old", type=int, required=True)
    ap.add_argument("--new", type=int, required=True)
    ap.add_argument("--keep", default="", help="comma separated char ids to leave alone")
    ap.add_argument("--only", default="", help="if set, only remap these char ids")
    args = ap.parse_args()

    keep = {int(x) for x in args.keep.split(",") if x.strip()}
    only = {int(x) for x in args.only.split(",") if x.strip()}
    data, _ = load_swf_raw(args.infile)
    buf = bytearray(data)
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    changed_tags = 0
    changed_refs = 0
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = bytes(buf[p : p + length])
        if code in (11, 33) and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            if only and cid not in only:
                pass
            elif cid not in keep:
                offs = text_font_offsets(body, code)
                hit = False
                for off in offs:
                    if struct.unpack_from("<H", body, off)[0] == args.old:
                        struct.pack_into("<H", buf, p + off, args.new)
                        changed_refs += 1
                        hit = True
                if hit:
                    changed_tags += 1
        elif code == 37 and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            if (not only or cid in only) and cid not in keep:
                off = edit_text_font_offset(body)
                if off is not None and struct.unpack_from("<H", body, off)[0] == args.old:
                    struct.pack_into("<H", buf, p + off, args.new)
                    changed_refs += 1
                    changed_tags += 1
        pos = p + length

    write_swf_fws(bytes(buf), args.outfile)
    print(f"repointed {changed_refs} refs in {changed_tags} text tags -> {args.outfile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
