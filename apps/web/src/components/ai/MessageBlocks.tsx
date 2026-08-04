"use client";

/**
 * How a tool result looks.
 *
 * Every block here was built by the server from data a tool returned. Nothing
 * on this screen was typed by the language model except the prose beside it.
 */

import React from "react";
import { Database } from "lucide-react";
import type { ChatBlock, ChatCitation } from "@ocr/shared-types";
import { InfographicCard } from "../InfographicCard";
import { VoterChip } from "./VoterChip";

const MARKER = /\[\[v:([A-Za-z0-9_-]{1,40})\]\]/g;

/** Prose with its citation markers turned into chips. */
export const AnswerText: React.FC<{ text: string; citations: ChatCitation[] }> = ({
  text,
  citations,
}) => {
  const byId = new Map(citations.map((c) => [c.id, c]));
  const parts: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  MARKER.lastIndex = 0;
  while ((match = MARKER.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const citation = byId.get(match[1]);
    parts.push(
      citation ? (
        <VoterChip key={`${match[1]}-${match.index}`} citation={citation} />
      ) : (
        ""
      ),
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));

  return <p className="whitespace-pre-wrap">{parts}</p>;
};

const cell = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
};

const Table: React.FC<{
  columns: string[];
  rows: Record<string, unknown>[];
  total?: number | null;
  truncated?: boolean;
}> = ({ columns, rows, total, truncated }) => (
  <div className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/40 overflow-hidden">
    <div className="overflow-x-auto">
      <table className="w-full text-[10px] border-collapse">
        <thead>
          <tr className="bg-slate-800/60 text-slate-300">
            {columns.map((c) => (
              <th key={c} className="text-left font-bold uppercase tracking-wide px-2 py-1.5 whitespace-nowrap">
                {c.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-slate-800/70 text-slate-200">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1.5 whitespace-nowrap">{cell(row[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {(truncated || total != null) && (
      <p className="px-2 py-1 text-[9px] text-slate-500 border-t border-slate-800">
        Showing {rows.length}
        {total != null ? ` of ${total}` : ""}
        {truncated ? " — narrow the question to see the rest" : ""}
      </p>
    )}
  </div>
);

export const MessageBlocks: React.FC<{ blocks: ChatBlock[] }> = ({ blocks }) => {
  if (!blocks?.length) return null;

  return (
    <div className="space-y-2">
      {blocks.map((block, i) => {
        if (block.kind === "chart") {
          return <InfographicCard key={i} data={block.infographic} />;
        }

        if (block.kind === "table") {
          return (
            <Table
              key={i}
              columns={block.columns}
              rows={block.rows}
              total={block.total}
              truncated={block.truncated}
            />
          );
        }

        if (block.kind === "sql") {
          return (
            <div key={i} className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/60 p-2.5">
              <p className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wide text-slate-400">
                <Database className="w-3 h-3" />
                Query run — {block.rationale}
              </p>
              <pre className="mt-1.5 text-[10px] text-emerald-300 font-mono whitespace-pre-wrap break-all">
                {block.sql}
              </pre>
            </div>
          );
        }

        const voter = block.voter as Record<string, unknown>;
        const provenance = block.provenance as Record<string, unknown>;
        return (
          <div key={i} className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/40 p-3">
            <p className="text-xs font-bold text-white">{cell(voter.name)}</p>
            <p className="text-[10px] text-slate-400 font-mono">{cell(voter.epic)}</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
              {["age", "gender", "relation_name", "house_number", "part_number", "verified"].map((key) => (
                <div key={key} className="flex justify-between gap-2 border-b border-slate-800/60 pb-0.5">
                  <dt className="text-slate-500">{key.replace(/_/g, " ")}</dt>
                  <dd className="text-slate-200 font-medium text-right">{cell(voter[key])}</dd>
                </div>
              ))}
            </dl>
            {block.ocr_fields.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-[10px]">
                {block.ocr_fields.map((f) => (
                  <li key={f.field_name} className="flex justify-between gap-2">
                    <span className="text-slate-500">{f.field_name}</span>
                    <span className={f.confidence < 0.75 ? "text-amber-400 font-bold" : "text-slate-400"}>
                      {Math.round(f.confidence * 100)}%
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {provenance.source_file_name != null && (
              <p className="mt-2 text-[9px] text-slate-500">
                From {cell(provenance.source_file_name)}, page {cell(provenance.page_number)}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
};
