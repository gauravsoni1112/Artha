"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { useAuth } from "@/lib/auth";
import { useProfile } from "@/lib/queries";

const EVENTS = [
  { type: "STCG", stock: "ZOMATO",     date: "Mar 12", buy: "₹182",   sell: "₹224",   gain: "+₹58K",  tax: "₹8,700", holding: "8 mo",  up: true  },
  { type: "STCG", stock: "BAJFINANCE", date: "Feb 28", buy: "₹6,800", sell: "₹7,100", gain: "+₹36K",  tax: "₹5,400", holding: "7 mo",  up: true  },
  { type: "LTCG", stock: "TCS",        date: "Jan 15", buy: "₹3,200", sell: "₹3,500", gain: "+₹96K",  tax: "₹9,600", holding: "14 mo", up: true  },
  { type: "LTCG", stock: "HDFCBANK",   date: "Dec 20", buy: "₹1,420", sell: "₹1,580", gain: "+₹38K",  tax: "₹3,840", holding: "18 mo", up: true  },
  { type: "LOSS", stock: "INFY",       date: "Nov 10", buy: "₹1,580", sell: "₹1,492", gain: "−₹44K",  tax: "Harvest",holding: "4 mo",  up: false },
];

const OPPS = [
  { icon: "📉", title: "Harvest INFY loss",          saving: "₹6,600",  desc: "₹44K unrealized loss offsets ₹44K of STCG",                color: "oklch(0.66 0.18 25)",  urgent: true  },
  { icon: "⏰", title: "Wait on HDFCBANK (21 days)", saving: "₹4,800",  desc: "LTCG threshold May 12 — avoid 15% STCG tax",               color: "oklch(0.76 0.16 65)",  urgent: false },
  { icon: "💡", title: "Invest ₹1.5L in ELSS",       saving: "₹46,800", desc: "80C deduction at 31.2% slab saves real cash",              color: "oklch(0.76 0.16 195)", urgent: false },
];

const QUARTERS = [
  { q: "Q1", date: "Jun 15", pct: 15,  paid: true  },
  { q: "Q2", date: "Sep 15", pct: 45,  paid: true  },
  { q: "Q3", date: "Dec 15", pct: 75,  paid: true  },
  { q: "Q4", date: "Mar 15", pct: 100, paid: false },
];

function typeColor(t: string) {
  if (t === "LTCG") return "oklch(0.76 0.16 195)";
  if (t === "STCG") return "oklch(0.76 0.16 65)";
  return "oklch(0.66 0.18 25)";
}
function typeBg(t: string) {
  if (t === "LTCG") return "oklch(0.76 0.16 195 / 0.1)";
  if (t === "STCG") return "oklch(0.76 0.16 65 / 0.1)";
  return "oklch(0.66 0.18 25 / 0.1)";
}

// ── New-regime tax helper (FY 2024-25) ───────────────────────
function calcTax(income: number) {
  const std = 75000;
  const taxable = Math.max(0, income - std);
  const slabs = [
    { from: 0,        to: 400000,  rate: 0    },
    { from: 400000,   to: 800000,  rate: 0.05 },
    { from: 800000,   to: 1200000, rate: 0.10 },
    { from: 1200000,  to: 1600000, rate: 0.15 },
    { from: 1600000,  to: 2000000, rate: 0.20 },
    { from: 2000000,  to: 2400000, rate: 0.25 },
    { from: 2400000,  to: Infinity,rate: 0.30 },
  ];
  let tax = 0;
  for (const s of slabs) {
    if (taxable <= s.from) break;
    tax += (Math.min(taxable, s.to) - s.from) * s.rate;
  }
  return Math.round(tax);
}

