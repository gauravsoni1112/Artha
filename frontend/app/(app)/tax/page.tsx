"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { useAuth } from "@/lib/auth";
import { useProfile, useTaxData } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";

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
  const ownerId = owner?.owner_id;
  const { data: profile } = useProfile(ownerId);
  const { data: taxRecords, isLoading } = useTaxData(ownerId);

  const annualIncome = useMemo(() => {
    if (!profile?.total_monthly_income_paise) return null;
    return profile.total_monthly_income_paise * 12;
  }, [profile]);

  const taxRupees = useMemo(() => annualIncome ? calcTax(Math.floor(annualIncome / 100)) : null, [annualIncome]);

  // Estimated taxable income from profile (annualIncome paise → rupees − standard deduction ₹75K)
  const estTaxableIncomePaise = useMemo(() => {
    if (!annualIncome) return null;
    const rupees = Math.floor(annualIncome / 100);
    return Math.max(0, rupees - 75_000) * 100; // back to paise
  }, [annualIncome]);

  // ~83% of estimated tax paid via advance tax/TDS (rough planning heuristic)
  const ESTIMATED_TAX_PAID_RATIO = 0.83;

  // KPIs — prefer latest ITR record if available, else estimate from profile
  const latestITR = taxRecords?.[0];
  const totalLiability = latestITR?.taxable_income_paise != null
    ? formatINRShort(latestITR.taxable_income_paise)
    : estTaxableIncomePaise != null ? formatINRShort(estTaxableIncomePaise) : "—";
  const paidTax = latestITR?.tax_paid_paise != null
    ? formatINRShort(latestITR.tax_paid_paise)
    : taxRupees != null ? formatINRShort(Math.round(taxRupees * ESTIMATED_TAX_PAID_RATIO) * 100) : "—";
  const tdsPaid = latestITR?.tds_paise != null
    ? formatINRShort(latestITR.tds_paise)
    : "—";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Tax Centre"
        subtitle={latestITR ? `Latest: FY ${latestITR.fiscal_year} · New Regime` : "FY 2025–26 · New Regime · Slab: 30%"}
        actions={<ActionBtn color="oklch(0.76 0.16 65)">Download ITR Summary</ActionBtn>}
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
          {[
            { label: "Taxable Income",  val: totalLiability, color: "oklch(0.76 0.16 65)"  },
            { label: "Tax Paid",        val: paidTax,        color: "oklch(0.73 0.16 145)" },
            { label: "TDS Deducted",    val: tdsPaid,        color: "oklch(0.76 0.16 195)" },
            { label: "Potential Saving",val: "₹58.2K",       color: "oklch(0.66 0.18 25)"  },
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

        {/* ITR Records table (F8) */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>
            ITR Records
          </div>
          {isLoading ? (
            <div style={{ padding: "20px 16px", fontSize: 13, color: "var(--text-3)" }}>Loading…</div>
          ) : !taxRecords?.length ? (
            <div style={{ padding: "20px 16px", fontSize: 13, color: "var(--text-3)" }}>
              No ITR records found. Use the static-data/itr endpoint to seed your tax history.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                  {["Fiscal Year", "Gross Income", "Taxable Income", "Tax Paid", "TDS", "Filed"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "7px 14px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {taxRecords.map((r) => (
                  <ITRRow key={r.id} record={r} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function ITRRow({ record }: { record: { id: string; fiscal_year: string; gross_income_paise: number | null; taxable_income_paise: number | null; tax_paid_paise: number | null; tds_paise: number | null; itr_filed: boolean } }) {
  const [hovered, setHovered] = useState(false);
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ borderBottom: "1px solid var(--border)", background: hovered ? "rgba(255,255,255,0.02)" : "transparent" }}
    >
      <td style={{ padding: "9px 14px", fontSize: 13, color: "var(--text)", fontWeight: 500, fontFamily: "JetBrains Mono, monospace" }}>{record.fiscal_year}</td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>
        {record.gross_income_paise != null ? formatINRShort(record.gross_income_paise) : "—"}
      </td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>
        {record.taxable_income_paise != null ? formatINRShort(record.taxable_income_paise) : "—"}
      </td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>
        {record.tax_paid_paise != null ? formatINRShort(record.tax_paid_paise) : "—"}
      </td>
      <td style={{ padding: "9px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>
        {record.tds_paise != null ? formatINRShort(record.tds_paise) : "—"}
      </td>
      <td style={{ padding: "9px 14px" }}>
        <span style={{
          fontSize: 10, padding: "2px 7px", borderRadius: 4, fontWeight: 600,
          background: record.itr_filed ? "oklch(0.73 0.16 145 / 0.1)" : "oklch(0.66 0.18 25 / 0.1)",
          color: record.itr_filed ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)",
        }}>
          {record.itr_filed ? "✓ Filed" : "Pending"}
        </span>
      </td>
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
