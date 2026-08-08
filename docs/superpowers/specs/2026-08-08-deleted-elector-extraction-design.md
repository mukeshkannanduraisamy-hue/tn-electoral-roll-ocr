# Deleted electors — detecting the DELETED stamp and recovering what it covers

A Special Intensive Revision roll strikes electors off by stamping their card
with a large diagonal `DELETED` watermark and prefixing the serial with a reason
code (`S` shifted, `E` expired, `R` repeated, `M` missing, `Q` disqualified,
`W` withdrawn). The columns to record that already exist and every consumer
downstream already reads them, so no storage, export or API work is needed. Two
things are: nothing ever sets the flag, and the stamp silently corrupts three
fields on its way past.

Measurements below come from
`PDF/Penn PDF/2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-16-WI (1).pdf`
page 4 (serials 1–30), rendered at 200–300 dpi.

## What is already built

`VoterRow.is_deleted` and `VoterRow.deletion_reason` exist (`app/db.py:273`),
the reason-code map is written (`app/templates/electoral_roll_ta.py:425`), the
query API filters on the flag (`app/routers/voters.py:127`), promote carries it
across (`app/routers/voters.py:1009`), the exporter has a `Deleted` column
(`app/services/voter_export.py:43`), and the table view has column definitions
(`app/templates/electoral_roll_ta.py:186`). "Give me the deleted voter list" is
already one API call once the flag is populated.

So nothing downstream needs building. This spec is entirely about making the
flag true when it should be, and about the data the stamp damages.

## What is broken

**The flag has never once been set.** Across all 632 records in
`data/ocr.sqlite`, `is_deleted` is the empty string with confidence `0.0` while
`serial` beside it reads `0.9998`.

**"Not deleted" and "never evaluated" are stored identically.**
`electoral_roll_ta.py:561` writes the field only when the answer is `"Yes"`, so
an active elector and an unexamined one are both `""`. Under a rule that accepts
either signal, auditing a disagreement requires knowing a signal was evaluated
at all.

**The watermark check reads only what OCR returned.** The check at
`electoral_roll_ta.py:386-393` scans recognised lines for the literal string
`DELETED`. The stamp is rotated 55–68°, and while PaddleOCR does return
fragments of it — serial 13 yields a spurious `C` at `0.945`, most likely the
outline of the `D` — it never returns anything matching `DELETED`. This branch
has almost certainly never fired. Those fragments are a second problem: they
enter the cell's line list as high-confidence text and can be mistaken for a
field value.

**The reason-code regex captures one letter.** `[SERMQWsermqw]?` at
`electoral_roll_ta.py:419` and `:436` cannot match the `S2` on serial 25.

**`is_deletions_page` marks a whole page.** Page 4 of TAM-16 is *mixed* — 15 of
30 cards stamped — so a page-level flag would strike off every active elector
sharing the page.

## The two signals and how they relate

Every stamped card also carries a reason-code prefix, and every unstamped card
carries none. Checked by eye at 200 dpi on the 15 cards of serials 13–27:
stamped and prefixed are 13, 14, 15, 16, 18, 20, 21, 22, 25, 27; clean and
unprefixed are 17, 19, 23, 24, 26. Two independent signals agreeing is what
makes cross-validation possible, and it is the reason the design records which
signal fired rather than collapsing both into one boolean.

The signals are *not* equally easy to read. The prefix is horizontal black text
in its own box, but it is the **lowest-confidence line on the card** — `0.710`,
`0.832`, `0.837` on serials 20, 13, 14, where every other line on those cards
exceeds `0.90`. A naive confidence gate at 0.85 would discard the deletion
signal while keeping everything else.

## What the stamp destroys

The stamp's diagonal crosses the lower-left of each card, which is where age,
house number and relation name sit. Same page, stamped against clean:

| serial | | age line as OCR read it | truth |
|---|---|---|---|
| 13 | stamped | `வயது : 5ஆபீலினம் : ஆண்` | 59 |
| 14 | stamped | `வயது : 4ூபிலினம் : பெண்` | 44 |
| 20 | stamped | `வயது : 3யீலினம் : ஆண்` | 30 |
| 17 | clean | `வயது : 22 பாலினம் : பெண்` | 22 |
| 19 | clean | `வயது : 53 பாலினம் : ஆண்` | 53 |
| 23 | clean | `வயது : 38 பாலினம் : ஆண்` | 38 |

Age was destroyed on 3 of 3 stamped cards and correct on 3 of 3 clean ones.
House number lost its hyphen — `2-2` read as `22`, `2-24` as `224`. Relation
name garbled — `காளியப்பன்` as `கூளியீப்பன்`, `ராஜேந்திரன்` as `ரநஜந்திரன்`.
Gender survived, because it sits at the right end of the line past the stamp.

This is the likely origin of the implausible ages that commit `812ad57` had to
coerce to unknown.

