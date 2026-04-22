"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sparkline } from "@/components/charts/Sparkline";
import { Donut } from "@/components/charts/Donut";
import { RiskArc } from "@/components/charts/RiskArc";
import type { ViewMode } from "@/components/layout/Sidebar";

// ── Static demo data ─────────────────────────────────────────
const BAR_DATA = [
  { income: 65, expense: 42 }, { income: 58, expense: 50 },
  { income: 72, expense: 38 }, { income: 61, expense: 45 },
  { income: 78, expense: 52 }, { income: 69, expense: 41 }, { income: 82, expense: 48 },
];
const MONTHS = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"];

const ALL_INSIGHTS = [
  { id: 1, type: "amber", label: "Tax Opportunity", bold: "₹32K unrealized loss", rest: " in INFY offsets ₹58K STCG. Harvest before Mar 31.", cta: "View holdings →", route: "/tax" },
  { id: 2, type: "cyan", label: "LTCG Window", bold: "HDFCBANK", rest: " crosses 1yr on May 12. Wait 21 days to save ~₹4,800.", cta: "See tax preview →", route: "/tax" },
  { id: 3, type: "red", label: "Cash Drag", bold: "₹2.4L idle", rest: " >30d in savings. Liquid fund ~7% p.a. earns ₹1,400/mo more.", cta: "Explore →", route: "/accounts" },
  { id: 4, type: "green", label: "SIP Health", bold: "5 SIPs active", rest: ". Next debit ₹35K on May 1. Parag Parikh leads (+19.2%).", cta: null, route: "/investments" },
];

// ── Helpers ───────────────────────────────────────────────────
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

