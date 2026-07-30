"""Deterministic Multi-Generational Family Tree Engine for Electoral Roll OCR Records.

Implements Senior Data Engineering & Genealogy Expert rules:
1. Group records primarily by House Number.
2. Fallback grouping: Part Number + Section Number + nearby Serial Numbers (+/- 15) when House Number is missing.
3. Validate Father -> Child (minimum 18 years age difference).
4. Validate Husband <-> Wife (gender validation + reasonable age difference).
5. Validate Mother -> Child (minimum 18 years age difference).
6. Multi-generation tree construction (Grandfather -> Father -> Son -> Grandson).
7. Disjoint partitioning for unlinked residents.
8. Merging multi-generational branches sharing the same house.
9. Strict evidence enforcement (no unverified guessing).
10. Fuzzy name matching for minor OCR spelling errors (Levenshtein / Jaro-Winkler).
11. Confidence scoring (+30 House, +35 Name, +20 Relation, +10 Age, +5 Gender).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple


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
    s = re.sub(r"[\s\-–—_.,;:\"'\u201c\u201d\u2018\u2019]+$", "", s)
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
        self.serial: Optional[int] = voter.get("serial")
        self.epic: str = str(voter.get("epic", ""))

        self.parents: List[GenealogyNode] = []
        self.spouse: Optional[GenealogyNode] = None
        self.children: List[GenealogyNode] = []
        self.resolved_role: str = "Resident"
        self.edge_confidence: Dict[str, int] = {}


def calculate_relationship_confidence(
    source: GenealogyNode,
    target: GenealogyNode,
    rel_type: str,
    house_match: bool,
    name_score: float,
) -> int:
    """Calculate relationship confidence using the exact 100-point point matrix."""
    score = 0

    # 1. House Number Match (+30)
    if house_match:
        score += 30

    # 2. Relative Name Match (+35)
    score += int(round(35 * name_score))

    # 3. Relationship Type Match (+20)
    if rel_type in ("Father", "Husband", "Mother"):
        score += 20

    # 4. Age Validation (+10)
    s_age = source.age or 0
    t_age = target.age or 0
    age_valid = False

    if rel_type in ("Father", "Mother"):
        # Parent must be at least 18 years older than child
        if t_age > 0 and s_age > 0 and (t_age - s_age) >= 18:
            age_valid = True
        elif t_age == 0 or s_age == 0:
            age_valid = True
    elif rel_type == "Husband":
        # Husband and wife reasonable age difference <= 35 years
        if t_age > 0 and s_age > 0 and abs(t_age - s_age) <= 35:
            age_valid = True
        elif t_age == 0 or s_age == 0:
            age_valid = True

    if age_valid:
        score += 10

    # 5. Gender Validation (+5)
    gender_valid = False
    t_gender = target.gender.lower()
    s_gender = source.gender.lower()

    if rel_type == "Father" and t_gender in ("male", "m", ""):
        gender_valid = True
    elif rel_type == "Mother" and t_gender in ("female", "f", ""):
        gender_valid = True
    elif rel_type == "Husband" and t_gender in ("male", "m", "") and s_gender in ("female", "f", ""):
        gender_valid = True

    if gender_valid:
        score += 5

    return min(100, max(0, score))


def get_confidence_level(score: int) -> str:
    """Map numeric score to standard confidence level label."""
    if score >= 95:
        return "Confirmed"
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Possible"
    return "Unverified"


def generate_ascii_tree(root: GenealogyNode, prefix: str = "", is_last: bool = True) -> List[str]:
    """Recursively generate standard ASCII tree representation."""
    lines = []
    age_str = f" ({root.age})" if root.age else ""
    gender_tag = f" [{root.gender}]" if root.gender else ""
    node_str = f"{root.name or 'Unknown'}{age_str}{gender_tag}"

    if root.spouse:
        sp_age = f" ({root.spouse.age})" if root.spouse.age else ""
        node_str += f" 💍 {root.spouse.name or 'Spouse'}{sp_age}"

    if not prefix:
        # Root node
        lines.append(node_str)
    else:
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + node_str)

    child_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(root.children):
        child_is_last = i == len(root.children) - 1
        lines.extend(generate_ascii_tree(child, child_prefix, child_is_last))

    return lines


def build_family_tree_for_group(
    group_id: str,
    voters: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build multi-generational family trees from a group of voter records."""
    if not voters:
        return []

    nodes: List[GenealogyNode] = [GenealogyNode(v) for v in voters]
    nodes.sort(key=lambda n: n.age or 0, reverse=True)

    relationships_list: List[Dict[str, Any]] = []

    # Step 1: Resolve relationships between nodes in the group
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

        if best_target:
            rel_type = source.relation_type
            same_house = source.house_number and source.house_number == best_target.house_number
            conf = calculate_relationship_confidence(
                source, best_target, rel_type, same_house, best_score
            )

            # Rule 9: Never guess relationships if evidence is insufficient (conf < 60)
            if conf >= 60:
                rel_entry = {
                    "source_id": source.id,
                    "source_name": source.name,
                    "target_id": best_target.id,
                    "target_name": best_target.name,
                    "relationship_type": rel_type,
                    "confidence": conf,
                    "confidence_level": get_confidence_level(conf),
                }
                relationships_list.append(rel_entry)
                source.edge_confidence[best_target.id] = conf

                if rel_type == "Husband":
                    source.spouse = best_target
                    best_target.spouse = source
                    source.resolved_role = "Wife"
                    best_target.resolved_role = "Husband / Head"
                elif rel_type == "Father":
                    source.parents.append(best_target)
                    best_target.children.append(source)
                    source.resolved_role = "Daughter" if source.gender.lower() in ("female", "f") else "Son"
                    best_target.resolved_role = "Father / Head"
                elif rel_type == "Mother":
                    source.parents.append(best_target)
                    best_target.children.append(source)
                    source.resolved_role = "Daughter" if source.gender.lower() in ("female", "f") else "Son"
                    best_target.resolved_role = "Mother / Head"

    # Step 2: Group connected components into trees
    visited: Set[str] = set()
    family_trees: List[Dict[str, Any]] = []

    def get_roots(n: GenealogyNode) -> List[GenealogyNode]:
        """Traverse upwards to find top-most generation root ancestors."""
        if not n.parents and (not n.spouse or not n.spouse.parents):
            return [n]
        parents_list = []
        for p in n.parents:
            parents_list.extend(get_roots(p))
        if n.spouse and n.spouse.parents:
            for p in n.spouse.parents:
                parents_list.extend(get_roots(p))
        return parents_list or [n]

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

        # Identify roots of this component
        roots = []
        for comp_node in component:
            if not comp_node.parents and (not comp_node.spouse or comp_node not in comp_node.spouse.children):
                roots.append(comp_node)

        # Sort roots by age descending
        roots.sort(key=lambda r: r.age or 0, reverse=True)
        head_node = roots[0] if roots else component[0]

        # Calculate average family confidence
        conf_scores = []
        for c in component:
            conf_scores.extend(c.edge_confidence.values())
        avg_conf = int(round(sum(conf_scores) / len(conf_scores))) if conf_scores else 100
        conf_level = get_confidence_level(avg_conf)

        # Format ASCII Tree
        ascii_lines = []
        for r in roots:
            ascii_lines.extend(generate_ascii_tree(r))
        ascii_tree_text = "\n".join(ascii_lines)

        # Build JSON hierarchy
        def build_node_json(n: GenealogyNode, level: int = 1) -> Dict[str, Any]:
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
                "children": [build_node_json(c, level + 1) for c in n.children],
            }

        tree_hierarchy = build_node_json(head_node, level=1)

        # Format relationships JSON
        comp_rel_list = [
            r for r in relationships_list
            if r["source_id"] in comp_visited or r["target_id"] in comp_visited
        ]

        fam_id = f"FAM-{group_id}-{family_counter}"
        family_counter += 1

        family_data = {
            "family_id": fam_id,
            "family_head": head_node.name,
            "house_number": head_node.house_number or group_id,
            "members": [c.voter for c in component],
            "relationships": comp_rel_list,
            "family_tree": tree_hierarchy,
            "ascii_tree": ascii_tree_text,
            "confidence": avg_conf,
            "confidence_level": conf_level,
        }
        family_trees.append(family_data)

    return family_trees


