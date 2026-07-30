"use client";

/**
 * The household graph for one voter, as resolved by the server.
 *
 * Nothing here infers relationships. The roll's Tamil relation labels, the
 * fuzzy name matching and the genealogical constraints all live in
 * app/services/family_tree_solver.py; this file lays the resulting graph out
 * and makes the *evidence* legible, because the reviewer's job is to decide
 * whether to trust each inferred link. Hence the two ideas the design leans on:
 *
 *   1. Every link is drawn in its confidence colour, and a contradicted one is
 *      drawn broken. Data quality is readable from the linework alone.
 *   2. Selecting a link opens its scoring ledger, so the percentage is a
 *      receipt you can audit rather than a number to take on faith.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  ChevronDown,
  ChevronRight,
  Copy,
  Crown,
  Home,
  Loader2,
  RefreshCw,
  Ruler,
  Scale,
  Users,
  X,
} from "lucide-react";
import type {
  ConfidenceLevel,
  FamilyMember,
  FamilyRelationship,
  FamilyTree,
  FamilyTreeResponse,
  UnresolvedReason,
} from "@ocr/shared-types";
import { toast } from "sonner";

// --- Layout geometry --------------------------------------------------------
// Fixed card metrics let the SVG links and the HTML cards be positioned from
// one shared set of coordinates, so nothing has to be measured in the DOM.
const NODE_W = 184;
const NODE_H = 78;
const H_GAP = 26;
const V_GAP = 84;
const SPOUSE_GAP = 26;
const PAD = 20;

type Unit = {
  key: string;
  primary: FamilyMember;
  spouse: FamilyMember | null;
  children: Unit[];
  /** Left edge of the primary card. */
  x: number;
  y: number;
  /** Width of this unit's whole subtree. */
  width: number;
};

const unitOwnWidth = (u: Unit) => (u.spouse ? NODE_W * 2 + SPOUSE_GAP : NODE_W);

/** Where links to children leave a unit: between the couple, or below one card. */
const descentX = (u: Unit) =>
  u.spouse ? u.x + NODE_W + SPOUSE_GAP / 2 : u.x + NODE_W / 2;

/**
 * Group members into couples and hang each couple's children beneath them.
 * A `placed` set means a person appears exactly once even though a spouse is
 * reachable from both halves of the pair.
 */
function buildUnits(
  family: FamilyTree,
  collapsed: Set<string>,
): { roots: Unit[]; units: Unit[] } {
  const byId = new Map(family.members.map((m) => [m.id, m]));
  const placed = new Set<string>();
  const units: Unit[] = [];

  // Everyone the graph can reach from its declared roots, ignoring collapse.
  // This distinguishes a member deliberately hidden inside a collapsed branch
  // from one the graph genuinely cannot reach — without it, collapsing a branch
  // would send its children to the orphan net below and re-draw them as roots.
  const reachable = new Set<string>();
  const walk = (ids: readonly string[]) => {
    for (const id of ids) {
      if (reachable.has(id) || !byId.has(id)) continue;
      reachable.add(id);
      const m = byId.get(id)!;
      if (m.spouse_id) walk([m.spouse_id]);
      walk(m.child_ids);
    }
  };
  walk(family.root_ids);

  function makeUnit(member: FamilyMember): Unit {
    placed.add(member.id);

    const partner = member.spouse_id ? byId.get(member.spouse_id) : undefined;
    const spouse = partner && !placed.has(partner.id) ? partner : null;
    if (spouse) placed.add(spouse.id);

    const unit: Unit = {
      key: member.id,
      primary: member,
      spouse: spouse ?? null,
      children: [],
      x: 0,
      y: 0,
      width: 0,
    };
    units.push(unit);

    if (!collapsed.has(member.id)) {
      const childIds = [...member.child_ids, ...(spouse?.child_ids ?? [])];
      for (const id of childIds) {
        const child = byId.get(id);
        if (child && !placed.has(child.id)) unit.children.push(makeUnit(child));
      }
    }
    return unit;
  }

  // Sequential, not `.filter().map()`: filter would run to completion before
  // the first makeUnit call, so its `placed` check would always see an empty
  // set and a spouse already drawn on their partner's card would be drawn again.
  const roots: Unit[] = [];
  for (const id of family.root_ids) {
    const member = byId.get(id);
    if (member && !placed.has(member.id)) roots.push(makeUnit(member));
  }

  // Safety net: a member the graph cannot reach at all still gets drawn rather
  // than silently vanishing from a household under review. Members merely
  // hidden by a collapsed ancestor are reachable, so they stay hidden.
  for (const member of family.members) {
    if (!placed.has(member.id) && !reachable.has(member.id)) {
      roots.push(makeUnit(member));
    }
  }

  return { roots, units };
}

