"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sparkline } from "@/components/charts/Sparkline";
import { Donut } from "@/components/charts/Donut";
import { RiskArc } from "@/components/charts/RiskArc";
import { useGoals, useAccounts, useTransactions, useNetWorth, useHoldings } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";
import type { ViewMode } from "@/components/layout/Sidebar";

const ALL_INSIGHTS = [
  { id: 1, type: "amber", label: "Tax Opportunity", bold: "₹32K unrealized loss", rest: " in INFY offsets ₹58K STCG. Harvest before Mar 31.", cta: "View holdings →", route: "/tax" },
  { id: 2, type: "cyan", label: "LTCG Window", bold: "HDFCBANK", rest: " crosses 1yr on May 12. Wait 21 days to save ~₹4,800.", cta: "See tax preview →", route: "/tax" },
  { id: 3, type: "red", label: "Cash Drag", bold: "₹2.4L idle", rest: " >30d in savings. Liquid fund ~7% p.a. earns ₹1,400/mo more.", cta: "Explore →", route: "/accounts" },
  { id: 4, type: "green", label: "SIP Health", bold: "5 SIPs active", rest: ". Next debit ₹35K on May 1. Parag Parikh leads (+19.2%).", cta: null, route: "/investments" },
];

const GOAL_COLORS = [
  "var(--green)", "var(--cyan)", "var(--amber)", "var(--red)",
];

function goalColor(index: number, pct: number): string {
  if (pct >= 100) return "var(--green)";
  return GOAL_COLORS[index % GOAL_COLORS.length];
}

function accountIcon(type: string): string {
  const icons: Record<string, string> = {
    SAVINGS: "🏦", CURRENT: "🏦", SALARY: "🏦",
    BROKER: "📈", DEMAT: "📈",
    MUTUAL_FUND: "💼",
    CREDIT_CARD: "💳",
    FIXED_DEPOSIT: "🏦",
    LOAN: "💰",
    PPF: "🏛️", NPS: "🏛️",
  };
  return icons[type] ?? "💳";
}

function accountBg(type: string): string {
  const bgs: Record<string, string> = {
    SAVINGS: "rgba(0,180,140,0.12)", CURRENT: "rgba(0,180,140,0.12)", SALARY: "rgba(0,180,140,0.12)",
    BROKER: "rgba(0,160,220,0.12)", DEMAT: "rgba(0,160,220,0.12)",
    MUTUAL_FUND: "rgba(160,100,240,0.12)",
    CREDIT_CARD: "rgba(240,80,80,0.12)",
    LOAN: "rgba(240,80,80,0.12)",
    FIXED_DEPOSIT: "rgba(240,180,0,0.12)",
  };
  return bgs[type] ?? "rgba(120,120,120,0.12)";
}

function LiveDot() {
  return (
    <span
      style={{
        display: "inline-block", width: 6, height: 6, borderRadius: "50%",
        background: "var(--green)", boxShadow: "0 0 6px var(--green)",
        animation: "pulse-dot 2s ease-in-out infinite", flexShrink: 0,
      }}
    />
  );
}

function Delta({ dir, children }: { dir: "up" | "down"; children: React.ReactNode }) {
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 11, fontWeight: 500, padding: "2px 7px", borderRadius: 4,
        background: dir === "up" ? "var(--green-dim)" : "var(--red-dim)",
        color: dir === "up" ? "var(--green)" : "var(--red)",
      }}
    >
      {children}
    </span>
  );
}

function Tile({ children, span, onClick }: { children: React.ReactNode; span: number; onClick?: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        gridColumn: `span ${span}`,
        background: hovered ? "var(--surface-hover)" : "var(--surface)",
        border: `1px solid ${hovered ? "var(--border-bright)" : "var(--border)"}`,
        borderRadius: 12, padding: "18px 20px",
        cursor: "pointer", transition: "all 0.2s",
        position: "relative", overflow: "hidden",
        transform: hovered ? "translateY(-1px)" : "none",
      }}
    >
      <span
        style={{
          position: "absolute", top: 18, right: 18, fontSize: 14,
          color: "var(--text-3)", opacity: hovered ? 1 : 0,
          transform: hovered ? "translateX(2px)" : "none",
          transition: "all 0.2s",
        }}
      >
        →
      </span>
      {children}
    </div>
  );
}

