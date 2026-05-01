"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface ScreenHeaderProps {
  title: string;
  subtitle?: string;
  live?: boolean;
  onBack?: () => void;
  tabs?: React.ReactNode;
  actions?: React.ReactNode;
}

export function ScreenHeader({ title, subtitle, live, onBack, tabs, actions }: ScreenHeaderProps) {
  const router = useRouter();
  const handleBack = onBack ?? (() => router.push("/"));
  const [btnHovered, setBtnHovered] = useState(false);

  return (
    <div
      style={{
        padding: "14px 24px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexShrink: 0,
      }}
    >
      <button
        onClick={handleBack}
        onMouseEnter={() => setBtnHovered(true)}
        onMouseLeave={() => setBtnHovered(false)}
        style={{
          background: "var(--surface)",
          border: `1px solid ${btnHovered ? "var(--border-bright)" : "var(--border)"}`,
          borderRadius: 7,
          padding: "5px 12px",
          color: btnHovered ? "var(--text)" : "var(--text-2)",
          fontSize: 12,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 5,
          fontFamily: "Space Grotesk, sans-serif",
          whiteSpace: "nowrap",
          transition: "all 0.15s",
        }}
      >
        ← Dashboard
      </button>
      <div style={{ flex: 1 }}>
        <div
          style={{
            fontSize: 18,
            fontWeight: 600,
            color: "var(--text)",
            letterSpacing: "-0.02em",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {title}
          {live && (
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "oklch(0.73 0.16 145)",
                boxShadow: "0 0 6px oklch(0.73 0.16 145)",
                display: "inline-block",
                animation: "pulse-dot 2s ease-in-out infinite",
              }}
            />
          )}
        </div>
        {subtitle && (
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>
            {subtitle}
          </div>
        )}
      </div>
      {(tabs || actions) && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
          {tabs}
          {actions}
        </div>
      )}
    </div>
  );
}
