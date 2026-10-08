#!/usr/bin/env python3
"""Move Flash (SWF) sprite timelines into a Godot project.

Pipeline
--------
1. ``ffdec -swf2xml`` dumps the SWF to an XML tree (cached).
2. This tool streams the XML and reconstructs every ``DefineSprite``
   timeline as an ordered list of per-frame display-list operations
   (place / move / remove), keeping Flash matrices and color transforms.
3. Leaf shapes are rasterized to PNG and bitmaps are extracted to PNG by
   FFDec, one batch per type, restricted to the character ids we need.
4. Everything is written as JSON that the Godot runtime
   ``SwfMovieClip`` (addons/swf_timeline) interprets frame by frame.

Example
-------
    uv run python godot/exporter/swf_to_godot.py \
        --swf dist/Road-Of-The-Dead.swf --named --limit 40 --max-frames 200

    uv run python godot/exporter/swf_to_godot.py --swf ... --list
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
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FFDEC = REPO_ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_GODOT = REPO_ROOT / "godot"
TWIP = 20.0

SHAPE_TAGS = {"DefineShapeTag", "DefineShape2Tag", "DefineShape3Tag", "DefineShape4Tag"}
MORPH_TAGS = {"DefineMorphShapeTag", "DefineMorphShape2Tag"}
IMAGE_TAGS = {
    "DefineBitsTag",
    "DefineBitsJPEG2Tag",
    "DefineBitsJPEG3Tag",
    "DefineBitsJPEG4Tag",
    "DefineBitsLosslessTag",
    "DefineBitsLossless2Tag",
}
TEXT_TAGS = {"DefineTextTag", "DefineText2Tag", "DefineEditTextTag"}
BUTTON_TAGS = {"DefineButtonTag", "DefineButton2Tag"}
PLACE_TAGS = {"PlaceObject2Tag", "PlaceObject3Tag"}
PATTERN_PREFIX = "MC_LevelPattern_"


# --------------------------------------------------------------------------
# XML parsing
# --------------------------------------------------------------------------
def _parse_color_transform(el: ET.Element) -> list[float] | None:
    has_mult = el.get("hasMultTerms") == "true"
    has_add = el.get("hasAddTerms") == "true"
    if not has_mult and not has_add:
        return None

    def mult(name: str) -> float:
        raw = float(el.get(f"{name}MultTerm", "256")) if has_mult else 256.0
        return raw / 256.0

    def add(name: str) -> float:
        raw = float(el.get(f"{name}AddTerm", "0")) if has_add else 0.0
        return raw / 255.0

    return [
        round(mult("red"), 5),
        round(mult("green"), 5),
        round(mult("blue"), 5),
        round(mult("alpha"), 5),
        round(add("red"), 5),
        round(add("green"), 5),
        round(add("blue"), 5),
        round(add("alpha"), 5),
    ]


def _matrix_op(el: ET.Element | None) -> list | None:
    if el is None:
        return None
    sx = float(el.get("scaleX", "1") or 1.0)
    sy = float(el.get("scaleY", "1") or 1.0)
    k0 = float(el.get("rotateSkew0", "0") or 0.0)
    k1 = float(el.get("rotateSkew1", "0") or 0.0)
    tx = float(el.get("translateX", "0") or 0.0) / TWIP
    ty = float(el.get("translateY", "0") or 0.0) / TWIP
    if any(abs(v) > 1e-9 for v in (sx - 1.0, sy - 1.0, k0, k1, tx, ty)):
        return [round(sx, 6), round(k0, 6), round(k1, 6), round(sy, 6), round(tx, 4), round(ty, 4)]
    return None


def _button_state_ops(el: ET.Element, want_over: bool) -> list:
    """Placements of a DefineButton's up (or over/down) state as one frame."""
    records = el.find("characters")
    if records is None:
        return []
    ops: list = []
    for rec in records.findall("item"):
        if rec.get("type") != "BUTTONRECORD":
            continue
        if want_over:
            if rec.get("buttonStateOver") != "true" and rec.get("buttonStateDown") != "true":
                continue
        elif rec.get("buttonStateUp") != "true":
            continue
        cid = rec.get("characterId")
        if not cid:
            continue
        op: dict = {"op": "p", "d": int(rec.get("placeDepth", "0")), "c": int(cid)}
        mat = _matrix_op(rec.find("placeMatrix"))
        if mat:
            op["m"] = mat
        ct_el = rec.find("colorTransform")
        if ct_el is not None:
            ct = _parse_color_transform(ct_el)
            if ct is not None:
                op["ct"] = ct
        ops.append(op)
    return ops