/** Bottom-up width measurement, then top-down placement centring parents. */
function layout(roots: Unit[]): { width: number; height: number; depth: number } {
  function measure(u: Unit): number {
    const own = unitOwnWidth(u);
    if (!u.children.length) {
      u.width = own;
      return own;
    }
    const childrenWidth = u.children.reduce(
      (sum, c, i) => sum + measure(c) + (i ? H_GAP : 0),
      0,
    );
    u.width = Math.max(own, childrenWidth);
    return u.width;
  }

  let maxDepth = 0;

  function place(u: Unit, left: number, depth: number) {
    maxDepth = Math.max(maxDepth, depth);
    u.y = depth * (NODE_H + V_GAP);
    const own = unitOwnWidth(u);

    if (!u.children.length) {
      u.x = left + (u.width - own) / 2;
      return;
    }

    const childrenWidth = u.children.reduce(
      (sum, c, i) => sum + c.width + (i ? H_GAP : 0),
      0,
    );
    let cursor = left + (u.width - childrenWidth) / 2;
    for (const child of u.children) {
      place(child, cursor, depth + 1);
      cursor += child.width + H_GAP;
    }

    // Sit the parent above the midpoint of its children's span.
    const first = u.children[0];
    const last = u.children[u.children.length - 1];
    const span = (first.x + (last.x + unitOwnWidth(last))) / 2;
    u.x = span - own / 2;
  }

  let cursor = 0;
  for (const root of roots) {
    measure(root);
    place(root, cursor, 0);
    cursor += root.width + H_GAP * 2;
  }

  return {
    width: Math.max(cursor - H_GAP * 2, NODE_W),
    height: maxDepth * (NODE_H + V_GAP) + NODE_H,
    depth: maxDepth + 1,
  };
}

// --- Confidence presentation ------------------------------------------------

const CONF_VAR: Record<ConfidenceLevel, string> = {
  Confirmed: "--conf-confirmed",
  Strong: "--conf-strong",
  Possible: "--conf-possible",
  Unverified: "--conf-unverified",
};

const confColor = (level: ConfidenceLevel, alpha = 1) =>
  `hsl(var(${CONF_VAR[level]}) / ${alpha})`;

function levelOf(score: number): ConfidenceLevel {
  if (score >= 95) return "Confirmed";
  if (score >= 80) return "Strong";
  if (score >= 60) return "Possible";
  return "Unverified";
}

const UNRESOLVED_COPY: Record<UnresolvedReason, { title: string; detail: string }> = {
  no_relation_recorded: {
    title: "No relative named on the roll",
    detail:
      "There is nothing to match against, so no link can be drawn. This is a gap in the source document, not a failed extraction.",
  },
  relative_not_in_household: {
    title: "Named relative is not registered at this address",
    detail:
      "The relative is usually enrolled in a neighbouring part. Search their name across parts to confirm.",
  },
  contradicted: {
    title: "Every asserted link contradicts the evidence",
    detail:
      "The names match but the ages or genders cannot be reconciled. Re-read the source card — this normally means a field was mis-read.",
  },
};

/** Four dots filled to the confidence band. Reads at a glance; no gradient. */
function ConfidenceMeter({ score, level }: { score: number; level: ConfidenceLevel }) {
  const filled = level === "Confirmed" ? 4 : level === "Strong" ? 3 : level === "Possible" ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-2" title={`${score}% — ${level}`}>
      <span className="flex items-center gap-1" aria-hidden>
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background:
                i < filled ? confColor(level) : "hsl(var(--muted-foreground) / 0.25)",
            }}
          />
        ))}
      </span>
      <span className="text-xs font-bold tabular-nums" style={{ color: confColor(level) }}>
        {score}%
      </span>
      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        {level}
      </span>
    </span>
  );
}

// --- Node card --------------------------------------------------------------

