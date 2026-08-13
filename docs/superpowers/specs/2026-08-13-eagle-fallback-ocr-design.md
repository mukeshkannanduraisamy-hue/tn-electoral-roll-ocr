# Eagle vision-model fallback for cells PaddleOCR gets wrong

## What this is not

The previous attempt at this (commits `6b3ca43`, `5cf4157`) built a page-level
"OCR engine" dropdown with a `BaseOcrEngine` interface and an `EagleOcrEngine`
that never called Eagle — its `run_ocr` had a `pass` where inference belonged
and unconditionally fell through to PaddleOCR. It was deleted, uncommitted,
sometime after, leaving `config.py`, `ocr_service.py`, `pipeline.py`,
`BulkExtractModal.tsx` and `SettingsView.tsx` with dangling edits. That
inconsistent state is what this repo carried into this session.

The page-level framing was also the wrong shape for what Eagle actually is.
NVLabs/Eagle is a vision-language model — it answers questions about an image,
it does not emit per-word bounding boxes. This pipeline's grid layout, cell
assignment, stamp-alignment and age-recovery re-reads all depend on that
geometry, which PaddleOCR provides and a VLM does not. "Eagle instead of
PaddleOCR for a page" was never a real option; there is no dropdown value that
makes sense for it.

## What this is

A **per-cell fallback**. PaddleOCR runs exactly as it does today, for every
page. When one elector's record already fails a check this pipeline runs —
bad EPIC format, an age outside 18–120, the house-number separator check, a
low-confidence field — that cell's crop is sent to Eagle, and its answer is
attached as a *suggestion*, not written over the original value.

This is the same shape as the crop-recovery re-read already in
`electoral_roll_ta.py` (a second reader consulted for one damaged cell), and
the same shape as `consensus.py`'s spelling suggestions: `FieldValue` already
has a `suggested_value` slot, and `records.py` already has an endpoint that
promotes a suggestion into `edited_value` when an operator accepts it. Eagle
needs no new "how does a suggestion get applied" — that machinery exists.

## Architecture

**Credentials.** Extend `app_settings.py`'s existing pattern rather than build
a parallel one. It already resolves `nvidia_api_key` / `nvidia_base_url` /
`nvidia_model` from Settings-page-override-then-environment, and calls
`{base_url}/chat/completions` in OpenAI format for the chat assistant. Add a
second triple — `eagle_api_key`, `eagle_base_url`, `eagle_model` — resolved the
same way, in a new `resolve_eagle_credentials(session) -> AiCredentials`
(the existing `AiCredentials` dataclass is generic enough to reuse as-is).
Shown in Settings next to the existing AI panel, not merged into it: they are
different credentials for a different call shape (multimodal content), and
conflating them would make clearing one look like it affects the other.

**What I cannot verify without a live call.** Whether NVIDIA's hosted catalog
serves an Eagle checkpoint under that name, and the exact multimodal message
shape it expects, are unknown until tested against a real key. The `model` and
`base_url` fields are operator-supplied configuration for exactly this reason
— nothing here hardcodes a specific NVIDIA model id. The first successful call
against a configured endpoint is the actual integration test; nothing before
that is a promise it works.

**Trigger.** A new module, `app/services/eagle_engine.py`, exposing one
function: given a cell's cropped image and the `Issue`s already raised against
its fields, decide whether Eagle is worth calling and for which fields. It
fires only on the issue codes that already mean "this value is suspect":
`BAD_FORMAT`, `OUT_OF_RANGE`, `LOW_CONFIDENCE`. It does not fire on missing
fields (`MISSING_REQUIRED`) — an empty field with nothing printed there is not
a misreading, and sending a blank crop to a VLM to guess at text that was
never OCR'd risks manufacturing a plausible-looking wrong answer rather than
correctly reporting nothing was there.

**Where it runs.** Alongside `_recover_stamped_age` and
`_flag_suspect_house_number` in `electoral_roll_ta.py`'s per-cell pass, after
validation has produced the record's `Issue` list and while the cell crop is
still in hand. Gated on a per-job flag (see below): when off, the check is
skipped entirely and nothing changes from today's behaviour.

**The call.** One `chat/completions` request per flagged cell (not per
flagged field — a cell rarely has more than one or two suspect fields, and one
image with a prompt naming which fields to read is cheaper than several).
Image sent as a base64 data URI in the message content, matching the standard
NIM multimodal shape. The prompt asks only for the fields flagged, in a
constrained format (e.g. `field: value` lines), because free-form prose from
a VLM is harder to attach to a specific `FieldValue` reliably than a
constrained response is.

**Applying the result.** Eagle's answer for a field is written to
`suggested_value` only if it passes the *same* validator the original value
failed — an out-of-range age suggestion that is itself out of range is
discarded, not stored. A new `IssueCode.AI_SUGGESTED` (plain Python enum
addition; `issues` is a JSON column, no migration) is attached so the review
UI can show "Eagle suggests: 45" the way it already shows spelling
consensus. The operator's existing accept/reject flow decides from there —
this design adds no new acceptance mechanism.

**Failure handling.** A failed Eagle call (network error, bad response,
unconfigured credentials) is logged and the record is left exactly as it was
without Eagle — the existing `Issue` from validation stays, nothing crashes,
extraction is never blocked on this being available. Same posture as the
existing `except Exception: pass` around crop recovery.

**Per-job control.** The old dropdown becomes a checkbox: "Try Eagle on cells
that fail validation," on the same submission surface the old per-job engine
selector lived on (`BulkExtractModal.tsx`), passed through to the job and
read by the per-cell pass. Off by default, since it makes outbound calls with
a cost and requires configured credentials.

## Testing

Unit tests for `eagle_engine.py`'s trigger logic need no network: given a
record's `Issue` list, assert which fields are selected and which are not
(confirm `MISSING_REQUIRED` is excluded, confirm a clean record triggers
nothing). The HTTP call itself is tested by monkeypatching
`urllib.request.urlopen` on the module — `test_ai_transport.py` already does
exactly this for the chat endpoint's `stream_chat`/`chat_with_tools`, down to
a `_FakeResponse` helper and a fail-if-called guard for the
no-credentials case. Same pattern here: assert the request body (image
present, correct fields named in the prompt) and that a validator-failing
suggestion is discarded rather than stored. No test calls the real NVIDIA API;
whether a real Eagle endpoint exists and answers correctly is verified by hand
against a real key, not by the suite.

## Out of scope

Full-page Eagle transcription. Replacing PaddleOCR. Local/self-hosted Eagle
inference (ruled out by the GTX 1650's 4 GB VRAM — one PaddleOCR engine
already uses 591 MB, and a 7B+-parameter VLM checkpoint would not coexist with
it, measured this session in `job_queue.py`'s worker-count work). A manual
"re-read this cell" operator-triggered button — deferred, not rejected; the
automatic fallback covers the traffic that matters and a manual trigger can be
added later without touching this design if the automatic one proves useful
but insufficient.
