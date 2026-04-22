"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

export type ViewMode = "individual" | "family";

const NAV_MAIN = [
  { href: "/", icon: "⬡", label: "Dashboard" },
  { href: "/advisory/chat", icon: "✦", label: "Ask Artha" },
  { href: "/transactions", icon: "⇄", label: "Transactions" },
  { href: "/investments", icon: "◈", label: "Investments", badge: "New" },
];

const NAV_PLANNING = [
  { href: "/goals", icon: "◎", label: "Goals" },
  { href: "/tax", icon: "◉", label: "Tax" },
  { href: "/risk", icon: "◐", label: "Risk" },
  { href: "/accounts", icon: "⬡", label: "Accounts" },
];

const NAV_BOTTOM = [
  { href: "/settings", icon: "⚙", label: "Settings" },
];

function NavItem({
  href,
  icon,
  label,
  active,
  badge,
}: {
  href: string;
  icon: string;
  label: string;
  active: boolean;
  badge?: string;
}) {
  return (
    <Link href={href} style={{ textDecoration: "none" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "8px 10px",
          borderRadius: 8,
          cursor: "pointer",
          color: active ? "var(--cyan)" : "var(--text-2)",
          fontSize: 13,
          fontWeight: 400,
          transition: "all 0.15s",
          position: "relative",
          marginBottom: 1,
          background: active ? "var(--cyan-dim)" : "transparent",
        }}
        className="nav-item-hover"
      >
        {active && (
          <div
            style={{
              position: "absolute",
              left: -12,
              top: "50%",
              transform: "translateY(-50%)",
              width: 3,
              height: 18,
              background: "var(--cyan)",
              borderRadius: "0 2px 2px 0",
            }}
          />
        )}
        <span style={{ fontSize: 15, opacity: active ? 1 : 0.7, flexShrink: 0 }}>{icon}</span>
        <span style={{ flex: 1 }}>{label}</span>
        {badge && (
          <span
            style={{
              fontSize: 10,
              background: "oklch(0.76 0.16 195 / 0.2)",
              color: "var(--cyan)",
              padding: "1px 6px",
              borderRadius: 10,
            }}
          >
            {badge}
          </span>
        )}
      </div>
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { owner, logout } = useAuth();

  const [viewMode, setViewMode] = useState<ViewMode>("individual");

  useEffect(() => {
    const stored = localStorage.getItem("artha-view") as ViewMode | null;
    if (stored === "individual" || stored === "family") setViewMode(stored);
  }, []);

  function toggleView() {
    const next: ViewMode = viewMode === "individual" ? "family" : "individual";
    setViewMode(next);
    localStorage.setItem("artha-view", next);
    window.dispatchEvent(new CustomEvent("artha-view-change", { detail: next }));
  }

  const initials = owner?.name
    ? owner.name.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase()
    : "?";

  function isActive(href: string) {
    return href === "/" ? pathname === "/" : pathname.startsWith(href);
  }

  return (
    <>
      <style>{`
        .nav-item-hover:hover {
          background: var(--surface) !important;
          color: var(--text) !important;
        }
        .user-chip-hover:hover { background: var(--surface); }
      `}</style>
      <aside
        style={{
          width: "var(--sidebar-w)",
          flexShrink: 0,
          background: "var(--bg2)",
          borderRight: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          position: "relative",
          zIndex: 10,
          paddingBottom: 16,
        }}
      >
        {/* Logo + Me/Family toggle */}
        <div
          style={{
            padding: "18px 20px 16px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 28, height: 28,
              background: "linear-gradient(135deg, var(--cyan), oklch(0.6 0.16 270))",
              borderRadius: 7,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, fontWeight: 700, color: "#000",
            }}
          >
            A
          </div>
          <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: "0.02em", color: "var(--text)" }}>
            Artha
          </span>
          {/* Me / Family toggle */}
          <div
            onClick={toggleView}
            style={{
              marginLeft: "auto",
              display: "flex", alignItems: "center", gap: 1,
              background: "var(--bg3)",
              border: "1px solid var(--border)",
              borderRadius: 6, padding: 2,
              cursor: "pointer", flexShrink: 0,
            }}
          >
            {(["individual", "family"] as ViewMode[]).map((m) => (
              <span
                key={m}
                style={{
                  fontSize: 10, padding: "2px 8px", borderRadius: 4,
                  fontFamily: "JetBrains Mono, monospace",
                  fontWeight: 600,
                  textTransform: "capitalize",
                  transition: "all 0.15s",
                  background: viewMode === m ? "var(--cyan-dim)" : "transparent",
                  color: viewMode === m ? "var(--cyan)" : "var(--text-3)",
                  border: viewMode === m ? "1px solid oklch(0.76 0.16 195 / 0.25)" : "1px solid transparent",
                }}
              >
                {m === "individual" ? "Me" : "Family"}
              </span>
            ))}
          </div>
        </div>

        {/* Main nav */}
        <div style={{ padding: "16px 12px 4px" }}>
          {NAV_MAIN.map((item) => (
            <NavItem key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>

        {/* Planning section */}
        <div style={{ padding: "16px 12px 4px" }}>
          <div
            style={{
              fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
              textTransform: "uppercase", color: "var(--text-3)",
              padding: "0 8px 8px",
            }}
          >
            Planning
          </div>
          {NAV_PLANNING.map((item) => (
            <NavItem key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>

        {/* Bottom nav */}
        <div style={{ marginTop: "auto", padding: "0 12px" }}>
          {NAV_BOTTOM.map((item) => (
            <NavItem key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>

        {/* User footer */}
        <div style={{ padding: 12, borderTop: "1px solid var(--border)", marginTop: 8 }}>
          <div
            className="user-chip-hover"
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "8px 10px", borderRadius: 8,
              cursor: "pointer", transition: "background 0.15s",
            }}
            onClick={logout}
            title="Sign out"
          >
            <div
              style={{
                width: 28, height: 28, borderRadius: "50%",
                background: "linear-gradient(135deg, oklch(0.6 0.16 270), var(--cyan))",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 600, color: "#fff", flexShrink: 0,
              }}
            >
              {initials}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 12, fontWeight: 500, color: "var(--text)",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}
              >
                {owner?.name ?? "Loading…"}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-3)" }}>
                {viewMode === "family" ? "Family · Pro" : "Pro · FY 25–26"}
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