const ROLE_TONE: Record<string, string> = {
  Father: "badge-amber",
  Mother: "badge-rose",
  Parent: "badge-amber",
  Son: "badge-blue",
  Daughter: "badge-violet",
  Child: "badge-blue",
  Husband: "badge-teal",
  Wife: "badge-rose",
  Spouse: "badge-teal",
  Resident: "badge-slate",
};

function NodeCard({
  member,
  isTarget,
  isHead,
  related,
  childCount,
  collapsed,
  onToggle,
  onNavigate,
  onHover,
  registerRef,
}: {
  member: FamilyMember;
  isTarget: boolean;
  isHead: boolean;
  related: boolean | null;
  childCount: number;
  collapsed: boolean;
  onToggle: () => void;
  onNavigate: () => void;
  onHover: (id: string | null) => void;
  registerRef: (el: HTMLButtonElement | null) => void;
}) {
  const initial = (member.name || "?").trim().charAt(0).toUpperCase() || "?";

  return (
    <div
      className="family-node absolute"
      data-related={related === null ? undefined : related}
      style={{ width: NODE_W, height: NODE_H }}
      onMouseEnter={() => onHover(member.id)}
      onMouseLeave={() => onHover(null)}
    >
      <button
        ref={registerRef}
        type="button"
        onClick={onNavigate}
        onFocus={() => onHover(member.id)}
        onBlur={() => onHover(null)}
        aria-label={`Open ${member.name || "unnamed voter"}, ${member.resolved_role}, EPIC ${member.epic}`}
        className={`w-full h-full text-left rounded-xl border px-3 py-2 flex items-start gap-2.5 bg-card ${
          isTarget
            ? "border-primary ring-2 ring-primary/35 shadow-md"
            : "border-border hover:border-primary/45 hover:shadow-sm"
        }`}
      >
        <span
          className={`w-8 h-8 rounded-lg shrink-0 grid place-items-center text-xs font-bold ${
            isHead
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground"
          }`}
          aria-hidden
        >
          {initial}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1">
            <span className="block text-[13px] font-semibold leading-tight truncate">
              {member.name || "Unnamed"}
            </span>
            {isHead && <Crown className="w-3 h-3 shrink-0 text-primary" aria-label="Head of household" />}
            {member.verified && (
              <BadgeCheck className="w-3 h-3 shrink-0 text-emerald-500" aria-label="Verified" />
            )}
          </span>

          <span className="flex items-center gap-1.5 mt-1">
            <span
              className={`px-1.5 py-px rounded text-[9px] font-bold uppercase tracking-wide ${
                ROLE_TONE[member.resolved_role] ?? "badge-slate"
              }`}
            >
              {member.resolved_role}
            </span>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {member.age ?? "—"} · {member.gender || "—"}
            </span>
          </span>

          <span className="block font-mono text-[10px] text-muted-foreground truncate mt-0.5">
            {member.epic || "no EPIC"}
          </span>
        </span>
      </button>

      {childCount > 0 && (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={`${collapsed ? "Show" : "Hide"} ${childCount} ${childCount === 1 ? "child" : "children"} of ${member.name || "this voter"}`}
          className="absolute -bottom-3 left-1/2 -translate-x-1/2 z-10 w-6 h-6 rounded-full border border-border bg-card grid place-items-center text-muted-foreground hover:text-primary hover:border-primary/50 shadow-sm"
        >
          {collapsed ? (
            <span className="text-[9px] font-bold tabular-nums">{childCount}</span>
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
        </button>
      )}
    </div>
  );
}

// --- Evidence ledger --------------------------------------------------------

/**
 * The 100-point score, itemised. Shown in a panel under the canvas rather than
 * a floating popover: there is no collision maths to get wrong, and on a narrow
 * screen the reader is not fighting a tooltip.
 */
function EvidenceLedger({
  rel,
  onClose,
}: {
  rel: FamilyRelationship;
  onClose: () => void;
}) {
  const e = rel.evidence;
  const declared =
    rel.relationship_type === "Husband"
      ? `${rel.source_name} is recorded with husband “${rel.target_name}”`
      : `${rel.source_name} is recorded with ${rel.relationship_type.toLowerCase()} “${rel.target_name}”`;

  const rows = [
    {
      label: "Address",
      points: e.locality_score,
      max: 30,
      note:
        e.locality_score >= 30
          ? "Same house number and part"
          : e.locality_score >= 22
            ? "Same building, different sub-door"
            : "No house number — inferred from adjacent serial numbers",
    },
    {
      label: "Name match",
      points: e.name_points,
      max: 35,
      note:
        e.name_score === 1
          ? "Exact match after label stripping"
          : `${(e.name_score * 100).toFixed(1)}% similarity — OCR variant`,
    },
    {
      label: "Relation recorded",
      points: e.relation_points,
      max: 20,
      note: `Roll states “${rel.relationship_type}”`,
    },
    {
      label: "Age",
      points: e.age_valid ? 10 : 0,
      max: 10,
      note: !e.age_known
        ? "Not scored — no age on one of the records"
        : e.age_valid
          ? "Generation gap is consistent"
          : "Ages do not corroborate",
    },
    {
      label: "Gender",
      points: e.gender_valid ? 5 : 0,
      max: 5,
      note: !e.gender_known
        ? "Not scored — gender missing"
        : e.gender_valid
          ? "Consistent with the stated relation"
          : "Does not corroborate",
    },
  ];

  return (
    <div className="card-vimc p-5">
      <div className="flex items-start justify-between gap-4 mb-1">
        <div className="flex items-center gap-2">
          <Scale className="w-4 h-4" style={{ color: confColor(rel.confidence_level) }} />
          <h4 className="text-xs font-bold uppercase tracking-wider">How this link scored</h4>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close scoring breakdown"
          className="w-6 h-6 rounded grid place-items-center text-muted-foreground hover:text-foreground hover:bg-muted"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <p className="text-xs text-muted-foreground mb-4">{declared}</p>

      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.label} className="flex items-baseline gap-3 text-xs">
            <span className="w-32 shrink-0 font-medium">{r.label}</span>
            <span
              className={`w-12 shrink-0 text-right font-mono tabular-nums font-semibold ${
                r.points === 0 ? "text-muted-foreground" : ""
              }`}
              style={r.points > 0 ? { color: confColor(rel.confidence_level) } : undefined}
            >
              {r.points > 0 ? `+${r.points}` : "0"}
            </span>
            <span className="w-8 shrink-0 text-[10px] text-muted-foreground font-mono">
              /{r.max}
            </span>
            <span className="text-muted-foreground">{r.note}</span>
          </li>
        ))}
      </ul>

      <div className="flex items-baseline gap-3 text-xs mt-3 pt-3 border-t border-border">
        <span className="w-32 shrink-0 font-bold uppercase tracking-wider text-[10px]">
          Total
        </span>
        <span
          className="w-12 shrink-0 text-right font-mono tabular-nums font-bold"
          style={{ color: confColor(rel.confidence_level) }}
        >
          {rel.confidence}
        </span>
        <span className="w-8 shrink-0 text-[10px] text-muted-foreground font-mono">/100</span>
        <span className="font-bold" style={{ color: confColor(rel.confidence_level) }}>
          {rel.confidence_level}
        </span>
      </div>
    </div>
  );
}

