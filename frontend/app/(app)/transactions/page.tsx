"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { useAuth } from "@/lib/auth";
import { useTransactions } from "@/lib/queries";
import { formatDate, formatINR } from "@/lib/format";

const BAR_DATA = [
  { i: 65, e: 42 }, { i: 58, e: 50 }, { i: 72, e: 38 },
  { i: 61, e: 45 }, { i: 78, e: 52 }, { i: 69, e: 41 }, { i: 82, e: 48 },
];
const M_LABELS = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"];
const MAX_B = 82;

const EXP_BREAK = [
  { label: "Housing",       pct: 28, color: "oklch(0.76 0.16 195)", val: "₹76K" },
  { label: "Health",        pct: 22, color: "oklch(0.6 0.12 270)",  val: "₹60K" },
  { label: "Food",          pct: 18, color: "oklch(0.73 0.16 145)", val: "₹49K" },
  { label: "Subscriptions", pct: 8,  color: "oklch(0.76 0.16 65)",  val: "₹22K" },
  { label: "Other",         pct: 24, color: "var(--text-3)",         val: "₹65K" },
];

const TXN_ICONS: Record<string, string> = {
  income: "💼", expense: "💳", investment: "📊",
};

type CatFilter = "all" | "income" | "expense" | "investment";

