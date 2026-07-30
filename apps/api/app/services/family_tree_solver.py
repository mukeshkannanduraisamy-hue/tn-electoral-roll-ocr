"""Deterministic Multi-Generational Family Tree Engine for Electoral Roll OCR Records.

Implements Senior Data Engineering & Genealogy Expert rules:
1. Group records primarily by House Number.
2. Fallback grouping: Part Number + nearby Serial Numbers (+/- 15) when House Number is missing.
3. Validate Father -> Child (minimum 18 years age difference).
4. Validate Husband <-> Wife (gender validation + reasonable age difference).
5. Validate Mother -> Child (minimum 18 years age difference).
6. Multi-generation tree construction (Grandfather -> Father -> Son -> Grandson).
7. Disjoint partitioning for unlinked residents.
8. Merging multi-generational branches sharing the same house.
9. Strict evidence enforcement (no unverified guessing).
10. Fuzzy name matching for minor OCR spelling errors (Levenshtein / Jaro-Winkler).
11. Confidence scoring (+30 Locality, +35 Name, +20 Relation, +10 Age, +5 Gender).

Rules 3-5 and 9 are enforced as *hard gates*, not as scoring nudges. An edge that
contradicts the physical evidence — a father two years older than his child, a
woman recorded as another woman's husband — is rejected outright and reported in
``rejected_links`` rather than being emitted at high confidence. Points are only
awarded for evidence that is actually present: a record with no age contributes
nothing to the age term, so it caps below "Confirmed" instead of scoring as if
the check had passed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# --- Scoring weights (100-point matrix) -------------------------------------
POINTS_LOCALITY_HOUSE = 30
#: Same building, different sub-door. Weaker than an exact door match but far
#: stronger than mere proximity in the roll.
POINTS_LOCALITY_BUILDING = 22
POINTS_LOCALITY_SERIAL_WINDOW = 15
POINTS_NAME = 35
POINTS_RELATION = 20
POINTS_AGE = 10
POINTS_GENDER = 5

# --- Genealogical constraints ----------------------------------------------
MIN_PARENT_CHILD_AGE_GAP = 18
MAX_SPOUSE_AGE_GAP = 35

#: Below this an edge is discarded as unsupported guesswork (rule 9).
MIN_EDGE_CONFIDENCE = 60

#: Relation types the roll records, all of which point from the declarant to an
#: elder. Anything else ("Other", "") gives no direction to build an edge from.
DIRECTED_RELATIONS = ("Father", "Mother", "Husband")

MALE_TOKENS = ("male", "m")
FEMALE_TOKENS = ("female", "f")


#: The roll writes the same door inconsistently — "2-332" in one entry and
#: "2/332" in the next — and marks sub-doors with a third segment or a letter
#: ("2/332-1", "2-191A"). Grouping on the raw string therefore splits real
#: families: a father recorded at "2-332" never meets the children recorded at
#: "2/332-1", even though they are the same address in the same part.
_HOUSE_SEPARATORS = re.compile(r"[\s./\\_,;]+")
#: A digit run followed by letters, e.g. "191A" or "332ஏ" — a sub-door marker.
_SUBDOOR_LETTERS = re.compile(r"^(\d+)[^\W\d_]+$", re.UNICODE)


def normalise_house(house: Optional[str]) -> str:
    """Canonical form of one house number: separators unified, case folded.

    ``"2/332-1"`` and ``"2-332-1"`` both become ``"2-332-1"``. This identifies a
    single door, so it still distinguishes a sub-door from its parent.
    """
    if not house:
        return ""
    s = str(house).strip().upper()
    s = _HOUSE_SEPARATORS.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def building_key(house: Optional[str]) -> str:
    """The dwelling a house number belongs to, ignoring its sub-door.

    ``"2-332"``, ``"2/332-1"`` and ``"2-332A"`` all resolve to ``"2-332"``.

    Grouping on this widens the candidate pool rather than asserting anything:
    the solver still needs a name and relation match to draw an edge, so
    unrelated occupants of a neighbouring sub-door simply never link. Being
    slightly over-inclusive here is the safer error — the alternative loses
    families that are plainly families.
    """
    s = normalise_house(house)
    if not s:
        return ""
    parts = s.split("-")
    if len(parts) > 2:
        parts = parts[:2]
    match = _SUBDOOR_LETTERS.match(parts[-1])
    if match:
        parts[-1] = match.group(1)
    return "-".join(parts)


def is_missing_house(house: Optional[str]) -> bool:
    """True when a record carries no usable house number."""
    return normalise_house(house) in ("", "0", "NA", "NIL")


def clean_name(text: Optional[str]) -> str:
    """Normalize Tamil/English name for OCR fuzzy matching."""
    if not text:
        return ""
    s = str(text)
    # Strip label prefixes (including multi-word Tamil labels like "கணவர் பெயர் : ")
    s = re.sub(
        r"^\s*(\d+[\.\:\)\-\s]+)?((கணவர்|கணவரின்|தந்தை|தந்தையின்|தாய்|தாயின்|குடும்ப|பாதுகாவலர்|உறவினர்|Husband|Father|Mother|Family|Guardian|Relative)[\s\.\,]+)?(பெயர்|பெயா்|பெயா|Name)[\s\:\;\=\-\.\,]+",
        "",
        s,
        flags=re.IGNORECASE,
    )
    # Strip remaining leading punctuation/numbers (preserving house number hyphens and slashes)
    s = re.sub(r"^(\s*\d+[\.\:\)\s]+\s*|[\s\-–—.,;:])+", "", s)
    # Strip trailing punctuation
    s = re.sub(r"[\s\-–—_.,;:\"'“”‘’]+$", "", s)
    # Remove extra spaces
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Calculate Jaro-Winkler similarity between two strings."""
    s1, s2 = clean_name(s1), clean_name(s2)
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    max_dist = max(len1, len2) // 2 - 1
    if max_dist < 0:
        max_dist = 0

    match1 = [False] * len1
    match2 = [False] * len2

    matches = 0
    for i in range(len1):
        start = max(0, i - max_dist)
        end = min(i + max_dist + 1, len2)
        for j in range(start, end):
            if not match2[j] and s1[i] == s2[j]:
                match1[i] = True
                match2[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    t = 0.0
    k = 0
    for i in range(len1):
        if match1[i]:
            while not match2[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 0.5
            k += 1

    jaro = (matches / len1 + matches / len2 + (matches - t) / matches) / 3.0
    p = 0.1
    l = 0
    for i in range(min(4, min(len1, len2))):
        if s1[i] == s2[i]:
            l += 1
        else:
            break

    return jaro + l * p * (1 - jaro)


def fuzzy_match_names(name1: str, name2: str, threshold: float = 0.78) -> Tuple[bool, float]:
    """Check if name1 and name2 match with fuzzy OCR tolerance."""
    c1, c2 = clean_name(name1), clean_name(name2)
    if not c1 or not c2:
        return False, 0.0

    if c1 == c2:
        return True, 1.0

    # Substring / initial prefix match (e.g. "s. raman" vs "raman")
    if len(c1) >= 3 and len(c2) >= 3:
        if c1 in c2 or c2 in c1:
            return True, 0.95

    score = jaro_winkler_similarity(c1, c2)
    return score >= threshold, score


def _is_male(gender: str) -> bool:
    return gender.strip().lower() in MALE_TOKENS


def _is_female(gender: str) -> bool:
    return gender.strip().lower() in FEMALE_TOKENS


def _gender_known(gender: str) -> bool:
    return _is_male(gender) or _is_female(gender)


class GenealogyNode:
    """Internal node representation for family tree building."""

    def __init__(self, voter: Dict[str, Any]):
        self.voter = voter
        self.id: str = str(voter.get("id", ""))
        self.name: str = str(voter.get("name", ""))
        self.clean_name: str = clean_name(self.name)
        self.relation_type: str = str(voter.get("relation_type", "")).capitalize()
        self.relation_name: str = str(voter.get("relation_name", ""))
        self.clean_rel_name: str = clean_name(self.relation_name)
        self.gender: str = str(voter.get("gender", "")).capitalize()
        self.age: Optional[int] = voter.get("age")
        self.house_number: str = str(voter.get("house_number", "")).strip()
        #: Canonical door, and the building it sits in. Compared instead of the
        #: raw string so spelling variants do not split a family.
        self.house_key: str = normalise_house(self.house_number)
        self.building_key: str = building_key(self.house_number)
        self.serial: Optional[int] = voter.get("serial")
        self.epic: str = str(voter.get("epic", ""))

        self.parents: List[GenealogyNode] = []
        self.spouse: Optional[GenealogyNode] = None
        self.children: List[GenealogyNode] = []
        self.generation_level: int = 1
        self.resolved_role: str = "Resident"
        self.edge_confidence: Dict[str, int] = {}


def validate_relationship(
    source: GenealogyNode,
    target: GenealogyNode,
    rel_type: str,
) -> Tuple[bool, str]:
    """Apply the hard genealogical gates to a candidate edge.

    ``source`` declared ``rel_type`` naming ``target`` — so for Father/Mother the
    target is the parent, and for Husband the target is the source's husband.

    Returns ``(True, "")`` when the edge is physically possible, or
    ``(False, reason)`` when the roll data contradicts itself. Unknown ages and
    genders never reject: a missing value is absence of evidence, not evidence
    of a contradiction. It simply earns no points later on.
    """
    if rel_type not in DIRECTED_RELATIONS:
        return False, "Relation type gives no direction to infer a link from"

    s_age, t_age = source.age or 0, target.age or 0

    if rel_type in ("Father", "Mother"):
        # Rules 3 & 5: a parent must be at least 18 years older than the child.
        if s_age > 0 and t_age > 0 and (t_age - s_age) < MIN_PARENT_CHILD_AGE_GAP:
            gap = t_age - s_age
            if gap <= 0:
                return False, (
                    f"{target.name or 'The named parent'} ({t_age}) is not older than "
                    f"{source.name or 'the child'} ({s_age}), so cannot be their parent"
                )
            return False, (
                f"{target.name or 'The named parent'} ({t_age}) is only {gap} "
                f"{'year' if gap == 1 else 'years'} older than "
                f"{source.name or 'the child'} ({s_age}); a parent must be at least "
                f"{MIN_PARENT_CHILD_AGE_GAP} years older"
            )
        if rel_type == "Father" and _is_female(target.gender):
            return False, f"{target.name or 'Target'} is recorded as female but named as a father"
        if rel_type == "Mother" and _is_male(target.gender):
            return False, f"{target.name or 'Target'} is recorded as male but named as a mother"

    if rel_type == "Husband":
        # Rule 4: gender validation plus a plausible age difference.
        if _is_female(target.gender):
            return False, f"{target.name or 'Target'} is recorded as female but named as a husband"
        if _is_male(source.gender):
            return False, f"{source.name or 'Source'} is recorded as male but declares a husband"
        if s_age > 0 and t_age > 0 and abs(t_age - s_age) > MAX_SPOUSE_AGE_GAP:
            return False, (
                f"Spouse age gap of {abs(t_age - s_age)} years exceeds the "
                f"{MAX_SPOUSE_AGE_GAP}-year plausibility limit"
            )

    return True, ""


def creates_cycle(child: GenealogyNode, parent: GenealogyNode) -> bool:
    """True when making ``parent`` the parent of ``child`` would close a loop.

    Fuzzy name matching on a household where several generations reuse a name
    can otherwise make someone their own ancestor, which would recurse forever
    in the tree walk.
    """
    if child.id == parent.id:
        return True
    seen: Set[str] = set()
    stack = [child]
    while stack:
        node = stack.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        if node.id == parent.id:
            return True
        stack.extend(node.children)
    return False


def calculate_relationship_confidence(
    source: GenealogyNode,
    target: GenealogyNode,
    rel_type: str,
    locality_score: int,
    name_score: float,
) -> Tuple[int, Dict[str, Any]]:
    """Score an edge that has already passed :func:`validate_relationship`.

    Because the gates reject contradictions, everything scored here is possible;
    the number expresses how much evidence *corroborates* it. Points are only
    awarded for checks that could actually run — a record with no age recorded
    scores 0 on the age term rather than being waved through, so it tops out at
    85 ("Strong") instead of reaching "Confirmed" on missing data.

    Returns the score together with the per-term evidence breakdown, so the UI
    can explain why a link scored what it did.
    """
    # 1. Locality (+30 exact house, +15 serial-window proximity)
    score = locality_score

    # 2. Relative name match (+35, scaled by similarity)
    name_points = int(round(POINTS_NAME * name_score))
    score += name_points

    # 3. Relationship type recorded (+20)
    relation_points = POINTS_RELATION if rel_type in DIRECTED_RELATIONS else 0
    score += relation_points

    # 4. Age corroboration (+10) — requires both ages to be known.
    s_age, t_age = source.age or 0, target.age or 0
    age_valid = False
    if s_age > 0 and t_age > 0:
        if rel_type in ("Father", "Mother"):
            age_valid = (t_age - s_age) >= MIN_PARENT_CHILD_AGE_GAP
        elif rel_type == "Husband":
            age_valid = abs(t_age - s_age) <= MAX_SPOUSE_AGE_GAP
    if age_valid:
        score += POINTS_AGE

    # 5. Gender corroboration (+5) — requires the genders it checks to be known.
    gender_valid = False
    if rel_type == "Father":
        gender_valid = _is_male(target.gender)
    elif rel_type == "Mother":
        gender_valid = _is_female(target.gender)
    elif rel_type == "Husband":
        gender_valid = _is_male(target.gender) and _is_female(source.gender)
    if gender_valid:
        score += POINTS_GENDER

    evidence = {
        "locality_score": locality_score,
        "name_score": round(name_score, 4),
        "name_points": name_points,
        "relation_points": relation_points,
        "age_valid": age_valid,
        "age_known": s_age > 0 and t_age > 0,
        "gender_valid": gender_valid,
        "gender_known": _gender_known(source.gender) and _gender_known(target.gender),
    }
    return min(100, max(0, score)), evidence


def get_confidence_level(score: int) -> str:
    """Map numeric score to standard confidence level label."""
    if score >= 95:
        return "Confirmed"
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Possible"
    return "Unverified"


def resolve_role(node: GenealogyNode) -> str:
    """Name a member's position from the resolved graph, not from edge order.

    Deriving the role at the end keeps it stable: a man who is both someone's
    son and someone's father used to end up labelled by whichever edge happened
    to be built last. His relation to the household is "Son", and his own
    children hang below him in the tree regardless.
    """
    if node.parents:
        if _is_female(node.gender):
            return "Daughter"
        if _is_male(node.gender):
            return "Son"
        return "Child"
    if node.children:
        if _is_female(node.gender):
            return "Mother"
        if _is_male(node.gender):
            return "Father"
        return "Parent"
    if node.spouse:
        if _is_female(node.gender):
            return "Wife"
        if _is_male(node.gender):
            return "Husband"
        return "Spouse"
    return "Resident"


def generate_ascii_tree(
    root: GenealogyNode,
    prefix: str = "",
    is_last: bool = True,
    rendered: Optional[Set[str]] = None,
) -> List[str]:
    """Recursively generate standard ASCII tree representation.

    ``rendered`` tracks who has already been printed so a spouse shown inline on
    their partner's line is not also emitted as a second root.
    """
    if rendered is None:
        rendered = set()

    lines = []
    rendered.add(root.id)

    age_str = f" ({root.age})" if root.age else ""
    gender_tag = f" [{root.gender}]" if root.gender else ""
    node_str = f"{root.name or 'Unknown'}{age_str}{gender_tag}"

    if root.spouse and root.spouse.id not in rendered:
        rendered.add(root.spouse.id)
        sp_age = f" ({root.spouse.age})" if root.spouse.age else ""
        node_str += f" 💍 {root.spouse.name or 'Spouse'}{sp_age}"

    if not prefix:
        # Root node
        lines.append(node_str)
    else:
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + node_str)

    child_prefix = prefix + ("    " if is_last else "│   ")
    children = [c for c in root.children if c.id not in rendered]
    for i, child in enumerate(children):
        child_is_last = i == len(children) - 1
        lines.extend(generate_ascii_tree(child, child_prefix, child_is_last, rendered))

    return lines


def _primary_roots(component: List[GenealogyNode]) -> List[GenealogyNode]:
    """Pick one root per family, collapsing married pairs to a single node.

    Both halves of a couple have no parents, so both look like roots. Rendering
    both duplicates the couple and every child beneath them. The partner with
    children wins; ties break on age descending, then serial ascending so the
    choice is stable across runs.

    Someone who married into the family is parentless here too — the roll records
    her husband, not her father — so her partner's position, not her own missing
    parents, decides which generation she belongs to.
    """
    roots = [
        n for n in component
        if not n.parents and not (n.spouse and n.spouse.parents)
    ]
    chosen: List[GenealogyNode] = []
    claimed: Set[str] = set()

    def rank(n: GenealogyNode) -> Tuple[int, int, int]:
        return (-len(n.children), -(n.age or 0), n.serial if n.serial is not None else 10**9)

    for node in sorted(roots, key=rank):
        if node.id in claimed:
            continue
        chosen.append(node)
        claimed.add(node.id)
        if node.spouse:
            claimed.add(node.spouse.id)

    return chosen


def _assign_generations(roots: List[GenealogyNode], component: List[GenealogyNode]) -> None:
    """Breadth-first generation numbering: roots are 1, each child one deeper."""
    for node in component:
        node.generation_level = 1

    queue: List[GenealogyNode] = []
    for root in roots:
        root.generation_level = 1
        queue.append(root)
        if root.spouse:
            root.spouse.generation_level = 1
            queue.append(root.spouse)

    seen = {n.id for n in queue}
    while queue:
        node = queue.pop(0)
        for child in node.children:
            if child.id in seen:
                continue
            seen.add(child.id)
            child.generation_level = node.generation_level + 1
            queue.append(child)
            if child.spouse and child.spouse.id not in seen:
                seen.add(child.spouse.id)
                child.spouse.generation_level = child.generation_level
                queue.append(child.spouse)


def build_family_tree_for_group(
    group_id: str,
    voters: List[Dict[str, Any]],
    locality: str = "house",
) -> List[Dict[str, Any]]:
    """Build multi-generational family trees from a group of voter records.

    ``locality`` describes how the group was formed — ``"house"`` for an exact
    house-number match, ``"serial_window"`` for the weaker fallback of adjacent
    serials in the same part — and weights the locality term accordingly.
    """
    if not voters:
        return []

    locality_score = (
        POINTS_LOCALITY_HOUSE if locality == "house" else POINTS_LOCALITY_SERIAL_WINDOW
    )

    nodes: List[GenealogyNode] = [GenealogyNode(v) for v in voters]
    nodes.sort(key=lambda n: n.age or 0, reverse=True)

    relationships_list: List[Dict[str, Any]] = []
    rejected_links: List[Dict[str, Any]] = []

    # Step 1: Resolve relationships between nodes in the group. Oldest first, so
    # that when a name is ambiguous the senior generation is linked before the
    # cycle guard starts rejecting.
    for source in nodes:
        if not source.clean_rel_name:
            continue

        best_target: Optional[GenealogyNode] = None
        best_score: float = 0.0

        for target in nodes:
            if source.id == target.id:
                continue
            matched, score = fuzzy_match_names(source.clean_rel_name, target.name)
            if matched and score > best_score:
                best_score = score
                best_target = target

        if not best_target:
            continue

        rel_type = source.relation_type

        def reject(reason: str) -> None:
            rejected_links.append({
                "source_id": source.id,
                "source_name": source.name,
                "target_id": best_target.id,
                "target_name": best_target.name,
                "relationship_type": rel_type,
                "reason": reason,
            })

        # Rules 3-5: hard gates. A contradiction is reported, never emitted.
        valid, reason = validate_relationship(source, best_target, rel_type)
        if not valid:
            reject(reason)
            continue

        if rel_type in ("Father", "Mother") and creates_cycle(source, best_target):
            reject(
                f"Linking {best_target.name or 'the named parent'} as parent would make "
                f"them their own descendant"
            )
            continue

        # Marriage is exclusive. Several electors naming the same husband — common
        # when a joint family shares a house number, or when a name is mis-read —
        # would otherwise overwrite the man's spouse pointer and leave the edge
        # asymmetric, splitting the household into overlapping families that each
        # re-listed the same people.
        if rel_type == "Husband" and (source.spouse or best_target.spouse):
            held = source if source.spouse else best_target
            partner = held.spouse
            reject(
                f"{held.name or 'That elector'} is already recorded as married to "
                f"{partner.name or 'another elector'}; a second marriage cannot be "
                f"inferred from the roll"
            )
            continue

        # Locality is scored in tiers, so a link across two spellings of the same
        # building is credited without being mistaken for a same-door match.
        if source.house_key and source.house_key == best_target.house_key:
            edge_locality = POINTS_LOCALITY_HOUSE
        elif source.building_key and source.building_key == best_target.building_key:
            edge_locality = POINTS_LOCALITY_BUILDING
        else:
            edge_locality = POINTS_LOCALITY_SERIAL_WINDOW

        conf, evidence = calculate_relationship_confidence(
            source, best_target, rel_type, edge_locality, best_score
        )

        # Rule 9: never guess a relationship the evidence cannot support.
        if conf < MIN_EDGE_CONFIDENCE:
            rejected_links.append({
                "source_id": source.id,
                "source_name": source.name,
                "target_id": best_target.id,
                "target_name": best_target.name,
                "relationship_type": rel_type,
                "reason": f"Evidence scores only {conf}/100, below the {MIN_EDGE_CONFIDENCE} threshold",
            })
            continue

        relationships_list.append({
            "source_id": source.id,
            "source_name": source.name,
            "target_id": best_target.id,
            "target_name": best_target.name,
            "relationship_type": rel_type,
            "confidence": conf,
            "confidence_level": get_confidence_level(conf),
            "evidence": evidence,
        })
        source.edge_confidence[best_target.id] = conf

        if rel_type == "Husband":
            source.spouse = best_target
            best_target.spouse = source
        else:  # Father / Mother
            source.parents.append(best_target)
            best_target.children.append(source)

    # Keep sibling order predictable: eldest child first.
    for node in nodes:
        node.children.sort(key=lambda c: (-(c.age or 0), c.serial if c.serial is not None else 10**9))

    # Step 2: Group connected components into trees
    visited: Set[str] = set()
    family_trees: List[Dict[str, Any]] = []

    family_counter = 1
    for node in nodes:
        if node.id in visited:
            continue

        # Find all reachable nodes in this connected family graph component
        component: List[GenealogyNode] = []
        queue = [node]
        comp_visited = set([node.id])

        while queue:
            curr = queue.pop(0)
            component.append(curr)
            visited.add(curr.id)

            neighbors = list(curr.parents) + list(curr.children)
            if curr.spouse:
                neighbors.append(curr.spouse)

            for nbr in neighbors:
                if nbr.id not in comp_visited:
                    comp_visited.add(nbr.id)
                    queue.append(nbr)

        roots = _primary_roots(component) or [component[0]]
        _assign_generations(roots, component)
        head_node = roots[0]

        for member in component:
            member.resolved_role = resolve_role(member)

        # Family confidence is the mean of the edges actually resolved inside
        # this component. A component with no edges has proved nothing, so it
        # scores 0 rather than defaulting to a "Confirmed" 100.
        comp_ids = {c.id for c in component}
        comp_rel_list = [
            r for r in relationships_list
            if r["source_id"] in comp_ids and r["target_id"] in comp_ids
        ]
        # Attach a rejection to the declarant's family only. Theirs is the record
        # that needs re-reading, and matching the target too would repeat the same
        # rejection in every family the failed link touches.
        comp_rejected = [r for r in rejected_links if r["source_id"] in comp_ids]

        if comp_rel_list:
            avg_conf = int(round(sum(r["confidence"] for r in comp_rel_list) / len(comp_rel_list)))
            unresolved_reason = None
        else:
            avg_conf = 0
            if comp_rejected:
                unresolved_reason = "contradicted"
            elif any(n.clean_rel_name for n in component):
                unresolved_reason = "relative_not_in_household"
            else:
                unresolved_reason = "no_relation_recorded"
        conf_level = get_confidence_level(avg_conf)

        # Format ASCII Tree. A shared `rendered` set spans all roots so nobody
        # is printed twice.
        ascii_lines: List[str] = []
        rendered: Set[str] = set()
        for r in roots:
            if r.id in rendered:
                continue
            ascii_lines.extend(generate_ascii_tree(r, rendered=rendered))
        # Anyone the walk could not reach (isolated resident) still gets a line.
        for member in component:
            if member.id not in rendered:
                rendered.add(member.id)
                age_str = f" ({member.age})" if member.age else ""
                gender_tag = f" [{member.gender}]" if member.gender else ""
                ascii_lines.append(f"{member.name or 'Unknown'}{age_str}{gender_tag}")
        ascii_tree_text = "\n".join(ascii_lines)

        # Flat member graph. A nested-only payload can silently drop anyone the
        # walk cannot reach; the flat form carries every member plus the edge
        # ids, and the UI tiers them by generation_level.
        members_payload = [
            {
                **member.voter,
                "resolved_role": member.resolved_role,
                "generation_level": member.generation_level,
                "is_head": member.id == head_node.id,
                "spouse_id": member.spouse.id if member.spouse else None,
                "parent_ids": [p.id for p in member.parents],
                "child_ids": [c.id for c in member.children],
            }
            for member in component
        ]

        # Nested hierarchy retained for the ASCII/JSON views.
        def build_node_json(n: GenealogyNode, level: int = 1, seen: Optional[Set[str]] = None) -> Dict[str, Any]:
            if seen is None:
                seen = set()
            seen.add(n.id)
            return {
                "id": n.id,
                "name": n.name,
                "epic": n.epic,
                "age": n.age,
                "gender": n.gender,
                "relation_type": n.relation_type,
                "relation_name": n.relation_name,
                "resolved_role": n.resolved_role,
                "generation_level": level,
                "spouse": {
                    "id": n.spouse.id,
                    "name": n.spouse.name,
                    "epic": n.spouse.epic,
                    "age": n.spouse.age,
                    "gender": n.spouse.gender,
                } if n.spouse else None,
                "children": [
                    build_node_json(c, level + 1, seen)
                    for c in n.children if c.id not in seen
                ],
            }

        tree_hierarchy = build_node_json(head_node, level=1)

        fam_id = f"FAM-{group_id}-{family_counter}"
        family_counter += 1

        family_trees.append({
            "family_id": fam_id,
            "family_head": head_node.name,
            "house_number": head_node.house_number or group_id,
            "locality": locality,
            "members": members_payload,
            "relationships": comp_rel_list,
            "rejected_links": comp_rejected,
            "root_ids": [r.id for r in roots],
            "generation_count": max((m.generation_level for m in component), default=1),
            "family_tree": tree_hierarchy,
            "ascii_tree": ascii_tree_text,
            "confidence": avg_conf,
            "confidence_level": conf_level,
            "unresolved_reason": unresolved_reason,
        })

    return family_trees


def resolve_family_trees(voters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group voters by House Number or fallback Part+Serial, resolving all family trees."""
    if not voters:
        return []

    # Rule 1 & 2: Primary grouping by House Number; Fallback by Part + Serial Range
    #
    # Grouped on the *building*, not the raw string. The roll spells one address
    # several ways ("2-332", "2/332", "2/332-1"), so grouping on the literal
    # value used to split a father from his own children.
    house_groups: Dict[str, List[Dict[str, Any]]] = {}
    fallback_voters: List[Dict[str, Any]] = []

    for v in voters:
        house = v.get("house_number")
        if is_missing_house(house):
            fallback_voters.append(v)
        else:
            house_groups.setdefault(building_key(house), []).append(v)

    all_family_trees: List[Dict[str, Any]] = []

    # Resolve house number groups
    for house_no, house_voters in house_groups.items():
        trees = build_family_tree_for_group(house_no, house_voters, locality="house")
        all_family_trees.extend(trees)

    # Resolve fallback voters grouped by Part + Serial window (+/- 15)
    if fallback_voters:
        fallback_voters.sort(key=lambda v: (str(v.get("part_number", "")), v.get("serial") or 0))
        current_chunk: List[Dict[str, Any]] = []
        last_serial: Optional[int] = None
        last_part: Optional[str] = None
        chunk_counter = 1

        def flush(chunk: List[Dict[str, Any]], counter: int) -> None:
            if chunk:
                all_family_trees.extend(
                    build_family_tree_for_group(
                        f"CHUNK-{counter}", chunk, locality="serial_window"
                    )
                )

        for v in fallback_voters:
            serial = v.get("serial")
            part = str(v.get("part_number", ""))
            # A new part starts a new chunk: adjacent serials only imply a shared
            # household within the same part of the roll.
            part_changed = last_part is not None and part != last_part
            serial_gap = (
                last_serial is not None
                and serial is not None
                and abs(serial - last_serial) > 15
            )
            if part_changed or serial_gap:
                flush(current_chunk, chunk_counter)
                chunk_counter += 1
                current_chunk = []
                last_serial = None

            current_chunk.append(v)
            last_part = part
            if serial is not None:
                last_serial = serial

        flush(current_chunk, chunk_counter)

    return all_family_trees
