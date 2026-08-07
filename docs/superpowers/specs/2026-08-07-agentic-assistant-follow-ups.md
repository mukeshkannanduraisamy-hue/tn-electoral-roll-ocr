# Agentic assistant — known limits and follow-ups

Recorded at the end of the `feat/agentic-db-chatbot` build. Every item here was
found by review, deliberately not fixed, and judged not to block merge. None is
a correctness bug in the shipped guarantees; they are limits worth knowing.

## What the guards actually guarantee

The assistant's core promise is that **the model never produces a number** —
figures are rebuilt from tool results and a sentence quoting anything else is
dropped whole. Three things that promise does *not* cover:

**Direction is unchecked.** The guard verifies a magnitude came from a tool, not
that the claim built around it is true. A tool returning `difference: -20`
(twenty *fewer* electors than the roll declared) cannot stop the model writing
"20 more than declared". Documented in `guards.py`.

**Percentage-phrased figures are weakly guarded.** Confidence scores are stored
as 0–1 floats and spoken as percentages, so the guard permits ×100 renderings
where a `%` follows the digits. On a turn carrying many confidence rows that
covers 89 of the 101 integers 0–100, so a fabricated "85%" can survive. Bare
counts are much tighter (42 of 101). Narrowing further needs a design change —
most cleanly, having the tools emit percentages directly so no ×100 machinery is
needed.

**The roll-profile seed is wider than the prompt.** `permitted_from_profile`
seeds from the whole profile dict, but `profile_sentence` only renders the first
10 parts and 5 constituencies. On a large corpus ~84% of the seeded numbers were
never shown to the model. Not a fabrication vector — every value is a real DB
count — but the seed should mirror the same truncation.

## Data-quality tools

- `implausible_age`, `missing_field` and `low_confidence_records` cap results
  with `.limit()` and disclose no `scanned`/`truncated` flag. This is the same
  defect that *was* fixed in `epic_format`; the inconsistency is more damaging
  than the gap. **Fix this first.**
- `count_mismatch` runs a `COUNT(*)` per polling station, and that table grows
  one row per ingested file. `page_details` does the same per page, bounded at
  50. Fine at 3,473 electors; revisit at scale.

## Routing

Any "how many \<app noun\>" question — "how many files can I upload at once" —
routes to `data` rather than `howto`, so it takes the slow agent path and likely
comes back vague. Deliberate: the router prefers a slow correct answer to a fast
wrong one. Tell operators if they start asking about upload or field limits.

## Frontend

There is no test runner in `apps/web` and no frontend tests exist. Tasks 13–15
shipped with `tsc --noEmit` as their only automated gate. Everything verified
about the SSE parser, the citation chips and the panel came from source reading
plus extracting `parseFrames` into Node.

`apps/web/tsconfig.json` maps `@ocr/shared-types` to
`apps/web/src/types/shared-types.ts`, **not** to `packages/shared-types`. Both
copies exist and are currently identical. They will drift unless edited together
or the alias is repointed.

## Smaller items

- `context.invalidate()` has no callers. The 60-second TTL is the only staleness
  bound on the roll profile; whichever component owns ingestion should call it.
- Thread list orders by `updated_at`, but appending a message never touches the
  thread row, so a revisited thread does not bubble up.
- `chat_threads.created_at` declares `index=True` with no migration creating the
  index.
- `_parameters_schema` pops `$defs` unconditionally. No current tool produces
  one; a nested argument model would emit a dangling `$ref` and the provider
  would reject the whole tool array.
- `household_of` fetches the voter twice.
- `aggregate` returns neither `returned` nor `total`, so its trace line shows no
  count while every other tool's does.

## Unrelated, and worth doing

`app_settings.py` contains a hardcoded live NVIDIA API key as
`DEFAULT_NVIDIA_API_KEY`, committed in `1756cae`. The SQL guard stops the
assistant reading the key *from the database*, but that does nothing about the
copy in git history on a public repo. Rotate it and read the fallback from the
environment.
