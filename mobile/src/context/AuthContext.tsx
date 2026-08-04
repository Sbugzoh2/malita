import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as api from "../api/client";

const TOKEN_KEY = "malita_token";

type AuthContextValue = {
  token: string | null;
  me: api.MeResponse | null;
  loading: boolean;
  refreshMe: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (params: api.RegisterParams) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<api.MeResponse | null>(null);
  // Starts true - we don't know yet whether a token is stored, so the
  // navigator below must wait for this before deciding Login vs Home.
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async (activeToken?: string | null) => {
    const t = activeToken ?? token;
    if (!t) {
      setMe(null);
      return;
    }
    try {
      const info = await api.getMe(t);
      setMe(info);
    } catch (e) {
      // Token expired/revoked server-side - drop it locally too.
      await AsyncStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setMe(null);
    }
  }, [token]);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem(TOKEN_KEY);
      if (stored) {
        setToken(stored);
        await refreshMe(stored);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { token: newToken } = await api.login(email, password);
    await AsyncStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    await refreshMe(newToken);
  }, [refreshMe]);

  const register = useCallback(async (params: api.RegisterParams) => {
    const { token: newToken } = await api.register(params);
    await AsyncStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    await refreshMe(newToken);
  }, [refreshMe]);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await api.logout(token);
      } catch {
        // Best-effort - still clear the local session even if the
        // network call fails, so the user isn't stuck "logged in".
      }
    }
    await AsyncStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setMe(null);
  }, [token]);

  return (
    <AuthContext.Provider
      value={{ token, me, loading, refreshMe: () => refreshMe(), login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