export default function TransactionsPage() {
  const { owner } = useAuth();
  const { data: txns, isLoading } = useTransactions(owner?.owner_id, { limit: 100 });
  const [search, setSearch] = useState("");
  const [catF, setCatF] = useState<CatFilter>("all");

  const allTxns = txns ?? [];

  // Categorise API transactions
  const mapped = useMemo(() => allTxns.map((t) => {
    const cat =
      t.transaction_type === "CREDIT"
        ? "income"
        : (t.category?.toLowerCase().includes("invest") || t.category?.toLowerCase().includes("sip") || t.category?.toLowerCase().includes("mutual"))
          ? "investment"
          : "expense";
    return { ...t, cat };
  }), [allTxns]);

  const filtered = useMemo(() =>
    mapped.filter((t) =>
      (catF === "all" || t.cat === catF) &&
      (!search || t.description.toLowerCase().includes(search.toLowerCase()))
    ),
    [mapped, catF, search]
  );

  // KPI calculations
  const income = useMemo(() => mapped.filter((t) => t.cat === "income").reduce((s, t) => s + t.amount_paise, 0), [mapped]);
  const expenses = useMemo(() => mapped.filter((t) => t.cat === "expense").reduce((s, t) => s + t.amount_paise, 0), [mapped]);
  const investments = useMemo(() => mapped.filter((t) => t.cat === "investment").reduce((s, t) => s + t.amount_paise, 0), [mapped]);
  const savingsRate = income > 0 ? Math.round(((income - expenses - investments) / income) * 100) : 0;

  const hasRealData = allTxns.length > 0;

  // Demo KPIs when no real data
  const kpiIncome     = hasRealData ? formatINR(income)      : "+₹8.2L";
  const kpiExpenses   = hasRealData ? "−" + formatINR(expenses) : "−₹2.7L";
  const kpiInvestments = hasRealData ? "−" + formatINR(investments) : "−₹2.0L";
  const kpiSavings    = hasRealData ? `${savingsRate}%`      : "67%";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Cashflow"
        subtitle={hasRealData ? `${allTxns.length} transactions` : "April 2025 · 47 transactions"}
        actions={<ActionBtn color="oklch(0.73 0.16 145)">+ Add Transaction</ActionBtn>}
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
          {[
            { label: "Income",      val: kpiIncome,      color: "oklch(0.73 0.16 145)" },
            { label: "Expenses",    val: kpiExpenses,    color: "oklch(0.66 0.18 25)"  },
            { label: "Investments", val: kpiInvestments, color: "oklch(0.76 0.16 195)" },
            { label: "Savings Rate",val: kpiSavings,     color: "oklch(0.73 0.16 145)" },
          ].map((k) => (
            <div key={k.label} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px" }}>
              <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 6 }}>{k.label}</div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 22, color: k.color }}>{k.val}</div>
            </div>
          ))}
        </div>

        {/* Bar chart + expense split */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 14 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 14 }}>Income vs Expenses</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 90 }}>
              {BAR_DATA.map((b, i) => (
                <div key={i} style={{ flex: 1, display: "flex", gap: 2, alignItems: "flex-end", height: "100%" }}>
                  <div style={{ flex: 1, background: "oklch(0.73 0.16 145)", opacity: 0.7, borderRadius: "2px 2px 0 0", height: `${(b.i / MAX_B) * 100}%`, minHeight: 2 }} />
                  <div style={{ flex: 1, background: "oklch(0.66 0.18 25)", opacity: 0.6, borderRadius: "2px 2px 0 0", height: `${(b.e / MAX_B) * 100}%`, minHeight: 2 }} />
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
              {M_LABELS.map((m) => <div key={m} style={{ flex: 1, textAlign: "center", fontSize: 9, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{m}</div>)}
            </div>
            <div style={{ display: "flex", gap: 14, marginTop: 10 }}>
              {[["oklch(0.73 0.16 145)", "Income"], ["oklch(0.66 0.18 25)", "Expenses"]].map(([c, l]) => (
                <div key={l} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 10, height: 10, background: c, borderRadius: 2 }} />
                  <span style={{ fontSize: 11, color: "var(--text-2)" }}>{l}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Expense Split</div>
            <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", gap: 1, marginBottom: 12 }}>
              {EXP_BREAK.map((c) => <div key={c.label} style={{ flex: c.pct, background: c.color, opacity: 0.8 }} />)}
            </div>
            {EXP_BREAK.map((c) => (
              <div key={c.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: c.color, flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: "var(--text-2)", flex: 1 }}>{c.label}</span>
                <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{c.val}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Transaction list */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", gap: 10, alignItems: "center" }}>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search transactions…"
              style={{ flex: 1, background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 7, padding: "6px 10px", fontSize: 12, color: "var(--text)", fontFamily: "inherit", outline: "none" }}
            />
            <div style={{ display: "flex", gap: 4 }}>
              {(["all", "income", "expense", "investment"] as CatFilter[]).map((c) => (
                <button key={c} onClick={() => setCatF(c)}
                  style={{
                    padding: "4px 10px", borderRadius: 6, border: "1px solid",
                    borderColor: catF === c ? "oklch(0.76 0.16 195 / 0.4)" : "var(--border)",
                    background: catF === c ? "oklch(0.76 0.16 195 / 0.08)" : "transparent",
                    color: catF === c ? "oklch(0.76 0.16 195)" : "var(--text-2)",
                    fontSize: 11, cursor: "pointer", fontFamily: "inherit", textTransform: "capitalize",
                  }}
                >{c}</button>
              ))}
            </div>
          </div>

          {isLoading ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-3)", fontSize: 13 }}>Loading transactions…</div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-3)", fontSize: 13 }}>No transactions match your filter.</div>
          ) : (
            filtered.slice(0, 50).map((t, i) => (
              <TxnRow
                key={t.id}
                icon={TXN_ICONS[t.cat] ?? "💰"}
                name={t.description}
                date={formatDate(t.transaction_date)}
                cat={t.cat}
                amount={(t.transaction_type === "CREDIT" ? "+" : "−") + formatINR(t.amount_paise)}
                up={t.transaction_type === "CREDIT"}
                isInvestment={t.cat === "investment"}
                last={i === Math.min(filtered.length, 50) - 1}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function TxnRow({ icon, name, date, cat, amount, up, isInvestment, last }: {
  icon: string; name: string; date: string; cat: string; amount: string;
  up: boolean; isInvestment: boolean; last: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const amtColor = up ? "oklch(0.73 0.16 145)" : isInvestment ? "oklch(0.76 0.16 195)" : "oklch(0.66 0.18 25)";
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        borderBottom: last ? "none" : "1px solid var(--border)",
        cursor: "pointer", background: hovered ? "rgba(255,255,255,0.025)" : "transparent",
        transition: "background 0.1s",
      }}
    >
      <div style={{ width: 32, height: 32, borderRadius: 8, background: "var(--bg3)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>{icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 360 }}>{name}</div>
        <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2, textTransform: "capitalize" }}>{date} · {cat}</div>
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: amtColor, fontWeight: 500 }}>{amount}</div>
    </div>
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
