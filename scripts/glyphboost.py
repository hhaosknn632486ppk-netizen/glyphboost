"""glyphboost: pre-flight readability check for images sent to vision LLM APIs.

Run BEFORE attaching a screenshot/diagram to a vision model message.
100% local (RapidOCR, CPU only), model-agnostic, zero API calls.

Pipeline:
  1. Detect all text regions (RapidOCR det+rec, local CPU).
  2. Simulate the API-side downscale (long edge -> --target, default 1568px,
     typical for Claude/GPT vision inputs).
  3. Estimate effective glyph height AFTER downscale; classify each region:
       safe    (>= --hi px, default 28)  -> model will read it fine
       risky   (between --lo and --hi)   -> may misread
       lost    (< --lo px, default 16)   -> model will likely misread
  4. Outputs (written to <image>_probe/ or --out-dir):
       report.json   - machine-readable diagnosis (always)
       annotated.png - visualization: green/yellow/red boxes (default on)
       crop_XX.png   - boost crops for lost+risky regions, cut from the
                       ORIGINAL resolution, upscaled just enough that glyphs
                       land in the safe band (default on; --no-crops to skip)

Exit codes (stable contract for agent callers):
  0  CLEAN             no lost/risky regions, send the image as-is
  2  BOOST_RECOMMENDED lost/risky regions found, crops were written
  1  ERROR             bad input or runtime failure

Usage:
  python glyphboost.py screenshot.png
  python glyphboost.py screenshot.png --json            # stdout = report.json only
  python glyphboost.py screenshot.png --quiet           # one-line verdict
  python glyphboost.py screenshot.png --target 2048     # GPT-4o style limit
  python glyphboost.py screenshot.png --no-crops        # diagnosis only, fastest

Token note: sending all crops is NOT free. Recommended agent flow is
"send the original image + only the crops covering regions the user's
question actually touches" (see report.json -> boost_crops[].contains).
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PROG = "glyphboost"

# exit codes
EXIT_CLEAN, EXIT_BOOST, EXIT_ERROR = 0, 2, 1


def cluster_regions(boxes, y_grow=35, x_grow=60):
    """Merge nearby boxes via morphological connected components.

    Paint bad boxes onto a mask, dilate (x_grow horizontal, y_grow vertical),
    then each connected component becomes one crop cluster. The dilation
    kernel bounds chain-spread, preventing whole-screen mega-clusters.
    Returns list of merged rects [x0,y0,x1,y1] in original coords.
    """
    H = int(boxes[:, 1].max()) + 80
    W = int(boxes[:, 0].max()) + 80
    mask = np.zeros((H, W), np.uint8)
    for b in boxes:
        x0, y0, x1, y1 = [int(v) for v in
                          (b[:, 0].min(), b[:, 1].min(), b[:, 0].max(), b[:, 1].max())]
        cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)
    kernel = np.ones((y_grow * 2 + 1, x_grow * 2 + 1), np.uint8)
    dil = cv2.dilate(mask, kernel)
    num, labels = cv2.connectedComponents(dil, connectivity=8)
    rects = []
    for lb in range(1, num):
        ys, xs = np.where(labels == lb)
        if len(xs) == 0:
            continue
        rects.append([float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())])
    return rects


def run(image, target=1568, lo=16.0, hi=28.0, out_dir=None,
        want_crops=True, want_annotated=True):
    """Core routine. Returns (exit_code, report_dict)."""
    img_path = Path(image)
    if not img_path.exists():
        print(f"{PROG}: file not found: {img_path}", file=sys.stderr)
        return EXIT_ERROR, None
    out_dir = Path(out_dir) if out_dir else img_path.parent / (img_path.stem + "_probe")

    img = cv2.imdecode(np.fromfile(str(img_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print(f"{PROG}: cannot decode image: {img_path}", file=sys.stderr)
        return EXIT_ERROR, None
    H, W = img.shape[:2]
    long_edge = max(H, W)
    scale = min(1.0, target / long_edge)  # API-side downscale factor

    from rapidocr import RapidOCR
    engine = RapidOCR()
    result = engine(str(img_path))
    if result.boxes is None or result.txts is None or len(result.txts) == 0:
        report = dict(source=str(img_path), width=W, height=H,
                      api_target_long_edge=target,
                      total_text_regions=0, safe=0, risky=0, lost=0,
                      boost_crops=[], verdict="CLEAN",
                      note="no text detected; nothing to check")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return EXIT_CLEAN, report

    boxes = np.array(result.boxes)
    regions = []
    for b, t, s in zip(boxes, result.txts, result.scores):
        x0, y0 = b[:, 0].min(), b[:, 1].min()
        x1, y1 = b[:, 0].max(), b[:, 1].max()
        box_h = y1 - y0
        glyph_h = box_h * 0.72   # box includes ascender/descender padding
        eff_h = glyph_h * scale  # effective height after API downscale
        if eff_h >= hi:
            lvl = "safe"
        elif eff_h >= lo:
            lvl = "risky"
        else:
            lvl = "lost"
        regions.append(dict(text=str(t), score=float(s),
                            box=[float(x0), float(y0), float(x1), float(y1)],
                            box_h=float(box_h), eff_h=round(float(eff_h), 1),
                            level=lvl))

    n_lost = sum(r["level"] == "lost" for r in regions)
    n_risky = sum(r["level"] == "risky" for r in regions)

    # ---- annotated visualization ----
    if want_annotated:
        vis = img.copy()
        colors = {"safe": (60, 200, 60), "risky": (30, 180, 255), "lost": (50, 50, 255)}
        for r in regions:
            x0, y0, x1, y1 = [int(v) for v in r["box"]]
            cv2.rectangle(vis, (x0, y0), (x1, y1), colors[r["level"]], 2)
        out_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / "annotated.png"), vis)

    # ---- boost crops for lost+risky ----
    crops = []
    if want_crops and (n_lost + n_risky) > 0:
        out_dir.mkdir(parents=True, exist_ok=True)
        bad_idx = [i for i, r in enumerate(regions) if r["level"] != "safe"]
        bad_boxes = boxes[bad_idx]
        rects = cluster_regions(bad_boxes)
        for ci, crect in enumerate(rects):
            x0, y0, x1, y1 = crect
            pad = 24
            x0 = max(0, int(x0 - pad)); y0 = max(0, int(y0 - pad))
            x1 = min(W, int(x1 + pad)); y1 = min(H, int(y1 + pad))
            crop = img[y0:y1, x0:x1]
            ch, cw = y1 - y0, x1 - x0
            inner = [i for i, b in zip(bad_idx, bad_boxes)
                     if b[:, 0].min() >= x0 - 1 and b[:, 0].max() <= x1 + 1
                     and b[:, 1].min() >= y0 - 1 and b[:, 1].max() <= y1 + 1]
            worst_eff = min(regions[i]["eff_h"] for i in inner) if inner else lo
            need = max(1.0, hi / max(worst_eff, 1e-6))
            # cap: never let the upscaled crop exceed the API long edge,
            # otherwise the API re-downscales it and the boost is wasted
            crop_long = max(cw, ch)
            need = min(need, 4.0, max(1.0, target / crop_long))
            if need > 1.05:
                crop = cv2.resize(crop, None, fx=need, fy=need,
                                  interpolation=cv2.INTER_LANCZOS4)
            fname = f"crop_{ci:02d}.png"
            cv2.imwrite(str(out_dir / fname), crop)
            member_texts = [regions[i]["text"] for i in inner]
            crops.append(dict(file=fname, crop_box=[x0, y0, x1, y1],
                              upscale=round(need, 2), contains=member_texts))

    verdict = ("CLEAN" if n_lost + n_risky == 0 else
               f"BOOST_RECOMMENDED ({n_lost} lost, {n_risky} risky -> {len(crops)} crops)")
    report = dict(
        source=str(img_path), width=W, height=H,
        api_target_long_edge=target, downscale_factor=round(scale, 4),
        total_text_regions=len(regions),
        safe=len(regions) - n_lost - n_risky, risky=n_risky, lost=n_lost,
        worst_regions=sorted(regions, key=lambda r: r["eff_h"])[:10],
        boost_crops=crops,
        verdict=verdict,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    code = EXIT_CLEAN if n_lost + n_risky == 0 else EXIT_BOOST
    return code, report


def main():
    ap = argparse.ArgumentParser(prog=PROG, description=__doc__.splitlines()[0])
    ap.add_argument("image", help="path to the image (png/jpg/bmp/webp)")
    ap.add_argument("--target", type=int, default=1568,
                    help="long-edge px the API will downscale to "
                         "(Claude ~1568, GPT-4o ~2048) [default 1568]")
    ap.add_argument("--lo", type=float, default=16,
                    help="below this px glyph height after downscale = lost [default 16]")
    ap.add_argument("--hi", type=float, default=28,
                    help="above this px glyph height after downscale = safe [default 28]")
    ap.add_argument("--out-dir", default=None, help="output dir [default <image>_probe]")
    ap.add_argument("--json", action="store_true",
                    help="print report.json to stdout only (for agent parsing)")
    ap.add_argument("--quiet", action="store_true", help="print one-line verdict only")
    ap.add_argument("--no-crops", action="store_true",
                    help="diagnosis only, skip boost crop generation")
    ap.add_argument("--no-annotated", action="store_true",
                    help="skip annotated.png generation")
    args = ap.parse_args()

    code, report = run(args.image, target=args.target, lo=args.lo, hi=args.hi,
                       out_dir=args.out_dir, want_crops=not args.no_crops,
                       want_annotated=not args.no_annotated)
    if report is None:
        sys.exit(EXIT_ERROR)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.quiet:
        print(report["verdict"])
    else:
        print(f"regions={report['total_text_regions']} "
              f"safe={report['safe']} risky={report['risky']} lost={report['lost']}")
        print(f"downscale x{report['downscale_factor']:.3f} "
              f"(long edge {max(report['width'], report['height'])} -> {args.target})")
        print(f"verdict: {report['verdict']}")
        if report["boost_crops"]:
            print(f"crops: {', '.join(c['file'] for c in report['boost_crops'])}")
        print(f"output: {args.out_dir or Path(args.image).parent / (Path(args.image).stem + '_probe')}")
    sys.exit(code)


if __name__ == "__main__":
    main()
