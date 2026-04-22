"use client";

import React, { useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { Sparkline } from "@/components/charts/Sparkline";
import { useAuth } from "@/lib/auth";
import { useAccounts } from "@/lib/queries";

const DEMO_ACCOUNTS = [
  { icon: "🏦", name: "HDFC Savings",  num: "••••4821",    bal: "₹4.2L",  sub: "Last sync 2m ago",   synced: true,  data: [4.0,3.8,4.1,3.9,4.0,4.2,4.2], color: "oklch(0.73 0.16 145)", type: "Bank",         credit: false },
  { icon: "📈", name: "Zerodha",        num: "DQ8291",      bal: "₹6.1L",  sub: "47 holdings · Live", synced: true,  data: [5.2,5.8,5.5,6.0,5.9,6.2,6.1], color: "oklch(0.76 0.16 195)", type: "Broker",        credit: false },
  { icon: "💼", name: "MF Portfolio",   num: "CAMS Linked", bal: "₹3.1L",  sub: "12 schemes",         synced: true,  data: [2.6,2.7,2.9,3.0,2.9,3.1,3.1], color: "oklch(0.6 0.12 270)",  type: "Mutual Fund",   credit: false },
  { icon: "💳", name: "HDFC Credit",    num: "••••7219",    bal: "−₹32K",  sub: "Due May 5",          synced: true,  data: [0,8,15,22,28,32,32],           color: "oklch(0.66 0.18 25)",  type: "Credit Card",   credit: true  },
  { icon: "🏦", name: "SBI FD",         num: "3 deposits",  bal: "₹80L",   sub: "Matures Jun 2026",   synced: false, data: [72,74,76,78,78,80,80],         color: "oklch(0.76 0.16 65)",  type: "Fixed Deposit", credit: false },
  { icon: "🥇", name: "Digital Gold",   num: "Groww Linked",bal: "₹45K",   sub: "12.4g · ₹3,621/g",  synced: true,  data: [38,40,41,43,44,44,45],         color: "oklch(0.82 0.14 80)",  type: "Commodity",     credit: false },
];

export default function AccountsPage() {
  const { owner } = useAuth();
  const { data: accountsList } = useAccounts(owner?.owner_id);

  // If real accounts exist, merge with demo; otherwise show demo
  const realAccounts = accountsList ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Accounts"
        subtitle={`${DEMO_ACCOUNTS.length} linked accounts · Net liquid ₹6.7L`}
        actions={
          <ActionBtn color="oklch(0.76 0.16 195)">+ Link Account</ActionBtn>
        }
      />
      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* Real accounts summary if available */}
        {realAccounts.length > 0 && (
          <div style={{ background: "oklch(0.76 0.16 195 / 0.05)", border: "1px solid oklch(0.76 0.16 195 / 0.2)", borderRadius: 10, padding: "10px 16px", marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12, color: "var(--cyan)" }}>✦</span>
            <span style={{ fontSize: 12, color: "var(--text-2)" }}>
              {realAccounts.length} account{realAccounts.length > 1 ? "s" : ""} linked via Artha — {realAccounts.map((a) => a.nickname ?? a.institution).join(", ")}
            </span>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {DEMO_ACCOUNTS.map((a) => (
            <AccountCard key={a.name} {...a} />
          ))}
        </div>
      </div>
    </div>
  );
}

function AccountCard({ icon, name, num, bal, sub, synced, data, color, type, credit }: {
  icon: string; name: string; num: string; bal: string; sub: string;
  synced: boolean; data: number[]; color: string; type: string; credit: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: "var(--surface)",
        border: `1px solid ${hovered ? color + "50" : "var(--border)"}`,
        borderRadius: 12, padding: "16px 18px",
        cursor: "pointer", transition: "all 0.2s",
        transform: hovered ? "translateY(-1px)" : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: 9, background: color + "20", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, marginRight: 10 }}>{icon}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{name}</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>{num}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {synced && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "oklch(0.73 0.16 145)", display: "inline-block" }} />}
          <span style={{ fontSize: 9, padding: "1px 6px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3, color: "var(--text-3)" }}>{type}</span>
        </div>
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 22, fontWeight: 500, color: credit ? "oklch(0.66 0.18 25)" : "var(--text)", marginBottom: 8 }}>{bal}</div>
      <Sparkline data={data} color={color} height={36} />
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 8 }}>{sub}</div>
    </div>
  );
}

function ActionBtn({ children, color }: { children: React.ReactNode; color: string }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: "6px 14px",
        background: hovered ? color + "20" : color + "10",
        border: `1px solid ${color + "30"}`,
        borderRadius: 8, color,
        fontSize: 12, cursor: "pointer", fontFamily: "inherit",
        transition: "all 0.15s",
      }}
    >{children}</button>
  );
}
