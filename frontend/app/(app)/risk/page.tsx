"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { RiskArc } from "@/components/charts/RiskArc";
import { useAuth } from "@/lib/auth";
import { useAccounts, useProfile, useTransactions, useHoldings } from "@/lib/queries";

const METRICS = [
  { label: "Beta",          val: "0.88",   desc: "vs Nifty 50",      up: true  },
  { label: "Sharpe Ratio",  val: "1.35",   desc: "12-mo rolling",    up: true  },
  { label: "Alpha",         val: "+4.2%",  desc: "annualised",       up: true  },
  { label: "Max Drawdown",  val: "−18.5%", desc: "COVID low",        up: false },
  { label: "Volatility",    val: "22.4%",  desc: "annualised σ",     up: false },
  { label: "Sortino",       val: "1.82",   desc: "downside ratio",   up: true  },
];

const STRESS = [
  { scenario: "COVID Crash (Mar 2020)",  impact: "−31.2%", recovery: "8 mo",  color: "oklch(0.66 0.18 25)"  },
  { scenario: "2008 Crisis",             impact: "−52.4%", recovery: "18 mo", color: "oklch(0.66 0.18 25)"  },
  { scenario: "Rate Hike Cycle",         impact: "−12.8%", recovery: "4 mo",  color: "oklch(0.76 0.16 65)"  },
  { scenario: "Bull Run +30%",           impact: "+28.4%", recovery: "—",     color: "oklch(0.73 0.16 145)" },
];

const APPETITE_META: Record<string, { score: number; label: string; color: string }> = {
  conservative: { score: 0.28, label: "Conservative",  color: "oklch(0.76 0.16 195)" },
  moderate:     { score: 0.55, label: "Moderate",       color: "oklch(0.76 0.16 65)"  },
  aggressive:   { score: 0.82, label: "Aggressive",     color: "oklch(0.66 0.18 25)"  },
};

const ASSET_CLASS_COLORS: Record<string, string> = {
  EQUITY:       "oklch(0.76 0.16 195)",
  MUTUAL_FUND:  "oklch(0.73 0.16 145)",
  GOLD:         "oklch(0.82 0.14 80)",
  REAL_ESTATE:  "oklch(0.6 0.12 270)",
  FIXED_INCOME: "oklch(0.76 0.16 65)",
  CASH:         "oklch(0.73 0.16 145)",
};

