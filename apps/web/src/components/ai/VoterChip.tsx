"use client";

/**
 * A citation the operator can act on.
 *
 * Clicking opens the elector in the main workspace. The assistant does not
 * navigate on its own — it hands over a link, and the operator decides whether
 * to follow it. That boundary was drawn deliberately when UI-driving was removed
 * from the earlier assistant, and this keeps it.
 */

import React from "react";
import { ExternalLink } from "lucide-react";
import type { ChatCitation } from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";

export const VoterChip: React.FC<{ citation: ChatCitation }> = ({ citation }) => {
  const setActiveTab = useOcrStore((s) => s.setActiveTab);
  const setSelectedRecordId = useOcrStore((s) => s.setSelectedRecordId);

  const label = citation.name || citation.epic || citation.id;

  return (
    <button
      type="button"
      onClick={() => {
        setSelectedRecordId(citation.id);
        setActiveTab("voters");
      }}
      title={
        citation.epic
          ? `Open ${label} (${citation.epic})`
          : `Open ${label}`
      }
      className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded-md bg-indigo-500/15 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 font-semibold transition-colors align-baseline"
    >
      {label}
      <ExternalLink className="w-3 h-3 shrink-0" />
    </button>
  );
};
