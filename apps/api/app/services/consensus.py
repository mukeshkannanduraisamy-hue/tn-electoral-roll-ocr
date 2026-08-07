"""Cross-corpus spelling consensus for OCR'd proper nouns.

The problem
-----------
PaddleOCR's Tamil model systematically under-reads the *long* vowel signs as
their short counterparts -- ே as ெ, ோ as ொ. Measured on page 10_10 of the
sample corpus, 60 name fields contained ெ twelve times against ே four
times, which is backwards for Tamil names (ராஜேந்திரன், சேகர், கோவிந்தராஜ்
are all long).

These errors are invisible to confidence filtering: the misread fields still
score ~0.98, because the model is confident, just wrong.

The insight
-----------
Names repeat across an electoral roll -- a father's name recurs on every one
of his children's records, a village shares surnames. So the same name is
usually read *correctly* more often than incorrectly:

    இராகவன்  x5   vs   இரொகவன்  x1
    இராஜேந்திரன் x1  vs   இராஜெந்திரன் x2

Grouping readings by their vowel-sign-stripped skeleton and taking the
majority recovers the true spelling with no dictionary and no extra OCR.
Accuracy improves as more pages are processed.

Safety
------
Consensus never touches ``original_value`` -- the raw OCR reading is
immutable. It writes ``suggested_value`` and attaches a ``SPELLING_VARIANT``
issue so every change is visible and reversible. Auto-application to
``edited_value`` is controlled by ``consensus_auto_apply`` and only happens
when the majority is decisive.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field

from ..config import settings
from ..schemas.core import Issue, IssueCode, IssueSeverity, Page, Record

logger = logging.getLogger(__name__)

# Tamil dependent vowel signs + the AU length mark. Deliberately excludes the
# pulli (U+0BCD): it marks a bare consonant and is structural, not a vowel
# quality, so stripping it would merge genuinely different names.
_TAMIL_VOWEL_SIGNS = re.compile(r"[ா-ௌௗ]")


def skeleton(value: str) -> str:
    """Vowel-sign-stripped form used to group readings of the same name."""
    return _TAMIL_VOWEL_SIGNS.sub("", value or "").strip()


@dataclass
class Variant:
    value: str
    count: int = 0
    confidence_sum: float = 0.0

    @property
    def mean_confidence(self) -> float:
        return self.confidence_sum / self.count if self.count else 0.0


_SHORT_VOWELS = frozenset("ெொ")
_LONG_VOWELS = frozenset("ேோாீூ")


def _is_short_to_long_correction(candidate: str, competitor: str) -> bool:
    """True if candidate replaces short vowel signs (ெ, ொ) with long counterparts (ே, ோ, ா, ீ, ூ)."""
    has_short_in_competitor = any(c in competitor for c in _SHORT_VOWELS)
    has_long_in_candidate = any(c in candidate for c in _LONG_VOWELS)
    return has_short_in_competitor and has_long_in_candidate


def _variant_score(v: Variant) -> tuple[float, int, float]:
    """Score a variant considering count, confidence, and long vowel signs.

    PaddleOCR's Tamil model systematically under-reads long vowel signs (ே, ோ),
    emitting short counterparts (ெ, ொ). Weighting long-vowel occurrences corrects
    this systematic model bias.
    """
    long_count = sum(1 for ch in v.value if ch in _LONG_VOWELS)
    weighted_count = v.count * (1.0 + 0.25 * long_count)
    return (weighted_count, v.count, v.confidence_sum)


@dataclass
class ConsensusGroup:
    skeleton: str
    variants: dict[str, Variant] = dc_field(default_factory=dict)

    def add(self, value: str, confidence: float) -> None:
        variant = self.variants.setdefault(value, Variant(value=value))
        variant.count += 1
        variant.confidence_sum += confidence

    @property
    def total(self) -> int:
        return sum(v.count for v in self.variants.values())

    def ranked(self) -> list[Variant]:
        """Most likely spelling first: weighted count, count, then summed confidence."""
        return sorted(
            self.variants.values(),
            key=_variant_score,
            reverse=True,
        )

    def winner(self) -> Variant | None:
        """The majority spelling, or None when the vote is inconclusive."""
        ranked = self.ranked()
        if len(ranked) < 2:
            return None
        best, runner_up = ranked[0], ranked[1]
        if self.total < settings.consensus_min_group:
            return None

        is_vowel_repair = _is_short_to_long_correction(best.value, runner_up.value)
        if best.count <= runner_up.count and not is_vowel_repair:
            return None

        min_ratio = 0.8 if is_vowel_repair else settings.consensus_min_ratio
        if best.count < runner_up.count * min_ratio:
            return None
        return best


@dataclass
class ConsensusReport:
    groups_examined: int = 0
    groups_with_conflict: int = 0
    suggestions: int = 0
    auto_applied: int = 0
    details: list[str] = dc_field(default_factory=list)


def build_groups(
    records: list[Record], field_keys: list[str]
) -> dict[str, ConsensusGroup]:
    """Bucket every reading of `field_keys` by its skeleton."""
    groups: dict[str, ConsensusGroup] = {}
    for record in records:
        for key in field_keys:
            field = record.fields.get(key)
            if field is None:
                continue
            value = field.value.strip()
            if not value or len(value) < settings.consensus_min_length:
                continue
            skel = skeleton(value)
            if not skel:
                continue
            group = groups.setdefault(skel, ConsensusGroup(skeleton=skel))
            group.add(value, field.confidence)
    return groups


def apply_consensus(
    pages: list[Page],
    field_keys: list[str] | None = None,
    auto_apply: bool | None = None,
) -> ConsensusReport:
    """Harmonise spellings across every record in `pages`.

    Mutates fields in place. Returns a report for logging / UI display.
    """
    report = ConsensusReport()
    if not settings.consensus_enabled:
        return report

    auto_apply = settings.consensus_auto_apply if auto_apply is None else auto_apply

    records = [r for page in pages for r in page.records]
    if not records:
        return report

    # Default to whatever the template declares as free-text proper nouns.
    if field_keys is None:
        field_keys = _default_field_keys(pages)
    if not field_keys:
        return report

    groups = build_groups(records, field_keys)
    report.groups_examined = len(groups)

    # Resolve each group once, then apply.
    winners: dict[str, str] = {}
    for skel, group in groups.items():
        if len(group.variants) < 2:
            continue
        report.groups_with_conflict += 1
        winner = group.winner()
        if winner is None:
            ranked = group.ranked()
            report.details.append(
                f"unresolved: {' vs '.join(f'{v.value} x{v.count}' for v in ranked)}"
            )
            continue
        winners[skel] = winner.value
        ranked = group.ranked()
        report.details.append(
            f"{winner.value} <- {', '.join(f'{v.value} x{v.count}' for v in ranked[1:])}"
        )

    if not winners:
        return report

    for record in records:
        for key in field_keys:
            field = record.fields.get(key)
            if field is None:
                continue
            value = field.value.strip()
            if not value:
                continue
            consensus = winners.get(skeleton(value))
            if not consensus or consensus == value:
                continue

            field.suggested_value = consensus
            report.suggestions += 1

            if auto_apply:
                field.edited_value = consensus
                report.auto_applied += 1
                message = (
                    f"Spelling harmonised to '{consensus}' "
                    f"(OCR read '{field.original_value}'); "
                    f"the majority reading across this batch"
                )
            else:
                message = (
                    f"Majority spelling across this batch is '{consensus}' "
                    f"(OCR read '{value}')"
                )

            field.issues.append(
                Issue(
                    code=IssueCode.SPELLING_VARIANT,
                    severity=IssueSeverity.WARNING,
                    message=message,
                    field=key,
                )
            )

    logger.info(
        "Consensus: %d groups, %d conflicts, %d suggestions, %d applied",
        report.groups_examined,
        report.groups_with_conflict,
        report.suggestions,
        report.auto_applied,
    )
    return report


def _default_field_keys(pages: list[Page]) -> list[str]:
    """Ask the page's template which columns hold proper nouns."""
    from ..templates import registry

    keys: list[str] = []
    seen: set[str] = set()
    for page in pages:
        template = registry.get_or_generic(page.template_id)
        getter = getattr(template, "consensus_fields", None)
        if getter is None:
            continue
        for key in getter():
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys
