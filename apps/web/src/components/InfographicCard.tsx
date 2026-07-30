"use client";

/**
 * A chart card for one computed figure, rendered inline in the copilot chat.
 *
 * Every number here came from SQL (see app/services/infographic.py) — the model
 * chose the measure and wrote the commentary, but never the values. So this
 * component renders what it is given without rounding, re-deriving or inferring.
 *
 * Form follows the data's job, decided server-side: a headline figure is a stat
 * tile rather than a one-bar chart; an ordinal breakdown is columns; a small
 * part-of-whole is a donut; a ranked comparison is horizontal bars, because the
 * labels are Tamil names and part codes that need room without rotated text.
 * Colour only varies where it carries meaning — a single measure across
 * categories uses one hue, since a different colour per bar would imply a
 * distinction that is not in the data.
 */

import React, { useMemo, useState } from "react";
import { BarChart3, Database, Info, Table2 } from "lucide-react";
import type { Infographic, InfographicPoint, MetricUnit } from "@ocr/shared-types";

/** Validated categorical slots, capped at three. See globals.css. */
const SLOTS = ["var(--viz-s1)", "var(--viz-s2)", "var(--viz-s3)"];

function formatValue(value: number | null, unit: MetricUnit): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (unit === "percent") return `${value}%`;
  if (unit === "years") return `${value} yrs`;
  return value.toLocaleString();
}

/** Donut geometry from cumulative shares — no layout library needed. */
function useDonutArcs(series: InfographicPoint[]) {
  return useMemo(() => {
    const total = series.reduce((sum, p) => sum + (p.value ?? 0), 0);
    if (!total) return [];
    const circumference = 2 * Math.PI * 40;
    let offset = 0;
    return series.map((point, i) => {
      const fraction = (point.value ?? 0) / total;
      // A 2px surface gap between segments keeps adjacent fills legible.
      const gap = series.length > 1 ? 2 : 0;
      const length = Math.max(fraction * circumference - gap, 0);
      const arc = {
        point,
        color: SLOTS[i % SLOTS.length],
        dashArray: `${length} ${circumference - length}`,
        dashOffset: -offset,
      };
      offset += fraction * circumference;
      return arc;
    });
  }, [series]);
}

