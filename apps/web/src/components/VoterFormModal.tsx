"use client";

import React, { useEffect, useState } from "react";
import { AlertCircle, Loader2, Save, X } from "lucide-react";
import { toast } from "sonner";
import { Voter, VoterInput } from "@ocr/shared-types";
import { ApiError, createVoter, updateVoter } from "@/lib/voterApi";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSaved: (voter: Voter) => void;
  /** Present when editing; absent when creating. */
  voter?: Voter | null;
}

const EMPTY: VoterInput = {
  epic: "",
  name: "",
  serial: null,
  relation_type: "",
  relation_name: "",
  house_number: "",
  age: null,
  gender: "",
  part_number: "",
  constituency: "",
  notes: "",
  verified: false,
};

const RELATION_OPTIONS = ["", "Husband", "Father", "Mother", "Other"] as const;
const GENDER_OPTIONS = ["", "Male", "Female", "Other"] as const;

/** Mirrors the server rules so the user sees problems before a round trip. */
function validate(form: VoterInput): Record<string, string> {
  const errors: Record<string, string> = {};
  const epic = form.epic.replace(/[^A-Za-z0-9]/g, "").toUpperCase();

  if (!epic) errors.epic = "EPIC is required";
  else if (!/^[A-Z]{2,4}\d{6,9}$/.test(epic))
    errors.epic = "Expected 2–4 letters then 6–9 digits, e.g. ZHT0308742";

  if (!form.name.trim()) errors.name = "Name is required";

  if (form.age !== null && (form.age < 18 || form.age > 120))
    errors.age = "Age must be between 18 and 120";

  if (form.relation_name.trim() && !form.relation_type)
    errors.relation_type = "Choose a relation type";

  return errors;
}

export const VoterFormModal: React.FC<Props> = ({ isOpen, onClose, onSaved, voter }) => {
  const [form, setForm] = useState<VoterInput>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const editing = Boolean(voter);

  useEffect(() => {
    if (!isOpen) return;
    setErrors({});
    setServerError(null);
    setForm(
      voter
        ? {
            epic: voter.epic,
            name: voter.name,
            serial: voter.serial,
            relation_type: voter.relation_type,
            relation_name: voter.relation_name,
            house_number: voter.house_number,
            age: voter.age,
            gender: voter.gender,
            part_number: voter.part_number,
            constituency: voter.constituency,
            notes: voter.notes,
            verified: voter.verified,
          }
        : EMPTY,
    );
  }, [isOpen, voter]);

  // Escape closes, which is what every dialog on the web does.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, saving, onClose]);

  if (!isOpen) return null;

  const set = <K extends keyof VoterInput>(key: K, value: VoterInput[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => {
      if (!e[key as string]) return e;
      const { [key as string]: _removed, ...rest } = e;
      return rest;
    });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    setServerError(null);
    try {
      const payload: VoterInput = {
        ...form,
        epic: form.epic.replace(/[^A-Za-z0-9]/g, "").toUpperCase(),
        name: form.name.trim(),
      };
      const saved = editing
        ? await updateVoter(voter!.id, payload)
        : await createVoter(payload);
      toast.success(editing ? "Voter updated" : "Voter created");
      onSaved(saved);
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Save failed";
      // A duplicate EPIC is the expected conflict here; point at the field.
      if (err instanceof ApiError && err.status === 409) {
        setErrors((e) => ({ ...e, epic: message }));
      } else {
        setServerError(message);
      }
    } finally {
      setSaving(false);
    }
  };

  const field = (name: string) =>
    `w-full rounded-lg border bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 outline-none transition focus:ring-2 focus:ring-indigo-500/40 ${
      errors[name]
        ? "border-rose-400 dark:border-rose-700"
        : "border-slate-300 dark:border-slate-700 focus:border-indigo-500"
    }`;

  const Err = ({ name }: { name: string }) =>
    errors[name] ? (
      <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-1">{errors[name]}</p>
    ) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-slate-900/50 backdrop-blur-sm p-0 sm:p-4">
      <div className="w-full sm:max-w-2xl max-h-[92vh] overflow-y-auto bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-t-2xl sm:rounded-2xl shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-t-2xl">
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            {editing ? `Edit voter · ${voter?.epic}` : "Add voter"}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={submit} className="p-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                EPIC ID <span className="text-rose-500">*</span>
              </label>
              <input
                value={form.epic}
                onChange={(e) => set("epic", e.target.value)}
                className={`${field("epic")} font-mono uppercase`}
                placeholder="ZHT0308742"
                autoFocus={!editing}
              />
              <Err name="epic" />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                பெயர் · Name <span className="text-rose-500">*</span>
              </label>
              <input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                className={field("name")}
                placeholder="சுசீலா"
              />
              <Err name="name" />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                உறவு முறை · Relation
              </label>
              <select
                value={form.relation_type}
                onChange={(e) => set("relation_type", e.target.value as VoterInput["relation_type"])}
                className={field("relation_type")}
              >
                {RELATION_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o || "— none —"}
                  </option>
                ))}
              </select>
              <Err name="relation_type" />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                உறவினரின் பெயர் · Relation name
              </label>
              <input
                value={form.relation_name}
                onChange={(e) => set("relation_name", e.target.value)}
                className={field("relation_name")}
                placeholder="சண்முகம்"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                வீட்டு எண் · House no.
              </label>
              <input
                value={form.house_number}
                onChange={(e) => set("house_number", e.target.value)}
                className={field("house_number")}
                placeholder="5-177"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  வயது · Age
                </label>
                <input
                  type="number"
                  min={18}
                  max={120}
                  value={form.age ?? ""}
                  onChange={(e) =>
                    set("age", e.target.value === "" ? null : Number(e.target.value))
                  }
                  className={field("age")}
                />
                <Err name="age" />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  பாலினம் · Gender
                </label>
                <select
                  value={form.gender}
                  onChange={(e) => set("gender", e.target.value as VoterInput["gender"])}
                  className={field("gender")}
                >
                  {GENDER_OPTIONS.map((o) => (
                    <option key={o} value={o}>
                      {o || "—"}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  S.No
                </label>
                <input
                  type="number"
                  min={1}
                  value={form.serial ?? ""}
                  onChange={(e) =>
                    set("serial", e.target.value === "" ? null : Number(e.target.value))
                  }
                  className={field("serial")}
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Part
                </label>
                <input
                  value={form.part_number}
                  onChange={(e) => set("part_number", e.target.value)}
                  className={field("part_number")}
                  placeholder="10"
                />
              </div>
            </div>

            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Notes
              </label>
              <textarea
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
                rows={2}
                className={`${field("notes")} resize-y`}
                placeholder="Anything a later reviewer should know"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={form.verified}
              onChange={(e) => set("verified", e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500/40"
            />
            Mark as verified against the source page
          </label>

          {serverError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 px-3 py-2 text-xs text-rose-700 dark:text-rose-300"
            >
              <AlertCircle className="h-4 w-4 shrink-0 mt-px" />
              <span>{serverError}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold flex items-center gap-2 shadow-sm transition"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {editing ? "Save changes" : "Create voter"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
