# OCR Workspace — Tamil Nadu Electoral Roll

Extract, review and export structured voter records from scanned SIR / EROLLGEN
electoral-roll PDFs, using PaddleOCR with a document-template layer.

Ships with two templates: `electoral_roll_ta` (30 voter records per page in a
3×10 grid) and a `generic` fallback that emits one row per text line, so the
app still works on arbitrary PDFs.

---

## What to expect from the OCR

Worth reading before you judge the output.

**Structure extraction is reliable.** On the sample corpus the grid detector
finds all 30 record cells geometrically, and serial numbers, EPIC IDs, house
numbers, ages and genders come through essentially clean — 30/30 records with
zero validation errors on a typical page.

**Tamil name recognition is approximate.** PP-OCRv5's Tamil recognition model
was trained on roughly 2,100 text images. It systematically under-reads the
long vowel marks — `ே` as `ெ`, `ோ` as `ொ` — which affects roughly 8 of 60 name
fields per page. Those errors carry *high* confidence (~0.98), so confidence
filtering will not surface them.

Two mitigations are built in:

- **Vowel-sign repair** fixes provably-invalid sequences (two dependent vowel
  signs in a row cannot occur in Tamil).
- **Cross-corpus consensus** groups readings of the same name across a batch
  and adopts the majority spelling. `இராகவன் ×5` beats `இரொகவன் ×1`. It is
  deliberately conservative: the winner must outnumber the runner-up 3:1, or
  the conflict is flagged for a human instead of guessed at. A bare majority
  is not enough — in the sample corpus a *wrong* spelling led a correct one
  2:1 on a single page.

The app is therefore built around fast human correction, not the pretence that
OCR alone is sufficient.

---

## Quick start (local)

Requires **Node 20+**. Python 3.11 is installed for you if missing.

```bash
git clone https://github.com/mukeshkannanduraisamy-hue/tn-electoral-roll-ocr.git OCR && cd OCR
```

```bash
pwsh -File scripts/bootstrap.ps1
```

Then run both services:

```bash
npm run dev
```

- Frontend → <http://localhost:3000>
- API docs → <http://localhost:8000/docs>

<details>
<summary>Manual setup, if you prefer</summary>

```bash
python -m venv apps/api/.venv
apps/api/.venv/Scripts/pip install -r apps/api/requirements.txt
apps/api/.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

```bash
npm ci && npm run build --workspace @ocr-workspace/web && npm run start --workspace @ocr-workspace/web
```

</details>

### Docker

```bash
docker compose up --build
```

Give the Docker engine at least 3 GB — on Docker Desktop that is the VM's
allocation under *Settings → Resources*, not merely free host RAM. See
[Memory](#memory-the-thing-that-decides-your-plan).

The compose file pins `platform: linux/amd64` because PaddlePaddle ships
manylinux x86_64 wheels only; on Apple Silicon the build runs under emulation
and is slow but works.

> The compose stack is reviewed and statically validated, but has not been
> executed end-to-end. The native setup above is the tested path.

---

## CLI

Useful for batch runs and for checking extraction quality without the UI.

```bash
apps/api/.venv/Scripts/python apps/api/cli.py extract "PDF/.../10_10.pdf" --overlay debug.png
```

```bash
apps/api/.venv/Scripts/python apps/api/cli.py batch "PDF" --limit 20 --out results.json
```

`--overlay` writes the page image with detected cells and OCR boxes drawn on
it, which is the fastest way to diagnose a layout problem. `batch` applies
spelling consensus across the whole run and prints what it changed.

---

## Architecture

```
apps/
  api/                  FastAPI + PaddleOCR
    app/
      services/         pdf · preprocess · layout · ocr · pipeline · consensus · export · job_queue
      templates/        base · registry · electoral_roll_ta · generic · text_utils
      routers/          files · pages · records · jobs · export · templates
      db.py             SQLite (JSON payloads + denormalised query columns)
    cli.py
  web/                  Next.js 15 · TanStack Table · Zustand · Tailwind
packages/shared-types/  the wire contract, mirrored in TypeScript
```

### The pipeline

```
PDF ─PyMuPDF─> page image ─preprocess─> deskew · denoise · 3× upscale · CLAHE · unsharp
                                                  │
                        ┌─────────────────────────┴──────────────────┐
                        ▼                                            ▼
             OpenCV cell detection                            PaddleOCR.predict()
             (morphological rule extraction;                  → lines[] {text, score, poly}
              rebuilds a full grid from a
              partial detection; falls back
              to a proportional 3×10 grid)
                        └──────────────────┬─────────────────────────┘
                                           ▼
                              assign lines → cells by centroid
                                           ▼
                          template.parse() → validate() → review queue