function TileLabel({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
      {icon}{children}
    </div>
  );
}

function TileValue({ children, size = "md", color }: { children: React.ReactNode; size?: "lg" | "md" | "sm"; color?: string }) {
  const fs = { lg: 32, md: 26, sm: 20 }[size];
  return (
    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: fs, fontWeight: 500, color: color ?? "var(--text)", letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 6 }}>
      {children}
    </div>
  );
}

function HlTag({ color, children }: { color: "green" | "amber" | "cyan" | "red"; children: React.ReactNode }) {
  const styles: Record<string, React.CSSProperties> = {
    green: { background: "var(--green-dim)", color: "var(--green)" },
    amber: { background: "var(--amber-dim)", color: "var(--amber)" },
    cyan:  { background: "var(--cyan-dim)",  color: "var(--cyan)"  },
    red:   { background: "var(--red-dim)",   color: "var(--red)"   },
  };
  return (
    <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 500, fontFamily: "JetBrains Mono, monospace", ...styles[color] }}>
      {children}
    </span>
  );
}

function QuickBtn({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "7px 14px", borderRadius: 8,
        background: hovered ? "var(--cyan-dim)" : "var(--surface)",
        border: `1px solid ${hovered ? "var(--cyan)" : "var(--border)"}`,
        fontSize: 12, color: hovered ? "var(--cyan)" : "var(--text-2)",
        cursor: "pointer", transition: "all 0.15s",
        fontFamily: "Space Grotesk, sans-serif",
      }}
    >
      {children}
    </button>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { owner } = useAuth();
  const [timeRange, setTimeRange] = useState("FY");
  const [dismissed, setDismissed] = useState<number[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("individual");

  useEffect(() => {
    const stored = localStorage.getItem("artha-view") as ViewMode | null;
    if (stored === "individual" || stored === "family") setViewMode(stored);
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as ViewMode;
      if (detail === "individual" || detail === "family") setViewMode(detail);
    };
    window.addEventListener("artha-view-change", handler);
    return () => window.removeEventListener("artha-view-change", handler);
  }, []);

  const ownerId = owner?.owner_id;
  const isFamily = viewMode === "family";
  const firstName = owner?.name?.split(" ")[0] ?? "there";
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  // ── Data hooks ────────────────────────────────────────────────
  const { data: goalsData } = useGoals(ownerId);
  const { data: accountsList } = useAccounts(ownerId);
  const { data: netWorthData } = useNetWorth(ownerId);
  const { data: holdingsData } = useHoldings(ownerId);

  const sevenMonthsAgo = (() => {
    const d = new Date(); d.setMonth(d.getMonth() - 7); return d.toISOString().slice(0, 10);
  })();
  const txnFilters = useMemo(() => ({ date_from: sevenMonthsAgo, limit: 500 }), [sevenMonthsAgo]);
  const { data: txns } = useTransactions(ownerId, txnFilters);

  // ── Goals (F1) ────────────────────────────────────────────────
  const activeGoals = useMemo(() => (goalsData ?? []).filter((g) => g.is_active), [goalsData]);

  // ── Accounts (F2) ─────────────────────────────────────────────
  const accountsDisplay = useMemo(() => {
    const list = accountsList ?? [];
    if (list.length === 0) return [];
    return list.slice(0, 4).map((a) => ({
      icon: accountIcon(a.account_type),
      name: a.nickname ?? a.institution,
      sub: a.institution,
      val: a.balance_paise != null ? formatINRShort(Math.abs(a.balance_paise)) : "—",
      bg: accountBg(a.account_type),
      negative: (a.balance_paise ?? 0) < 0,
    }));
  }, [accountsList]);

  const liquidPaise = useMemo(() => {
    return (accountsList ?? [])
      .filter((a) => !["LOAN", "CREDIT_CARD"].includes(a.account_type))
      .reduce((sum, a) => sum + (a.balance_paise ?? 0), 0);
  }, [accountsList]);

  // ── Cashflow bar chart (F3) ───────────────────────────────────
  const { barData, barMonths, cfLabel, incomeLabel, expenseLabel, savingsRate } = useMemo(() => {
    if (!txns?.length) {
      return {
        barData: [] as { income: number; expense: number }[],
        barMonths: [] as string[],
        cfLabel: "—",
        incomeLabel: "—",
        expenseLabel: "—",
        savingsRate: "—",
      };
    }

    const monthMap = new Map<string, { income: number; expense: number }>();
    for (const t of txns) {
      const month = t.transaction_date.slice(0, 7);
      if (!monthMap.has(month)) monthMap.set(month, { income: 0, expense: 0 });
      const m = monthMap.get(month)!;
      if (t.transaction_type === "CREDIT") m.income += t.amount_paise;
      else m.expense += t.amount_paise;
    }

    const sorted = Array.from(monthMap.entries()).sort(([a], [b]) => a.localeCompare(b));
    const last7 = sorted.slice(-7);

    const bd = last7.map(([, v]) => ({ income: v.income, expense: v.expense }));
    const bm = last7.map(([m]) => {
      const [y, mo] = m.split("-");
      return new Date(Number(y), Number(mo) - 1).toLocaleString("en-IN", { month: "short" });
    });

    const latestMonth = last7[last7.length - 1]?.[1];
    const netCF = latestMonth ? latestMonth.income - latestMonth.expense : 0;
    const totalIncome = (latestMonth?.income ?? 0);
    const totalExpense = (latestMonth?.expense ?? 0);
    const rate = totalIncome > 0 ? Math.round(((totalIncome - totalExpense) / totalIncome) * 100) : 0;

    return {
      barData: bd,
      barMonths: bm,
      cfLabel: netCF >= 0 ? `+${formatINRShort(netCF)}` : formatINRShort(netCF),
      incomeLabel: `+${formatINRShort(totalIncome)}`,
      expenseLabel: `−${formatINRShort(totalExpense)}`,
      savingsRate: `${rate}%`,
    };
  }, [txns]);

  const maxBarPaise = useMemo(
    () => Math.max(...barData.map((b) => Math.max(b.income, b.expense)), 1),
    [barData]
  );

  // ── Net Worth (F4) ────────────────────────────────────────────
  const nwPaise = netWorthData?.net_worth_paise ?? 0;
  const nwLabel = nwPaise > 0 ? formatINRShort(nwPaise) : "—";
  const nwSparkData = useMemo(() => {
    const hist = netWorthData?.history ?? [];
    if (hist.length === 0) return [0, 0];
    return hist.slice(-7).map((h) => h.net_worth_paise / 1e7);
  }, [netWorthData]);

  const lastTwoNW = netWorthData?.history.slice(-2) ?? [];
  const nwChangePaise = lastTwoNW.length >= 2
    ? lastTwoNW[1].net_worth_paise - lastTwoNW[0].net_worth_paise
    : 0;
  const nwChangePct = lastTwoNW.length >= 2 && lastTwoNW[0].net_worth_paise > 0
    ? ((nwChangePaise / lastTwoNW[0].net_worth_paise) * 100).toFixed(1)
    : "0.0";

  // ── Portfolio (F4 + F6 preview) ───────────────────────────────
  const portValuePaise = useMemo(
    () => (holdingsData ?? []).reduce((s, h) => s + (h.current_value_paise ?? 0), 0),
    [holdingsData]
  );
  const portLabel = portValuePaise > 0 ? formatINRShort(portValuePaise) : "—";

  // Donut segments from assets_by_category (or holdings if no networth yet)
  const donutSegments = useMemo(() => {
    const cats = netWorthData?.assets_by_category ?? [];
    if (cats.length === 0) return [
      { value: 58, color: "oklch(0.76 0.16 195)" },
      { value: 28, color: "oklch(0.73 0.16 145)" },
      { value: 14, color: "oklch(0.76 0.16 65)" },
    ];
    const colors = ["oklch(0.76 0.16 195)", "oklch(0.73 0.16 145)", "oklch(0.76 0.16 65)", "oklch(0.6 0.12 270)", "oklch(0.82 0.14 80)"];
    return cats.slice(0, 5).map((c, i) => ({ value: c.pct, color: colors[i] }));
  }, [netWorthData]);

  const insights = ALL_INSIGHTS.filter((i) => !dismissed.includes(i.id));

  return (
    <>
      {/* Top bar */}
      <div style={{ padding: "14px 24px", display: "flex", alignItems: "flex-start", justifyContent: "space-between", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 600, color: "var(--text)", letterSpacing: "-0.02em", lineHeight: 1, marginBottom: 4 }}>
            {greeting}, <span style={{ color: "var(--cyan)" }}>{isFamily ? (owner?.name?.split(" ").slice(-1)[0] ?? "Family") + " Family" : firstName}</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-3)", display: "flex", alignItems: "center", gap: 6 }}>
            {isFamily ? "Combined household overview" : "Your financial overview at a glance"}
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <LiveDot /> Live as of {new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ display: "flex", gap: 2, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 3 }}>
            {["1M", "3M", "FY", "All"].map((r) => (
              <button key={r} onClick={() => setTimeRange(r)}
                style={{
                  padding: "4px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                  cursor: "pointer", transition: "all 0.15s", fontFamily: "inherit",
                  border: timeRange === r ? "1px solid var(--border-bright)" : "1px solid transparent",
                  background: timeRange === r ? "var(--bg3)" : "none",
                  color: timeRange === r ? "var(--cyan)" : "var(--text-2)",
                }}
              >{r}</button>
            ))}
          </div>
          <TopIconBtn title="Upload statement">↑</TopIconBtn>
          <TopIconBtn title="Notifications" dot>🔔</TopIconBtn>
        </div>
      </div>

      {/* Headline strip */}
      <div style={{ padding: "10px 24px", background: "linear-gradient(90deg, oklch(0.76 0.16 195 / 0.07), transparent 60%)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
        <LiveDot />
        <span style={{ fontSize: 12.5, color: "var(--text-2)" }}>
          <strong style={{ color: "var(--cyan)" }}>You&apos;re ₹12K under budget</strong> this month
        </span>
        <span style={{ color: "var(--text-3)" }}>·</span>
        <HlTag color="green">{activeGoals.filter((g) => g.progress_pct >= 80).length || 3} goals on track</HlTag>
        <span style={{ color: "var(--text-3)" }}>·</span>
        <HlTag color="amber">Tax due Jul 31</HlTag>
        <span style={{ color: "var(--text-3)" }}>·</span>
        <HlTag color="cyan">Portfolio +2.1% today</HlTag>
        <span
          onClick={() => router.push("/tax")}
          style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-3)", cursor: "pointer", whiteSpace: "nowrap" }}
        >All insights →</span>
      </div>

      {/* Scroll area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 24px 100px" }}>

        {/* Insights strip */}
        {insights.length > 0 && (
          <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
            {insights.map((ins) => (
              <InsightCard
                key={ins.id}
                {...ins}
                onDismiss={() => setDismissed((d) => [...d, ins.id])}
                onClick={() => router.push(ins.route)}
              />
            ))}
          </div>
        )}

        {/* Main grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 12 }}>

          {/* Net Worth (F4) */}
          <Tile span={3} onClick={() => router.push("/networth")}>
            <TileLabel icon={<LiveDot />}>
              Net Worth{isFamily && (
                <span style={{ fontSize: 9, background: "oklch(0.6 0.12 270 / 0.15)", color: "oklch(0.6 0.12 270)", padding: "1px 5px", borderRadius: 3, fontWeight: 600, marginLeft: 4 }}>FAMILY</span>
              )}
            </TileLabel>
            <TileValue size="lg">{nwLabel}</TileValue>
            {nwChangePaise !== 0 && (
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                <Delta dir={nwChangePaise >= 0 ? "up" : "down"}>
                  {nwChangePaise >= 0 ? "▲" : "▼"} {formatINRShort(Math.abs(nwChangePaise))}
                </Delta>
                <Delta dir={nwChangePaise >= 0 ? "up" : "down"}>
                  {nwChangePaise >= 0 ? "+" : ""}{nwChangePct}%
                </Delta>
                <span style={{ fontSize: 10, color: "var(--text-3)" }}>vs last month</span>
              </div>
            )}
            <Sparkline data={nwSparkData} color="oklch(0.76 0.16 195)" height={44} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-3)", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
              <span>{barMonths[0] ?? "Oct"}</span><span>{barMonths[barMonths.length - 1] ?? "Apr"}</span>
            </div>
            {netWorthData && (
              <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6 }}>
                Assets <strong style={{ color: "var(--text-2)" }}>{formatINRShort(netWorthData.total_assets_paise)}</strong>
                {netWorthData.total_liabilities_paise > 0 && (
                  <> · Liab <strong style={{ color: "var(--red)" }}>{formatINRShort(netWorthData.total_liabilities_paise)}</strong></>
                )}
              </div>
            )}
          </Tile>

          {/* Cashflow (F3) */}
          <Tile span={5} onClick={() => router.push("/transactions")}>
            <TileLabel>Monthly Cashflow</TileLabel>
            <div style={{ display: "flex", gap: 20, alignItems: "flex-end", marginBottom: 10 }}>
              <div>
                <TileValue color="var(--green)">{cfLabel}</TileValue>
                <div style={{ display: "flex", gap: 6 }}>
                  <Delta dir="up">this month</Delta>
                </div>
              </div>
              <div style={{ display: "flex", gap: 20 }}>
                {[
                  { label: "Income",   val: incomeLabel,   color: "var(--green)" },
                  { label: "Expenses", val: expenseLabel,  color: "var(--red)"   },
                  { label: "Savings",  val: savingsRate,   color: "var(--green)" },
                ].map((s) => (
                  <div key={s.label}>
                    <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>{s.label}</div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: s.color }}>{s.val}</div>
                  </div>
                ))}
              </div>
            </div>
            {barData.length > 0 ? (
              <>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 72 }}>
                  {barData.map((b, i) => (
                    <div key={i} style={{ flex: 1, display: "flex", gap: 1.5, alignItems: "flex-end" }}>
                      <div style={{ flex: 1, borderRadius: "2px 2px 0 0", minHeight: 2, height: `${(b.income / maxBarPaise) * 100}%`, background: "var(--green)", opacity: 0.7 }} />
                      <div style={{ flex: 1, borderRadius: "2px 2px 0 0", minHeight: 2, height: `${(b.expense / maxBarPaise) * 100}%`, background: "var(--red)", opacity: 0.6 }} />
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
                  {barMonths.map((m) => <div key={m} style={{ flex: 1, textAlign: "center", fontSize: 9, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{m}</div>)}
                </div>
              </>
            ) : (
              <div style={{ height: 72, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: "var(--text-3)" }}>No transaction data yet</div>
            )}
          </Tile>

          {/* Portfolio */}
          <Tile span={4} onClick={() => router.push("/investments")}>
            <TileLabel>Portfolio</TileLabel>
            <div style={{ display: "flex", gap: 14, alignItems: "flex-start", marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
                  {[
                    { label: "Value", val: portLabel, color: "var(--cyan)" },
                    { label: "Today P&L", val: "—", color: "var(--text-3)" },
                    { label: "XIRR", val: "—", color: "var(--text-3)" },
                  ].map((k) => (
                    <div key={k.label}>
                      <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3 }}>{k.label}</div>
                      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, fontWeight: 500, color: k.color }}>{k.val}</div>
                    </div>
                  ))}
                </div>
                <Sparkline data={nwSparkData} color="oklch(0.76 0.16 195)" height={46} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-3)", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
                  <span>{barMonths[0] ?? "Oct"}</span><span>Portfolio trend</span>
                </div>
              </div>
              <div style={{ flexShrink: 0 }}>
                <Donut size={72} segments={donutSegments} />
                <div style={{ fontSize: 9, color: "var(--text-3)", textAlign: "center", marginTop: 4 }}>By category</div>
              </div>
            </div>
            {holdingsData && holdingsData.length > 0 && (
              <div style={{ display: "flex", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--text-3)", background: "var(--bg3)", padding: "2px 7px", borderRadius: 4, fontFamily: "JetBrains Mono, monospace" }}>
                  {holdingsData.length} holdings
                </span>
              </div>
            )}
          </Tile>

          {/* Goals (F1) */}
          <Tile span={4} onClick={() => router.push("/goals")}>
            <TileLabel>Goals</TileLabel>
            {activeGoals.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--text-3)", textAlign: "center", padding: "20px 0" }}>
                No goals set yet
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
                  <TileValue size="sm">{activeGoals.length} active</TileValue>
                  <Delta dir="up">{activeGoals.filter((g) => g.progress_pct >= 80).length} on track</Delta>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {activeGoals.slice(0, 4).map((g, i) => {
                    const color = goalColor(i, g.progress_pct);
                    return (
                      <div key={g.id}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                          <span style={{ fontSize: 12, color: "var(--text-2)" }}>{g.goal_name}</span>
                          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color }}>{g.progress_pct}%</span>
                        </div>
                        <div style={{ height: 4, background: "var(--bg3)", borderRadius: 2, overflow: "hidden" }}>
                          <div style={{ width: `${Math.min(g.progress_pct, 100)}%`, height: "100%", borderRadius: 2, background: color, transition: "width 0.8s ease" }} />
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>
                          <span>{formatINRShort(g.current_amount_paise)}</span>
                          <span>{formatINRShort(g.target_amount_paise)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </Tile>

          {/* Tax */}
          <Tile span={3} onClick={() => router.push("/tax")}>
            <TileLabel>Tax</TileLabel>
            <TileValue>₹1.8Cr</TileValue>
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              <Delta dir="down">▲ ₹18K</Delta>
              <span style={{ fontSize: 10, color: "var(--text-3)" }}>FY 25–26</span>
            </div>
            {[["STCG", "₹58K"], ["LTCG", "₹1.2L"], ["Income", "₹1.6Cr"], ["Paid", "₹1.5Cr"]].map(([l, v]) => (
              <div key={l} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                <span style={{ fontSize: 11, color: "var(--text-3)" }}>{l}</span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--text-2)" }}>{v}</span>
              </div>
            ))}
            <div style={{ marginTop: 10, padding: "7px 10px", background: "oklch(0.76 0.16 65 / 0.08)", border: "1px solid oklch(0.76 0.16 65 / 0.2)", borderRadius: 7, display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ fontSize: 12 }}>⏰</span>
              <span style={{ fontSize: 11, color: "var(--text-2)" }}>Advance tax due <strong style={{ color: "var(--amber)" }}>Jul 31</strong></span>
            </div>
          </Tile>

          {/* Risk */}
          <Tile span={2} onClick={() => router.push("/risk")}>
            <TileLabel>Risk</TileLabel>
            <RiskArc value={0.55} />
            <div style={{ textAlign: "center", margin: "6px 0 8px" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "var(--amber-dim)", border: "1px solid oklch(0.76 0.16 65 / 0.3)", borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600, color: "var(--amber)" }}>Moderate</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {[["Beta", "0.88"], ["Sharpe", "1.35"], ["Max DD", "−18.5%"]].map(([l, v]) => (
                <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                  <span style={{ color: "var(--text-3)" }}>{l}</span>
                  <span style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--text-2)" }}>{v}</span>
                </div>
              ))}
            </div>
          </Tile>

          {/* Accounts (F2) */}
          <Tile span={3} onClick={() => router.push("/accounts")}>
            <TileLabel>Accounts</TileLabel>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
              <TileValue size="sm">{liquidPaise > 0 ? formatINRShort(liquidPaise) : "—"}</TileValue>
              <span style={{ fontSize: 10, color: "var(--text-3)" }}>liquid</span>
            </div>
            {accountsDisplay.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--text-3)", textAlign: "center", padding: "10px 0" }}>No accounts yet</div>
            ) : (
              accountsDisplay.map((a, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <div style={{ width: 28, height: 28, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, flexShrink: 0, background: a.bg }}>{a.icon}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: "var(--text-2)" }}>{a.name}</div>
                    <div style={{ fontSize: 10, color: "var(--text-3)" }}>{a.sub}</div>
                  </div>
                  <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: a.negative ? "var(--red)" : "var(--text)" }}>{a.val}</div>
                </div>
              ))
            )}
          </Tile>

        </div>

        {/* Quick actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 16 }}>
          <span style={{ fontSize: 11, color: "var(--text-3)", whiteSpace: "nowrap" }}>Quick actions</span>
          <QuickBtn>↑ Upload statement</QuickBtn>
          <QuickBtn>+ Add transaction</QuickBtn>
          <QuickBtn onClick={() => router.push("/advisory/chat")}>✦ Ask Artha</QuickBtn>
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <LiveDot />
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>
              {txns ? `${txns.length} txns loaded` : "Loading..."}
            </span>
          </div>
        </div>
      </div>

      {/* Floating Ask Artha pill */}
      <div
        onClick={() => router.push("/advisory/chat")}
        style={{
          position: "fixed", bottom: 24, right: 24,
          display: "flex", alignItems: "center", gap: 10,
          background: "linear-gradient(135deg, oklch(0.35 0.16 195), oklch(0.3 0.12 250))",
          border: "1px solid var(--cyan-glow)",
          boxShadow: "0 0 24px var(--cyan-glow), 0 8px 32px rgba(0,0,0,0.5)",
          borderRadius: 50, padding: "10px 18px 10px 14px",
          cursor: "pointer", zIndex: 100,
          animation: "pill-float 4s ease-in-out infinite",
          transition: "all 0.2s",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.animation = "none"; e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 0 36px var(--cyan-glow), 0 12px 40px rgba(0,0,0,0.6)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.animation = "pill-float 4s ease-in-out infinite"; e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "0 0 24px var(--cyan-glow), 0 8px 32px rgba(0,0,0,0.5)"; }}
      >
        <div style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--cyan)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12 }}>✦</div>
        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>Ask Artha</span>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--text-3)", background: "rgba(255,255,255,0.08)", border: "1px solid var(--border-bright)", padding: "2px 6px", borderRadius: 4 }}>⌘K</span>
      </div>
    </>
  );
}

