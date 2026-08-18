"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  getValidationSummary,
  getValidationReports,
  getValidationMismatches,
  triggerValidationScan,
  ValidationSummary,
  ValidationReport,
  ValidationMismatch,
} from "../lib/voterApi";

export default function ValidationView() {
  const [summary, setSummary] = useState<ValidationSummary | null>(null);
  const [reports, setReports] = useState<ValidationReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "PASS" | "PARTIAL" | "FAIL" | "PENN">("ALL");

  // Mismatch Modal State
  const [selectedPdf, setSelectedPdf] = useState<string | null>(null);
  const [selectedPart, setSelectedPart] = useState<string | null>(null);
  const [mismatches, setMismatches] = useState<ValidationMismatch[]>([]);
  const [mismatchLoading, setMismatchLoading] = useState(false);
  const [mismatchFilterField, setMismatchFilterField] = useState<string>("ALL");
  const [mismatchSearch, setMismatchSearch] = useState("");

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sum, reps] = await Promise.all([
        getValidationSummary(),
        getValidationReports(),
      ]);
      setSummary(sum);
      setReports(reps);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRescan = async () => {
    setScanning(true);
    try {
      await triggerValidationScan();
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Scan failed: ${msg}`);
    } finally {
      setScanning(false);
    }
  };

  const handleOpenMismatches = async (pdfFile: string, partNumber: string) => {
    setSelectedPdf(pdfFile);
    setSelectedPart(partNumber);
    setMismatchLoading(true);
    try {
      const res = await getValidationMismatches({
        pdf_file: pdfFile,
        limit: 300,
      });
      setMismatches(res.items || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to load mismatches: ${msg}`);
    } finally {
      setMismatchLoading(false);
    }
  };

  // Filtered reports
  const filteredReports = useMemo(() => {
    return reports.filter((r) => {
      // Search
      const searchMatch =
        searchTerm === "" ||
        r.pdf_file.toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(r.part_number).includes(searchTerm) ||
        r.ac_number.includes(searchTerm);

      // Status filter
      if (statusFilter === "PASS") return searchMatch && r.status === "PASS";
      if (statusFilter === "PARTIAL") return searchMatch && r.status === "PARTIAL";
      if (statusFilter === "FAIL") return searchMatch && r.status === "FAIL";
      if (statusFilter === "PENN") return searchMatch && r.ac_number === "58";
      return searchMatch;
    });
  }, [reports, searchTerm, statusFilter]);

  // Filtered Mismatches in modal
  const filteredMismatches = useMemo(() => {
    return mismatches.filter((m) => {
      const matchField =
        mismatchFilterField === "ALL" || m.field_name === mismatchFilterField;
      const matchSearch =
        mismatchSearch === "" ||
        String(m.serial_number).includes(mismatchSearch) ||
        m.pdf_value.toLowerCase().includes(mismatchSearch.toLowerCase()) ||
        m.db_value.toLowerCase().includes(mismatchSearch.toLowerCase()) ||
        m.difference.toLowerCase().includes(mismatchSearch.toLowerCase());
      return matchField && matchSearch;
    });
  }, [mismatches, mismatchFilterField, mismatchSearch]);

  // CSV Export for validation results
  const handleExportCsv = () => {
    if (!reports.length) return;
    const headers = [
      "PDF File",
      "AC Number",
      "Part Number",
      "Total PDF Records",
      "Total DB Records",
      "Matched",
      "Missing in DB",
      "Extra in DB",
      "Incorrect",
      "Duplicates",
      "Pass %",
      "Status",
    ];
    const rows = reports.map((r) => [
      r.pdf_file,
      r.ac_number,
      r.part_number,
      r.total_pdf_records,
      r.total_db_records,
      r.matched,
      r.missing_in_db,
      r.extra_in_db,
      r.incorrect,
      r.duplicates,
      `${r.pass_percentage}%`,
      r.status,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.map((val) => `"${val}"`).join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `pdf_validation_report_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10">
      {/* Header Banner */}
      <div className="max-w-7xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-2xl">📋</span>
              <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
                PDF vs Database Verification & Audit
              </h1>
              {summary && (
                <span
                  className={`px-3 py-1 text-xs font-bold rounded-full uppercase tracking-wider ${
                    summary.overall_status === "PASS"
                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                      : summary.overall_status === "PARTIAL"
                      ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                      : "bg-rose-950 text-rose-300 border border-rose-500/40"
                  }`}
                >
                  Verdict: {summary.overall_status} ({summary.overall_pass_pct}%)
                </span>
              )}
            </div>
            <p className="text-slate-400 text-sm mt-1">
              Read-only validation scanning all PDF electoral rolls in{" "}
              <code className="text-slate-300 bg-slate-900 px-2 py-0.5 rounded text-xs">
                D:\OCR\PDF\Penn PDF
              </code>{" "}
              against Supabase PostgreSQL records.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleExportCsv}
              className="px-4 py-2 text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition shadow-sm flex items-center gap-2"
            >
              📥 Export CSV Report
            </button>
            <button
              onClick={handleRescan}
              disabled={scanning}
              className="px-5 py-2 text-sm font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition shadow-lg shadow-emerald-900/30 flex items-center gap-2 disabled:opacity-50"
            >
              {scanning ? "🔄 Scanning Repository..." : "⚡ Run Live Verification Scan"}
            </button>
          </div>
        </div>

        {/* Global Summary KPI Grid */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
            <div className="bg-slate-900/80 border border-slate-800/80 rounded-xl p-4 flex flex-col">
              <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">
                Total PDFs
              </span>
              <span className="text-2xl font-black text-slate-100 mt-1">
                {summary.total_pdfs}
              </span>
              <span className="text-xs text-slate-500 mt-1">
                {summary.passed_pdfs} Passed / {summary.failed_pdfs} Fail
              </span>
            </div>

            <div className="bg-slate-900/80 border border-slate-800/80 rounded-xl p-4 flex flex-col">
              <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">
                PDF Expected
              </span>
              <span className="text-2xl font-black text-slate-100 mt-1">
                {summary.total_pdf_records?.toLocaleString() || 0}
              </span>
              <span className="text-xs text-slate-500 mt-1">Printed in rolls</span>
            </div>

            <div className="bg-slate-900/80 border border-slate-800/80 rounded-xl p-4 flex flex-col">
              <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">
                DB Stored
              </span>
              <span className="text-2xl font-black text-slate-100 mt-1">
                {summary.total_db_records?.toLocaleString() || 0}
              </span>
              <span className="text-xs text-slate-500 mt-1">Stored in database</span>
            </div>

            <div className="bg-emerald-950/40 border border-emerald-800/40 rounded-xl p-4 flex flex-col">
              <span className="text-emerald-400 text-xs font-semibold uppercase tracking-wider">
                Matched
              </span>
              <span className="text-2xl font-black text-emerald-300 mt-1">
                {summary.matched?.toLocaleString() || 0}
              </span>
              <span className="text-xs text-emerald-500/80 mt-1">
                Clean valid records
              </span>
            </div>

            <div className="bg-rose-950/40 border border-rose-800/40 rounded-xl p-4 flex flex-col">
              <span className="text-rose-400 text-xs font-semibold uppercase tracking-wider">
                Missing in DB
              </span>
              <span className="text-2xl font-black text-rose-300 mt-1">
                {summary.missing_in_db?.toLocaleString() || 0}
              </span>
              <span className="text-xs text-rose-500/80 mt-1">Missing serials</span>
            </div>

            <div className="bg-amber-950/40 border border-amber-800/40 rounded-xl p-4 flex flex-col">
              <span className="text-amber-400 text-xs font-semibold uppercase tracking-wider">
                Extra in DB
              </span>
              <span className="text-2xl font-black text-amber-300 mt-1">
                {summary.extra_in_db?.toLocaleString() || 0}
              </span>
              <span className="text-xs text-amber-500/80 mt-1">Out of range</span>
            </div>

            <div className="bg-indigo-950/40 border border-indigo-800/40 rounded-xl p-4 flex flex-col">
              <span className="text-indigo-400 text-xs font-semibold uppercase tracking-wider">
                Incorrect
              </span>
              <span className="text-2xl font-black text-indigo-300 mt-1">
                {summary.incorrect?.toLocaleString() || 0}
              </span>
              <span className="text-xs text-indigo-500/80 mt-1">Field format flaws</span>
            </div>

            <div className="bg-purple-950/40 border border-purple-800/40 rounded-xl p-4 flex flex-col">
              <span className="text-purple-400 text-xs font-semibold uppercase tracking-wider">
                Duplicates
              </span>
              <span className="text-2xl font-black text-purple-300 mt-1">
                {summary.duplicates || 0}
              </span>
              <span className="text-xs text-purple-500/80 mt-1">Serial/EPIC clashes</span>
            </div>
          </div>
        )}

        {/* Filters and Controls */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          {/* Status Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto">
            {(
              [
                { id: "ALL", label: `All (${reports.length})` },
                {
                  id: "PENN",
                  label: `Pennagaram AC 58 (${
                    reports.filter((r) => r.ac_number === "58").length
                  })`,
                },
                {
                  id: "PASS",
                  label: `Pass (${
                    reports.filter((r) => r.status === "PASS").length
                  })`,
                },
                {
                  id: "PARTIAL",
                  label: `Partial (${
                    reports.filter((r) => r.status === "PARTIAL").length
                  })`,
                },
                {
                  id: "FAIL",
                  label: `Fail (${
                    reports.filter((r) => r.status === "FAIL").length
                  })`,
                },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                  statusFilter === tab.id
                    ? "bg-emerald-500 text-slate-950 shadow-md font-bold"
                    : "bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="w-full md:w-80">
            <input
              type="text"
              placeholder="🔍 Search by PDF name, Part # or AC..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition"
            />
          </div>
        </div>

        {/* Validation Reports Table */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          {loading ? (
            <div className="p-12 text-center text-slate-400">
              <div className="animate-spin text-3xl mb-3">🔄</div>
              <p>Scanning database and generating validation metrics...</p>
            </div>
          ) : error ? (
            <div className="p-12 text-center text-rose-400">
              <p>Error loading validation report: {error}</p>
            </div>
          ) : filteredReports.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              No matching PDF validation records found.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                    <th className="py-3 px-4">PDF File</th>
                    <th className="py-3 px-3 text-center">Part</th>
                    <th className="py-3 px-3 text-right">PDF Records</th>
                    <th className="py-3 px-3 text-right">DB Records</th>
                    <th className="py-3 px-3 text-right">Matched</th>
                    <th className="py-3 px-3 text-right">Missing</th>
                    <th className="py-3 px-3 text-right">Extra</th>
                    <th className="py-3 px-3 text-right">Incorrect</th>
                    <th className="py-3 px-3 text-right">Duplicates</th>
                    <th className="py-3 px-4 text-center">Pass %</th>
                    <th className="py-3 px-3 text-center">Status</th>
                    <th className="py-3 px-4 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredReports.map((r, i) => (
                    <tr
                      key={i}
                      className="hover:bg-slate-800/40 transition group"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-slate-200">
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-400">
                            AC {r.ac_number}
                          </span>
                          <span className="truncate max-w-xs md:max-w-md text-slate-300">
                            {r.pdf_file}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center font-bold text-slate-100">
                        #{r.part_number}
                      </td>
                      <td className="py-3 px-3 text-right font-medium text-slate-300">
                        {r.total_pdf_records.toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-right font-medium text-slate-300">
                        {r.total_db_records.toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-emerald-400">
                        {r.matched.toLocaleString()}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-bold ${
                          r.missing_in_db > 0
                            ? "text-rose-400 bg-rose-950/20"
                            : "text-slate-500"
                        }`}
                      >
                        {r.missing_in_db}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-bold ${
                          r.extra_in_db > 0
                            ? "text-amber-400 bg-amber-950/20"
                            : "text-slate-500"
                        }`}
                      >
                        {r.extra_in_db}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-bold ${
                          r.incorrect > 0
                            ? "text-indigo-400 bg-indigo-950/20"
                            : "text-slate-500"
                        }`}
                      >
                        {r.incorrect}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-bold ${
                          r.duplicates > 0
                            ? "text-purple-400 bg-purple-950/20"
                            : "text-slate-500"
                        }`}
                      >
                        {r.duplicates}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <div className="w-14 bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                r.pass_percentage >= 98
                                  ? "bg-emerald-500"
                                  : r.pass_percentage >= 90
                                  ? "bg-amber-500"
                                  : "bg-rose-500"
                              }`}
                              style={{ width: `${r.pass_percentage}%` }}
                            />
                          </div>
                          <span className="font-mono text-xs font-bold text-slate-200">
                            {r.pass_percentage}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span
                          className={`px-2 py-0.5 text-[10px] font-black rounded-md uppercase tracking-wider ${
                            r.status === "PASS"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                              : r.status === "PARTIAL"
                              ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                              : "bg-rose-950 text-rose-300 border border-rose-500/40"
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <button
                          onClick={() => handleOpenMismatches(r.pdf_file, r.part_number)}
                          className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition ${
                            r.mismatches_count > 0
                              ? "bg-indigo-600/80 hover:bg-indigo-500 text-white shadow-sm"
                              : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                          }`}
                        >
                          🔍 Mismatches ({r.mismatches_count})
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Mismatch Drill-down Modal */}
      {selectedPdf && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-5xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xl">🔍</span>
                  <h3 className="text-lg font-bold text-slate-100">
                    Discrepancy & Mismatch Ledger
                  </h3>
                  <span className="px-2 py-0.5 text-xs font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                    Part #{selectedPart}
                  </span>
                </div>
                <p className="text-xs text-slate-400 font-mono mt-1 truncate max-w-2xl">
                  {selectedPdf}
                </p>
              </div>
              <button
                onClick={() => setSelectedPdf(null)}
                className="text-slate-400 hover:text-slate-100 text-xl px-2 py-1 rounded-lg hover:bg-slate-800 transition"
              >
                ✕
              </button>
            </div>

            {/* Modal Filters */}
            <div className="p-4 border-b border-slate-800 bg-slate-900/80 flex flex-col md:flex-row gap-3 items-center justify-between">
              <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto">
                <span className="text-xs text-slate-400 font-semibold">
                  Field:
                </span>
                {[
                  "ALL",
                  "record_presence",
                  "epic",
                  "name",
                  "age",
                  "gender",
                  "serial_duplicate",
                  "epic_duplicate",
                ].map((f) => (
                  <button
                    key={f}
                    onClick={() => setMismatchFilterField(f)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition whitespace-nowrap ${
                      mismatchFilterField === f
                        ? "bg-indigo-600 text-white font-bold"
                        : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                    }`}
                  >
                    {f === "ALL" ? "All Fields" : f.replace("_", " ")}
                  </button>
                ))}
              </div>

              <input
                type="text"
                placeholder="Search within mismatches..."
                value={mismatchSearch}
                onChange={(e) => setMismatchSearch(e.target.value)}
                className="w-full md:w-64 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
              />
            </div>

            {/* Modal Body Table */}
            <div className="overflow-y-auto p-4 flex-1">
              {mismatchLoading ? (
                <div className="p-12 text-center text-slate-400">
                  <div className="animate-spin text-2xl mb-2">🔄</div>
                  <p>Loading discrepancy ledger...</p>
                </div>
              ) : filteredMismatches.length === 0 ? (
                <div className="p-12 text-center text-emerald-400 bg-emerald-950/20 border border-emerald-800/40 rounded-xl">
                  🎉 No field mismatches or missing entries found for this selection!
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                        <th className="py-2.5 px-3">Page #</th>
                        <th className="py-2.5 px-3">Serial #</th>
                        <th className="py-2.5 px-3">Field Name</th>
                        <th className="py-2.5 px-4 text-emerald-400">
                          PDF Expected Value
                        </th>
                        <th className="py-2.5 px-4 text-rose-400">
                          DB Stored Value
                        </th>
                        <th className="py-2.5 px-4">Difference Detail</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {filteredMismatches.map((m, idx) => (
                        <tr
                          key={idx}
                          className="hover:bg-slate-800/30 transition"
                        >
                          <td className="py-2.5 px-3 text-slate-400 font-bold">
                            p.{m.page_number}
                          </td>
                          <td className="py-2.5 px-3 text-slate-200 font-bold">
                            #{m.serial_number}
                          </td>
                          <td className="py-2.5 px-3 font-sans">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-indigo-300">
                              {m.field_name}
                            </span>
                          </td>
                          <td className="py-2.5 px-4 text-emerald-300 bg-emerald-950/10">
                            {m.pdf_value}
                          </td>
                          <td className="py-2.5 px-4 text-rose-300 bg-rose-950/10 font-bold">
                            {m.db_value}
                          </td>
                          <td className="py-2.5 px-4 font-sans text-slate-300 text-xs">
                            {m.difference}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400">
              <span>
                Showing {filteredMismatches.length} of {mismatches.length} discrepancies
              </span>
              <button
                onClick={() => setSelectedPdf(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition font-medium"
              >
                Close Ledger
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
