import React from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { AlertTriangle, X } from "lucide-react";

export function ConfirmationModal() {
  const { confirmModal, setConfirmModal } = useOcrStore();

  if (!confirmModal || !confirmModal.isOpen) return null;

  const handleConfirm = async () => {
    try {
      await confirmModal.onConfirm();
    } finally {
      setConfirmModal(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 overflow-hidden">
        {/* Close Button */}
        <button
          onClick={() => setConfirmModal(null)}
          className="absolute top-4 right-4 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-start space-x-4">
          <div
            className={`p-3 rounded-xl ${
              confirmModal.danger
                ? "bg-rose-100 text-rose-600 dark:bg-rose-950/80 dark:text-rose-400"
                : "bg-amber-100 text-amber-600 dark:bg-amber-950/80 dark:text-amber-400"
            }`}
          >
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="flex-1 pr-6">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {confirmModal.title}
            </h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
              {confirmModal.message}
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end space-x-3 pt-4 border-t border-slate-100 dark:border-slate-800/80">
          <button
            onClick={() => setConfirmModal(null)}
            className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className={`px-4 py-2 text-sm font-medium text-white rounded-xl shadow-lg transition-all ${
              confirmModal.danger
                ? "bg-rose-600 hover:bg-rose-500 shadow-rose-600/25"
                : "bg-indigo-600 hover:bg-indigo-500 shadow-indigo-600/25"
            }`}
          >
            {confirmModal.confirmText || "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
