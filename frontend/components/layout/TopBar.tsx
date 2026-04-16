"use client";

import React from "react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { Moon, Sun, Users, LogOut, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { profile as profileApi } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

export function TopBar() {
  const { owner, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();

  async function handleFamilyScopeToggle(checked: boolean) {
    if (!owner) return;
    await profileApi.patch(owner.owner_id, { is_family_scope: checked });
    // Invalidate all queries so widgets reload with new scope
    queryClient.invalidateQueries();
  }

  return (
    <header className="sticky top-0 z-50 flex h-14 items-center justify-between border-b bg-background px-4 md:px-6">
      {/* Left: brand */}
      <Link href="/" className="flex items-center gap-2 font-semibold">
        <span className="text-lg">Artha</span>
      </Link>

      {/* Right: controls */}
      <div className="flex items-center gap-3">
        {/* Family scope toggle */}
        {owner && (
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <Label htmlFor="family-scope" className="text-sm text-muted-foreground cursor-pointer">
              Family
            </Label>
            <Switch
              id="family-scope"
              onCheckedChange={handleFamilyScopeToggle}
              aria-label="Toggle family scope"
            />
          </div>
        )}

        {/* Theme toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>

        {/* Admin link */}
        {owner?.is_admin && (
          <Button variant="ghost" size="icon" asChild aria-label="Admin panel">
            <Link href="/admin">
              <Shield className="h-4 w-4" />
            </Link>
          </Button>
        )}

        {/* Owner name + logout */}
        {owner && (
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground md:inline">{owner.name}</span>
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
