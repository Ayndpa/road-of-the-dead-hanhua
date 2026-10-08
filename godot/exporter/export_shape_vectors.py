"""Export SWF ``DefineShape`` geometry as pre-tessellated Godot meshes.

The main exporter rasterises every shape to a PNG, which blurs when the stage is
scaled up.  This tool instead reads each shape as SVG from FFDec and turns it
into final triangles (even-odd filled, gradients baked as per-vertex colours,
strokes expanded to quads) so the runtime only has to upload a mesh -- no
``Geometry2D`` work, no per-frame hitching, and no runtime tessellation dropping
fine detail.

Output:
  * ``assets/swf/shapes.bin``  compact little-endian mesh data
  * ``assets/swf/shapes.json`` tiny index (shape ids + bounds + glow flag)

Only shapes whose fills are solid or gradient are vectorised; shapes using
bitmap fills are skipped and keep their PNG.

Usage:
    python godot/exporter/export_shape_vectors.py --swf dist/Road-Of-The-Dead.swf
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import pyclipper
from shapely.geometry import Polygon
from shapely.ops import triangulate, unary_union

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_GODOT = ROOT / "godot"

TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")
NUM = re.compile(r"-?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
SC = 100.0  # pyclipper integer scale
MAGIC = b"SVEC"


# --------------------------------------------------------------------------
# SVG path parsing (M/L/H/V/C/S/Q/T/A/Z -> flattened contours)
# --------------------------------------------------------------------------
def _ranges(ids):
    out = []
    for cid in sorted(ids):
        if out and cid - 1 == int(out[-1].split("-")[-1]):
            out[-1] = f"{out[-1].split('-')[0]}-{cid}"
        else:
            out.append(str(cid))
    return ",".join(out)


def _seg_count(pts):
    length = 0.0
    for a, b in zip(pts, pts[1:]):
        length += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    return max(4, min(32, int(length / 3.0) + 1))


def parse_path(d):
    tokens = []
    for m in TOKEN.finditer(d):
        tokens.append(m.group(1) if m.group(1) else float(m.group(2)))
    contours = []
    closed = []
    cur = []
    x = y = 0.0
    sx = sy = 0.0
    cx = cy = 0.0
    qx = qy = 0.0
    i = 0
    cmd = ""

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    def quad(p0, p1, p2):
        n = _seg_count([p0, p1, p2])
        for k in range(1, n + 1):
            t = k / n
            mt = 1 - t
            cur.append((mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
                        mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]))

    def cubic(p0, p1, p2, p3):
        n = _seg_count([p0, p1, p2, p3])
        for k in range(1, n + 1):
            t = k / n
            mt = 1 - t
            cur.append((mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
                        mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]))

    while i < len(tokens):
        if isinstance(tokens[i], str):
            cmd = tokens[i]
            i += 1
        if cmd in ("M", "m"):
            nx, ny = num(), num()
            if cmd == "m":
                nx += x; ny += y
            if cur:
                contours.append(cur)
                closed.append(False)
            cur = [(nx, ny)]
            x, y = nx, ny
            sx, sy = x, y
            cmd = "L" if cmd == "M" else "l"
        elif cmd in ("L", "l"):
            nx, ny = num(), num()
            if cmd == "l":
                nx += x; ny += y
            cur.append((nx, ny)); x, y = nx, ny
        elif cmd in ("H", "h"):
            nx = num()
            if cmd == "h":
                nx += x
            cur.append((nx, y)); x = nx
        elif cmd in ("V", "v"):
            ny = num()
            if cmd == "v":
                ny += y
            cur.append((x, ny)); y = ny
        elif cmd in ("C", "c"):
            p1, p2, p3 = (num(), num()), (num(), num()), (num(), num())
            if cmd == "c":
                p1 = (p1[0] + x, p1[1] + y); p2 = (p2[0] + x, p2[1] + y); p3 = (p3[0] + x, p3[1] + y)
            cubic((x, y), p1, p2, p3); cx, cy = p2; x, y = p3
        elif cmd in ("S", "s"):
            p2, p3 = (num(), num()), (num(), num())
            if cmd == "s":
                p2 = (p2[0] + x, p2[1] + y); p3 = (p3[0] + x, p3[1] + y)
            p1 = (2 * x - cx, 2 * y - cy)
            cubic((x, y), p1, p2, p3); cx, cy = p2; x, y = p3
        elif cmd in ("Q", "q"):
            p1, p2 = (num(), num()), (num(), num())
            if cmd == "q":
                p1 = (p1[0] + x, p1[1] + y); p2 = (p2[0] + x, p2[1] + y)
            quad((x, y), p1, p2); qx, qy = p1; x, y = p2
        elif cmd in ("T", "t"):
            p2 = (num(), num())
            if cmd == "t":
                p2 = (p2[0] + x, p2[1] + y)
            p1 = (2 * x - qx, 2 * y - qy)
            quad((x, y), p1, p2); qx, qy = p1; x, y = p2
        elif cmd in ("A", "a"):
            nx, ny = num(), num()
            if cmd == "a":
                nx += x; ny += y
            cur.append((nx, ny)); x, y = nx, ny
        elif cmd in ("Z", "z"):
            if cur:
                contours.append(cur)
                closed.append(True)
                cur = []
            x, y = sx, sy
        else:
            i += 1
    if cur:
        contours.append(cur)
        closed.append(False)
    return [(c, cl) for c, cl in zip(contours, closed) if len(c) >= 3]


def _matrix(raw):
    m = re.search(r"matrix\(\s*([^)]*)\)", raw)
    if m:
        vals = [float(v) for v in NUM.findall(m.group(1))]
        if len(vals) == 6:
            return tuple(vals)
    t = re.search(r"translate\(\s*([^)]*)\)", raw)
    s = re.search(r"scale\(\s*([^)]*)\)", raw)
    a = d = 1.0
    if s:
        sv = [float(v) for v in NUM.findall(s.group(1))]
        a = sv[0]; d = sv[1] if len(sv) > 1 else sv[0]
    e = f = 0.0
    if t:
        tv = [float(v) for v in NUM.findall(t.group(1))]
        e = tv[0]; f = tv[1] if len(tv) > 1 else 0.0
    return (a, 0.0, 0.0, d, e, f)


def _apply(mat, pts):
    a, b, c, d, e, f = mat
    return [(a * px + c * py + e, b * px + d * py + f) for px, py in pts]


def _parse_gradients(text):
    grads = {}
    for m in re.finditer(r"<(linearGradient|radialGradient)\b([^>]*)>(.*?)</\1>", text, re.S):
        kind, attrs, body = m.group(1), m.group(2), m.group(3)
        gid_m = re.search(r'id="([^"]*)"', attrs)
        if not gid_m:
            continue
        gt = re.search(r'gradientTransform="([^"]*)"', attrs)
        mat = _matrix(gt.group(1)) if gt else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

        def f(name, default=0.0):
            mm = re.search(name + r'="(-?[\d.eE+]+)"', attrs)
            return float(mm.group(1)) if mm else default

        stops = []
        for sm in re.finditer(r"<stop\b([^>]*)/?>", body):
            sa = sm.group(1)
            om = re.search(r'offset="([^"]*)"', sa)
            off = float(om.group(1)) if om else 0.0
            cm = re.search(r'stop-color="([^"]*)"', sa)
            col = _color(cm.group(1)) if cm else [0, 0, 0, 255]
            if col is None:
                col = [0, 0, 0, 255]
            pm = re.search(r'stop-opacity="([^"]*)"', sa)
            if pm:
                col[3] = int(round(col[3] * float(pm.group(1))))
            stops.append([off, col])
        stops.sort(key=lambda s: s[0])
        if kind == "linearGradient":
            grads[gid_m.group(1)] = {"t": "l", "m": list(mat),
                                     "p": [f("x1"), f("y1"), f("x2", 1.0), f("y2")], "s": stops}
        else:
            grads[gid_m.group(1)] = {"t": "r", "m": list(mat),
                                     "p": [f("cx"), f("cy"), f("r", 1.0)], "s": stops}
    return grads


def _style(text):
    out = {}
    for part in text.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _color(value):
    value = value.strip()
    if not value or value in ("none", "transparent"):
        return None
    if value.startswith("url("):
        return None
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) >= 6:
            return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255]
    m = re.match(r"rgba?\(([^)]*)\)", value)
    if m:
        vals = [float(v) for v in NUM.findall(m.group(1))]
        if len(vals) >= 3:
            a = int(round(vals[3] * 255)) if len(vals) > 3 else 255
            return [int(vals[0]), int(vals[1]), int(vals[2]), a]
    return None


def parse_svg(text):
    """Return {'paths':[...]} with flattened contours, or None if bitmap."""
    mats = [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)]
    g = re.search(r"<g[^>]*transform=\"([^\"]*)\"", text)
    if g:
        mats.append(_matrix(g.group(1)))

    def xform(pts):
        for m in mats:
            pts = _apply(m, pts)
        return pts

    paths = []
    has_bitmap = ("<pattern" in text) or ("<image" in text)
    grads = _parse_gradients(text)
    for m in re.finditer(r"<path\b[^>]*?/>", text):
        tag = m.group(0)
        d = re.search(r'\sd="([^"]*)"', tag)
        if not d:
            continue
        sm = re.search(r'style="([^"]*)"', tag)
        st = _style(sm.group(1)) if sm else {}

        def attr(name):
            mm = re.search(name + r'="([^"]*)"', tag)
            return mm.group(1) if mm else st.get(name)

        fill_raw = attr("fill")
        stroke_raw = attr("stroke")
        if fill_raw is None:
            fill_raw = "#000000"
        grad = None
        if fill_raw.startswith("url("):
            gid_m = re.search(r"url\(#([^)]+)\)", fill_raw)
            gid = gid_m.group(1) if gid_m else ""
            if gid in grads:
                grad = grads[gid]
            else:
                has_bitmap = True
        fill = None if (grad is not None or fill_raw.startswith("url(")) else _color(fill_raw)
        stroke = _color(stroke_raw) if stroke_raw else None

        parsed = parse_path(d.group(1))
        if not parsed:
            continue
        contours = [c for c, _ in parsed]
        op = float(attr("fill-opacity") or 1.0)
        rule = 1 if (attr("fill-rule") == "evenodd") else 0
        if grad is not None:
            paths.append({"g": grad, "rule": rule, "p": [xform(c) for c in contours]})
        elif fill is not None:
            c = list(fill)
            c[3] = int(round(c[3] * op))
            if c[3] > 0:
                paths.append({"f": c, "rule": rule, "p": [xform(c2) for c2 in contours]})
        if stroke is not None:
            sw = float(attr("stroke-width") or 1.0)
            sop = float(attr("stroke-opacity") or 1.0)
            s = list(stroke)
            s[3] = int(round(s[3] * sop))
            for contour, cl in parsed:
                paths.append({"s": s, "w": round(sw, 2), "p": [xform(contour)], "closed": cl})
    if has_bitmap or not paths:
        return None
    return {"paths": paths}


# --------------------------------------------------------------------------
# even-odd resolution + triangulation (offline, robust)
# --------------------------------------------------------------------------
def _signed_area(ring):
    a = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a * 0.5


def _even_odd(rings):
    ints = [[(int(round(x * SC)), int(round(y * SC))) for x, y in r] for r in rings if len(r) >= 3]
    for r in ints:
        if _signed_area(r) < 0:
            r.reverse()
    if not ints:
        return []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(ints, pyclipper.PT_SUBJECT, True)
    sol = pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
    return [[(x / SC, y / SC) for x, y in p] for p in sol]


def _polys_from_paths(paths):
    shells, holes = [], []
    for p in paths:
        if len(p) < 3:
            continue
        (shells if _signed_area(p) > 0 else holes).append(p)
    polys = []
    for s in shells:
        poly = Polygon(s)
        if not poly.is_valid:
            poly = poly.buffer(0)
        polys.append(poly)
    if holes:
        hu = unary_union([Polygon(h).buffer(0) for h in holes])
        polys = [p.difference(hu) for p in polys]
    return polys


def _orient(ring, ccw):
    if (_signed_area(ring) > 0) != ccw:
        ring.reverse()
    return ring


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_tri(p, a, b, c):
    d1 = _cross(a, b, p)
    d2 = _cross(b, c, p)
    d3 = _cross(c, a, p)
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def _earclip(pts):
    idx = list(range(len(pts)))
    tris = []
    guard = 0
    limit = max(1, len(pts) * len(pts))
    while len(idx) > 3 and guard < limit:
        guard += 1
        n = len(idx)
        found = False
        for i in range(n):
            i0, i1, i2 = idx[(i - 1) % n], idx[i], idx[(i + 1) % n]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if _cross(a, b, c) <= 1e-9:
                continue
            clean = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                if _point_in_tri(pts[j], a, b, c):
                    clean = False
                    break
            if clean:
                tris.append((a, b, c))
                idx.pop(i)
                found = True
                break
        if not found:
            break
    if len(idx) == 3:
        tris.append((pts[idx[0]], pts[idx[1]], pts[idx[2]]))
    return tris


def _tris_poly(g, depth=0):
    """Triangulate a shapely Polygon (with holes) by clipping Delaunay
    triangles against it.  Holes are handled by the clip, so there are no
    bridge slits (which showed up as long thin lines)."""
    if g.is_empty or len(g.exterior.coords) < 4:
        return []
    ring = list(g.exterior.coords)[:-1]
    if not g.interiors or depth > 8:
        return _earclip(_orient(ring, True))
    out = []
    for tri in triangulate(g):
        inter = tri.intersection(g)
        if inter.is_empty:
            continue
        if inter.geom_type == "Polygon":
            pieces = [inter]
        elif inter.geom_type in ("MultiPolygon", "GeometryCollection"):
            pieces = [p for p in inter.geoms if p.geom_type == "Polygon"]
        else:
            continue
        for piece in pieces:
            out.extend(_tris_poly(piece, depth + 1))
    return out


def _triangles(polys):
    out = []
    for poly in polys:
        geoms = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
        for g in geoms:
            out.extend(_tris_poly(g))
    return out


def _grad_color(g, x, y):
    m = g.get("m", [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    a, b, c, d, e, f = [float(v) for v in m]
    det = a * d - b * c
    dx, dy = x - e, y - f
    if abs(det) < 1e-9:
        px, py = x, y
    else:
        px = (d * dx - c * dy) / det
        py = (-b * dx + a * dy) / det
    if str(g.get("t", "l")) == "l":
        p = g["p"]
        ax, ay, bx, by = float(p[0]), float(p[1]), float(p[2]), float(p[3])
        vx, vy = bx - ax, by - ay
        dd = vx * vx + vy * vy
        t = 0.0 if dd == 0 else ((px - ax) * vx + (py - ay) * vy) / dd
    else:
        p = g["p"]
        cx, cy, r = float(p[0]), float(p[1]), float(p[2])
        t = 0.0 if r == 0 else (((px - cx) ** 2 + (py - cy) ** 2) ** 0.5) / r
    t = max(0.0, min(1.0, t))
    stops = g.get("s", [])
    if not stops:
        return [255, 255, 255, 255]
    if len(stops) == 1:
        return list(stops[0][1])
    for i in range(len(stops) - 1):
        o0, o1 = float(stops[i][0]), float(stops[i + 1][0])
        if t <= o1 or i == len(stops) - 2:
            fq = 0.0 if o1 <= o0 else max(0.0, min(1.0, (t - o0) / (o1 - o0)))
            c0, c1 = stops[i][1], stops[i + 1][1]
            return [int(round(c0[k] + (c1[k] - c0[k]) * fq)) for k in range(4)]
    return list(stops[-1][1])


# --------------------------------------------------------------------------
# shape -> mesh
# --------------------------------------------------------------------------
def build_mesh(paths):
    verts = []   # list[(x,y)]
    idx = []     # triangle indices
    colors = []  # list[[r,g,b,a]] per vertex
    palette = {}
    pal = []
    ci = []

    def cidx(col):
        key = tuple(col)
        if key not in palette:
            palette[key] = len(pal)
            pal.append(list(col))
        return palette[key]

    for path in paths:
        if "s" in path:
            col = path["s"]
            half = max(float(path.get("w", 1.0)), 0.5) * 0.5
            for contour in path["p"]:
                pts = list(contour)
                n = len(pts)
                segments = n if path.get("closed", True) else n - 1
                for i in range(segments):
                    ax, ay = pts[i]
                    bx, by = pts[(i + 1) % n]
                    dx, dy = bx - ax, by - ay
                    ln = (dx * dx + dy * dy) ** 0.5
                    if ln < 1e-6:
                        continue
                    nx, ny = -dy / ln * half, dx / ln * half
                    quad = [(ax + nx, ay + ny), (ax - nx, ay - ny), (bx - nx, by - ny), (bx + nx, by + ny)]
                    base = len(verts)
                    for q in quad:
                        verts.append(q)
                        ci.append(cidx(col))
                    idx += [base, base + 1, base + 2, base, base + 2, base + 3]
            continue
        col_fn = None
        if "g" in path:
            col_fn = lambda p, g=path["g"]: _grad_color(g, p[0], p[1])
        else:
            col = path["f"]
            col_fn = lambda p, c=col: c
        rings = [list(c) for c in path["p"]]
        tris = _triangles(_polys_from_paths(_even_odd(rings)))
        for tri in tris:
            base = len(verts)
            for p in tri:
                verts.append((p[0], p[1]))
                ci.append(cidx(col_fn(p)))
            idx += [base, base + 1, base + 2]

    if not verts:
        return None
    xs = [p[0] for p in verts]
    ys = [p[1] for p in verts]
    rect = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    return {"v": verts, "i": idx, "ci": ci, "pal": pal, "rect": rect}


def write_bin(entries, out):
    with open(out, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<i", len(entries)))
        for sid, m in entries:
            v = m["v"]; idx = m["i"]; ci = m["ci"]; pal = m["pal"]; rect = m["rect"]
            fh.write(struct.pack("<i", sid))
            fh.write(struct.pack("<4f", *rect))
            fh.write(struct.pack("<3i", len(v), len(idx), len(pal)))
            fh.write(struct.pack("<%df" % (len(v) * 2), *[c for p in v for c in p]))
            fh.write(struct.pack("<%di" % len(idx), *idx))
            fh.write(struct.pack("<%di" % len(ci), *ci))
            fh.write(struct.pack("<%dB" % (len(pal) * 4), *[c for col in pal for c in col]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", type=Path, default=ROOT / "dist" / "Road-Of-The-Dead.swf")
    ap.add_argument("--godot", type=Path, default=DEFAULT_GODOT)
    ap.add_argument("--ffdec", type=Path, default=DEFAULT_FFDEC)
    ap.add_argument("--java", default="java")
    ap.add_argument("--ids", default="")
    ap.add_argument("--max-rings", type=int, default=6000)
    ap.add_argument("--max-points", type=int, default=120000)
    args = ap.parse_args()

    swf_dir = args.godot / "assets" / "swf"
    chars = json.loads((swf_dir / "characters.json").read_text(encoding="utf-8"))["characters"]
    if args.ids:
        shape_ids = sorted(int(x) for x in args.ids.split(",") if x.strip())
    else:
        shape_ids = sorted(int(k) for k, v in chars.items() if v.get("type") == "shape")
    print(f"[vectors] {len(shape_ids)} shapes")

    tmp = Path(tempfile.mkdtemp(prefix="rotl_vec_"))
    try:
        subprocess.run([args.java, "-jar", str(args.ffdec), "-selectid", _ranges(shape_ids),
                        "-format", "shape:svg", "-export", "shape", str(tmp), str(args.swf)],
                       capture_output=True, text=True, cwd=str(ROOT), check=True)
        entries = []
        index = {}
        skipped = 0
        for n, sid in enumerate(shape_ids):
            f = tmp / f"{sid}.svg"
            if not f.exists():
                continue
            parsed = parse_svg(f.read_text(encoding="utf-8"))
            if parsed is None:
                skipped += 1
                continue
            rings = sum(len(p["p"]) for p in parsed["paths"])
            points = sum(len(c) for p in parsed["paths"] for c in p["p"])
            if rings > args.max_rings or points > args.max_points:
                skipped += 1
                continue
            mesh = build_mesh(parsed["paths"])
            if mesh is None:
                skipped += 1
                continue
            entries.append((sid, mesh))
            index[str(sid)] = {"rect": [round(x, 2) for x in mesh["rect"]],
                               "nv": len(mesh["v"]), "npal": len(mesh["pal"])}
            if (n + 1) % 50 == 0:
                print(f"  {n + 1}/{len(shape_ids)} ...")
        bin_path = swf_dir / "shapes.bin"
        write_bin(entries, bin_path)
        (swf_dir / "shapes.json").write_text(
            json.dumps({"meta": {"swf": args.swf.name, "count": len(entries), "skipped": skipped},
                        "vectors": index}, separators=(",", ":")), encoding="utf-8")
        print(f"[vectors] {len(entries)} vector shapes, {skipped} skipped -> {bin_path} "
              f"({bin_path.stat().st_size / 1e6:.1f} MB)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
