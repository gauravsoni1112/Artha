"use client";

import React, { useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { Sparkline } from "@/components/charts/Sparkline";
import { Donut } from "@/components/charts/Donut";

const HOLDINGS = [
  { name: "HDFCBANK",           type: "eq", avg: "₹1,420", ltp: "₹1,612", pl: "+₹4.6L",  plp: "+13.5%", xirr: "14.2%", day: "+0.8%",  up: true  },
  { name: "RELIANCE",           type: "eq", avg: "₹2,680", ltp: "₹2,921", pl: "+₹4.3L",  plp: "+9.0%",  xirr: "11.8%", day: "+1.2%",  up: true  },
  { name: "TCS",                type: "eq", avg: "₹3,200", ltp: "₹3,688", pl: "+₹15.6L", plp: "+15.3%", xirr: "18.9%", day: "+0.5%",  up: true  },
  { name: "INFY",               type: "eq", avg: "₹1,580", ltp: "₹1,492", pl: "−₹4.4L",  plp: "−5.6%",  xirr: "−5.1%", day: "−0.9%",  up: false },
  { name: "ZOMATO",             type: "eq", avg: "₹182",   ltp: "₹224",   pl: "+₹17.6L", plp: "+23.1%", xirr: "31.2%", day: "+2.1%",  up: true  },
  { name: "BAJFINANCE",         type: "eq", avg: "₹6,800", ltp: "₹7,210", pl: "+₹4.9L",  plp: "+6.0%",  xirr: "9.4%",  day: "+0.4%",  up: true  },
  { name: "Parag Parikh Flexi", type: "mf", avg: "—",      ltp: "₹82.4",  pl: "+₹58L",   plp: "+19.2%", xirr: "19.2%", day: "+0.6%",  up: true  },
  { name: "Mirae Asset ELSS",   type: "mf", avg: "—",      ltp: "₹34.2",  pl: "+₹12L",   plp: "+16.8%", xirr: "16.8%", day: "+0.3%",  up: true  },
];

const SECTORS = [
  { name: "Banking",  pct: 35, color: "oklch(0.76 0.16 195)" },
  { name: "IT",       pct: 22, color: "oklch(0.73 0.16 145)" },
  { name: "Consumer", pct: 18, color: "oklch(0.76 0.16 65)"  },
  { name: "Finance",  pct: 15, color: "oklch(0.6 0.12 270)"  },
  { name: "Other",    pct: 10, color: "var(--text-3)"         },
];

const KPIS = [
  { label: "Portfolio Value", val: "₹9.2Cr",  color: "oklch(0.76 0.16 195)" },
  { label: "Today's P&L",     val: "+₹1.94L", color: "oklch(0.73 0.16 145)" },
  { label: "Overall P&L",     val: "+₹2.8Cr", color: "oklch(0.73 0.16 145)" },
  { label: "XIRR",            val: "18.4%",   color: "oklch(0.73 0.16 145)" },
  { label: "Invested",        val: "₹6.4Cr",  color: "var(--text)"          },
];

const PORT_SPARK = [7.2, 7.8, 8.1, 7.6, 8.4, 8.9, 9.2];

type FilterType = "all" | "eq" | "mf";

export default function InvestmentsPage() {
  const [filter, setFilter] = useState<FilterType>("all");
  const filtered = filter === "all" ? HOLDINGS : HOLDINGS.filter((h) => h.type === filter);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Portfolio"
        subtitle="Direct equity + mutual funds · 8 holdings"
        live
        actions={<ActionBtn color="oklch(0.76 0.16 195)">+ Add Holding</ActionBtn>}
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 14 }}>
          {KPIS.map((k) => (
            <div key={k.label} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px" }}>
              <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 6 }}>{k.label}</div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: k.color }}>{k.val}</div>
            </div>
          ))}
        </div>

        {/* Sector + sparkline */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 14 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Sector Allocation</span>
              <span style={{ fontSize: 11, color: "oklch(0.66 0.18 25)", background: "oklch(0.66 0.18 25 / 0.1)", padding: "2px 8px", borderRadius: 4 }}>⚠ Banking overweight</span>
            </div>
            <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", gap: 1, marginBottom: 10 }}>
              {SECTORS.map((s) => <div key={s.name} style={{ flex: s.pct, background: s.color, opacity: 0.8 }} />)}
            </div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {SECTORS.map((s) => (
                <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: s.color }} />
                  <span style={{ fontSize: 11, color: "var(--text-2)" }}>{s.name}</span>
                  <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{s.pct}%</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 8 }}>Allocation</div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <Donut size={80} segments={[
                { value: 58, color: "oklch(0.76 0.16 195)" },
                { value: 28, color: "oklch(0.73 0.16 145)" },
                { value: 14, color: "oklch(0.76 0.16 65)"  },
              ]} />
              <div style={{ flex: 1 }}>
                <Sparkline data={PORT_SPARK} color="oklch(0.76 0.16 195)" height={40} />
                <div style={{ fontSize: 9, color: "var(--text-3)", marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>Oct – Apr · +27.4%</div>
              </div>
            </div>
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          {(["all", "eq", "mf"] as FilterType[]).map((k) => {
            const labels = { all: "All", eq: "Equity", mf: "Mutual Funds" };
            const active = filter === k;
            return (
              <button key={k} onClick={() => setFilter(k)}
                style={{
                  padding: "5px 14px", borderRadius: 7,
                  border: `1px solid ${active ? "oklch(0.76 0.16 195 / 0.4)" : "var(--border)"}`,
                  background: active ? "oklch(0.76 0.16 195 / 0.08)" : "var(--surface)",
                  color: active ? "oklch(0.76 0.16 195)" : "var(--text-2)",
                  fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                }}
              >{labels[k]}</button>
            );
          })}
        </div>

        {/* Holdings table */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                {["Holding", "Type", "Avg Buy", "LTP / NAV", "P&L", "P&L %", "XIRR", "Day"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "8px 14px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((h) => (
                <HoldingRow key={h.name} {...h} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function HoldingRow({ name, type, avg, ltp, pl, plp, xirr, day, up }: typeof HOLDINGS[0]) {
  const [hovered, setHovered] = useState(false);
  const gain  = "oklch(0.73 0.16 145)";
  const loss  = "oklch(0.66 0.18 25)";
  const typeBg  = type === "eq" ? "oklch(0.76 0.16 195 / 0.1)" : "oklch(0.73 0.16 145 / 0.1)";
  const typeCol = type === "eq" ? "oklch(0.76 0.16 195)" : "oklch(0.73 0.16 145)";
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ borderBottom: "1px solid var(--border)", cursor: "pointer", background: hovered ? "rgba(255,255,255,0.025)" : "transparent" }}
    >
      <td style={{ padding: "10px 14px", fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{name}</td>
      <td style={{ padding: "10px 14px" }}>
        <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, background: typeBg, color: typeCol, fontWeight: 600, textTransform: "uppercase" }}>{type}</span>
      </td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{avg}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text)", fontFamily: "JetBrains Mono, monospace" }}>{ltp}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: up ? gain : loss, fontFamily: "JetBrains Mono, monospace" }}>{pl}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: up ? gain : loss, fontFamily: "JetBrains Mono, monospace" }}>{plp}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: up ? gain : loss, fontFamily: "JetBrains Mono, monospace" }}>{xirr}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: up ? gain : loss, fontFamily: "JetBrains Mono, monospace" }}>{day}</td>
    </tr>
  );
}

function ActionBtn({ children, color }: { children: React.ReactNode; color: string }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ padding: "6px 14px", background: hovered ? color + "20" : color + "10", border: `1px solid ${color + "30"}`, borderRadius: 8, color, fontSize: 12, cursor: "pointer", fontFamily: "inherit", transition: "all 0.15s" }}
    >{children}</button>
  );
}
