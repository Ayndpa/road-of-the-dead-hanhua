"""Minimal SWF tag walker: main-timeline frame labels + scene data.

Works on CWS (zlib) or FWS files.
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def read_u30(buf: bytes, pos: int) -> tuple[int, int]:
    val = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, pos
        shift += 7


def read_string(buf: bytes, pos: int) -> tuple[str, int]:
    end = buf.index(b"\x00", pos)
    return buf[pos:end].decode("utf-8", "replace"), end + 1


def load_swf(path: str) -> bytes:
    raw = Path(path).read_bytes()
    sig = raw[:3]
    if sig == b"CWS":
        return raw[:8] + zlib.decompress(raw[8:])
    if sig == b"ZWS":
        raise SystemExit("LZMA-compressed SWF not supported")
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("swf")
    args = ap.parse_args()

    data = load_swf(args.swf)
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    frame_rate = struct.unpack_from("<H", data, pos)[0] / 256.0
    pos += 2
    total_frames = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    print(f"fps={frame_rate:.3f} declaredFrames={total_frames}")

    frame = 0
    labels: list[tuple[int, str]] = []
    scenes: list[tuple[int, str]] = []
    stream_frames: list[int] = []
    while pos < len(data):
        code_len = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        body = data[pos : pos + length]
        if code == 0:  # End
            break
        if code == 1:  # ShowFrame
            frame += 1
        elif code == 18:  # SoundStreamHead (main timeline stream)
            stream_frames.append(frame + 1)
        elif code == 19:  # SoundStreamBlock
            stream_frames.append(frame + 1)
        elif code == 45:  # SoundStreamHead2
            stream_frames.append(frame + 1)
        elif code == 39:  # DefineSprite -> skip nested timeline
            pass
        elif code == 43:  # FrameLabel
            end = body.index(b"\x00")
            labels.append((frame + 1, body[:end].decode("utf-8", "replace")))
        elif code == 86:  # DefineSceneAndFrameLabelData
            p = 0
            n_scenes, p = read_u30(body, p)
            for _ in range(n_scenes):
                off, p = read_u30(body, p)
                nm, p = read_string(body, p)
                scenes.append((off + 1, nm))
            n_labels, p = read_u30(body, p)
            for _ in range(n_labels):
                fnum, p = read_u30(body, p)
                nm, p = read_string(body, p)
                print(f"  sceneLabel {fnum:>5} {fnum / frame_rate:>8.2f}s  {nm}")
        pos += length

    print("--- main timeline FrameLabels ---")
    for f, name in labels:
        print(f"  {f:>5} {f / frame_rate:>8.2f}s  {name}")
    if stream_frames:
        print(
            f"main-timeline stream tags: {len(stream_frames)}  "
            f"firstFrame={stream_frames[0]} lastFrame={stream_frames[-1]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
