"use client";

/**
 * Where an operator supplies the AI assistant's API key.
 *
 * The key goes one way: it is posted to the server, stored there, and used only
 * for the server's own outbound calls. Reads return a masked hint, so the
 * browser never holds the secret and a compromised session cannot read it back.
 * That is why there is no way to reveal the stored key here — only to replace or
 * clear it.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  PlugZap,
  Save,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import type { AiSettings, AiSettingsTest } from "@ocr/shared-types";
import {
  clearAiKey,
  getAiSettings,
  saveAiSettings,
  testAiSettings,
} from "@/lib/voterApi";

export function AiSettingsPanel() {
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AiSettingsTest | null>(null);

  // The key field starts empty on every load: there is nothing to prefill it
  // with, because the server does not hand the key back.
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getAiSettings();
      setSettings(next);
      setModel(next.model);
      setBaseUrl(next.base_url);
    } catch (e: any) {
      toast.error(e?.message || "Could not load the AI settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      // Send only what changed. Omitting api_key when the field is blank is what
      // stops a model tweak from wiping a working key; omitting the unchanged
      // fields keeps the store from filling up with rows that merely restate
      // the defaults.
      const next = await saveAiSettings({
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        ...(settings && model !== settings.model ? { model } : {}),
        ...(settings && baseUrl !== settings.base_url ? { base_url: baseUrl } : {}),
      });
      setSettings(next);
      setApiKey("");
      setShowKey(false);
      toast.success(apiKey.trim() ? "API key saved" : "AI settings saved");
    } catch (e: any) {
      toast.error(e?.message || "Could not save the AI settings");
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      await clearAiKey();
      await load();
      setApiKey("");
      toast.success("API key removed from this server");
    } catch (e: any) {
      toast.error(e?.message || "Could not remove the key");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await testAiSettings());
    } catch (e: any) {
      setTestResult({ ok: false, detail: e?.message || "The test call failed." });
    } finally {
      setTesting(false);
    }
  };

  const configured = settings?.configured ?? false;
  const dirty =
    Boolean(apiKey.trim()) ||
    (settings ? model !== settings.model || baseUrl !== settings.base_url : false);

  return (
    <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800/80 shadow-sm space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-500 grid place-items-center shrink-0">
          <Bot className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-bold">AI Assistant</h3>
          <p className="text-xs text-muted-foreground">
            Supplies the key the server uses to answer questions
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : (
        <>
          {/* Current state */}
          <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Status
              </span>
              {configured ? (
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Key configured
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="w-3.5 h-3.5" /> No key set
                </span>
              )}
            </div>

            {configured && (
              <>
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-muted-foreground">Stored key</span>
                  <span className="font-mono font-semibold">{settings?.key_hint}</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-muted-foreground">Read from</span>
                  <span className="font-medium">
                    {settings?.source === "settings" ? "This page" : "Server environment"}
                  </span>
                </div>
                {settings?.updated_by && (
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">Last set by</span>
                    <span className="font-medium">{settings.updated_by}</span>
                  </div>
                )}
              </>
            )}

            {!configured && (
              <p className="text-[11px] text-muted-foreground">
                The assistant still charts figures from the database, but answers
                come from a short built-in guide until a key is added.
              </p>
            )}
          </div>

          {/* Key entry */}
          <div className="space-y-1.5">
            <label
              htmlFor="ai-api-key"
              className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
            >
              {configured ? "Replace API key" : "API key"}
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  id="ai-api-key"
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={configured ? "Paste a new key to replace" : "Paste your key"}
                  autoComplete="off"
                  spellCheck={false}
                  className="vimc-input w-full pr-9 font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  aria-label={showKey ? "Hide the key" : "Show the key"}
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 grid place-items-center rounded text-muted-foreground hover:text-foreground"
                >
                  {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
              {configured && settings?.source === "settings" && (
                <button
                  type="button"
                  onClick={handleClear}
                  disabled={saving}
                  title="Remove the stored key"
                  className="vimc-btn-ghost h-9 px-3 text-xs shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <p className="text-[10px] text-muted-foreground">
              Stored on the server and never sent back to the browser — so it
              cannot be read out again here, only replaced or removed.
            </p>
          </div>

          {/* Model and endpoint */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label
                htmlFor="ai-model"
                className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
              >
                Model
              </label>
              <input
                id="ai-model"
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                spellCheck={false}
                className="vimc-input w-full font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <label
                htmlFor="ai-base-url"
                className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
              >
                Base URL
              </label>
              <input
                id="ai-base-url"
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                spellCheck={false}
                className="vimc-input w-full font-mono text-xs"
              />
            </div>
          </div>

          {/* Test outcome */}
          {testResult && (
            <div
              className={`p-3 rounded-xl border text-xs flex items-start gap-2 ${
                testResult.ok
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400"
                  : "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400"
              }`}
            >
              {testResult.ok ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <span>{testResult.detail}</span>
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !dirty}
              className="vimc-btn-primary h-9 text-xs"
            >
              {saving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              Save
            </button>
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || !configured}
              title={configured ? "Make one live call" : "Add a key first"}
              className="vimc-btn-ghost h-9 text-xs"
            >
              {testing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <PlugZap className="w-3.5 h-3.5" />
              )}
              Test connection
            </button>
          </div>
        </>
      )}
    </div>
  );
}