export default function RiskPage() {
  const { owner } = useAuth();
  const ownerId = owner?.owner_id;
  const { data: prof } = useProfile(ownerId);
  const { data: accountsList } = useAccounts(ownerId);
  const { data: holdingsData } = useHoldings(ownerId);

  const threeMonthsAgo = (() => {
    const d = new Date(); d.setMonth(d.getMonth() - 3); return d.toISOString().slice(0, 10);
  })();
  const txnFilters = useMemo(
    () => ({ date_from: threeMonthsAgo, transaction_type: "DEBIT" as const, limit: 500 }),
    [threeMonthsAgo]
  );
  const { data: recentTxns } = useTransactions(ownerId, txnFilters);

  const riskAppetite = prof?.risk_appetite ?? "moderate";
  const meta = APPETITE_META[riskAppetite] ?? APPETITE_META.moderate;
  const scoreInt = Math.round(meta.score * 100);

  const monthlyIncome = prof?.total_monthly_income_paise ?? 0;
  const emis = (prof?.emis_json as Array<{ monthly_paise?: number }> | undefined) ?? [];
  const totalEMIPaise = emis.reduce((s, e) => s + (e.monthly_paise ?? 0), 0);
  const dti = monthlyIncome > 0 ? (totalEMIPaise / monthlyIncome) * 100 : null;
  const dtiStr = dti !== null ? `${dti.toFixed(1)}%` : "—";
  const dtiColor = dti === null ? "var(--text-2)" : dti > 40 ? "oklch(0.66 0.18 25)" : dti > 20 ? "oklch(0.76 0.16 65)" : "oklch(0.73 0.16 145)";

  const avgMonthlyExpense = useMemo(() => {
    if (!recentTxns?.length) return 0;
    return Math.floor(recentTxns.reduce((s, t) => s + t.amount_paise, 0) / 3 / 100);
  }, [recentTxns]);
  const efTarget = avgMonthlyExpense > 0 ? `₹${((avgMonthlyExpense * 6) / 100000).toFixed(1)}L` : "—";

  const accountTypes = useMemo(() => {
    const types = new Set((accountsList ?? []).map((a) => a.account_type));
    return Array.from(types).length;
  }, [accountsList]);
  const divScore = Math.min(accountTypes * 20, 100);

  // F9: Concentration from holdings by asset_class
  const concentration = useMemo(() => {
    const holdings = holdingsData ?? [];
    if (holdings.length === 0) return null;

    const totalPaise = holdings.reduce((s, h) => s + (h.current_value_paise ?? 0), 0);
    if (totalPaise === 0) return null;

    const byClass = new Map<string, number>();
    for (const h of holdings) {
      byClass.set(h.asset_class, (byClass.get(h.asset_class) ?? 0) + (h.current_value_paise ?? 0));
    }
    return Array.from(byClass.entries())
      .sort(([, a], [, b]) => b - a)
      .map(([cls, val]) => ({
        label: cls.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
        pct: Math.round((val / totalPaise) * 100),
        color: ASSET_CLASS_COLORS[cls.toUpperCase()] ?? "var(--text-3)",
      }));
  }, [holdingsData]);

  // Fallback static concentration when no holdings data
  const STATIC_CONCENTRATION = [
    { label: "HDFC Group",  pct: 32, color: "oklch(0.76 0.16 195)" },
    { label: "IT Sector",   pct: 22, color: "oklch(0.73 0.16 145)" },
    { label: "ZOMATO",      pct: 19, color: "oklch(0.76 0.16 65)"  },
    { label: "Consumer",    pct: 14, color: "oklch(0.6 0.12 270)"  },
    { label: "Others",      pct: 13, color: "var(--text-3)"        },
  ];

  const concentrationData = concentration ?? STATIC_CONCENTRATION;
  const topHolding = concentrationData[0];
  const isOverweight = topHolding && topHolding.pct > 30;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Risk Analysis"
        subtitle={`Portfolio risk profile · Score ${scoreInt} / 100`}
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* Top section: Arc + Metrics grid */}
        <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 12, marginBottom: 14 }}>
          {/* Risk arc card */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "18px 16px", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, alignSelf: "flex-start" }}>Risk Score</div>
            <RiskArc value={meta.score} />
            <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 28, fontWeight: 700, color: meta.color, lineHeight: 1 }}>{scoreInt}</div>
            <div style={{ fontSize: 11, color: meta.color, background: meta.color + "18", padding: "3px 10px", borderRadius: 20, fontWeight: 600 }}>{meta.label}</div>
            <div style={{ marginTop: 8, width: "100%" }}>
              {[
                { label: "DTI Ratio", val: dtiStr, color: dtiColor },
                { label: "EF Target", val: efTarget, color: "var(--text-2)" },
                { label: "Asset Types", val: accountTypes > 0 ? `${accountTypes} types` : "—", color: divScore >= 60 ? "oklch(0.73 0.16 145)" : "oklch(0.76 0.16 65)" },
              ].map((r) => (
                <div key={r.label} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 10, color: "var(--text-3)" }}>{r.label}</span>
                  <span style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", color: r.color }}>{r.val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 3×2 metrics grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gridTemplateRows: "repeat(2, 1fr)", gap: 8 }}>
            {METRICS.map((m) => (
              <MetricCard key={m.label} {...m} />
            ))}
          </div>
        </div>

        {/* Concentration + Stress test */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {/* Concentration (F9) */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Concentration Risk</span>
              {isOverweight && (
                <span style={{ fontSize: 10, background: "oklch(0.66 0.18 25 / 0.1)", color: "oklch(0.66 0.18 25)", padding: "2px 8px", borderRadius: 4 }}>
                  ⚠ {topHolding.label} overweight
                </span>
              )}
            </div>
            {concentrationData.map((c, i) => (
              <div key={i} style={{ marginBottom: i < concentrationData.length - 1 ? 10 : 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: "var(--text-2)" }}>{c.label}</span>
                  <span style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", color: c.color }}>{c.pct}%</span>
                </div>
                <div style={{ height: 4, background: "var(--bg3)", borderRadius: 2 }}>
                  <div style={{ height: "100%", width: `${c.pct}%`, background: c.color, borderRadius: 2 }} />
                </div>
              </div>
            ))}
            {!concentration && (
              <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-3)", fontStyle: "italic" }}>
                Showing placeholder data — ingest holdings to see real concentration
              </div>
            )}
          </div>

          {/* Stress test */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Stress Test Scenarios</div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.02)" }}>
                  {["Scenario", "Impact", "Recovery"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "7px 14px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {STRESS.map((s, i) => (
                  <StressRow key={i} {...s} last={i === STRESS.length - 1} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, val, desc, up }: { label: string; val: string; desc: string; up: boolean }) {
  const [hovered, setHovered] = useState(false);
  const color = up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)";
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: "var(--surface)", border: `1px solid ${hovered ? color + "50" : "var(--border)"}`, borderRadius: 10, padding: "14px 16px", transition: "all 0.15s" }}
    >
      <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 22, color, fontWeight: 600, marginBottom: 4 }}>{val}</div>
      <div style={{ fontSize: 10, color: "var(--text-3)" }}>{desc}</div>
    </div>
  );
}

function StressRow({ scenario, impact, recovery, color, last }: { scenario: string; impact: string; recovery: string; color: string; last: boolean }) {
  const [hovered, setHovered] = useState(false);
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ borderBottom: last ? "none" : "1px solid var(--border)", background: hovered ? "rgba(255,255,255,0.02)" : "transparent" }}
    >
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)" }}>{scenario}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, fontFamily: "JetBrains Mono, monospace", color }}>{impact}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-3)" }}>{recovery}</td>
    </tr>
  );
}
