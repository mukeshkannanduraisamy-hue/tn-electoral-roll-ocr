"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  Check,
} from "lucide-react";
import { FieldValue, Issue, Record_ } from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";
import { fetchRecords, updateRecord } from "@/lib/api";
import { toast } from "sonner";

const FIELD_TAMIL_LABELS: Record<string, string> = {
  serial: "வரிசை எண் (S.No)",
  epic: "அடையாள அட்டை எண் (EPIC ID)",
  name: "பெயர் (Name)",
  relation_type: "உறவு முறை (Relation)",
  relation_name: "உறவினரின் பெயர் (Relation Name)",
  house_number: "வீட்டு எண் (House No)",
  age: "வயது (Age)",
  gender: "பாலினம் (Gender)",
};

interface ReviewFieldInputProps {
  recordId: string;
  field: FieldValue;
  onUpdate: (updated: Record_) => void;
}

const ReviewFieldInput: React.FC<ReviewFieldInputProps> = ({ recordId, field, onUpdate }) => {
  const val = field.edited_value ?? field.original_value ?? "";
  const [localVal, setLocalVal] = useState(val);

  useEffect(() => {
    setLocalVal(val);
  }, [val]);

  const handleSave = async () => {
    if (localVal === val) return;
    try {
      const updated = await updateRecord(recordId, {
        edits: [{ key: field.key, value: localVal }],
      });
      onUpdate(updated);
      toast.success(`Updated ${FIELD_TAMIL_LABELS[field.key] || field.key}`);
    } catch (e) {
      console.error("Failed to save field edit", e);
      toast.error("Failed to save field change");
    }
  };

  return (
    <input
      type="text"
      value={localVal}
      onChange={(e) => setLocalVal(e.target.value)}
      onBlur={handleSave}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.currentTarget.blur();
        }
      }}
      className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 font-medium focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all shadow-xs"
    />
  );
};