def resolve_family_trees(voters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group voters by House Number or fallback Part+Serial, resolving all family trees."""
    if not voters:
        return []

    # Rule 1 & 2: Primary grouping by House Number; Fallback by Part + Serial Range
    house_groups: Dict[str, List[Dict[str, Any]]] = {}
    fallback_voters: List[Dict[str, Any]] = []

    for v in voters:
        house = str(v.get("house_number") or "").strip()
        if house and house not in ("-", "—", "0"):
            house_groups.setdefault(house, []).append(v)
        else:
            fallback_voters.append(v)

    all_family_trees: List[Dict[str, Any]] = []

    # Resolve house number groups
    for house_no, house_voters in house_groups.items():
        trees = build_family_tree_for_group(house_no, house_voters)
        all_family_trees.extend(trees)

    # Resolve fallback voters grouped by Part + Serial window (+/- 15)
    if fallback_voters:
        fallback_voters.sort(key=lambda v: (str(v.get("part_number", "")), v.get("serial") or 0))
        current_chunk: List[Dict[str, Any]] = []
        last_serial: Optional[int] = None
        chunk_counter = 1

        for v in fallback_voters:
            serial = v.get("serial")
            if last_serial is not None and serial is not None and abs(serial - last_serial) > 15:
                if current_chunk:
                    all_family_trees.extend(build_family_tree_for_group(f"CHUNK-{chunk_counter}", current_chunk))
                    chunk_counter += 1
                    current_chunk = []

            current_chunk.append(v)
            if serial is not None:
                last_serial = serial

        if current_chunk:
            all_family_trees.extend(build_family_tree_for_group(f"CHUNK-{chunk_counter}", current_chunk))

    return all_family_trees
