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
        if flags & 0x08:
            offsets.append(b.byte)      # FontID
            b.byte += 2
        if flags & 0x04:
            b.byte += 4 if code == 33 else 3   # TextColor (RGBA in DefineText2)
        if flags & 0x01:
            b.byte += 2                 # XOffset
        if flags & 0x02:
            b.byte += 2                 # YOffset
        if flags & 0x08:
            b.byte += 2                 # TextHeight
        count = body[b.byte]            # GlyphCount
        b.byte += 1
        if count == 0:
            break
        b.byte += (count * (glyph_bits + advance_bits) + 7) // 8
    return offsets


def edit_text_font_offset(body: bytes) -> int | None:
    b = Bits(body, 2)
    b.rect()
    flags = struct.unpack_from("<H", body, b.byte)[0]
    if flags & 0x0080:
        return b.byte + 2
    return None


def clear_font_style(infile: str, outfile: str,
                     ids: set[int] | dict[int, tuple[bool, bool]],
                     bold: bool = True, italic: bool = True) -> dict[int, tuple[int, int]]:
    """Clear chosen bold/italic FONTFLAGS bits on the given DefineFont2/3 tags.

    FFDec's ``-replace <fontId> <ttf>`` keeps the repurposed tag's existing
    style flags and *bakes* that style into the imported glyph outlines: a slot
    that was "Arial Bold Italic" makes the CJK glyphs slanted, and a "Bold" slot
    makes them synthetic-bold.  Clearing the bits on the input SWF before the
    font import makes FFDec embed the face exactly as drawn in the TTF.

    ``ids`` may be a plain set (clear both bits on each) or a ``{id: (bold,
    italic)}`` mapping that clears per slot -- the italic slots keep their
    italic bit so the CJK face still renders oblique.
    """
    if isinstance(ids, dict):
        spec = dict(ids)
    else:
        spec = {i: (bold, italic) for i in ids}
    data, _ = load_swf_raw(infile)
    buf = bytearray(data)
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    touched: dict[int, tuple[int, int]] = {}
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        if code in (48, 62, 75) and length >= 3:
            fid = struct.unpack_from("<H", buf, p)[0]
            if fid in spec:
                cb, ci = spec[fid]
                mask = (0x01 if cb else 0) | (0x02 if ci else 0)
                if mask and (buf[p + 2] & mask):
                    old = buf[p + 2]
                    buf[p + 2] = old & ~mask
                    touched[fid] = (old, buf[p + 2])
        pos = p + length
    write_swf_fws(bytes(buf), outfile)
    return touched


def encode_tag(code: int, body: bytes) -> bytes:
    if len(body) < 0x3F:
        return struct.pack("<H", (code << 6) | len(body)) + body
    return (struct.pack("<H", (code << 6) | 0x3F)
            + struct.pack("<I", len(body)) + body)


def _font_tags(buf: bytes) -> list[tuple[int, int, int, int]]:
    """(tag_start, body_start, body_end, font_id) for every DefineFont2/3."""
    out: list[tuple[int, int, int, int]] = []
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    while pos < len(buf):
        cl = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = cl >> 6
        length = cl & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        if code in (48, 75) and length >= 2:
            out.append((pos, p, p + length, struct.unpack_from("<H", buf, p)[0]))
        pos = p + length
        if code == 0:
            break
    return out


def copy_font_layout(infile: str, outfile: str, target: int, donor: int) -> bool:
    """Give ``target`` the donor's DefineFont body (id rewritten to ``target``).

    FFDec's ``-replace <id> <ttf>`` preserves the repurposed tag's existing
    ``HasLayout`` bit and, when set, regenerates the advance table from the new
    face.  A slot whose original DefineFont had no layout (font 10082) therefore
    imports a CJK face with no advances, and any dynamic ``DefineEditText`` on it
    collapses to zero width and disappears.  Cloning a layout-bearing face's tag
    body (eg. font 95) makes FFDec emit layout on import; the glyph indices are
    irrelevant because every repointed tag is truncated/re-imported afterwards.
    """
    data, _ = load_swf_raw(infile)
    buf = bytearray(data)
    donor_body: bytes | None = None
    target_span: tuple[int, int, int] | None = None
    for start, bstart, bend, fid in _font_tags(buf):
        if fid == donor:
            donor_body = bytes(buf[bstart:bend])
        if fid == target:
            target_span = (start, bstart, bend)
    if donor_body is None or target_span is None:
        raise SystemExit(f"copy_font_layout: donor {donor} or target {target} missing")
    start, bstart, bend = target_span
    new_body = bytearray(donor_body)
    struct.pack_into("<H", new_body, 0, target)
    code = struct.unpack_from("<H", buf, start)[0] >> 6
    out = buf[:start] + encode_tag(code, bytes(new_body)) + buf[bend:]
    write_swf_fws(bytes(out), outfile)
    return True


