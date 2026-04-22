"use client";

import React, { useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { Sparkline } from "@/components/charts/Sparkline";
import { Donut } from "@/components/charts/Donut";

const NW_DATA    = [10.2, 11.1, 11.8, 12.5, 13.1, 13.9, 14.2, 14.8, 15.1];
const NW_MONTHS  = ["Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"];

const ASSETS = [
  { label: "Direct Equity", val: "₹6.1Cr", pct: 40,  color: "oklch(0.76 0.16 195)", delta: "+₹24L",  up: true  },
  { label: "Mutual Funds",  val: "₹3.1Cr", pct: 21,  color: "oklch(0.73 0.16 145)", delta: "+₹12L",  up: true  },
  { label: "Real Estate",   val: "₹4.2Cr", pct: 28,  color: "oklch(0.6 0.12 270)",  delta: "+₹8L",   up: true  },
  { label: "Cash & FD",     val: "₹1.6Cr", pct: 11,  color: "oklch(0.76 0.16 65)",  delta: "+₹2L",   up: true  },
  { label: "Gold",          val: "₹45K",   pct: 0.3, color: "oklch(0.82 0.14 80)",  delta: "+₹3K",   up: true  },
  { label: "Liabilities",   val: "−₹32K",  pct: 0.2, color: "oklch(0.66 0.18 25)",  delta: "−₹8K",   up: false },
];

const HISTORY = [
  { month: "Apr 25", nw: "₹15.1Cr", change: "+₹42L",  pct: "+2.9%", up: true  },
  { month: "Mar 25", nw: "₹14.8Cr", change: "+₹32L",  pct: "+2.2%", up: true  },
  { month: "Feb 25", nw: "₹14.5Cr", change: "+₹18L",  pct: "+1.3%", up: true  },
  { month: "Jan 25", nw: "₹14.2Cr", change: "+₹30L",  pct: "+2.2%", up: true  },
  { month: "Dec 24", nw: "₹13.9Cr", change: "−₹32L",  pct: "−2.2%", up: false },
  { month: "Nov 24", nw: "₹13.1Cr", change: "+₹55L",  pct: "+4.4%", up: true  },
];

const RANGES = ["3M", "6M", "FY", "All"] as const;

export default function NetWorthPage() {
  const [range, setRange] = useState<string>("FY");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Net Worth"
        subtitle="Total assets minus liabilities · Live"
        live
        actions={
          <div style={{ display: "flex", gap: 2, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 3 }}>
            {RANGES.map((r) => (
              <button key={r} onClick={() => setRange(r)}
                style={{
                  padding: "3px 10px", borderRadius: 5,
                  border: r === range ? "1px solid var(--border-bright)" : "none",
                  background: r === range ? "var(--bg3)" : "none",
                  color: r === range ? "oklch(0.76 0.16 195)" : "var(--text-2)",
                  fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                }}
              >{r}</button>
            ))}
          </div>
        }
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* Hero value */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 44, fontWeight: 500, color: "var(--text)", letterSpacing: "-0.04em", lineHeight: 1 }}>₹15.1Cr</div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
            <span style={{ background: "oklch(0.73 0.16 145 / 0.15)", color: "oklch(0.73 0.16 145)", padding: "3px 9px", borderRadius: 5, fontSize: 12, fontFamily: "JetBrains Mono, monospace" }}>▲ ₹42L (+2.9%)</span>
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>vs last month</span>
            <span style={{ background: "oklch(0.73 0.16 145 / 0.15)", color: "oklch(0.73 0.16 145)", padding: "3px 9px", borderRadius: 5, fontSize: 12, fontFamily: "JetBrains Mono, monospace" }}>▲ +47.9% this FY</span>
          </div>
        </div>

        {/* Sparkline */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 20px", marginBottom: 14 }}>
          <Sparkline data={NW_DATA} color="oklch(0.76 0.16 195)" height={100} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
            {NW_MONTHS.map((m) => <span key={m} style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{m}</span>)}
          </div>
        </div>

        {/* Asset cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 14 }}>
          {ASSETS.map((a) => (
            <AssetCard key={a.label} {...a} />
          ))}
        </div>

        {/* Allocation + History */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Allocation</div>
            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
              <Donut size={90} segments={ASSETS.filter((a) => a.pct > 1).map((a) => ({ value: a.pct, color: a.color }))} />
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {ASSETS.filter((a) => a.pct > 1).map((a) => (
                  <div key={a.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: a.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: "var(--text-2)" }}>{a.label}</span>
                    <span style={{ fontSize: 10, color: "var(--text-3)", marginLeft: "auto", fontFamily: "JetBrains Mono, monospace", paddingLeft: 8 }}>{a.pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Monthly History</div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Month", "Net Worth", "Change", "%"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {HISTORY.map((row) => (
                  <tr key={row.month} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "7px 8px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{row.month}</td>
                    <td style={{ padding: "7px 8px", fontSize: 12, color: "var(--text)", fontFamily: "JetBrains Mono, monospace" }}>{row.nw}</td>
                    <td style={{ padding: "7px 8px", fontSize: 12, color: row.up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{row.change}</td>
                    <td style={{ padding: "7px 8px", fontSize: 12, color: row.up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{row.pct}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function AssetCard({ label, val, pct, color, delta, up }: { label: string; val: string; pct: number; color: string; delta: string; up: boolean }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: "var(--surface)", border: `1px solid ${hovered ? "var(--border-bright)" : "var(--border)"}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer", transition: "all 0.15s" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: "var(--text)", marginBottom: 4 }}>{val}</div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, color: up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{delta}</span>
        <span style={{ fontSize: 10, color: "var(--text-3)" }}>{pct}%</span>
      </div>
      <div style={{ marginTop: 6, height: 3, background: "var(--bg3)", borderRadius: 2 }}>
        <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, background: color, borderRadius: 2 }} />
      </div>
    </div>
  );
}