function TopIconBtn({ children, title, dot }: { children: React.ReactNode; title?: string; dot?: boolean }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div title={title} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{ width: 32, height: 32, borderRadius: 8, background: "var(--surface)", border: `1px solid ${hovered ? "var(--border-bright)" : "var(--border)"}`, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: hovered ? "var(--text)" : "var(--text-2)", transition: "all 0.15s", position: "relative" }}>
      {children}
      {dot && <span style={{ position: "absolute", top: 4, right: 4, width: 7, height: 7, borderRadius: "50%", background: "var(--amber)", border: "1.5px solid var(--bg2)" }} />}
    </div>
  );
}

function InsightCard({ type, label, bold, rest, cta, onDismiss, onClick }: {
  type: string; label: string; bold: string; rest: string; cta: string | null;
  onDismiss: () => void; onClick: () => void;
}) {
  const accentColor: Record<string, string> = { amber: "var(--amber)", cyan: "var(--cyan)", red: "var(--red)", green: "var(--green)" };
  const [hovered, setHovered] = useState(false);
  return (
    <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onClick={onClick}
      style={{ flex: 1, padding: "11px 14px", background: hovered ? "var(--surface-hover)" : "var(--surface)", border: `1px solid ${hovered ? "var(--border-bright)" : "var(--border)"}`, borderRadius: 10, cursor: "pointer", transition: "all 0.2s", position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, borderRadius: "3px 0 0 3px", background: accentColor[type] ?? "var(--text-3)" }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)" }}>{label}</span>
        <span onClick={(e) => { e.stopPropagation(); onDismiss(); }} style={{ fontSize: 14, color: "var(--text-3)", cursor: "pointer", lineHeight: 1 }}>×</span>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--text)", lineHeight: 1.4 }}>
        <strong>{bold}</strong>{rest}
      </div>
      {cta && <div style={{ marginTop: 6, fontSize: 11, color: "var(--cyan)", cursor: "pointer" }}>{cta}</div>}
    </div>
  );
}
