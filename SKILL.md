---
name: glyphboost
description: Pre-flight readability check for images before sending them to vision LLM APIs. Use when attaching screenshots, UI captures, diagrams, or any image containing text to a vision model message. Detects small text that will become unreadable after API-side downscaling, and generates boosted crops (cut from original resolution, selectively magnified) to attach alongside the original image. 100% local CPU, no API calls, works with Claude / GPT / Gemini / any vision model.
---

# glyphboost — pre-flight readability check for vision API images

Vision APIs (Claude ~1568px, GPT-4o ~2048px long edge) silently downscale
attached images. Small text that looks fine on screen often becomes
unreadable to the model, causing misreads like "崩坏"→"拆怀", "27页"→"2节".
glyphboost predicts which text will survive and which will not, BEFORE
the image is sent — and cuts boosted crops from the original resolution
so the model can actually read the small parts.

## When to use

- You are about to attach a screenshot / diagram / table image with text
  to a vision model message, AND the answer depends on reading that text.
- A user complains the model misread text in an image.
- NOT needed for photos without text, or when the answer does not depend
  on small text.

## Setup (first use)

```bash
bash <skill_dir>/scripts/install.sh          # macOS / Linux
<skill_dir>\scripts\install.cmd              # Windows (double-click ok)
# if the default index is blocked/slow: --mirror mirrors.aliyun.com/pypi/simple/
```

Creates a local venv `<skill_dir>/.venv` with rapidocr + onnxruntime
(~90 MB, CPU only, no GPU required).

## Run

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/glyphboost.py IMAGE.png
# Windows: <skill_dir>\.venv\Scripts\python.exe <skill_dir>\scripts\glyphboost.py IMAGE.png
```

Options: `--target 2048` (GPT-4o), `--quiet` (one line), `--json`
(machine-readable), `--no-crops` (diagnosis only).

### Exit codes

| code | meaning | your action |
|---|---|---|
| 0 | CLEAN | attach the image as-is, no boost needed |
| 2 | BOOST_RECOMMENDED | attach original + relevant crops (below) |
| 1 | ERROR | bad input; tell the user |

## How to use the output

Outputs land in `IMAGE_probe/` next to the input:

- `report.json` — verdict, per-region levels (safe/risky/lost),
  worst regions, and `boost_crops[]` with the text each crop contains.
- `annotated.png` — green/yellow/red boxes for human inspection.
- `crop_XX.png` — boosted crops for lost/risky regions.

**Recommended flow**: attach the ORIGINAL image, plus ONLY the crops whose
`contains` fields overlap the user's question. Sending every crop is not
free (~500-800 tokens each) — be selective. If the user asks about a
number in a table, send the crop containing that table, not all nine.

## Costs & limits (honest)

- Boost crops add tokens; they trade cost for accuracy on small text.
- Upscaling cannot recover text that is blurry in the original image —
  crops are cut from the original resolution, so this works best when
  the source is sharp (native screenshots are ideal).
- Detection is OCR-based; heavily stylized text may be missed.
- "Model-agnostic" means: no access to the target model's weights or
  internal states. It does not mean zero extra tokens.