def set_font_face(infile: str, outfile: str, names: dict[int, str]) -> None:
    """Rename the ``FontName`` stored inside DefineFont2/3 bodies.

    This is the name Flash's embedded-font registry uses; the separate
    ``DefineFontName`` tag is only metadata.  A preserved Latin slot whose body
    name collides with a repurposed CJK slot (both "Arial") makes runtime
    ``defaultTextFormat.font`` lookups resolve to the Latin face and render the
    Chinese text blank, so the preserved face must be renamed.
    """
    data, _ = load_swf_raw(infile)
    buf = data
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    out = bytearray(buf[:pos])
    while pos < len(buf):
        cl = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = cl >> 6
        length = cl & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = buf[p:p + length]
        if code in (48, 75) and len(body) >= 5:
            fid = struct.unpack_from("<H", body, 0)[0]
            if fid in names:
                enc = names[fid].encode("utf-8")
                body = body[:4] + bytes([len(enc)]) + enc + body[5 + body[4]:]
        out += encode_tag(code, body)
        pos = p + length
        if code == 0:
            break
    write_swf_fws(bytes(out), outfile)


def set_font_name(infile: str, outfile: str, names: dict[int, str]) -> None:
    """Rename embedded fonts (DefineFontName) by font id.

    A runtime ``TextField`` re-formats via ``defaultTextFormat``, which carries
    the font *name*, and with ``embedFonts`` Flash resolves that name against the
    embedded fonts.  If a repurposed CJK slot shares a name with a preserved
    Latin slot (eg. the sans slot 10082 and the untouched Arial 95 are both
    "Arial"), a Chinese runtime field resolves back to the Latin face and renders
    blank.  Renaming the preserved face and giving the CJK slot the expected name
    makes the lookup land on the CJK glyphs.
    """
    data, _ = load_swf_raw(infile)
    buf = data
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    out = bytearray(buf[:pos])
    while pos < len(buf):
        cl = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = cl >> 6
        length = cl & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = buf[p:p + length]
        if code == 88 and len(body) >= 3:
            fid = struct.unpack_from("<H", body, 0)[0]
            if fid in names:
                body = struct.pack("<H", fid) + names[fid].encode("utf-8") + b"\x00"
        out += encode_tag(code, body)
        pos = p + length
        if code == 0:
            break
    write_swf_fws(bytes(out), outfile)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--old", required=True, help="comma separated font ids to replace")
    ap.add_argument("--new", type=int, required=True)
    ap.add_argument("--keep", default="", help="comma separated char ids to leave alone")
    ap.add_argument("--only", default="", help="if set, only remap these char ids")
    args = ap.parse_args()

    keep = {int(x) for x in args.keep.split(",") if x.strip()}
    only = {int(x) for x in args.only.split(",") if x.strip()}
    old = {int(x) for x in args.old.split(",") if x.strip()}
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
                    if struct.unpack_from("<H", body, off)[0] in old:
                        struct.pack_into("<H", buf, p + off, args.new)
                        changed_refs += 1
                        hit = True
                if hit:
                    changed_tags += 1
        elif code == 37 and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            if (not only or cid in only) and cid not in keep:
                off = edit_text_font_offset(body)
                if off is not None and struct.unpack_from("<H", body, off)[0] in old:
                    struct.pack_into("<H", buf, p + off, args.new)
                    changed_refs += 1
                    changed_tags += 1
        pos = p + length

    write_swf_fws(bytes(buf), args.outfile)
    print(f"repointed {changed_refs} refs in {changed_tags} text tags -> {args.outfile}")
    return 0


def _first_tag_pos(data: bytes) -> int:
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    return pos


def _iter_swf_tags(buf, start):
    """Yield ``(tag_start, code, body)`` for the top-level tag stream."""
    pos = start
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        yield pos, code, buf[p : p + length]
        pos = p + length


def _signed_bits(v: int) -> int:
    if v >= 0:
        return max(1, v.bit_length() + 1)
    return max(1, (~v).bit_length() + 1)