export function InfographicCard({ data }: { data: Infographic }) {
  const [showTable, setShowTable] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);

  const { series, metric, chart_type: chartType } = data;
  const maxValue = Math.max(...series.map((p) => p.value ?? 0), 0) || 1;
  const arcs = useDonutArcs(chartType === "donut" ? series : []);
  const isCategorical = chartType === "donut";

  return (
    <figure className="viz card-vimc p-4 my-2 text-left">
      {/* Heading */}
      <figcaption className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <h4 className="text-sm font-semibold leading-tight">{data.title}</h4>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {data.metric.description}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {series.length > 0 && (
            <button
              type="button"
              onClick={() => setShowTable((v) => !v)}
              aria-pressed={showTable}
              title={showTable ? "Show chart" : "Show the figures as a table"}
              className="w-7 h-7 rounded-lg grid place-items-center text-muted-foreground hover:text-foreground hover:bg-muted"
            >
              {showTable ? <BarChart3 className="w-3.5 h-3.5" /> : <Table2 className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </figcaption>

      {/* Filters in scope */}
      {data.filters_applied.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {data.filters_applied.map((f) => (
            <span
              key={f.key}
              className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground"
            >
              {f.label}: <span className="text-foreground">{f.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* Headline figure. The only form with no plot, so no hover layer. */}
      {chartType === "stat" && (
        <div className="py-3">
          <div className="text-4xl font-bold tabular-nums tracking-tight">
            {formatValue(data.total, metric.unit)}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {metric.label} · {data.population.toLocaleString()} electors in scope
          </div>
        </div>
      )}

      {showTable ? (
        <TableView data={data} />
      ) : (
        <>
          {/* Ranked comparison. Horizontal so long labels need no rotation. */}
          {chartType === "bar" && (
            <ul className="space-y-1.5">
              {series.map((p) => {
                const dim = hovered !== null && hovered !== p.label;
                return (
                  <li
                    key={p.label}
                    className="grid grid-cols-[minmax(4.5rem,7rem)_1fr_auto] items-center gap-2.5 transition-opacity"
                    style={{ opacity: dim ? 0.45 : 1 }}
                    onMouseEnter={() => setHovered(p.label)}
                    onMouseLeave={() => setHovered(null)}
                    title={`${p.label}: ${formatValue(p.value, metric.unit)}${
                      p.share !== null ? ` (${p.share}%)` : ""
                    }`}
                  >
                    <span className="text-[11px] text-muted-foreground truncate">{p.label}</span>
                    <span
                      className="h-2.5 rounded-full overflow-hidden"
                      style={{ background: "var(--viz-track)" }}
                    >
                      <span
                        className="block h-full rounded-full transition-[width] duration-500"
                        style={{
                          width: `${Math.max(((p.value ?? 0) / maxValue) * 100, 1.5)}%`,
                          background: "var(--viz-mark)",
                        }}
                      />
                    </span>
                    <span className="text-[11px] font-semibold tabular-nums">
                      {formatValue(p.value, metric.unit)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          {/* Ordinal sequence, so it reads left to right. */}
          {chartType === "column" && (
            <div className="flex items-end gap-2 h-36 pt-2">
              {series.map((p) => {
                const dim = hovered !== null && hovered !== p.label;
                return (
                  <div
                    key={p.label}
                    className="flex-1 flex flex-col items-center justify-end gap-1.5 h-full min-w-0 transition-opacity"
                    style={{ opacity: dim ? 0.45 : 1 }}
                    onMouseEnter={() => setHovered(p.label)}
                    onMouseLeave={() => setHovered(null)}
                    title={`${p.label}: ${formatValue(p.value, metric.unit)}${
                      p.share !== null ? ` (${p.share}%)` : ""
                    }`}
                  >
                    <span className="text-[10px] font-semibold tabular-nums">
                      {formatValue(p.value, metric.unit)}
                    </span>
                    <span
                      className="w-full rounded-t-[4px] transition-[height] duration-500"
                      style={{
                        height: `${Math.max(((p.value ?? 0) / maxValue) * 100, 1.5)}%`,
                        background: "var(--viz-mark)",
                      }}
                    />
                    <span className="text-[10px] text-muted-foreground truncate w-full text-center">
                      {p.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Part-of-whole. Only reachable for a summable measure. */}
          {chartType === "donut" && (
            <div className="flex items-center gap-5 flex-wrap">
              <svg viewBox="0 0 100 100" className="w-28 h-28 shrink-0 -rotate-90" role="img"
                aria-label={`${data.title}: ${series
                  .map((p) => `${p.label} ${formatValue(p.value, metric.unit)}`)
                  .join(", ")}`}
              >
                <circle cx="50" cy="50" r="40" fill="none" strokeWidth="14"
                  style={{ stroke: "var(--viz-track)" }} />
                {arcs.map((arc) => (
                  <circle
                    key={arc.point.label}
                    cx="50" cy="50" r="40" fill="none" strokeWidth="14"
                    stroke={arc.color}
                    strokeDasharray={arc.dashArray}
                    strokeDashoffset={arc.dashOffset}
                    className="transition-opacity"
                    style={{
                      opacity: hovered !== null && hovered !== arc.point.label ? 0.35 : 1,
                    }}
                  />
                ))}
              </svg>

              {/* Legend doubles as the direct labelling the contrast check
                  requires: identity never rests on colour alone. */}
              <ul className="flex-1 min-w-[10rem] space-y-1.5">
                {arcs.map((arc) => (
                  <li
                    key={arc.point.label}
                    className="flex items-center gap-2 text-[11px] transition-opacity"
                    style={{
                      opacity: hovered !== null && hovered !== arc.point.label ? 0.45 : 1,
                    }}
                    onMouseEnter={() => setHovered(arc.point.label)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0"
                      style={{ background: arc.color }} aria-hidden />
                    <span className="truncate flex-1 text-muted-foreground">
                      {arc.point.label}
                    </span>
                    <span className="font-semibold tabular-nums">
                      {formatValue(arc.point.value, metric.unit)}
                    </span>
                    {arc.point.share !== null && (
                      <span className="text-muted-foreground tabular-nums w-11 text-right">
                        {arc.point.share}%
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {data.truncated_groups > 0 && (
        <p className="text-[10px] text-muted-foreground mt-2.5">
          {data.truncated_groups} smaller{" "}
          {data.truncated_groups === 1 ? "group" : "groups"}{" "}
          {metric.unit === "count" ? "folded into “Other”" : "not shown"}.
        </p>
      )}

      {/* Commentary. Already stripped of any figure the database did not produce. */}
      {data.insights.length > 0 && (
        <ul className="mt-3 pt-3 border-t border-border space-y-1">
          {data.insights.map((insight, i) => (
            <li key={i} className="flex gap-2 text-[11px] text-muted-foreground">
              <Info className="w-3 h-3 mt-0.5 shrink-0 text-primary" aria-hidden />
              <span>{insight}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground mt-2.5">
        <Database className="w-3 h-3 shrink-0" aria-hidden />
        {data.provenance}
      </p>
    </figure>
  );
}

/** The table view. Required relief for the light-mode contrast warning. */
function TableView({ data }: { data: Infographic }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <caption className="sr-only">{data.title}</caption>
        <thead>
          <tr className="text-left text-muted-foreground border-b border-border">
            <th scope="col" className="py-1.5 pr-3 font-medium">
              {data.dimension?.label ?? "Group"}
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium text-right">
              {data.metric.label}
            </th>
            <th scope="col" className="py-1.5 font-medium text-right">Share</th>
          </tr>
        </thead>
        <tbody>
          {data.series.map((p) => (
            <tr key={p.label} className="border-b border-border/50 last:border-0">
              <th scope="row" className="py-1.5 pr-3 font-normal text-left">{p.label}</th>
              <td className="py-1.5 pr-3 text-right tabular-nums font-semibold">
                {formatValue(p.value, data.metric.unit)}
              </td>
              <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                {p.share === null ? "—" : `${p.share}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
