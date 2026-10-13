# glyphboost

**Pre-flight readability check for images sent to vision LLM APIs.**
Runs before you attach a screenshot to Claude / GPT / Gemini — detects the
small text that will become unreadable after API-side downscaling, and cuts
boosted crops from the original resolution so the model can actually read it.

> Vision APIs silently downscale images (Claude: 1568px long edge, GPT-4o:
> 2048px). A 2560px screenshot gets crushed to 0.61x — 15px UI text becomes
> 9px, and the model reads "崩坏" as "拆怀", "27页" as "2节". glyphboost
> predicts this before you hit send.

| Model saw (downscaled) | Reality (boosted crop) |
|---|---|
| 帮我**修**一下**拆怀** | 帮我**找**一下**崩坏** |
| PDF第**2节**例题 | PDF第**27页**例题 |
| 信号采样与**叠加**仿真 | 信号采样与**混叠**仿真 |

## Features

- Detects all text regions locally (RapidOCR, CPU only, ~10s for a 2560px screenshot)
- Simulates the API-side downscale and grades every text region:
  `safe` / `risky` / `lost`
- Generates boosted crops for lost/risky regions — cut from ORIGINAL
  resolution, upscaled just enough to be readable, capped so the API won't
  downscale them again
- Outputs: `report.json` (machine-readable), `annotated.png`
  (green/yellow/red boxes), `crop_XX.png` (boosts)
- Works with any vision model — 100% local, zero API calls, no GPU needed

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/hhaosknn632486ppk-netizen/glyphboost
cd glyphboost

bash scripts/install.sh        # macOS / Linux
scripts\install.cmd            # Windows
# blocked index? --mirror mirrors.aliyun.com/pypi/simple/
```

Creates a local `.venv` (~90 MB) with RapidOCR + onnxruntime.

## Use

```bash
.venv/bin/python scripts/glyphboost.py screenshot.png
# Windows: .venv\Scripts\python.exe scripts\glyphboost.py screenshot.png
```

Output lands in `screenshot_probe/` next to your image:

```
regions=106 safe=0 risky=23 lost=83
downscale x0.613 (long edge 2560 -> 1568)
verdict: BOOST_RECOMMENDED (83 lost, 23 risky -> 9 crops)
crops: crop_00.png, crop_01.png, ...
```

| file | what |
|---|---|
| `report.json` | verdict + per-region levels + crop contents |
| `annotated.png` | green = safe, yellow = risky, red = lost |
| `crop_XX.png` | boosted crops — attach alongside the original image |

Exit codes: `0` CLEAN (send as-is) · `2` BOOST_RECOMMENDED · `1` error.

### Options

| flag | default | meaning |
|---|---|---|
| `--target` | 1568 | API long-edge limit (Claude 1568, GPT-4o 2048) |
| `--lo` / `--hi` | 16 / 28 | lost/risky/safe thresholds in px (after downscale) |
| `--quiet` | | one-line verdict |
| `--json` | | print report.json to stdout |
| `--no-crops` | | diagnosis only, fastest |

**Tip**: don't attach every crop — check `boost_crops[].contains` in
report.json and send only the crops that overlap your question.

## Use as a harness skill (Claude Code / OpenClaw / OpenCode / dsh)

The repo root is a standard [Agent Skills](https://agentskills.io) package:

```bash
git clone https://github.com/hhaosknn632486ppk-netizen/glyphboost ~/.claude/skills/glyphboost
```

Same directory works for OpenClaw skills, OpenCode, and dsh plugins.
After that, just attach images in conversation — the agent runs the
pre-flight automatically. See `SKILL.md` for agent-facing instructions.

## How it works

1. Detect all text regions (RapidOCR det+rec, onnxruntime, CPU).
2. Simulate the API-side downscale (long edge → `--target`).
3. Grade each region by effective glyph height after downscale.
4. Cluster lost/risky regions, cut each cluster from the ORIGINAL
   resolution, upscale into the safe band (capped at the API long edge).

## License

MIT