```

Three details that matter:

- **Pages are rendered at their native resolution** when the PDF is a single
  full-page scan. Rasterising at an arbitrary 300 DPI and then upscaling
  resamples twice and visibly smears small glyphs.
- **One coordinate space.** Deskew defines the "display" space; the page image
  written to disk, the detected cells and the OCR boxes all live in it, so
  overlays line up.
- **Validation drives review**, not confidence. EPIC format, age range, gender
  enum, serial sequence and duplicate detection catch errors that high
  confidence hides.

---

## Configuration

Copy `.env.example` to `.env`. Every backend variable takes the **`OCR_`
prefix** — a bare `DATA_DIR` is silently ignored.

| Variable | Default | Notes |
|---|---|---|
| `OCR_DATA_DIR` | `./data` | SQLite, uploads, rendered pages |
| `OCR_OCR_LANG` | `ta` | PaddleOCR language code |
| `OCR_OCR_VERSION` | `PP-OCRv5` | the version with a published Tamil model |
| `OCR_OCR_DEVICE` | `cpu` | or `gpu:0` |
| `OCR_OCR_WORKERS` | `1` | `0` = in-process thread, ~half the memory |
| `OCR_OCR_DET_MODEL` | `PP-OCRv5_mobile_det` | lightweight detector paired with `ta_PP-OCRv5_mobile_rec` |
| `OCR_UPSCALE_FACTOR` | `1.5` | source scans are ~144 DPI; 1.5x balances accuracy and speed |
| `OCR_CONSENSUS_MIN_RATIO` | `3.0` | how decisive a spelling vote must be |
| `OCR_ALLOW_FOLDER_IMPORT` | `true` | **set `false` in production** |
| `OCR_CORS_ORIGINS` | `*` | bare hostnames get a scheme applied |

### GPU

This is the single biggest lever in the project, by an order of magnitude.
Eight voter pages, same corpus, same output (240 records either way):

| Device | 1 worker | 2 workers | 3 workers |
|---|---|---|---|
| CPU | 16.60 s/page | 14.97 s/page | 14.74 s/page |
| GTX 1650 | 2.33 s/page | 2.01 s/page | 1.98 s/page |

**7x from the card; 11–18% from the worker count.** Tuning threads, upscale or
preprocessing is rearranging the 13% while the 87% sits in which device ran the
inference.

```bash
pip uninstall -y paddlepaddle
pip install paddlepaddle-gpu==3.1.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
```

You do **not** then have to set anything: `OCR_AUTO_GPU` is on by default, so a
usable card is detected and preferred over the `cpu` default. Set
`OCR_OCR_DEVICE=gpu:0` only to force it, or `OCR_AUTO_GPU=false` to force CPU on
a machine that has a card. Needs a CUDA 12.6-capable driver.

To confirm which device is actually in use — the config default reads `cpu`
even when auto-detection has chosen the GPU, which is misleading:

```bash
cd apps/api && .venv/Scripts/python -c "from app.services import ocr_service; print(ocr_service.resolve_device())"
```

---

## Memory: the thing that decides your plan

PaddleOCR keeps its weights resident. Measured on this corpus:

| Configuration | Resident |
|---|---|
| API idle, models not yet loaded | ~200 MB |
| API after first OCR (`OCR_OCR_WORKERS=0`) | **~1.1 GB** |
| Each additional worker *process* | **+~0.9 GB** |
| Model cache on disk | 92 MB |
| Installed Python dependencies | ~900 MB |

So `OCR_OCR_WORKERS=0` is not a downgrade — it is what makes the service fit
in 2 GB. It runs jobs on a thread inside the API process, reusing the models
already loaded there. PaddleOCR spends most of its time in native code that
releases the GIL, so a single thread is not much slower than a single process;
you lose page-level parallelism, not throughput per page (~20–25 s/page on
CPU either way).

---

## Deploying to Render

### Choosing a plan

| Service | Plan | Why |
|---|---|---|
| `ocr-api` | **Standard (2 GB)** — minimum | Free and Starter cap at 512 MB. The service will deploy, pass its health check, and then be OOM-killed the first time you process a page. |
| `ocr-api` | **Pro (4 GB)** — if processing volume matters | Headroom for `OCR_OCR_WORKERS=1–2` and the `server_det` detector. |
| `ocr-web` | **Starter (512 MB)** | An ordinary Next.js server; Free also works but cold-starts. |
| Disk | **10 GB on `ocr-api`** | Required. Without it every deploy loses all extracted data and re-downloads the models. |

Do not put the API on Free to "try it out" — the failure mode is a healthy-looking
service that dies on first use, which is more confusing than a failed deploy.

### Steps

1. **Push to GitHub.** `data/` and `PDF/` are gitignored; confirm no PII is
   staged before the first push:
   ```bash
   git status --porcelain
   ```
2. **Render Dashboard → New → Blueprint**, connect the repo. Render reads
   `render.yaml` and proposes both services plus the disk.
3. **Confirm the plans** in the preview — override there if you want Pro.
4. **Apply.** First build takes ~10 minutes (paddlepaddle is a large wheel).
5. **Wait for the first OCR run to be slow.** Models download to the disk on
   first use (~92 MB); subsequent restarts reuse them.
6. **Verify:**
   ```bash
   curl https://ocr-api-XXXX.onrender.com/api/health
   ```
   Then open the frontend URL, upload a PDF, and press **Run OCR**.

Everything else — `BACKEND_URL`, `OCR_CORS_ORIGINS`, the data directory, the
model cache path — is wired by the blueprint via `fromService`, so there are no
hostnames to paste by hand.

### Database

The blueprint uses **SQLite on the persistent disk**, which is the right call
here: the service also writes page images to that same disk, and the job queue
runs in-process, so it is single-instance by construction. Postgres would add
an operational dependency without removing that constraint.

Switch only if you need multiple instances — and note that would also require
moving the job queue out of the process (Redis/RQ or Render Background
Workers). `OCR_DATABASE_URL` is already honoured by SQLAlchemy:

```
OCR_DATABASE_URL=postgresql+psycopg://user:pass@host/db
```
(add `psycopg[binary]` to `requirements.txt`).

### Deployment checklist

- [ ] `git status` clean — no `data/`, no PDFs, no `.env`
- [ ] API on Standard or larger, **not** Free/Starter
- [ ] 10 GB disk attached at `/var/data`
- [ ] `OCR_DATA_DIR=/var/data` (with the `OCR_` prefix)
- [ ] `PADDLE_PDX_CACHE_HOME=/var/data/.paddlex`
- [ ] `OCR_ALLOW_FOLDER_IMPORT=false`
- [ ] `OCR_OCR_WORKERS=0` on a 2 GB instance
- [ ] `/api/health` returns 200
- [ ] Upload → Run OCR → records appear
- [ ] Export downloads a non-empty `.xlsx`
- [ ] Restart the service; confirm data survives and no file is stuck "processing"

---

## Operational notes

**Interrupted jobs self-heal.** A job only lives as long as the process
running it, so a deploy or restart mid-run would otherwise leave files stuck
on "processing" forever. On boot the API marks orphaned jobs failed and
returns their files to "pending". Expect to see this in the logs after every
deploy:

```
Startup reconciliation: 7 interrupted job(s) failed, 90 file(s) reset
```

**Re-processing replaces, never duplicates.** Page identity is derived from
(file, page number), and `save_page` enforces one row per physical page.

**Deleting a file never deletes your source PDF.** Folder-imported PDFs are
referenced in place; only files copied into the uploads directory are removed
from disk.

---

## Testing

```bash
apps/api/.venv/Scripts/python -m pytest apps/api/tests
```

65 tests, ~2 s — they use captured OCR strings rather than invoking PaddleOCR,
so they are CI-safe. Coverage is concentrated where the bugs actually were:
Tamil label segmentation, vowel-sign repair, cell parsing, spelling consensus,
re-processing idempotency, and the delete-safety guard.

```bash
npm run typecheck --workspace @ocr-workspace/web
npm run build --workspace @ocr-workspace/web
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| API dies on first OCR, no error | OOM. You are on Free/Starter — see [plans](#choosing-a-plan). |
| Everything stuck on "processing" | Restart mid-job; fixed automatically on next boot. |
| Data gone after deploy | No persistent disk, or `DATA_DIR` set without the `OCR_` prefix. |
| Models re-download every restart | `PADDLE_PDX_CACHE_HOME` not pointing at the disk. |
| CORS errors in the browser | `OCR_CORS_ORIGINS` must be the frontend origin; bare hostnames are fine. |
| Tamil renders as boxes in Excel | Open the `.xlsx`, not the `.csv`; or import the CSV as UTF-8. |
| `npm run build` fails on `@ocr/shared-types` | Install from the repo root — it is an npm workspace. |
| Compose: container killed as soon as OCR starts | Docker engine has under ~1.5 GB. Raise the Desktop VM allocation. |
| Compose: `mem_limit` seems ignored | You are on legacy `docker-compose` (v1). Use `docker compose` (v2). |
| Compose on Apple Silicon: pip fails on paddlepaddle | Missing `--platform=linux/amd64` on a standalone `docker build`. |