export const ReviewQueue: React.FC = () => {
  const { activeFileId, refreshStats } = useOcrStore();

  const [records, setRecords] = useState<Record_[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const loadQueue = async () => {
    setIsLoading(true);
    try {
      const res = await fetchRecords({
        file_id: activeFileId || undefined,
        only_issues: true,
        unreviewed: true,
        limit: 100,
      });
      setRecords(res.items);
      setCurrentIndex(0);
    } catch (e) {
      console.error("Failed to load review queue", e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, [activeFileId]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeRecord = records[currentIndex];

  const handleApproveCurrent = async () => {
    if (!activeRecord) return;
    try {
      await updateRecord(activeRecord.id, { reviewed: true });
      toast.success(`Approved Record #${activeRecord.index + 1}`);
      const nextRecords = records.filter((r) => r.id !== activeRecord.id);
      setRecords(nextRecords);
      if (currentIndex >= nextRecords.length) {
        setCurrentIndex(Math.max(0, nextRecords.length - 1));
      }
      refreshStats(activeFileId || undefined);
    } catch (e) {
      console.error(e);
      toast.error("Failed to approve record");
    }
  };

  const handleAcceptSuggestion = async (key: string, suggestion: string) => {
    if (!activeRecord) return;
    try {
      const updated = await updateRecord(activeRecord.id, {
        edits: [{ key, value: suggestion }],
      });
      handleRecordUpdate(updated);
      refreshStats(activeFileId || undefined);
      toast.success("Applied consensus suggestion");
    } catch (e) {
      console.error(e);
    }
  };

  const handleRecordUpdate = (updated: Record_) => {
    setRecords((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm bg-white dark:bg-slate-950 animate-pulse">
        Loading validation review queue…
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-white dark:bg-slate-950 transition-colors duration-200">
        <div className="w-14 h-14 rounded-full bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 flex items-center justify-center mb-4 shadow-sm">
          <CheckCircle2 className="w-7 h-7 text-emerald-500" />
        </div>
        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Review Queue Empty!</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm mt-1.5 leading-relaxed">
          All validation issues for the selected document have been resolved or approved. Excellent work!
        </p>
      </div>
    );
  }

  const issues: Issue[] = activeRecord
    ? [
        ...activeRecord.issues,
        ...(Object.values(activeRecord.fields) as FieldValue[]).flatMap((f: FieldValue) => f.issues),
      ]
    : [];

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-slate-950 p-6 overflow-auto transition-colors duration-200">
      {/* Header Bar */}
      <div className="max-w-4xl mx-auto w-full flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2.5">
            Validation Review Queue
            <span className="px-2.5 py-0.5 rounded-full bg-rose-50 dark:bg-rose-500/20 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-500/30 text-xs font-bold">
              {records.length} pending
            </span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Reviewing Record #{currentIndex + 1} of {records.length}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleApproveCurrent}
            className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-2 shadow-md shadow-emerald-600/20 transition-all"
          >
            <Check className="w-4 h-4" />
            <span>Approve & Next</span>
            <ArrowRight className="w-3.5 h-3.5 ml-0.5" />
          </button>
        </div>
      </div>

      {/* Main Active Card */}
      {activeRecord && (
        <div className="max-w-4xl mx-auto w-full bg-slate-50/50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
          {/* Card Header & Issues List */}
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <span className="text-xs font-mono text-indigo-600 dark:text-indigo-400 font-bold">
                Record #{activeRecord.index + 1}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400 font-semibold">
                Mean Confidence: {((activeRecord.mean_confidence ?? 0) * 100).toFixed(1)}%
              </span>
            </div>

            <div className="space-y-2">
              {issues.map((issue: Issue, idx: number) => (
                <div
                  key={idx}
                  className={`p-3.5 rounded-xl border flex items-start gap-3 text-xs ${
                    issue.severity === "error"
                      ? "bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/30 text-rose-700 dark:text-rose-300"
                      : "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30 text-amber-700 dark:text-amber-300"
                  }`}
                >
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5 text-rose-500" />
                  <div>
                    <div className="font-bold flex items-center gap-2">
                      {issue.code}
                      {issue.field && (
                        <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-white/60 dark:bg-slate-950/40">
                          Field: {FIELD_TAMIL_LABELS[issue.field] || issue.field}
                        </span>
                      )}
                    </div>
                    <div className="text-xs opacity-90 mt-0.5">{issue.message}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Fields Review Grid */}
          <div className="grid grid-cols-2 gap-4">
            {(Object.values(activeRecord.fields) as FieldValue[]).map((field: FieldValue) => {
              const hasFieldIssue = field.issues.length > 0;
              const val = field.edited_value ?? field.original_value;
              const hasSuggestion = field.suggested_value && field.suggested_value !== val;

              return (
                <div
                  key={field.key}
                  className={`p-4 rounded-xl border transition-all shadow-xs ${
                    hasFieldIssue
                      ? "bg-rose-50/30 dark:bg-rose-950/20 border-rose-200 dark:border-rose-500/40"
                      : "bg-white dark:bg-slate-950/60 border-slate-200 dark:border-slate-800"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="font-semibold text-slate-600 dark:text-slate-400">
                      {FIELD_TAMIL_LABELS[field.key] || field.key}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {(field.confidence * 100).toFixed(0)}% conf
                    </span>
                  </div>

                  <ReviewFieldInput
                    recordId={activeRecord.id}
                    field={field}
                    onUpdate={handleRecordUpdate}
                  />

                  {hasSuggestion && (
                    <button
                      onClick={() => handleAcceptSuggestion(field.key, field.suggested_value!)}
                      className="mt-2.5 text-xs px-3 py-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-600/30 hover:bg-indigo-100 dark:hover:bg-indigo-600/50 border border-indigo-200 dark:border-indigo-500/50 text-indigo-700 dark:text-indigo-200 flex items-center gap-1.5 w-full justify-center font-semibold transition-all"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                      Accept Consensus Spelling: &quot;{field.suggested_value}&quot;
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
