"""Re-centre translated ROTD2 UI labels that lost their alignment.

FFDec's text import lays the (often shorter) Chinese out from the tag's left
origin, so labels the original centred come out off-axis.  This pass mirrors
``align_controls.py``: export each affected static ``DefineText`` tag in FFDec's
"formatted" form, measure the rendered ink from an SVG dump (font-agnostic), and
rewrite the tag's ``translatex`` so the Chinese ink sits on the original English
ink centre.

Only single-record static tags are touched; dynamic text fields (``DefineEditText``,
which carry their own ``align``) and multi-record blocks are left alone.

Usage:
    python pipeline/align_rotd2.py --swf <in.swf> --orig <orig.swf> --out <out.swf> --ids 1,2,3
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_controls import (  # noqa: E402
    export_formatted, export_svg_ink, header_int, widen_bounds,
)
from translations import UI_TRANSLATIONS  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True, help="localised SWF (already translated)")
    ap.add_argument("--orig", required=True, help="original English SWF")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", required=True, help="candidate char ids (comma separated)")
    ap.add_argument("--outdir", default=str(ROOT / "work2" / "aligned"))
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    # Only tags we actually translated as a single record.
    ids = [i for i in ids
           if str(i) in UI_TRANSLATIONS and len(UI_TRANSLATIONS[str(i)]) == 1]
    if not ids:
        print("nothing to align")
        return 0

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    cur = export_formatted(args.swf, ids)
    ofmt = export_formatted(args.orig, ids)
    oink = export_svg_ink(args.orig, ids)
    bink = export_svg_ink(args.swf, ids)

    repl = ["-replace", args.swf, args.out]
    n = 0
    for sid in ids:
        famt = cur.get(sid, "")
        ofamt = ofmt.get(sid, "")
        segs = UI_TRANSLATIONS[str(sid)]
        o, b = oink.get(sid), bink.get(sid)
        if (not famt or not ofamt or "align" in famt or "align" in ofamt
                or len(segs) != 1 or o is None or b is None):
            continue
        bxmin = header_int(famt, "xmin")
        bxmax = header_int(famt, "xmax")
        bymin = header_int(famt, "ymin")
        bymax = header_int(famt, "ymax")
        oxmin = header_int(ofamt, "xmin")
        tx = header_int(famt, "translatex")
        if None in (bxmin, bxmax, bymin, bymax, oxmin, tx):
            continue
        desired = oxmin + (o[0] + o[1]) / 2 * 20      # original English ink centre
        built_c = bxmin + (b[0] + b[1]) / 2 * 20       # current Chinese ink centre
        new_tx = int(round(tx - (built_c - desired)))
        if new_tx == tx:
            continue
        s = new_tx - tx
        famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
        famt2 = re.sub(r"\]\s*[^\]]*$", "]" + segs[0], famt2)
        famt2 = widen_bounds(famt2, bxmin, bxmax, bymin, bymax,
                             bxmin + b[0] * 20 + s, bxmin + b[1] * 20 + s,
                             bymin + b[2] * 20, bymin + b[3] * 20)
        p = outdir / f"{sid}.txt"
        p.write_text(famt2, encoding="utf-8")
        repl += [str(sid), str(p)]
        n += 1

    if n == 0:
        print("nothing to align")
        return 0
    proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stdout[-1200:])
        print(proc.stderr[-1200:], file=sys.stderr)
        return 1
    print(f"re-centred {n} labels -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
