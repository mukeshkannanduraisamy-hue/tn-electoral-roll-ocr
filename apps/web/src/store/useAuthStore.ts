"use client";

import { create } from "zustand";
import { AuthUser } from "@ocr/shared-types";
import * as api from "@/lib/voterApi";

interface AuthState {
  user: AuthUser | null;
  authEnabled: boolean;
  /** Undefined until the first status check resolves, so the UI can show a
   *  splash instead of flashing the login form at an already-signed-in user. */
  checked: boolean;
  loggingIn: boolean;
  error: string | null;

  check: () => Promise<void>;
  signIn: (username: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
  /** Called when any API call gets a 401 -- the session died server-side. */
  handleUnauthorized: () => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  authEnabled: true,
  checked: false,
  loggingIn: false,
  error: null,

  check: async () => {
    try {
      const status = await api.authStatus();
      set({
        authEnabled: status.auth_enabled,
        user: status.user,
        checked: true,
      });
    } catch {
      // The status endpoint is public; if it fails the API is unreachable.
      // Treat as signed out rather than locking the user out of the screen
      // that would tell them what is wrong.
      set({ checked: true, user: null });
    }
  },

  signIn: async (username, password) => {
    set({ loggingIn: true, error: null });
    try {
      const user = await api.login(username, password);
      set({ user, loggingIn: false, error: null });
      return true;
    } catch (err) {
      set({
        loggingIn: false,
        error: err instanceof Error ? err.message : "Sign-in failed",
      });
      return false;
    }
  },

  signOut: async () => {
    try {
      await api.logout();
    } finally {
      // Clear locally even if the request failed: the user asked to leave.
      set({ user: null, error: null });
    }
  },

  handleUnauthorized: () => {
    if (get().user !== null) {
      set({ user: null, error: "Your session expired. Please sign in again." });
    }
  },

  clearError: () => set({ error: null }),
}));
