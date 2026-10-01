"""Build the fully localised SWF: Chinese UI text + Chinese subtitles.

The decorative title face (font id 20, "Dirty Ego") is never touched: the logo,
credits names and HUD numerals keep their original design.  Only the texts that
actually become Chinese are repointed to a spare font slot that receives a CJK
face.
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from remap_font import edit_text_font_offset, load_swf_raw, text_font_offsets  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
ORIG = Path(r"D:\Dev\Codes\Test\road-of-the-dead.swf")


def texts_using_font(swf: str, font_id: int) -> set[int]:
    data, _ = load_swf_raw(swf)
    buf = data
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    found: set[int] = set()
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = buf[p : p + length]
        if code in (11, 33) and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            if any(struct.unpack_from("<H", body, o)[0] == font_id
                   for o in text_font_offsets(body, code)):
                found.add(cid)
        elif code == 37 and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            off = edit_text_font_offset(body)
            if off is not None and struct.unpack_from("<H", body, off)[0] == font_id:
                found.add(cid)
        pos = p + length
    return found


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        print("\n".join(proc.stdout.splitlines()[-15:]))
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"ffdec failed with {proc.returncode}")
    for ln in [x for x in proc.stdout.splitlines() if x.strip()][-2:]:
        print("   ", ln)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(ORIG))
    ap.add_argument("--out", default=str(ROOT / "dist" / "rotl-zh-full.swf"))
    ap.add_argument("--texts", default=str(ROOT / "work" / "ui_texts"))
    ap.add_argument("--bold-font", default=str(ROOT / "work" / "fonts" / "ui_bold.ttf"))
    ap.add_argument("--regular-font", default=str(ROOT / "work" / "fonts" / "ui_regular.ttf"))
    ap.add_argument("--decor-font-id", type=int, default=20)
    ap.add_argument("--cjk-font-id", type=int, default=88)
    ap.add_argument("--bold-font-ids", default="46,558")
    ap.add_argument(
        "--regular-font-ids",
        default="22,26,32,87,88,92,94,1103,1106,1758,2819,4013",
    )
    args = ap.parse_args()

    all_texts = {int(p.stem) for p in Path(args.texts).glob("*.txt")}
    from ui_text import UI_TRANSLATIONS

    translated = {int(k) for k in UI_TRANSLATIONS if int(k) in all_texts}

    decor = texts_using_font(args.orig, args.decor_font_id)
    remap_ids = sorted(decor & translated)
    keep_ids = sorted(decor - translated)
    print(f"decor font {args.decor_font_id}: {len(decor)} texts; "
          f"remap {len(remap_ids)}; keep original {len(keep_ids)}")

    base = ROOT / "work" / "base_remap.swf"
    (ROOT / "work").mkdir(parents=True, exist_ok=True)
    (ROOT / "dist").mkdir(parents=True, exist_ok=True)
    run([
        "uv", "run", "python",
        str(ROOT / "pipeline" / "remap_font.py"),
        args.orig, str(base),
        "--old", str(args.decor_font_id), "--new", str(args.cjk_font_id),
        "--only", ",".join(str(x) for x in remap_ids),
    ])

    texts = sorted(Path(args.texts).glob("*.txt"), key=lambda p: int(p.stem))
    texts = [p for p in texts if int(p.stem) not in keep_ids]
    print(f"text tags to import: {len(texts)} (skipping {len(keep_ids)} original-font texts)")

    tmp_ui = ROOT / "work" / "build_ui.swf"
    tmp_sub = ROOT / "dist" / "build_sub.swf"

    repl = ["-replace", str(base), str(tmp_ui)]
    for fid in (int(x) for x in args.bold_font_ids.split(",") if x):
        repl += [str(fid), args.bold_font]
    for fid in (int(x) for x in args.regular_font_ids.split(",") if x):
        repl += [str(fid), args.regular_font]
    for p in texts:
        repl += [p.stem, str(p)]
    run(["java", "-Xmx4g", "-jar", str(FFDEC), *repl])

    as3_dir = ROOT / "patch" / "as3"
    repl2 = ["-replace", str(tmp_ui), str(tmp_sub), "DTSound", str(ROOT / "patch" / "DTSound.as")]
    for p in sorted(as3_dir.glob("*.as")):
        repl2 += [p.stem, str(p)]
    run(["java", "-Xmx4g", "-jar", str(FFDEC), *repl2])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(tmp_sub.read_bytes())
    print(f"built {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
