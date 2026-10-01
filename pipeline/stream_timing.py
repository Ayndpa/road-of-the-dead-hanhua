"""Compute the exact main-timeline frame -> streaming-audio time mapping.

Walks depth-0 tags of the SWF, accumulates SoundStreamBlock payloads per frame,
then parses the concatenated MP3 stream to know how much audio time has elapsed
at each frame boundary.
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

BITRATES_V1_L3 = [
    0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0,
]
BITRATES_V2_L3 = [
    0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0,
]
SRATES = {
    3: [44100, 48000, 32000],  # MPEG1
    2: [22050, 24000, 16000],  # MPEG2
    0: [11025, 12000, 8000],   # MPEG2.5
}


def load_swf(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"CWS":
        return raw[:8] + zlib.decompress(raw[8:])
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("swf")
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args()

    data = load_swf(args.swf)
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 2  # frame rate
    pos += 2  # frame count

    # frame -> cumulative stream bytes before that frame
    frame_marks: list[int] = []
    buf = bytearray()
    frame = 0
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
        if code == 1:  # ShowFrame -> next frame begins
            frame += 1
            frame_marks.append(len(buf))
        elif code == 19:  # SoundStreamBlock
            buf += data[pos : pos + length]
        pos += length

    print(f"frames={frame} streamBytes={len(buf)}")

    # parse mp3 frames over the concatenated stream
    times: list[float] = [0.0] * (len(frame_marks) + 1)
    i = 0
    t = 0.0
    n = 0
    marks = frame_marks + [len(buf)]
    mi = 0
    while i + 4 <= len(buf):
        if buf[i] != 0xFF or (buf[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        h = struct.unpack_from(">I", buf, i)[0]
        ver = (h >> 19) & 0x3
        layer = (h >> 17) & 0x3
        bri = (h >> 12) & 0xF
        sri = (h >> 10) & 0x3
        pad = (h >> 9) & 0x1
        if layer != 1 or sri == 3 or bri in (0, 15):
            i += 1
            continue
        srate = SRATES[ver][sri]
        if ver == 3:
            bitrate = BITRATES_V1_L3[bri] * 1000
            spf, coef = 1152, 144
        else:
            bitrate = BITRATES_V2_L3[bri] * 1000
            spf, coef = 576, 72
        if bitrate == 0:
            i += 1
            continue
        size = (coef * bitrate) // srate + pad
        t += spf / srate
        n += 1
        i += size
        while mi < len(marks) and marks[mi] <= i:
            times[mi] = t
            mi += 1
    print(f"mp3 frames={n} decodedTime={t:.2f}s")

    print("--- audio time at selected SWF frames ---")
    for f in (1, 599, 709, 1450, 2000, 2511, 2779, 3776, 4845, 6316):
        if 1 <= f <= len(frame_marks):
            print(f"  frame {f:>5}  audio={times[f - 1]:>8.2f}s  frame/30={f / args.fps:>8.2f}s")

    print("--- frame for selected audio times ---")
    for want in (48.33, 53.40, 70.38, 83.70, 105.26, 139.69, 160.72):
        for f in range(1, len(frame_marks) + 1):
            if times[f - 1] >= want:
                print(
                    f"  audio {want:>7.2f}s -> frame {f:>5} "
                    f"(frame/30={f / args.fps:.2f}s, drift={f / args.fps - want:+.2f}s)"
                )
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
