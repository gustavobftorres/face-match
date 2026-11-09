"use client";

import { useState, useCallback, useEffect } from "react";
import { AuthState } from "@/lib/types";
import { fetchAuthUrl, exchangeCode } from "@/lib/api";

const STORAGE_KEY = "dff_auth";
const TOKEN_LIFETIME_MS = 3_600_000;

const INITIAL_AUTH_STATE: AuthState = {
  accessToken: null,
  isAuthenticated: false,
  userEmail: null,
  expiresAt: null,
};

function loadAuthState(): AuthState {
  if (typeof window === "undefined") return INITIAL_AUTH_STATE;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return INITIAL_AUTH_STATE;
    const parsed = JSON.parse(raw) as AuthState;
    if (parsed.expiresAt && Date.now() >= parsed.expiresAt) {
      localStorage.removeItem(STORAGE_KEY);
      return INITIAL_AUTH_STATE;
    }
    return parsed;
  } catch {
    return INITIAL_AUTH_STATE;
  }
}

function saveAuthState(state: AuthState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    return;
  }
}

function clearAuthState() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    return;
  }
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>(INITIAL_AUTH_STATE);

  useEffect(() => {
    setTimeout(() => setAuthState(loadAuthState()), 0);
  }, []);

  const login = useCallback(async () => {
    const url = await fetchAuthUrl();
    window.location.href = url;
  }, []);

  const logout = useCallback(() => {
    clearAuthState();
    setAuthState(INITIAL_AUTH_STATE);
  }, []);

  const handleCallback = useCallback(async (code: string) => {
    const data = await exchangeCode(code);
    const newState: AuthState = {
      accessToken: data.access_token,
      isAuthenticated: true,
      userEmail: data.email,
      expiresAt: Date.now() + TOKEN_LIFETIME_MS,
    };
    saveAuthState(newState);
    setAuthState(newState);
  }, []);

  return { authState, login, logout, handleCallback };
}
