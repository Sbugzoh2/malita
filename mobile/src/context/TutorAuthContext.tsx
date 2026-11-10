import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as api from "../api/client";

const TUTOR_TOKEN_KEY = "malita_tutor_token";

type TutorAuthContextValue = {
  token: string | null;
  me: api.TutorMe | null;
  loading: boolean;
  refreshMe: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const TutorAuthContext = createContext<TutorAuthContextValue | undefined>(undefined);

// A tutor's own session - entirely separate from AuthContext (learner
// accounts), since a tutor is a different kind of actor with its own
// login (see backend/tutoring.py's login_tutor). A device can hold both
// a learner token and a tutor token at once; RootNavigator decides which
// app to show.
export function TutorAuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<api.TutorMe | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async (activeToken?: string | null) => {
    const t = activeToken ?? token;
    if (!t) {
      setMe(null);
      return;
    }
    try {
      const info = await api.fetchTutorMe(t);
      setMe(info);
    } catch (e) {
      // Token expired/revoked server-side - drop it locally too.
      await AsyncStorage.removeItem(TUTOR_TOKEN_KEY);
      setToken(null);
      setMe(null);
    }
  }, [token]);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem(TUTOR_TOKEN_KEY);
      if (stored) {
        setToken(stored);
        await refreshMe(stored);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { token: newToken } = await api.tutorLogin(email, password);
    await AsyncStorage.setItem(TUTOR_TOKEN_KEY, newToken);
    setToken(newToken);
    await refreshMe(newToken);
  }, [refreshMe]);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await api.tutorLogout(token);
      } catch {
        // Best-effort - still clear the local session even if the
        // network call fails, so the tutor isn't stuck "logged in".
      }
    }
    await AsyncStorage.removeItem(TUTOR_TOKEN_KEY);
    setToken(null);
    setMe(null);
  }, [token]);

  return (
    <TutorAuthContext.Provider
      value={{ token, me, loading, refreshMe: () => refreshMe(), login, logout }}
    >
      {children}
    </TutorAuthContext.Provider>
  );
}

export function useTutorAuth() {
  const ctx = useContext(TutorAuthContext);
  if (!ctx) {
    throw new Error("useTutorAuth must be used within a TutorAuthProvider");
  }
  return ctx;
}