export default function TaxPage() {
  const { owner } = useAuth();
  const { data: profile } = useProfile(owner?.owner_id);

  const annualIncome = useMemo(() => {
    if (!profile?.total_monthly_income_paise) return null;
    return profile.total_monthly_income_paise * 12;
  }, [profile]);

  const taxRupees = useMemo(() => annualIncome ? calcTax(Math.floor(annualIncome / 100)) : null, [annualIncome]);

  const totalLiability = taxRupees ? `₹${(taxRupees / 100000).toFixed(1)}L` : "₹1.8Cr";
  const paidTax = taxRupees ? `₹${(taxRupees * 0.83 / 100000).toFixed(1)}L` : "₹1.5Cr";
  const balanceDue = taxRupees ? `₹${Math.round(taxRupees * 0.17 / 1000)}K` : "₹30K";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Tax Centre"
        subtitle="FY 2025–26 · New Regime · Slab: 30%"
        actions={<ActionBtn color="oklch(0.76 0.16 65)">Download ITR Summary</ActionBtn>}
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
          {[
            { label: "Total Liability",   val: totalLiability, color: "oklch(0.76 0.16 65)"  },
            { label: "Paid (Advance)",    val: paidTax,        color: "oklch(0.73 0.16 145)" },
            { label: "Balance Due",       val: balanceDue,     color: "oklch(0.66 0.18 25)"  },
            { label: "Potential Saving",  val: "₹58.2K",       color: "oklch(0.76 0.16 195)" },
          ].map((k) => (
            <div key={k.label} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px" }}>
              <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 6 }}>{k.label}</div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 22, color: k.color }}>{k.val}</div>
            </div>
          ))}
        </div>

        {/* Opportunities + Calendar */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Tax Saving Opportunities</div>
            {OPPS.map((o, i) => (
              <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderBottom: i < OPPS.length - 1 ? "1px solid var(--border)" : "none" }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, background: o.color + "18", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0 }}>{o.icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                    <span style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{o.title}</span>
                    {o.urgent && <span style={{ fontSize: 10, background: "oklch(0.66 0.18 25 / 0.15)", color: "oklch(0.66 0.18 25)", padding: "1px 6px", borderRadius: 3, fontWeight: 600 }}>URGENT</span>}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 4 }}>{o.desc}</div>
                  <div style={{ fontSize: 12, color: o.color, fontFamily: "JetBrains Mono, monospace", fontWeight: 600 }}>Save {o.saving}</div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Advance Tax Calendar</div>
            {QUARTERS.map((q) => (
              <div key={q.q} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: q.q !== "Q4" ? "1px solid var(--border)" : "none" }}>
                <div style={{ width: 32, height: 32, borderRadius: 8, background: q.paid ? "oklch(0.73 0.16 145 / 0.1)" : "oklch(0.66 0.18 25 / 0.1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: q.paid ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", flexShrink: 0 }}>{q.q}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: "var(--text)", marginBottom: 4 }}>Due {q.date} · {q.pct}% cumulative</div>
                  <div style={{ height: 3, background: "var(--bg3)", borderRadius: 2 }}>
                    <div style={{ height: "100%", width: `${q.pct}%`, background: q.paid ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", borderRadius: 2 }} />
                  </div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: q.paid ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", whiteSpace: "nowrap" }}>{q.paid ? "✓ Paid" : "Due"}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Capital gains table */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Capital Gains Events</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                {["Type", "Stock", "Date", "Buy", "Sell", "Gain/Loss", "Tax", "Holding"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "7px 14px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {EVENTS.map((e, i) => (
                <EventRow key={i} {...e} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function EventRow({ type, stock, date, buy, sell, gain, tax, holding, up }: typeof EVENTS[0]) {
  const [hovered, setHovered] = useState(false);
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ borderBottom: "1px solid var(--border)", background: hovered ? "rgba(255,255,255,0.02)" : "transparent" }}
    >
      <td style={{ padding: "9px 14px" }}><span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, background: typeBg(type), color: typeColor(type), fontWeight: 600 }}>{type}</span></td>
      <td style={{ padding: "9px 14px", fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{stock}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{date}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{buy}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{sell}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{gain}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: type === "LOSS" ? "oklch(0.73 0.16 145)" : "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{tax}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-3)" }}>{holding}</td>
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