class _BitWriter:
    def __init__(self):
        self.bits: list[int] = []

    def u(self, v: int, n: int) -> None:
        for i in range(n - 1, -1, -1):
            self.bits.append((v >> i) & 1)

    def si(self, v: int, n: int) -> None:
        if v < 0:
            v += 1 << n
        self.u(v, n)

    def align(self) -> None:
        while len(self.bits) % 8:
            self.bits.append(0)

    def bytes(self) -> bytes:
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            b = 0
            for j in range(8):
                b = (b << 1) | self.bits[i + j]
            out.append(b)
        return bytes(out)


def _read_matrix(body: bytes, bitpos: int) -> dict:
    st = {"p": bitpos}

    def u(n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((body[st["p"] >> 3] >> (7 - (st["p"] & 7))) & 1)
            st["p"] += 1
        return v

    def si(n):
        if n == 0:
            return 0
        v = u(n)
        return v - (1 << n) if v & (1 << (n - 1)) else v

    m = {"has_scale": u(1)}
    if m["has_scale"]:
        sb = u(5)
        m["sx"] = si(sb)
        m["sy"] = si(sb)
    m["has_rot"] = u(1)
    if m["has_rot"]:
        rb = u(5)
        m["r0"] = si(rb)
        m["r1"] = si(rb)
    tb = u(5)
    m["tx"] = si(tb)
    m["ty"] = si(tb)
    st["p"] = (st["p"] + 7) & ~7      # MATRIX is byte-aligned at its end
    m["end"] = st["p"] // 8
    return m


def _encode_matrix(m: dict) -> bytes:
    w = _BitWriter()
    w.u(1 if m.get("has_scale") else 0, 1)
    if m.get("has_scale"):
        sb = max(_signed_bits(m["sx"]), _signed_bits(m["sy"]))
        w.u(sb, 5)
        w.si(m["sx"], sb)
        w.si(m["sy"], sb)
    w.u(1 if m.get("has_rot") else 0, 1)
    if m.get("has_rot"):
        rb = max(_signed_bits(m["r0"]), _signed_bits(m["r1"]))
        w.u(rb, 5)
        w.si(m["r0"], rb)
        w.si(m["r1"], rb)
    tb = max(_signed_bits(m["tx"]), _signed_bits(m["ty"]))
    w.u(tb, 5)
    w.si(m["tx"], tb)
    w.si(m["ty"], tb)
    w.align()
    return w.bytes()


def shift_sprite_placements(infile: str, outfile: str, sprite_id: int,
                            target_ids: set[int], dy: int) -> int:
    """Move chosen children of ``sprite_id`` ``dy`` twips on Y.

    The in-game options bar places its dynamic ``DefineEditText`` values through
    the same left-anchored bar artwork as the static captions, but an EditText
    lays its first line out from the *font ascent*, so swapping the Latin face
    for a CJK one with a taller ascent pushes the values ~3px below the static
    names.  ``FCW``'s text import keeps the tag bounds, and bounds do not move an
    EditText's text, so the fix is to rewrite the child's placement matrix.
    """
    data, _ = load_swf_raw(infile)
    count = 0
    for tag_start, code, body in _iter_swf_tags(data, _first_tag_pos(data)):
        if code == 0:
            break
        if code != 39 or len(body) < 2:
            continue
        if struct.unpack_from("<H", body, 0)[0] != sprite_id:
            continue
        out = bytearray(body[:4])      # SpriteID + FrameCount
        for st, scode, tb in _iter_swf_tags(body, 4):
            if scode not in (26, 70) or len(tb) < 5:
                out += encode_tag(scode, bytes(tb))
                continue
            f1 = tb[0]
            f2 = tb[1] if scode == 70 else 0
            off = 4 if scode == 70 else 3
            if scode == 70 and (f2 & 0x80):
                off = tb.index(b"\x00", off) + 1
            cid = None
            if f1 & 0x02:
                cid = struct.unpack_from("<H", tb, off)[0]
                off += 2
            if cid in target_ids and (f1 & 0x04):
                m = _read_matrix(tb, off * 8)
                m["ty"] += dy
                tb = tb[:off] + _encode_matrix(m) + tb[m["end"]:]
                count += 1
            out += encode_tag(scode, bytes(tb))
        new_body = bytes(out)
        new_tag = encode_tag(39, new_body)
        # body_end is the byte after the original sprite tag's body
        p = tag_start + 2
        cl = struct.unpack_from("<H", data, tag_start)[0]
        length = cl & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, p)[0]
            p += 4
        data = data[:tag_start] + new_tag + data[p + length:]
        break
    write_swf_fws(data, outfile)
    return count


if __name__ == "__main__":
    sys.exit(main())