**The corruption is high-confidence, so it is silent.** Those three broken age
lines returned `0.936`, `0.962` and `0.944`. Confidence cannot be the trigger
for recovery, because by that measure nothing is wrong.

## Design

### 1. Detect the stamp geometrically

A new module, `app/services/stamp_detector.py`, exposing one function that takes
a cell image and returns the stamp components it found.

The stamp's glyphs are rendered as **hollow outline text** whose strokes are
nearly as dark as the printed text, so no intensity threshold separates them —
the raw histogram inside a stamped card is smooth, not bimodal. What does
separate them is shape. A stamp glyph is at least 20% of cell height, fills less
than 34% of its own bounding box (hollow), and is not an axis-aligned rectangle
(which excludes the card border and the photo box, the two large hollow
components every card has). Surviving components sit at 55–68°.

Scored **15/15 on the labelled set** (serials 13–27: 10 stamped, 5 clean), plus
**2 further true positives** on TAM-15 page 4 — cards this flagged that had been
assumed clean and proved on inspection to be genuinely stamped. **17 verified
classifications, zero false positives.** Cost is **40 ms per page** — 1.3 ms per
cell, about 132 s across all 3328 rendered pages, negligible against OCR. It
uses only `cv2.connectedComponentsWithStats` and `cv2.minAreaRect`; no new
dependency, no model, deterministic.

The module must not know about electoral rolls. It takes an image, returns
geometry. The template layer decides what that means.

Returning geometry rather than a boolean also solves the spurious-fragment
problem. An OCR line whose box falls inside a detected stamp component is stamp
ink, not a field value, and can be dropped before parsing — which is why the
function returns boxes and not just a count.

### 2. Validate fields by pattern, never by confidence

The age/gender line gets a strict pattern check: `வயது` then 1–3 digits, then
`பாலினம்` then a known gender word. All three corrupted lines above fail it;
all three clean lines pass. House number gets a similar check for the shape
these rolls actually use (digits, optional `-` or `/`, optional letter suffix).

This is the part that matters most, because it is the only thing that detects
the silent corruption. It is also useful independently of deletions — a pattern
failure on an unstamped card means something else went wrong.

### 3. Recover only what failed

When a cell is stamped **and** a field fails its pattern check, subtract the
stamp components from the cell image and re-OCR that crop. The re-OCR pass
already exists at `electoral_roll_ta.py:313-331`; it has been unreachable
because it is gated on `is_deleted == "Yes"`. Fixing detection switches it on,
but re-OCR of unchanged pixels changes nothing, so removal must happen first.

**This is the part expected to need iteration.** Where the stamp touches a glyph
the two merge into a single connected component, so removing the stamp risks
taking the glyph with it. Detection tolerates this because `DELETED` has seven
letters and the untouched ones are enough; removal does not get that luxury.
Recovery rate will be measured against a labelled set before any number is
claimed, and a field that cannot be recovered must be marked unreadable rather
than left holding a plausible wrong value — a silently wrong age is worse than a
missing one.

### 4. Fix the four defects

Write `is_deleted` explicitly as `"Yes"` or `"No"` so an evaluated-active card
is distinguishable from an unexamined one. Extend the reason code to accept a
trailing digit for `S2`. Confine `is_deletions_page` so it cannot override
per-cell evidence on a mixed page. Record which signals fired in
`deletion_reason` provenance so disagreements are auditable.

## Testing

The labelled set is serials 13–27 of TAM-16 page 4, with per-card truth for both
signals and for the age, house number and relation name values. That is the
regression fixture: detection must stay 15/15 on it, and the pattern validator
must fail exactly the ten stamped cards and pass the five clean ones. The two
confirmed TAM-15 cards belong in the fixture too, which makes 17 classifications
under test.

**There is no verified clean roll.** TAM-15 was assumed to be a negative control
and is not — page 4 carries stamps on serials 20 and 26, found by this detector
after being missed by eye. Every one of the 31 rolls in `PDF/Penn PDF/` should be
treated as unlabelled until checked. Building a real negative-control set means
labelling a sample by hand, and it matters more than usual here: under a rule
where either signal is sufficient, a false positive strikes a living elector off
the roll.

Cross-validation gives cheap coverage at scale without hand-labelling. The stamp
detector and the prefix reader are independent, so running both across a corpus
and collecting disagreements surfaces failures of either. Agreement is not proof
both are right, but every disagreement is a genuine defect in one of them.

`score_ground_truth.py` and `build_ground_truth_sheet.py` already exist and
should carry these fields rather than growing a parallel harness.

## Open questions

**What `S2` means.** Serial 25 reads `S2` where every other stamped card reads a
single letter. Whether that is a two-character reason code, a sub-code, or
something unrelated to deletion needs an answer from whoever produces these
rolls. Until then it is treated as deleted with reason recorded verbatim and not
mapped to a meaning.

## Out of scope

The `pages.image_data` blob loading defect, tracked separately. Photo extraction
from stamped cards. Any change to promote, export or the query API, all of which
already handle the flag.