// --- Main -------------------------------------------------------------------

export function FamilyTreeTab({
  data,
  loading,
  error,
  onRetry,
  onNavigate,
}: {
  data: FamilyTreeResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onNavigate: (voterId: string) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [hovered, setHovered] = useState<string | null>(null);
  const [selectedRel, setSelectedRel] = useState<string | null>(null);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());

  const targetId = data?.target_voter_id ?? "";

  const primary = useMemo(
    () =>
      data?.families.find((f) => f.family_id === data.primary_family_id) ??
      data?.families[0] ??
      null,
    [data],
  );

  const others = useMemo(
    () => (data?.families ?? []).filter((f) => f.family_id !== primary?.family_id),
    [data, primary],
  );

  // Collapse state is keyed by voter id, so it must be dropped when the tab
  // switches to a different household.
  useEffect(() => {
    setCollapsed(new Set());
    setSelectedRel(null);
  }, [primary?.family_id]);

  const graph = useMemo(() => {
    if (!primary) return null;
    const { roots, units } = buildUnits(primary, collapsed);
    const box = layout(roots);
    return { roots, units, ...box };
  }, [primary, collapsed]);

  const relByKey = useMemo(() => {
    const map = new Map<string, FamilyRelationship>();
    for (const r of primary?.relationships ?? []) {
      map.set(`${r.source_id}->${r.target_id}`, r);
    }
    return map;
  }, [primary]);

  /** A person's immediate circle: spouse, parents, children. */
  const relatedIds = useMemo(() => {
    if (!hovered || !primary) return null;
    const m = primary.members.find((x) => x.id === hovered);
    if (!m) return null;
    return new Set(
      [m.id, m.spouse_id, ...m.parent_ids, ...m.child_ids].filter(
        (v): v is string => Boolean(v),
      ),
    );
  }, [hovered, primary]);

  const toggle = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  /** Arrow keys walk the cards in reading order; Enter opens the profile. */
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!graph) return;
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const order = graph.units
        .flatMap((u) => (u.spouse ? [u.primary, u.spouse] : [u.primary]))
        .sort((a, b) => a.generation_level - b.generation_level);
      const active = document.activeElement;
      const idx = order.findIndex((m) => nodeRefs.current.get(m.id) === active);
      if (idx === -1) return;
      e.preventDefault();
      const next = order[idx + (e.key === "ArrowRight" ? 1 : -1)];
      if (next) nodeRefs.current.get(next.id)?.focus();
    },
    [graph],
  );

  if (loading) {
    return (
      <div className="card-vimc p-16 grid place-items-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Resolving the household…</p>
        </div>
      </div>
    );
  }

  if (error || !data || !primary) {
    return (
      <div className="card-vimc p-10 text-center">
        <AlertTriangle className="w-8 h-8 mx-auto mb-3 text-amber-500" />
        <p className="text-sm font-semibold mb-1">The household could not be resolved</p>
        <p className="text-xs text-muted-foreground max-w-sm mx-auto mb-4">
          {error ?? "The server returned no family data for this voter."}
        </p>
        <button type="button" onClick={onRetry} className="vimc-btn-ghost h-8 text-xs mx-auto">
          <RefreshCw className="w-3.5 h-3.5" /> Try again
        </button>
      </div>
    );
  }

  const { household } = data;
  const verified = primary.members.filter((m) => m.verified).length;
  const selected = selectedRel ? relByKey.get(selectedRel) ?? null : null;

  // Contradictions from every family at the address, not just the target's:
  // the reason a link was thrown out ("already recorded as married to X") names
  // the record to re-read, which the generic per-family copy cannot.
  const rejections = [
    ...primary.rejected_links,
    ...others.flatMap((f) => f.rejected_links),
  ];
  // Families that resolved nothing and have no contradiction to explain it —
  // here the generic copy is the whole story.
  const unlinked = others.filter(
    (f) => f.unresolved_reason && f.rejected_links.length === 0,
  );
  const reviewCount = rejections.length + unlinked.length;

  return (
    <div className="space-y-5" onKeyDown={onKeyDown}>
      {/* Household summary */}
      <div className="card-vimc p-5">
        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
          <div className="flex items-center gap-3 min-w-0">
            <span className="w-11 h-11 rounded-xl bg-primary/10 text-primary grid place-items-center shrink-0">
              <Home className="w-5 h-5" />
            </span>
            <div className="min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  House
                </span>
                <h3 className="font-mono text-lg font-bold leading-none">
                  {household.house_number || "unrecorded"}
                </h3>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Part {household.part_number || "—"}
                {household.constituency ? ` · ${household.constituency}` : ""} ·{" "}
                {household.size} {household.size === 1 ? "elector" : "electors"}
              </p>
              {household.house_variants.length > 1 && (
                <p className="text-[11px] text-muted-foreground mt-1.5">
                  Also written{" "}
                  {household.house_variants
                    .filter((v) => v !== household.house_number)
                    .map((v) => (
                      <span key={v} className="font-mono text-foreground">
                        {v}{" "}
                      </span>
                    ))}
                  in this part — the same address, spelled differently.
                </p>
              )}
            </div>
          </div>

          <dl className="flex items-center gap-8">
            <div>
              <dt className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">
                Link confidence
              </dt>
              <dd>
                <ConfidenceMeter
                  score={primary.confidence}
                  level={primary.confidence_level}
                />
              </dd>
            </div>
            <div>
              <dt className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">
                Verified
              </dt>
              <dd className="text-xs font-bold tabular-nums flex items-center gap-1.5">
                <BadgeCheck
                  className={`w-3.5 h-3.5 ${verified ? "text-emerald-500" : "text-muted-foreground"}`}
                />
                {verified} of {primary.members.length}
              </dd>
            </div>
            <div>
              <dt className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">
                Generations
              </dt>
              <dd className="text-xs font-bold tabular-nums flex items-center gap-1.5">
                <Ruler className="w-3.5 h-3.5 text-muted-foreground" />
                {primary.generation_count}
              </dd>
            </div>
          </dl>
        </div>

        {household.grouping === "serial_window" && (
          <p className="text-[11px] text-muted-foreground mt-4 pt-3 border-t border-border">
            No house number on this record, so the household was inferred from
            electors at adjacent serial numbers in the same part. Links here are
            scored lower to reflect that.
          </p>
        )}
        {household.truncated && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-3">
            This address matched the 200-elector cap, so some members are not
            shown. That usually means a placeholder house number.
          </p>
        )}
      </div>

      {/* The canvas */}
      <div className="card-vimc">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-border">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" />
            <h4 className="text-xs font-bold uppercase tracking-wider">Household graph</h4>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
            {(["Confirmed", "Strong", "Possible", "Unverified"] as ConfidenceLevel[]).map(
              (level) => (
                <span key={level} className="flex items-center gap-1.5">
                  <svg width="16" height="6" aria-hidden className="shrink-0">
                    <line
                      x1="0"
                      y1="3"
                      x2="16"
                      y2="3"
                      stroke={confColor(level)}
                      strokeWidth={level === "Confirmed" ? 2.5 : 1.75}
                      strokeDasharray={
                        level === "Possible" ? "3 2" : level === "Unverified" ? "2 2" : undefined
                      }
                    />
                  </svg>
                  <span className="font-semibold uppercase tracking-wider">{level}</span>
                </span>
              ),
            )}
          </div>
        </div>

        {primary.members.length === 1 && !primary.relationships.length ? (
          <SoloResident member={primary.members[0]} reason={primary.unresolved_reason} />
        ) : (
          <div className="overflow-x-auto px-5 py-6">
            <div
              className="family-canvas relative mx-auto"
              data-focusing={Boolean(relatedIds)}
              style={{
                width: (graph?.width ?? NODE_W) + PAD * 2,
                height: (graph?.height ?? NODE_H) + PAD * 2,
              }}
            >
              {/* Links sit behind the cards and carry the confidence. */}
              <svg
                className="absolute inset-0 pointer-events-none"
                width="100%"
                height="100%"
                aria-hidden
              >
                {graph?.units.map((u) => {
                  const links: React.ReactNode[] = [];

                  // Marriage: a double rule between the pair.
                  if (u.spouse) {
                    const rel =
                      relByKey.get(`${u.spouse.id}->${u.primary.id}`) ??
                      relByKey.get(`${u.primary.id}->${u.spouse.id}`);
                    const level = rel?.confidence_level ?? "Unverified";
                    const y = u.y + NODE_H / 2 + PAD;
                    const x1 = u.x + NODE_W + PAD;
                    const x2 = x1 + SPOUSE_GAP;
                    const isRelated =
                      !relatedIds ||
                      relatedIds.has(u.primary.id) ||
                      relatedIds.has(u.spouse.id);
                    links.push(
                      <g
                        key={`sp-${u.key}`}
                        className="family-link"
                        data-related={isRelated}
                        style={{ ["--link-length" as string]: SPOUSE_GAP }}
                      >
                        <line x1={x1} y1={y - 2.5} x2={x2} y2={y - 2.5} stroke={confColor(level)} strokeWidth={1.75} />
                        <line x1={x1} y1={y + 2.5} x2={x2} y2={y + 2.5} stroke={confColor(level)} strokeWidth={1.75} />
                      </g>,
                    );
                  }

                  // Descent: one curve per child, in that child's own colour.
                  for (const child of u.children) {
                    const rel =
                      relByKey.get(`${child.primary.id}->${u.primary.id}`) ??
                      (u.spouse
                        ? relByKey.get(`${child.primary.id}->${u.spouse.id}`)
                        : undefined);
                    const level = rel?.confidence_level ?? "Unverified";
                    const x1 = descentX(u) + PAD;
                    const y1 = u.y + NODE_H + PAD;
                    const x2 = child.x + NODE_W / 2 + PAD;
                    const y2 = child.y + PAD;
                    const mid = (y1 + y2) / 2;
                    const isRelated =
                      !relatedIds ||
                      (relatedIds.has(child.primary.id) &&
                        (relatedIds.has(u.primary.id) ||
                          Boolean(u.spouse && relatedIds.has(u.spouse.id))));
                    const length = Math.abs(y2 - y1) + Math.abs(x2 - x1) + 40;

                    links.push(
                      <path
                        key={`ch-${child.key}`}
                        d={`M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`}
                        fill="none"
                        stroke={confColor(level)}
                        strokeWidth={level === "Confirmed" ? 2.25 : 1.75}
                        strokeLinecap="round"
                        className={`family-link ${
                          level === "Possible" || level === "Unverified"
                            ? "family-link--dashed"
                            : ""
                        }`}
                        data-related={isRelated}
                        style={{ ["--link-length" as string]: length }}
                      />,
                    );
                  }
                  return links;
                })}
              </svg>

              {/* Generation rail: G1 is the senior generation, and each step
                  down is a real ordinal, so numbering it carries information. */}
              {graph &&
                Array.from({ length: graph.depth }, (_, i) => (
                  <span
                    key={i}
                    className="absolute -left-1 text-[9px] font-bold tracking-widest text-muted-foreground/50 font-mono"
                    style={{ top: i * (NODE_H + V_GAP) + PAD + NODE_H / 2 - 6 }}
                    aria-hidden
                  >
                    G{i + 1}
                  </span>
                ))}

              {graph?.units.map((u) => {
                const cards: React.ReactNode[] = [];
                const push = (m: FamilyMember, x: number) =>
                  cards.push(
                    <div key={m.id} className="absolute" style={{ left: x + PAD, top: u.y + PAD }}>
                      <NodeCard
                        member={m}
                        isTarget={m.id === targetId}
                        isHead={m.is_head}
                        related={relatedIds ? relatedIds.has(m.id) : null}
                        childCount={m.child_ids.length}
                        collapsed={collapsed.has(m.id)}
                        onToggle={() => toggle(m.id)}
                        onNavigate={() => onNavigate(m.id)}
                        onHover={setHovered}
                        registerRef={(el) => {
                          if (el) nodeRefs.current.set(m.id, el);
                          else nodeRefs.current.delete(m.id);
                        }}
                      />
                    </div>,
                  );

                push(u.primary, u.x);
                if (u.spouse) push(u.spouse, u.x + NODE_W + SPOUSE_GAP);
                return cards;
              })}
            </div>
          </div>
        )}

        {/* Link picker. Clicking a row opens its ledger — the links themselves
            are too thin to be reliable click targets. */}
        {primary.relationships.length > 0 && (
          <div className="border-t border-border px-5 py-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
              {primary.relationships.length} resolved{" "}
              {primary.relationships.length === 1 ? "link" : "links"} — select one to see its
              score
            </p>
            <div className="flex flex-wrap gap-1.5">
              {primary.relationships.map((r) => {
                const key = `${r.source_id}->${r.target_id}`;
                const active = selectedRel === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSelectedRel(active ? null : key)}
                    onMouseEnter={() => setHovered(r.source_id)}
                    onMouseLeave={() => setHovered(null)}
                    aria-pressed={active}
                    className={`px-2 py-1 rounded-lg border text-[11px] font-medium flex items-center gap-1.5 transition-colors ${
                      active ? "bg-muted border-primary/50" : "border-border hover:bg-muted"
                    }`}
                    style={active ? undefined : { borderLeftColor: confColor(r.confidence_level), borderLeftWidth: 3 }}
                  >
                    <span className="truncate max-w-[9rem]">{r.source_name || "—"}</span>
                    <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
                    <span className="truncate max-w-[9rem]">{r.target_name || "—"}</span>
                    <span
                      className="font-mono tabular-nums font-bold"
                      style={{ color: confColor(r.confidence_level) }}
                    >
                      {r.confidence}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {selected && (
        <EvidenceLedger rel={selected} onClose={() => setSelectedRel(null)} />
      )}

      {/* Needs review */}
      {reviewCount > 0 && (
        <div className="card-vimc p-5">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle
              className="w-4 h-4"
              style={{ color: confColor("Unverified") }}
            />
            <h4 className="text-xs font-bold uppercase tracking-wider">
              Needs review ({reviewCount})
            </h4>
          </div>
          <p className="text-xs text-muted-foreground mb-4">
            The roll asserts these, but the evidence does not support them. Each one
            points at a record worth re-reading against the source page.
          </p>

          <ul className="space-y-2">
            {rejections.map((r, i) => (
              <li
                key={`${r.source_id}-${r.target_id}-${i}`}
                className="rounded-lg border border-border p-3 text-xs"
                style={{ borderLeftColor: confColor("Unverified"), borderLeftWidth: 3 }}
              >
                <p className="font-semibold mb-0.5">
                  {r.source_name || "—"}{" "}
                  <span className="font-normal text-muted-foreground">
                    is recorded with {(r.relationship_type || "relative").toLowerCase()}
                  </span>{" "}
                  {r.target_name || "—"}
                </p>
                <p className="text-muted-foreground">{r.reason}</p>
              </li>
            ))}

            {unlinked
              .map((f) => {
                const copy = UNRESOLVED_COPY[f.unresolved_reason!];
                return (
                  <li
                    key={f.family_id}
                    className="rounded-lg border border-border p-3 text-xs"
                    style={{ borderLeftColor: confColor("Possible"), borderLeftWidth: 3 }}
                  >
                    <p className="font-semibold mb-0.5">
                      {f.members.map((m) => m.name || "Unnamed").join(", ")} —{" "}
                      <span className="font-normal">{copy.title}</span>
                    </p>
                    <p className="text-muted-foreground">{copy.detail}</p>
                  </li>
                );
              })}
          </ul>
        </div>
      )}

      {/* Other electors at the address */}
      {others.length > 0 && (
        <div className="card-vimc p-5">
          <h4 className="text-xs font-bold uppercase tracking-wider mb-1">
            Also at this address ({others.reduce((n, f) => n + f.members.length, 0)})
          </h4>
          <p className="text-xs text-muted-foreground mb-4">
            Registered at the same house but with no relationship to the family above
            that the roll supports.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {others.flatMap((f) =>
              f.members.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => onNavigate(m.id)}
                  className="flex items-center gap-2.5 p-2.5 rounded-lg border border-border hover:border-primary/45 hover:bg-muted/50 text-left transition-colors"
                >
                  <span className="w-7 h-7 rounded-lg bg-muted grid place-items-center text-[11px] font-bold shrink-0">
                    {(m.name || "?").trim().charAt(0).toUpperCase() || "?"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold truncate">
                      {m.name || "Unnamed"}
                    </span>
                    <span className="block font-mono text-[10px] text-muted-foreground truncate">
                      {m.epic || "no EPIC"}
                    </span>
                  </span>
                  <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                    {m.age ?? "—"} · {m.gender || "—"}
                  </span>
                </button>
              )),
            )}
          </div>
        </div>
      )}

      {/* ASCII tree */}
      <div className="card-vimc p-5">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h4 className="text-xs font-bold uppercase tracking-wider">Text tree</h4>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard
                ?.writeText(primary.ascii_tree)
                .then(() => toast.success("Text tree copied"))
                .catch(() => toast.error("Could not copy the text tree"));
            }}
            className="vimc-btn-ghost h-7 text-[11px]"
          >
            <Copy className="w-3 h-3" /> Copy
          </button>
        </div>
        <pre className="p-4 rounded-xl bg-muted/50 border border-border font-mono text-[11px] leading-relaxed overflow-x-auto">
          {primary.ascii_tree || "No links resolved."}
        </pre>
      </div>
    </div>
  );
}

function SoloResident({
  member,
  reason,
}: {
  member: FamilyMember;
  reason: UnresolvedReason | null;
}) {
  const copy = reason ? UNRESOLVED_COPY[reason] : null;
  return (
    <div className="px-5 py-12 text-center">
      <span className="w-12 h-12 rounded-xl bg-muted grid place-items-center mx-auto mb-4 text-base font-bold">
        {(member.name || "?").trim().charAt(0).toUpperCase() || "?"}
      </span>
      <p className="text-sm font-semibold mb-1">
        {member.name || "This elector"} is the only person linked here
      </p>
      {copy && (
        <p className="text-xs text-muted-foreground max-w-md mx-auto">{copy.detail}</p>
      )}
    </div>
  );
}