def _button_states(el: ET.Element) -> dict:
    """Up and over/down frames of a DefineButton/DefineButton2."""
    return {
        "up": _button_state_ops(el, False),
        "over": _button_state_ops(el, True),
    }


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = text.replace("&amp;", "&").replace("&#160;", " ").replace("&nbsp;", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def _parse_static_text(el: ET.Element) -> dict:
    records: list[dict] = []
    font_ids: set[int] = set()
    total_adv = 0.0
    cur_color = [0, 0, 0, 255]
    cur_font = 0
    cur_size = 12.0
    records_el = el.find("textRecords")
    if records_el is not None:
        for rec in records_el.findall("item"):
            if rec.get("type") != "TEXTRECORD":
                continue
            if rec.get("styleFlagsHasFont") == "true":
                cur_font = int(rec.get("fontId", "0") or 0)
                cur_size = float(rec.get("textHeight", "1200") or 1200) / TWIP
            fid = cur_font
            font_ids.add(fid)
            size = cur_size
            if rec.get("styleFlagsHasColor") == "true":
                c = rec.find("textColor")
                if c is not None:
                    cur_color = [
                        int(c.get("red", "0")),
                        int(c.get("green", "0")),
                        int(c.get("blue", "0")),
                        int(c.get("alpha", "255")),
                    ]
            color = list(cur_color)
            x = None
            if rec.get("styleFlagsHasXOffset") == "true":
                x = float(rec.get("xOffset", "0") or 0) / TWIP
            y = None
            if rec.get("styleFlagsHasYOffset") == "true":
                y = float(rec.get("yOffset", "0") or 0) / TWIP
            adv = 0.0
            ge = rec.find("glyphEntries")
            if ge is not None:
                for g in ge.findall("item"):
                    adv += float(g.get("glyphAdvance", "0") or 0)
            records.append({"font": fid, "size": round(size, 3), "color": color,
                            "x": x, "y": y, "adv": round(adv / TWIP, 3)})
            total_adv += adv / TWIP
    tmx = tmy = 0.0
    tm = el.find("textMatrix")
    if tm is not None:
        tmx = float(tm.get("translateX", "0") or 0) / TWIP
        tmy = float(tm.get("translateY", "0") or 0) / TWIP
    return {"kind": "static", "records": records, "fonts": sorted(font_ids),
            "x": round(tmx, 3), "y": round(tmy, 3)}


def _parse_edit_text(el: ET.Element) -> dict:
    font_ids: set[int] = set()
    fid = int(el.get("fontId", "0") or 0)
    if el.get("hasFont") == "true":
        font_ids.add(fid)
    size = float(el.get("fontHeight", "1200") or 1200) / TWIP
    color = [0, 0, 0, 255]
    c = el.find("textColor")
    if c is not None:
        color = [int(c.get("red", "0")), int(c.get("green", "0")),
                 int(c.get("blue", "0")), int(c.get("alpha", "255"))]
    b = el.find("bounds")
    bounds = [round(v / TWIP, 3) for v in _rect(b)] if b is not None else [0, 0, 0, 0]
    return {
        "kind": "edit",
        "font": fid,
        "fonts": sorted(font_ids),
        "size": round(size, 3),
        "color": color,
        "text": _html_to_text(el.get("initialText", "")),
        "align": int(el.get("align", "0") or 0),
        "multiline": el.get("multiline") == "true",
        "bounds": bounds,
    }


def _parse_place(el: ET.Element) -> dict | None:
    has_char = el.get("placeFlagHasCharacter") == "true"
    op: dict = {"op": "p" if has_char else "m", "d": int(el.get("depth", "0"))}
    if has_char:
        op["c"] = int(el.get("characterId", "0"))
    if el.get("placeFlagMove") == "true":
        op["mv"] = 1

    mat = _matrix_op(el.find("matrix"))
    if mat:
        op["m"] = mat

    ct_el = el.find("colorTransform")
    if ct_el is not None:
        ct = _parse_color_transform(ct_el)
        if ct is not None:
            op["ct"] = ct

    if el.get("placeFlagHasName") == "true" and el.get("name"):
        op["n"] = el.get("name")
    if el.get("placeFlagHasClipDepth") == "true":
        op["clip"] = int(el.get("clipDepth", "0"))
    if el.get("placeFlagHasRatio") == "true" and el.get("ratio") is not None:
        op["ratio"] = int(el.get("ratio", "0"))
    if el.get("placeFlagHasVisible") == "true" and el.get("visible") == "false":
        op["v"] = 0
    return op


def resolve_inherited_transforms(frames: list) -> None:
    """Bake Flash's retained placements into every frame.

    A PlaceObject tag only carries a matrix/colour when that transform changes;
    a ``Move`` that swaps the character at a depth (e.g. one info panel for the
    next) omits them and Flash keeps the depth's previous transform.  Our
    per-frame delta export dropped those inherited values, so seeking straight
    to such a frame started from the identity matrix and the object drifted
    outside its background.  Copy the retained fields onto the move so each
    frame is self-contained, then drop the temporary ``mv`` marker.
    """
    state: dict[int, dict] = {}
    for frame in frames:
        for op in frame:
            d = int(op.get("d", 0))
            kind = op.get("op")
            if kind == "r":
                state.pop(d, None)
                continue
            if kind == "m":
                cur = state.setdefault(d, {})
                for field in ("m", "ct", "ratio"):
                    if field in op:
                        cur[field] = op[field]
                continue
            moved = bool(op.pop("mv", False))
            prev = state.get(d)
            if moved and prev is not None:
                for field in ("m", "ct", "ratio"):
                    if field not in op and field in prev:
                        op[field] = prev[field]
            nxt: dict = {}
            for field in ("m", "ct", "ratio"):
                if field in op:
                    nxt[field] = op[field]
            state[d] = nxt


def _rect(el: ET.Element) -> tuple[float, float, float, float]:
    return (
        float(el.get("Xmin", "0")),
        float(el.get("Ymin", "0")),
        float(el.get("Xmax", "0")),
        float(el.get("Ymax", "0")),
    )


def parse_swf_xml(xml_path: Path) -> dict:
    sprites: dict[int, list] = {}
    bounds: dict[int, tuple[float, float, float, float]] = {}
    images: set[int] = set()
    morphs: set[int] = set()
    texts: set[int] = set()
    text_defs: dict[int, dict] = {}
    buttons: set[int] = set()
    buttons_def: dict[int, list] = {}
    symbols: dict[int, str] = {}
    header: dict = {}
    labels: dict[str, int] = {}
    sprite_labels: dict[int, dict[str, int]] = {}
    root_ctx: dict = {"id": 0, "frames": [[]], "labels": {}}
    sprite_stack: list[dict] = [root_ctx]

    for event, el in ET.iterparse(str(xml_path), events=("start", "end")):
        if event == "start":
            if el.tag == "swf":
                header = dict(el.attrib)
            elif el.tag == "item" and el.get("type") == "DefineSpriteTag":
                sprite_stack.append({"id": int(el.get("spriteId", "0")), "frames": [[]], "labels": {}})
            continue

        if el.tag != "item":
            # keep children (matrix/colorTransform/tags/names) until parent clears
            continue

        t = el.get("type", "")
        if not t or t in ("BUTTONRECORD", "TEXTRECORD", "GLYPHENTRY"):
            # plain value item (SymbolClass entry) or a child record read by its
            # parent tag: keep it until the parent is processed
            continue
        if t == "DefineSpriteTag":
            ctx = sprite_stack.pop()
            sprites[ctx["id"]] = ctx["frames"]
            if ctx["labels"]:
                sprite_labels[ctx["id"]] = ctx["labels"]
        elif t == "FrameLabelTag":
            if sprite_stack:
                fname = el.get("name")
                if fname:
                    sprite_stack[-1]["labels"][fname] = max(len(sprite_stack[-1]["frames"]) - 1, 0)
        elif t == "DefineSceneAndFrameLabelDataTag":
            nums_el = el.find("frameNums")
            names_el = el.find("frameNames")
            if nums_el is not None and names_el is not None:
                for raw_num, raw_name in zip(nums_el, names_el):
                    try:
                        labels[str(raw_name.text)] = int(raw_num.text)
                    except (TypeError, ValueError):
                        pass
        elif t == "SymbolClassTag":
            tags_el = el.find("tags")
            names_el = el.find("names")
            if tags_el is not None and names_el is not None:
                ids = [c.text for c in tags_el]
                names = [c.text for c in names_el]
                for raw_id, name in zip(ids, names):
                    try:
                        symbols[int(raw_id)] = name
                    except (TypeError, ValueError):
                        pass
        elif t in MORPH_TAGS:
            cid = int(el.get("characterId", el.get("shapeId", "0")))
            b = el.find("startBounds")
            if b is None:
                b = el.find("shapeBounds")
            if b is not None:
                bounds[cid] = _rect(b)
            morphs.add(cid)
        elif t in SHAPE_TAGS:
            cid = int(el.get("shapeId", el.get("characterID", "0")))
            b = el.find("shapeBounds")
            if b is not None:
                bounds[cid] = _rect(b)
        elif t in IMAGE_TAGS:
            cid = int(el.get("characterID", el.get("bitmapId", el.get("imageId", "0"))))
            images.add(cid)
        elif t in TEXT_TAGS:
            cid = int(el.get("characterID", el.get("characterId", "0")))
            texts.add(cid)
            if t == "DefineEditTextTag":
                text_defs[cid] = _parse_edit_text(el)
            else:
                text_defs[cid] = _parse_static_text(el)
        elif t in BUTTON_TAGS:
            bid = int(el.get("buttonId", el.get("characterId", el.get("characterID", "0"))))
            buttons_def[bid] = _button_states(el)
            buttons.add(bid)
        elif t in PLACE_TAGS and sprite_stack:
            op = _parse_place(el)
            if op is not None:
                sprite_stack[-1]["frames"][-1].append(op)
        elif t == "RemoveObject2Tag" and sprite_stack:
            sprite_stack[-1]["frames"][-1].append({"op": "r", "d": int(el.get("depth", "0"))})
        elif t == "ShowFrameTag" and sprite_stack:
            sprite_stack[-1]["frames"].append([])

        el.clear()

    sprites[0] = root_ctx["frames"]
    for frames in sprites.values():
        resolve_inherited_transforms(frames)
    return {
        "header": header,
        "sprites": sprites,
        "bounds": bounds,
        "images": images,
        "morphs": morphs,
        "texts": texts,
        "text_defs": text_defs,
        "buttons": buttons,
        "buttons_def": buttons_def,
        "symbols": symbols,
        "labels": labels,
        "sprite_labels": sprite_labels,
    }


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------
def _short_name(symbol: str) -> str:
    return symbol.rsplit(".", 1)[-1]


def resolve_selection(parsed: dict, args) -> list[int]:
    sprites: dict[int, list] = parsed["sprites"]
    symbols: dict[int, str] = parsed["symbols"]

    if args.sprites:
        chosen: list[int] = []
        for token in args.sprites.split(","):
            token = token.strip()
            if not token:
                continue
            if token.lstrip("-").isdigit():
                if "-" in token[1:]:
                    lo, hi = token.split("-", 1)
                    chosen.extend(range(int(lo), int(hi) + 1))
                else:
                    chosen.append(int(token))
            else:
                matches = [cid for cid, n in symbols.items() if _short_name(n) == token]
                if not matches:
                    print(f"  ! name not found: {token}", file=sys.stderr)
                chosen.extend(matches)
        return sorted({c for c in chosen if c in sprites})

    candidates = list(sprites.keys())
    if args.named:
        candidates = [c for c in candidates if c in symbols]
    if args.max_frames:
        candidates = [c for c in candidates if len(sprites[c]) <= args.max_frames]
    if args.min_frames:
        candidates = [c for c in candidates if len(sprites[c]) >= args.min_frames]
    candidates.sort(key=lambda c: (c not in symbols, symbols.get(c, "")))
    if args.limit:
        candidates = candidates[: args.limit]
    return candidates


def collect_characters(parsed: dict, selected: list[int], hidden: set[int] | None = None) -> dict:
    hidden = hidden or set()
    sprites = parsed["sprites"]
    needed_sprites: set[int] = set()
    needed = {"shapes": set(), "images": set(), "morphs": set(), "texts": set(), "buttons": set()}
    stack = list(selected)
    seen: set[int] = set()
    while stack:
        sid = stack.pop()
        if sid in seen or sid not in sprites or sid in hidden:
            continue
        seen.add(sid)
        needed_sprites.add(sid)
        for frame in sprites[sid]:
            for op in frame:
                if op.get("op") != "p" or "c" not in op:
                    continue
                c = op["c"]
                if c in hidden:
                    continue
                if c in sprites:
                    stack.append(c)
                elif c in parsed["morphs"]:
                    needed["morphs"].add(c)
                elif c in parsed["bounds"]:
                    needed["shapes"].add(c)
                elif c in parsed["images"]:
                    needed["images"].add(c)
                elif c in parsed["texts"]:
                    needed["texts"].add(c)
                elif c in parsed["buttons"]:
                    needed["buttons"].add(c)
    return {"sprites": needed_sprites, **needed}


# --------------------------------------------------------------------------
# root timeline slicing (for scenes like the main menu)
# --------------------------------------------------------------------------
def _merge_state(state: dict[int, dict], ops: list) -> None:
    for op in ops:
        depth = int(op.get("d", 0))
        kind = op.get("op")
        if kind == "r":
            state.pop(depth, None)
        elif kind == "p":
            state[depth] = dict(op)
        elif kind == "m" and depth in state:
            cur = dict(state[depth])
            if "m" in op:
                cur["m"] = op["m"]
            if "ct" in op:
                cur["ct"] = op["ct"]
            state[depth] = cur


def slice_timeline(frames: list, start0: int, end0: int) -> list:
    """Return frames[start0..end0] as a standalone timeline.

    Frame 0 of the slice is a full snapshot of the display list that is live
    at ``start0`` (Flash timelines are cumulative), the rest are the original
    per-frame operations.
    """
    if not frames:
        return [[]]
    start0 = max(0, min(start0, len(frames) - 1))
    end0 = max(start0, min(end0, len(frames) - 1))
    state: dict[int, dict] = {}
    for i in range(0, start0 + 1):
        _merge_state(state, frames[i])
    out = [[dict(state[d]) for d in sorted(state)]]
    for i in range(start0 + 1, end0 + 1):
        out.append(frames[i])
    return out


def resolve_frame(value: str, labels: dict[str, int], frame_count: int) -> int:
    value = value.strip()
    if value in labels:
        return labels[value]
    try:
        return int(value)
    except ValueError:
        raise SystemExit(f"unknown frame label/number: {value!r} (labels: {', '.join(labels)})")


def resolve_segment_range(parsed: dict, name: str) -> tuple[int, int]:
    labels: dict[str, int] = parsed["labels"]
    frame_count = len(parsed["sprites"].get(0, []))
    if name not in labels:
        raise SystemExit(f"unknown segment label {name!r} (labels: {', '.join(labels)})")
    start = labels[name]
    following = [f for f in labels.values() if f > start]
    end = (min(following) - 1) if following else frame_count
    return start, min(max(start, end), frame_count)


def resolve_root_range(parsed: dict, args) -> tuple[int, int]:
    labels: dict[str, int] = parsed["labels"]
    frame_count = len(parsed["sprites"].get(0, []))
    spec = args.root.strip()
    if ".." in spec:
        raw_start, raw_end = spec.split("..", 1)
        start = resolve_frame(raw_start, labels, frame_count)
        end = resolve_frame(raw_end, labels, frame_count)
    else:
        start = resolve_frame(spec, labels, frame_count)
        if args.root_end:
            end = resolve_frame(args.root_end, labels, frame_count)
        else:
            following = [f for f in labels.values() if f > start]
            end = (min(following) - 1) if following else start
    start = max(1, start)
    end = min(max(start, end), frame_count)
    return start, end


# --------------------------------------------------------------------------
# FFDec leaf export
# --------------------------------------------------------------------------
def _ranges(ids: set[int]) -> str:
    out: list[str] = []
    for cid in sorted(ids):
        if out and cid - 1 == int(out[-1].split("-")[-1]):
            start = out[-1].split("-")[0]
            out[-1] = f"{start}-{cid}"
        else:
            out.append(str(cid))
    return ",".join(out)


def _run_ffdec_export(java: str, ffdec: Path, item: str, fmt: str | None, outdir: Path, swf: Path, ids: set[int]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [java, "-jar", str(ffdec), "-selectid", _ranges(ids)]
    if fmt:
        cmd += ["-format", fmt]
    cmd += ["-export", item, str(outdir), str(swf)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"FFDec export failed: {item}")


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        head = fh.read(24)
    if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    return (0, 0)


def export_leaves(parsed: dict, needed: dict, args, godot_dir: Path) -> dict[int, dict]:
    characters: dict[int, dict] = {}
    shapes_dir = godot_dir / "assets" / "swf" / "shapes"
    images_dir = godot_dir / "assets" / "swf" / "images"
    shapes_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="rotl_swf_") as tmp:
        tmp = Path(tmp)
        if needed["shapes"]:
            _run_ffdec_export(args.java, args.ffdec, "shape", "shape:png", tmp / "shapes", args.swf, needed["shapes"])
            for png in (tmp / "shapes").rglob("*.png"):
                cid = int(png.stem) if png.stem.isdigit() else None
                if cid is None or cid not in needed["shapes"]:
                    continue
                dest = shapes_dir / f"{cid}.png"
                shutil.copyfile(png, dest)
                xmin, ymin, xmax, ymax = parsed["bounds"][cid]
                characters[cid] = {
                    "type": "shape",
                    "res": f"res://assets/swf/shapes/{cid}.png",
                    "x": round(xmin / TWIP, 4),
                    "y": round(ymin / TWIP, 4),
                    "w": round((xmax - xmin) / TWIP, 2),
                    "h": round((ymax - ymin) / TWIP, 2),
                }
        if needed["images"]:
            _run_ffdec_export(args.java, args.ffdec, "image", "image:png", tmp / "images", args.swf, needed["images"])
            for png in (tmp / "images").rglob("*.png"):
                cid = int(png.stem) if png.stem.isdigit() else None
                if cid is None or cid not in needed["images"]:
                    continue
                dest = images_dir / f"{cid}.png"
                shutil.copyfile(png, dest)
                w, h = _png_size(dest)
                characters[cid] = {
                    "type": "image",
                    "res": f"res://assets/swf/images/{cid}.png",
                    "x": 0.0,
                    "y": 0.0,
                    "w": w,
                    "h": h,
                }

    for cid in needed["morphs"]:
        characters[cid] = {"type": "morph"}
    for cid in needed["texts"]:
        characters[cid] = {"type": "text"}
    for cid in needed["buttons"]:
        characters[cid] = {"type": "button"}
    for cid in needed["sprites"]:
        entry: dict = {"type": "sprite", "frames": len(parsed["sprites"].get(cid, []))}
        if cid in parsed.get("buttons", set()):
            entry["button"] = True
        characters[cid] = entry
    return characters


def export_morphs(morph_ids: set[int], parsed: dict, args, godot_dir: Path) -> dict[int, dict]:
    """Export DefineMorphShape ids as PNG frame sequences (interpolated by FFDec)."""
    chars: dict[int, dict] = {}
    if not morph_ids:
        return chars
    seq_root = godot_dir / "assets" / "swf" / "seq"
    with tempfile.TemporaryDirectory(prefix="rotl_morph_") as tmp:
        tmp = Path(tmp)
        _run_ffdec_export(args.java, args.ffdec, "morphshape", "morphshape:png_frames", tmp, args.swf, morph_ids)
        for folder in tmp.iterdir():
            if not folder.is_dir() or not folder.name.isdigit():
                continue
            mid = int(folder.name)
            if mid not in morph_ids:
                continue
            pngs = sorted(folder.glob("*.png"), key=lambda p: int(p.name.split("_")[0]))
            dest_dir = seq_root / str(mid)
            shutil.rmtree(dest_dir, ignore_errors=True)
            dest_dir.mkdir(parents=True, exist_ok=True)
            for i, png in enumerate(pngs, 1):
                shutil.copyfile(png, dest_dir / f"{i}.png")
            b = parsed["bounds"].get(mid, (0.0, 0.0, 0.0, 0.0))
            chars[mid] = {
                "type": "morph",
                "dir": f"res://assets/swf/seq/{mid}",
                "frames": len(pngs),
                "x": round(b[0] / TWIP, 4),
                "y": round(b[1] / TWIP, 4),
            }
    return chars


def export_sounds(sound_ids: set[int], args, godot_dir: Path) -> dict[int, dict]:
    """Export DefineSound ids as MP3 and return {id: {name, res}}."""
    out: dict[int, dict] = {}
    if not sound_ids:
        return out
    snd_dir = godot_dir / "assets" / "swf" / "sounds"
    snd_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rotl_snd_") as tmp:
        tmp = Path(tmp)
        _run_ffdec_export(args.java, args.ffdec, "sound", "sound:mp3", tmp, args.swf, sound_ids)
        for mp3 in tmp.rglob("*.mp3"):
            head = mp3.stem.split("_", 1)[0]
            if head.isdigit() and int(head) in sound_ids:
                shutil.copyfile(mp3, snd_dir / mp3.name)
                out[int(head)] = {
                    "name": mp3.stem.split("_", 1)[1] if "_" in mp3.stem else "",
                    "res": f"res://assets/swf/sounds/{mp3.name}",
                }
    return out


def resolve_sound_ids(parsed: dict, spec: str) -> set[int]:
    ids: set[int] = set()
    for token in (spec or "").split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            ids.add(int(token))
        else:
            for cid, name in parsed["symbols"].items():
                if _short_name(name) == token:
                    ids.add(cid)
    return ids


def export_patterns(parsed: dict, godot_dir: Path) -> dict:
    """Extract MC_LevelPattern_* layout markers (positions, alpha, color offsets).

    The pattern symbols are MovieClips whose direct children are MC_LevelObject_*
    marker clips. The loader in ROTD1 only reads the child's class, x, y, alpha
    and colour-transform offsets, so those are all we export.
    """
    symbols: dict[int, str] = parsed["symbols"]
    patterns: dict[str, list] = {}
    for cid, name in symbols.items():
        short = _short_name(name)
        if not short.startswith(PATTERN_PREFIX):
            continue
        frames = parsed["sprites"].get(cid)
        if not frames:
            continue
        markers: list = []
        for op in frames[0]:
            if op.get("op") != "p" or "c" not in op:
                continue
            m = op.get("m", [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
            ct = op.get("ct")
            alpha = 1.0
            red = 0
            blue = 0
            if ct is not None and len(ct) >= 8:
                alpha = float(ct[3])
                red = int(round(float(ct[4]) * 255.0))
                blue = int(round(float(ct[6]) * 255.0))
            markers.append({
                "x": float(m[4]),
                "y": float(m[5]),
                "marker": _short_name(symbols.get(int(op["c"]), "")),
                "alpha": round(alpha, 3),
                "red": red,
                "blue": blue,
            })
        if markers:
            patterns[short] = markers
    out = godot_dir / "assets" / "swf" / "patterns.json"
    out.write_text(json.dumps(patterns, separators=(",", ":")), encoding="utf-8")
    return patterns


def export_fonts(font_ids: set[int], args, godot_dir: Path) -> dict[int, str]:
    """Export the given DefineFont ids as TTF and return {fontId: res://path}."""
    mapping: dict[int, str] = {}
    if not font_ids:
        return mapping
    fonts_dir = godot_dir / "assets" / "swf" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rotl_font_") as tmp:
        tmp = Path(tmp)
        _run_ffdec_export(args.java, args.ffdec, "font", "font:ttf", tmp, args.swf, font_ids)
        for ttf in tmp.rglob("*.ttf"):
            head = ttf.stem.split("_", 1)[0]
            if head.isdigit() and int(head) in font_ids:
                dest = fonts_dir / ttf.name
                shutil.copyfile(ttf, dest)
                mapping[int(head)] = f"res://assets/swf/fonts/{ttf.name}"
    return mapping


def export_text_strings(text_ids: set[int], args) -> dict[int, list[str]]:
    """Per-record strings for DefineText tags (FFDec splits records)."""
    out: dict[int, list[str]] = {}
    if not text_ids:
        return out
    with tempfile.TemporaryDirectory(prefix="rotl_txt_") as tmp:
        tmp = Path(tmp)
        _run_ffdec_export(args.java, args.ffdec, "text", None, tmp, args.swf, text_ids)
        for txt in tmp.rglob("*.txt"):
            if not txt.stem.isdigit() or int(txt.stem) not in text_ids:
                continue
            raw = txt.read_text(encoding="utf-8", errors="replace")
            parts = re.split(r"\r?\n--- RECORDSEPARATOR ---\r?\n", raw)
            if len(parts) == 1:
                parts = raw.split("--- RECORDSEPARATOR ---")
            out[int(txt.stem)] = [p.rstrip("\r\n") for p in parts]
    return out


def build_texts_payload(parsed: dict, needed_texts: set[int], font_map: dict[int, str],
                        strings: dict[int, list[str]]) -> dict:
    texts: dict[str, dict] = {}
    for tid in sorted(needed_texts):
        td = parsed["text_defs"].get(tid)
        if td is None:
            continue
        if td.get("kind") == "static" and tid in strings:
            records = []
            parts = strings[tid]
            for i, rec in enumerate(td.get("records", [])):
                rec = dict(rec)
                rec["text"] = parts[i] if i < len(parts) else ""
                records.append(rec)
            td = {**td, "records": records}
        texts[str(tid)] = td
    return {
        "fonts": {str(k): v for k, v in sorted(font_map.items())},
        "texts": texts,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Export SWF sprite timelines for the Godot SwfMovieClip runtime.")
    p.add_argument("--swf", type=Path, required=True, help="source SWF")
    p.add_argument("--godot", type=Path, default=DEFAULT_GODOT, help="Godot project directory")
    p.add_argument("--ffdec", type=Path, default=DEFAULT_FFDEC, help="ffdec-cli.jar")
    p.add_argument("--java", default="java", help="java executable")
    p.add_argument("--xml", type=Path, help="cached swf2xml output (generated if missing)")
    p.add_argument("--sprites", help="comma list of ids/ranges/class names, e.g. 603,900-910,MC_Explosion2")
    p.add_argument("--named", action="store_true", help="select all sprites that have a symbol class name")
    p.add_argument("--limit", type=int, default=40, help="max number of top-level sprites to export")
    p.add_argument("--max-frames", type=int, default=200, help="skip sprites longer than this many frames")
    p.add_argument("--min-frames", type=int, default=2, help="skip sprites shorter than this many frames")
    p.add_argument("--root", help="export a slice of the main timeline, e.g. 'Menu', '6265', 'Menu..Game'")
    p.add_argument("--root-end", help="end frame/label for --root (default: next frame label - 1)")
    p.add_argument(
        "--segments",
        help="comma list of main-timeline labels to export as separate top-level segments "
             "(e.g. 'Preloading,Disclaimer,NGIntro,EngineIntro,GameIntro,Menu')",
    )
    p.add_argument("--root-name", help="display name for the root slice (default: ROOT <spec>)")
    p.add_argument(
        "--hide",
        default="NewgroundsAPIAsset,APIConnector,FlashAd,MedalPopup",
        help="comma-separated substrings of symbol class names to drop (default: Newgrounds shims)",
    )
    p.add_argument("--hide-ids", default="", help="comma-separated character ids to drop (e.g. script-hidden overlays)")
    p.add_argument("--sounds", default="", help="comma list of DefineSound ids/class names to export as MP3 (e.g. SND_Music_MenuMusic)")
    p.add_argument("--patterns", action="store_true", help="extract MC_LevelPattern_* layout markers to patterns.json")
    p.add_argument("--list-labels", action="store_true", help="list main-timeline frame labels and exit")
    p.add_argument("--list", action="store_true", help="list candidate sprites and exit")
    p.add_argument("--dry-run", action="store_true", help="parse and report dependencies, but do not export")
    return p


def ensure_xml(args) -> Path:
    xml = args.xml
    if xml is None:
        xml = Path(tempfile.gettempdir()) / "rotl_godot" / f"{args.swf.stem}.xml"
    if xml.exists():
        return xml
    xml.parent.mkdir(parents=True, exist_ok=True)
    print(f"[xml] dumping {args.swf.name} -> {xml} ...")
    cmd = [args.java, "-Xmx4g", "-jar", str(args.ffdec), "-swf2xml", str(args.swf), str(xml)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not xml.exists():
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit("swf2xml failed")
    print(f"[xml] {xml.stat().st_size / 1e6:.1f} MB")
    return xml


def inject_buttons(parsed: dict) -> None:
    """Turn each DefineButton into a pseudo-sprite: frame 0 = up, frame 1 = over/down."""
    sprites: dict[int, list] = parsed["sprites"]
    for bid, states in parsed.get("buttons_def", {}).items():
        if bid in sprites:
            continue
        up = states.get("up", []) if isinstance(states, dict) else states
        over = states.get("over", []) if isinstance(states, dict) else []
        frames: list = [up]
        if over:
            frames.append(over)
        sprites[bid] = frames


def main() -> None:
    args = build_arg_parser().parse_args()
    if not args.ffdec.exists():
        raise SystemExit(f"FFDec not found at {args.ffdec}")
    if not args.swf.exists():
        raise SystemExit(f"SWF not found at {args.swf}")

    xml = ensure_xml(args)
    print(f"[parse] reading {xml.name} ...")
    parsed = parse_swf_xml(xml)
    header = parsed["header"]
    fps = float(header.get("frameRate", "30.0") or 30.0)
    print(
        f"[parse] sprites={len(parsed['sprites'])} shapes={len(parsed['bounds'])} "
        f"images={len(parsed['images'])} morphs={len(parsed['morphs'])} "
        f"texts={len(parsed['texts'])} symbols={len(parsed['symbols'])} fps={fps}"
    )
    inject_buttons(parsed)
    if args.patterns:
        pats = export_patterns(parsed, args.godot)
        print(f"[patterns] {len(pats)} patterns -> patterns.json")
        if not (args.sprites or args.named or args.root or args.segments):
            return
    hidden_ids: set[int] = set()
    hide_patterns = [p.strip().lower() for p in (args.hide or "").split(",") if p.strip()]
    if hide_patterns:
        for cid, cname in parsed["symbols"].items():
            if any(pat in cname.lower() for pat in hide_patterns):
                hidden_ids.add(cid)
    for tok in (args.hide_ids or "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            hidden_ids.add(int(tok))
    if hidden_ids:
        print(f"[hide] {len(hidden_ids)} hidden characters")

    if args.list_labels:
        for lname, num in sorted(parsed["labels"].items(), key=lambda kv: kv[1]):
            print(f"  {num:>6}  {lname}")
        print(f"  root frames={len(parsed['sprites'].get(0, []))}")
        return

    if args.list:
        rows = []
        for cid, frames in parsed["sprites"].items():
            if args.named and cid not in parsed["symbols"]:
                continue
            if args.max_frames and len(frames) > args.max_frames:
                continue
            rows.append((cid, len(frames), _short_name(parsed["symbols"].get(cid, ""))))
        rows.sort(key=lambda r: r[1], reverse=True)
        for cid, n, name in rows[: args.limit]:
            print(f"  {cid:>6}  {n:>4} frames  {name}")
        print(f"  ({len(rows)} candidates)")
        return

    root_entry: dict | None = None
    synth_names: dict[int, str] = {}
    if args.root:
        start1, end1 = resolve_root_range(parsed, args)
        parsed["sprites"][0] = slice_timeline(parsed["sprites"].get(0, []), start1 - 1, end1 - 1)
        root_entry = {
            "id": 0,
            "name": args.root_name or f"ROOT {args.root}",
            "frameCount": len(parsed["sprites"][0]),
        }
        print(f"[root] {args.root} -> frames {start1}..{end1} ({len(parsed['sprites'][0])} frames)")

    segment_ids: list[int] = []
    segment_entries: list[dict] = []
    if args.segments:
        root_frames = parsed["sprites"].get(0, [])
        for i, name in enumerate(s.strip() for s in args.segments.split(",") if s.strip()):
            s1, e1 = resolve_segment_range(parsed, name)
            sid = 900000 + i
            parsed["sprites"][sid] = slice_timeline(root_frames, s1 - 1, e1 - 1)
            synth_names[sid] = name
            entry = {"id": sid, "name": name, "frameCount": len(parsed["sprites"][sid])}
            segment_ids.append(sid)
            segment_entries.append(entry)
            print(f"[segment] {name}: frames {s1}..{e1} -> id {sid} ({entry['frameCount']} frames)")

    if args.segments:
        selected = segment_ids + (resolve_selection(parsed, args) if (args.sprites or args.named) else [])
    else:
        if args.root and not args.sprites and not args.named:
            selected = []
        else:
            selected = resolve_selection(parsed, args)
        if root_entry is not None:
            selected = [0] + selected
    if not selected:
        raise SystemExit("no sprites selected")
    print(f"[select] {len(selected)} top-level sprites")

    needed = collect_characters(parsed, selected, hidden_ids)
    print(
        f"[deps] sprites={len(needed['sprites'])} shapes={len(needed['shapes'])} "
        f"images={len(needed['images'])} morphs={len(needed['morphs'])} "
        f"texts={len(needed['texts'])} buttons={len(needed['buttons'])}"
    )
    if args.dry_run:
        return

    godot_dir: Path = args.godot
    swf_dir = godot_dir / "assets" / "swf"
    sprites_out = swf_dir / "sprites"
    sprites_out.mkdir(parents=True, exist_ok=True)
    characters = export_leaves(parsed, needed, args, godot_dir)
    characters.update(export_morphs(needed["morphs"], parsed, args, godot_dir))

    symbols_out: dict[str, str] = {}
    index: list[dict] = []
    total_frames = 0
    for cid in sorted(needed["sprites"]):
        frames = parsed["sprites"].get(cid, [])
        name = _short_name(parsed["symbols"].get(cid, "")) or None
        if cid == 0 and root_entry is not None:
            name = root_entry["name"]
        if cid in synth_names:
            name = synth_names[cid]
        if name:
            symbols_out[str(cid)] = name
        payload = {
            "id": cid,
            "name": name,
            "fps": fps,
            "frameCount": len(frames),
            "frames": frames,
        }
        if cid in parsed["sprite_labels"]:
            payload["labels"] = parsed["sprite_labels"][cid]
        (sprites_out / f"{cid}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        total_frames += len(frames)

    for cid in selected:
        if cid == 0 and root_entry is not None:
            index.append(root_entry)
            continue
        if cid in synth_names:
            index.append({
                "id": cid,
                "name": synth_names[cid],
                "frameCount": len(parsed["sprites"].get(cid, [])),
            })
            continue
        frames = parsed["sprites"].get(cid, [])
        index.append({
            "id": cid,
            "name": _short_name(parsed["symbols"].get(cid, "")) or f"sprite_{cid}",
            "frameCount": len(frames),
        })

    chars_payload = {
        "meta": {
            "swf": args.swf.name,
            "fps": fps,
            "frameCount": int(header.get("frameCount", "0") or 0),
        },
        "symbols": symbols_out,
        "characters": {str(k): v for k, v in sorted(characters.items())},
    }
    (swf_dir / "characters.json").write_text(json.dumps(chars_payload, separators=(",", ":")), encoding="utf-8")
    (swf_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")

    font_ids: set[int] = set()
    for tid in needed["texts"]:
        font_ids.update(parsed["text_defs"].get(tid, {}).get("fonts", []))
    static_text_ids = {t for t in needed["texts"] if parsed["text_defs"].get(t, {}).get("kind") == "static"}
    strings = export_text_strings(static_text_ids, args)
    font_map = export_fonts(font_ids, args, godot_dir)
    texts_payload = build_texts_payload(parsed, needed["texts"], font_map, strings)
    (swf_dir / "texts.json").write_text(json.dumps(texts_payload, separators=(",", ":")), encoding="utf-8")
    print(f"[text] {len(texts_payload['texts'])} texts, {len(font_map)} fonts -> texts.json")

    sound_ids = resolve_sound_ids(parsed, args.sounds)
    sound_map = export_sounds(sound_ids, args, godot_dir)
    (swf_dir / "sounds.json").write_text(
        json.dumps({str(k): v for k, v in sorted(sound_map.items())}, separators=(",", ":")), encoding="utf-8"
    )
    if sound_map:
        print(f"[sound] {len(sound_map)} sounds -> sounds.json")

    print(
        f"[done] {len(needed['sprites'])} sprite timelines, {total_frames} frames, "
        f"{len(characters)} characters -> {swf_dir}"
    )


if __name__ == "__main__":
    main()
