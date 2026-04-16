"use client";

/**
 * AuthProvider — stores token + owner info in localStorage.
 * Provides useAuth() hook for all client components.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { auth as authApi } from "@/lib/api";

const TOKEN_KEY = "artha_token";
const OWNER_KEY = "artha_owner";

interface AuthOwner {
  owner_id: string;
  name: string;
  is_admin: boolean;
}

interface AuthContextValue {
  owner: AuthOwner | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (owner_id: string, pin: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [owner, setOwner] = useState<AuthOwner | null>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const storedOwner = localStorage.getItem(OWNER_KEY);
    if (storedToken && storedOwner) {
      setToken(storedToken);
      try {
        setOwner(JSON.parse(storedOwner));
      } catch {
        localStorage.removeItem(OWNER_KEY);
      }
    }
  }, []);

  const login = useCallback(async (owner_id: string, pin: string) => {
    const resp = await authApi.login(owner_id, pin);
    localStorage.setItem(TOKEN_KEY, resp.token);
    const ownerData: AuthOwner = {
      owner_id: resp.owner_id,
      name: resp.name,
      is_admin: resp.is_admin,
    };
    localStorage.setItem(OWNER_KEY, JSON.stringify(ownerData));
    setToken(resp.token);
    setOwner(ownerData);
    router.push("/");
  }, [router]);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(OWNER_KEY);
    setToken(null);
    setOwner(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider
      value={{ owner, token, isAuthenticated: !!token, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Redirect to /login if not authenticated. Call this at the top of protected pages. */
export function useRequireAuth() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!isAuthenticated) router.push("/login");
  }, [isAuthenticated, router]);
}

/** Redirect to / if not admin. Call this at the top of admin pages. */
export function useRequireAdmin() {
  const { owner, isAuthenticated } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!isAuthenticated) router.push("/login");
    else if (owner && !owner.is_admin) router.push("/");
  }, [isAuthenticated, owner, router]);
}