// ── Dashboard Page ────────────────────────────────────────────
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

  const isFamily = viewMode === "family";
  const firstName = owner?.name?.split(" ")[0] ?? "there";
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  const nwData    = isFamily ? [14.2, 15.1, 15.8, 16.5, 17.1, 17.8, 18.4] : [12.1, 12.8, 13.2, 13.9, 14.5, 14.8, 15.1];
  const portData  = isFamily ? [9.1, 9.8, 10.1, 9.6, 10.4, 10.9, 11.2]    : [7.2, 7.8, 8.1, 7.6, 8.4, 8.9, 9.2];
  const nwLabel   = isFamily ? "₹18.4Cr" : "₹15.1Cr";
  const portLabel = isFamily ? "₹11.2Cr" : "₹9.2Cr";
  const cfLabel   = isFamily ? "+₹7.8L"  : "+₹5.5L";
  const savRate   = isFamily ? "61%"      : "67%";

  const GOALS_DATA = [
    { name: "New Home",       pct: 100, color: "var(--green)", cur: "₹18L",  target: "₹18L"  },
    { name: "Emergency Fund", pct: 70,  color: "var(--amber)", cur: "₹3.5L", target: "₹5L"   },
    { name: "Europe Trip",    pct: 30,  color: "var(--red)",   cur: "₹45K",  target: "₹1.5L" },
    { name: "Kid's Education",pct: 22,  color: "var(--cyan)",  cur: "₹2.2L", target: "₹10L"  },
  ];

  const ACCOUNTS = [
    { icon: "🏦", name: "HDFC Savings", sub: "Last sync 2m ago", val: "₹4.2L", bg: "rgba(0,180,140,0.12)" },
    { icon: "📈", name: "Zerodha",      sub: "47 holdings",      val: "₹6.1L", bg: "rgba(0,160,220,0.12)" },
    { icon: "💼", name: "MF Portfolio", sub: "12 schemes",       val: "₹3.1L", bg: "rgba(160,100,240,0.12)"},
    { icon: "💳", name: "HDFC Credit",  sub: "Due May 5",        val: "−₹32K", bg: "rgba(240,80,80,0.12)", negative: true },
  ];

  const insights = ALL_INSIGHTS.filter((i) => !dismissed.includes(i.id));
  const maxB = 82;

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
        <HlTag color="green">3 goals on track</HlTag>
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

        {/* Main grid — Row 1: NW(3) + Cashflow(5) + Portfolio(4) */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 12 }}>

          {/* Net Worth */}
          <Tile span={3} onClick={() => router.push("/networth")}>
            <TileLabel icon={<LiveDot />}>
              Net Worth{isFamily && (
                <span style={{ fontSize: 9, background: "oklch(0.6 0.12 270 / 0.15)", color: "oklch(0.6 0.12 270)", padding: "1px 5px", borderRadius: 3, fontWeight: 600, marginLeft: 4 }}>FAMILY</span>
              )}
            </TileLabel>
            <TileValue size="lg">{nwLabel}</TileValue>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <Delta dir="up">▲ ₹42L</Delta>
              <Delta dir="up">+2.9%</Delta>
              <span style={{ fontSize: 10, color: "var(--text-3)" }}>vs last month</span>
            </div>
            <Sparkline data={nwData} color="oklch(0.76 0.16 195)" height={44} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-3)", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
              <span>Oct</span><span>Apr</span>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6 }}>
              Equity <strong style={{ color: "var(--text-2)" }}>{isFamily ? "₹11.2Cr" : "₹9.2Cr"}</strong> · MF{" "}
              <strong style={{ color: "var(--text-2)" }}>{isFamily ? "₹4.8Cr" : "₹3.1Cr"}</strong> · Cash{" "}
              <strong style={{ color: "var(--text-2)" }}>{isFamily ? "₹2.4Cr" : "₹2.8Cr"}</strong>
            </div>
          </Tile>

          {/* Cashflow */}
          <Tile span={5} onClick={() => router.push("/transactions")}>
            <TileLabel>Monthly Cashflow</TileLabel>
            <div style={{ display: "flex", gap: 20, alignItems: "flex-end", marginBottom: 10 }}>
              <div>
                <TileValue color="var(--green)">{cfLabel}</TileValue>
                <div style={{ display: "flex", gap: 6 }}>
                  <Delta dir="up">▲ ₹60K</Delta>
                  <Delta dir="up">+12.2%</Delta>
                </div>
              </div>
              <div style={{ display: "flex", gap: 20 }}>
                {[
                  { label: "Income",   val: isFamily ? "+₹11.4L" : "+₹8.2L", color: "var(--green)" },
                  { label: "Expenses", val: isFamily ? "−₹3.6L"  : "−₹2.7L", color: "var(--red)"   },
                  { label: "Savings",  val: savRate,                           color: "var(--green)" },
                ].map((s) => (
                  <div key={s.label}>
                    <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>{s.label}</div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: s.color }}>{s.val}</div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 72 }}>
              {BAR_DATA.map((b, i) => (
                <div key={i} style={{ flex: 1, display: "flex", gap: 1.5, alignItems: "flex-end" }}>
                  <div style={{ flex: 1, borderRadius: "2px 2px 0 0", minHeight: 2, height: `${(b.income / maxB) * 100}%`, background: "var(--green)", opacity: 0.7 }} />
                  <div style={{ flex: 1, borderRadius: "2px 2px 0 0", minHeight: 2, height: `${(b.expense / maxB) * 100}%`, background: "var(--red)", opacity: 0.6 }} />
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
              {MONTHS.map((m) => <div key={m} style={{ flex: 1, textAlign: "center", fontSize: 9, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{m}</div>)}
            </div>
          </Tile>

          {/* Portfolio */}
          <Tile span={4} onClick={() => router.push("/investments")}>
            <TileLabel>Portfolio</TileLabel>
            <div style={{ display: "flex", gap: 14, alignItems: "flex-start", marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
                  {[
                    { label: "Value",      val: portLabel,                              color: "var(--cyan)"  },
                    { label: "Today P&L",  val: isFamily ? "+₹2.36L" : "+₹1.94L",      color: "var(--green)" },
                    { label: "XIRR",       val: "18.4%",                               color: "var(--green)" },
                  ].map((k) => (
                    <div key={k.label}>
                      <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3 }}>{k.label}</div>
                      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, fontWeight: 500, color: k.color }}>{k.val}</div>
                    </div>
                  ))}
                </div>
                <Sparkline data={portData} color="oklch(0.76 0.16 195)" height={46} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-3)", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
                  <span>Oct</span><span>+27.4% vs Nifty</span>
                </div>
              </div>
              <div style={{ flexShrink: 0 }}>
                <Donut size={72} segments={[
                  { value: 58, color: "oklch(0.76 0.16 195)" },
                  { value: 28, color: "oklch(0.73 0.16 145)" },
                  { value: 14, color: "oklch(0.76 0.16 65)"  },
                ]} />
                <div style={{ fontSize: 9, color: "var(--text-3)", textAlign: "center", marginTop: 4 }}>EQ/MF/Cash</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Delta dir="up">+2.1% today</Delta>
              <span style={{ fontSize: 11, color: "var(--amber)", background: "var(--amber-dim)", padding: "2px 7px", borderRadius: 4, fontFamily: "JetBrains Mono, monospace" }}>⚠ Concentrated</span>
            </div>
          </Tile>

          {/* Goals */}
          <Tile span={4} onClick={() => router.push("/goals")}>
            <TileLabel>Goals</TileLabel>
            <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
              <TileValue size="sm">4 active</TileValue>
              <Delta dir="up">3 on track</Delta>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {GOALS_DATA.map((g) => (
                <div key={g.name}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                    <span style={{ fontSize: 12, color: "var(--text-2)" }}>{g.name}</span>
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: g.color }}>{g.pct}%</span>
                  </div>
                  <div style={{ height: 4, background: "var(--bg3)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${g.pct}%`, height: "100%", borderRadius: 2, background: g.color, transition: "width 0.8s ease" }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>
                    <span>{g.cur}</span><span>{g.target}</span>
                  </div>
                </div>
              ))}
            </div>
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

          {/* Accounts */}
          <Tile span={3} onClick={() => router.push("/accounts")}>
            <TileLabel>Accounts</TileLabel>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
              <TileValue size="sm">{isFamily ? "₹9.2L" : "₹6.7L"}</TileValue>
              <span style={{ fontSize: 10, color: "var(--text-3)" }}>liquid</span>
            </div>
            {ACCOUNTS.map((a) => (
              <div key={a.name} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <div style={{ width: 28, height: 28, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, flexShrink: 0, background: a.bg }}>{a.icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: "var(--text-2)" }}>{a.name}</div>
                  <div style={{ fontSize: 10, color: "var(--text-3)" }}>{a.sub}</div>
                </div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: (a as typeof a & { negative?: boolean }).negative ? "var(--red)" : "var(--text)" }}>{a.val}</div>
              </div>
            ))}
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
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>Last sync <strong style={{ color: "var(--text-2)" }}>2 min ago</strong> · 847 txns</span>
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

// ── Helpers ───────────────────────────────────────────────────
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
