"""Read the native (design) stage size out of a SWF header."""
from __future__ import annotations

from pathlib import Path


def swf_stage_size(path: Path) -> tuple[float, float]:
    """Native (design) stage size of a SWF, in pixels.

    This is the coordinate space the movie is authored in (e.g. 600x400 for
    Road of the Dead). It is *not* the player window size: after the player
    window is resized/maximised, ``Stage.stageWidth/Height`` can report the
    scaled window instead, which is why overlays anchored to those values end
    up off-screen. Layout uses this fixed design size instead.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0, 0.0
    if len(data) < 9:
        return 0.0, 0.0
    sig = data[:3]
    body = data[8:]
    if sig == b"CWS":
        import zlib
        try:
            body = zlib.decompress(body)
        except zlib.error:
            return 0.0, 0.0
    elif sig == b"ZWS":
        import lzma
        try:
            body = lzma.decompress(body)
        except lzma.LZMAError:
            return 0.0, 0.0
    elif sig != b"FWS":
        return 0.0, 0.0

    bit = 0

    def read_bits(n: int) -> int:
        nonlocal bit
        v = 0
        for _ in range(n):
            byte = body[bit >> 3]
            v = (v << 1) | ((byte >> (7 - (bit & 7))) & 1)
            bit += 1
        return v

    def read_sbits(n: int) -> int:
        v = read_bits(n)
        if v & (1 << (n - 1)):
            v -= 1 << n
        return v

    nbits = read_bits(5)
    if nbits == 0:
        return 0.0, 0.0
    xmin = read_sbits(nbits)
    xmax = read_sbits(nbits)
    ymin = read_sbits(nbits)
    ymax = read_sbits(nbits)
    return (xmax - xmin) / 20.0, (ymax - ymin) / 20.0
