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

**The corruption is high-confidence.** Those three broken age lines returned
`0.936`, `0.962` and `0.944`, against `0.710`-`0.837` for the deletion signal
itself. Confidence cannot be the trigger for anything here: it would drop the
signal and keep the damage.

How silent the damage is differs by field, and an earlier draft of this document
overstated it. A lost age digit leaves a single digit under `MIN_AGE`, so the
existing range check does reject it -- the elector loses their age rather than
holding a wrong one. The house number and relation name are the genuinely silent
cases: `2-2` read as `22` is a valid house number, and `கூளியீப்பன்` is
valid-looking Tamil. Nothing existing flags either.

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

The age/gender line is intact when its digits are delimited before the gender
label; damage shows as a digit run butted straight against Tamil script. All
three corrupted lines above fail that; all three clean lines pass.

The house number check is the one that earns its keep, because it is the only
thing that sees the silent corruption. `2-2` read as `22` is a valid house
number, indistinguishable from a real `22` by inspection, so it is **not
corrected** — it is reported as *not verifiable* and raises a warning against the
field for a human to check. That only happens where a stamp actually crossed the
cell; on an unstamped card a bare number is simply a house number.

Note what this deliberately does not do. It never rewrites a value it cannot
confirm, and it does not use confidence, which on these cards points the wrong
way.

### 3. Recover by agreement across re-reads

**Subtracting the stamp was tried first and abandoned.** It recovered one age of
three, against three of three for what replaced it, and on two cards it left the
reading worse than doing nothing. The cause is the one predicted above: where a
stroke touches a glyph the two are one component, and removing the stroke takes
glyph with it. That module was deleted rather than kept.

What works needs no removal. Re-reading a narrower crop of the same cell recovers
the digit — the stamp ink is still there, but the recognizer segments the line
correctly:

    full cell     வயது : 5ஆபீலினம் : ஆண்     ->  5
    0.55 crop     வயது : 59ஆபிலினம் : ஆண்    -> 59

**No crop width is chosen, because the behaviour is not monotonic.** Across seven
fractions on three cards, 0.45 and 0.55 recovered every age while 0.50, 0.60 and
0.65 recovered none. That is the recognizer's internal resizing, not a property
of the card, so a fixed fraction would be fitted to three samples and would not
survive a change of DPI or model build.

So several fractions are read, readings that cannot be an age are discarded, and
a value is accepted only when the survivors agree. The ordering matters: the
damaged reading is the *majority* on these cards (`5` appears five times against
two for `59`), so plausibility has to filter before agreement is counted. Reading
stops as soon as two agree, costing 2-3 OCR passes and about 150 ms per damaged
cell.

Agreement is not proof — two variants could agree on a wrong-but-plausible age
and nothing here would catch it. What it rules out is trusting a single lucky
read. A field that cannot be recovered is left unreadable, and the damaged
remnant is cleared either way, because a silently wrong age is worse than a
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

**The rolls stay out of the repo.** `PDF/` is gitignored and the cards carry live
elector names, EPIC numbers and ages, so no fixture copies them in. Tests needing
real pages skip when the PDF is absent; the always-run tests use synthetic cards
that reproduce the geometry — a border, a photo box, and large thin-stroked
rotated text — which is enough to pin the shape logic but not to prove it right.
Both kinds are needed, and the synthetic ones must never be mistaken for
validation.

One defect this work exposed: `test_ocr_thread_safety.py` seeded the engine cache
with a stub and reset it only on entry, so the stub outlived the test. Nothing
noticed until a test did real OCR after it and silently read nothing. It now
resets on exit.

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
