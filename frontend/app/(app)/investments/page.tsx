"use client";

import React, { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { Donut } from "@/components/charts/Donut";
import { useMultiOwnerHoldings } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";
import { useOwnerIds, useTimeRange } from "@/lib/viewmode";
import { TimeRangeTabs } from "@/components/layout/TimeRangeTabs";
import { useAuth } from "@/lib/auth";
import { holdings as holdingsApi, CreateHoldingBody } from "@/lib/api";
import type { Holding } from "@/lib/types";

const ASSET_CLASS_COLORS: Record<string, string> = {
  EQUITY:       "oklch(0.76 0.16 195)",
  MUTUAL_FUND:  "oklch(0.73 0.16 145)",
  GOLD:         "oklch(0.82 0.14 80)",
  REAL_ESTATE:  "oklch(0.6 0.12 270)",
  FIXED_INCOME: "oklch(0.76 0.16 65)",
  FD:           "oklch(0.76 0.16 65)",
  PPF:          "oklch(0.73 0.14 165)",
  NPS:          "oklch(0.78 0.14 50)",
  INSURANCE:    "oklch(0.65 0.12 290)",
  CASH:         "oklch(0.73 0.16 145)",
};

const TAB_LABELS: Record<string, string> = {
  EQUITY: "Equity", MUTUAL_FUND: "Mutual Fund", FD: "FD", NPS: "NPS",
  PPF: "PPF", GOLD: "Gold", REAL_ESTATE: "Real Estate",
  INSURANCE: "Insurance", FIXED_INCOME: "Fixed Income", CASH: "Cash", OTHER: "Other",
};

function assetColor(assetClass: string): string {
  return ASSET_CLASS_COLORS[assetClass.toUpperCase()] ?? "var(--text-3)";
}

function assetTypeLabel(assetClass: string): string {
  const labels: Record<string, string> = {
    EQUITY: "EQ", MUTUAL_FUND: "MF", GOLD: "GOLD",
    REAL_ESTATE: "RE", FIXED_INCOME: "FI", CASH: "CASH",
    FD: "FD", NPS: "NPS", PPF: "PPF", INSURANCE: "INS",
  };
  return labels[assetClass.toUpperCase()] ?? assetClass.slice(0, 3).toUpperCase();
}

function tabLabel(k: string): string {
  if (k === "all") return "All";
  return TAB_LABELS[k] ?? k.replace(/_/g, " ");
}

const ASSET_CLASSES = ["EQUITY", "MUTUAL_FUND", "FD", "NPS", "PPF", "GOLD", "REAL_ESTATE", "INSURANCE", "FIXED_INCOME", "CASH", "OTHER"];

type FilterType = "all" | string;

// ── Per-asset-class metadata field config ────────────────────────────────────

interface MetaFieldDef {
  key: string;
  label: string;
  type: "text" | "number" | "select" | "date";
  placeholder?: string;
  options?: string[];
  isPaise?: true;
}

const ASSET_META_FIELDS: Record<string, MetaFieldDef[]> = {
  EQUITY: [
    { key: "isin",     label: "ISIN",     type: "text",   placeholder: "INE000A01036" },
    { key: "exchange", label: "Exchange", type: "select", options: ["NSE", "BSE"] },
    { key: "broker",   label: "Broker",   type: "text",   placeholder: "Zerodha, Groww…" },
  ],
  MUTUAL_FUND: [
    { key: "isin",       label: "ISIN",       type: "text", placeholder: "INF200K01LM3" },
    { key: "folio_no",   label: "Folio No",   type: "text" },
    { key: "fund_house", label: "Fund House", type: "text", placeholder: "HDFC AMC" },
  ],
  FD: [
    { key: "bank_name",     label: "Bank",            type: "text" },
    { key: "rate_pct",      label: "Interest Rate %", type: "number", placeholder: "7.5" },
    { key: "maturity_date", label: "Maturity Date",   type: "date" },
  ],
  PPF: [
    { key: "account_no",    label: "Account No",      type: "text" },
    { key: "maturity_year", label: "Maturity Year",   type: "number", placeholder: "2037" },
    { key: "rate_pct",      label: "Interest Rate %", type: "number", placeholder: "7.1" },
  ],
  NPS: [
    { key: "pran",         label: "PRAN",         type: "text" },
    { key: "fund_manager", label: "Fund Manager", type: "text" },
    { key: "tier",         label: "Tier",         type: "select", options: ["I", "II"] },
  ],
  INSURANCE: [
    { key: "insurer",              label: "Insurer",            type: "text" },
    { key: "policy_no",            label: "Policy No",          type: "text" },
    { key: "policy_type",          label: "Policy Type",        type: "text", placeholder: "Term / ULIP / Endowment…" },
    { key: "sum_assured_paise",    label: "Sum Assured (₹)",    type: "number", isPaise: true },
    { key: "annual_premium_paise", label: "Annual Premium (₹)", type: "number", isPaise: true },
    { key: "maturity_year",        label: "Maturity Year",      type: "number" },
  ],
  REAL_ESTATE: [
    { key: "property_type",          label: "Property Type",        type: "text", placeholder: "Flat / Land / Commercial…" },
    { key: "address",                label: "Address",              type: "text" },
    { key: "loan_outstanding_paise", label: "Loan Outstanding (₹)", type: "number", isPaise: true },
  ],
  GOLD: [
    { key: "gold_type", label: "Gold Type", type: "select", options: ["PHYSICAL", "DIGITAL", "SOVEREIGN_BOND", "ETF"] },
  ],
};

// Asset classes where units / LTP-per-unit fields are meaningful
const SHOWS_UNITS = new Set(["EQUITY", "MUTUAL_FUND", "GOLD"]);
const SHOWS_NAV   = new Set(["EQUITY", "MUTUAL_FUND"]);

// ── Per-asset-class table column config ──────────────────────────────────────

interface ColDef {
  header: string;
  render: (h: Holding) => React.ReactNode;
  mono?: true;
}

function metaVal(h: Holding, key: string): string {
  if (!h.metadata) return "—";
  const v = (h.metadata as Record<string, unknown>)[key];
  return v != null ? String(v) : "—";
}

function metaPaise(h: Holding, key: string): React.ReactNode {
  if (!h.metadata) return "—";
  const v = (h.metadata as Record<string, unknown>)[key] as number | undefined;
  return v != null ? formatINRShort(v) : "—";
}

const COMMON_COLS: ColDef[] = [
  { header: "Holding",  render: (h) => h.instrument_name },
  { header: "Invested", render: (h) => h.purchase_price_paise != null ? formatINRShort(h.purchase_price_paise) : "—", mono: true },
  { header: "Current",  render: (h) => h.current_value_paise != null ? formatINRShort(h.current_value_paise) : "—", mono: true },
  { header: "P&L",      render: (h) => h.pl_paise != null ? `${h.pl_paise >= 0 ? "+" : ""}${formatINRShort(Math.abs(h.pl_paise))}` : "—", mono: true },
  { header: "P&L %",    render: (h) => h.pl_pct != null ? `${h.pl_pct >= 0 ? "+" : ""}${h.pl_pct.toFixed(1)}%` : "—", mono: true },
];

const ASSET_CLASS_COLS: Record<string, ColDef[]> = {
  EQUITY: [
    ...COMMON_COLS,
    { header: "ISIN",     render: (h) => h.isin ?? "—" },
    { header: "Avg Buy",  render: (h) => h.avg_cost_paise != null ? formatINRShort(h.avg_cost_paise) : "—", mono: true },
    { header: "LTP",      render: (h) => h.nav_paise != null ? formatINRShort(h.nav_paise) : "—", mono: true },
    { header: "Exchange", render: (h) => metaVal(h, "exchange") },
    { header: "Broker",   render: (h) => metaVal(h, "broker") },
  ],
  MUTUAL_FUND: [
    ...COMMON_COLS,
    { header: "ISIN",       render: (h) => h.isin ?? "—" },
    { header: "NAV",        render: (h) => h.nav_paise != null ? formatINRShort(h.nav_paise) : "—", mono: true },
    { header: "Avg Cost",   render: (h) => h.avg_cost_paise != null ? formatINRShort(h.avg_cost_paise) : "—", mono: true },
    { header: "Folio",      render: (h) => metaVal(h, "folio_no") },
    { header: "Fund House", render: (h) => metaVal(h, "fund_house") },
  ],
  FD: [
    ...COMMON_COLS,
    { header: "Bank",    render: (h) => metaVal(h, "bank_name") },
    { header: "Rate",    render: (h) => { const r = metaVal(h, "rate_pct"); return r === "—" ? r : `${r}%`; } },
    { header: "Matures", render: (h) => metaVal(h, "maturity_date") },
  ],
  PPF: [
    ...COMMON_COLS,
    { header: "Account",       render: (h) => metaVal(h, "account_no") },
    { header: "Rate",          render: (h) => { const r = metaVal(h, "rate_pct"); return r === "—" ? r : `${r}%`; } },
    { header: "Maturity Year", render: (h) => metaVal(h, "maturity_year") },
  ],
  NPS: [
    ...COMMON_COLS,
    { header: "PRAN",         render: (h) => metaVal(h, "pran") },
    { header: "Fund Manager", render: (h) => metaVal(h, "fund_manager") },
    { header: "Tier",         render: (h) => metaVal(h, "tier") },
  ],
  INSURANCE: [
    ...COMMON_COLS,
    { header: "Insurer",      render: (h) => metaVal(h, "insurer") },
    { header: "Policy No",    render: (h) => metaVal(h, "policy_no") },
    { header: "Sum Assured",  render: (h) => metaPaise(h, "sum_assured_paise"), mono: true },
    { header: "Annual Prem.", render: (h) => metaPaise(h, "annual_premium_paise"), mono: true },
  ],
  REAL_ESTATE: [
    ...COMMON_COLS,
    { header: "Type",    render: (h) => metaVal(h, "property_type") },
    { header: "Address", render: (h) => metaVal(h, "address") },
    { header: "Loan O/S",render: (h) => metaPaise(h, "loan_outstanding_paise"), mono: true },
  ],
  GOLD: [
    ...COMMON_COLS,
    { header: "Units (g)", render: (h) => h.units != null ? String(h.units) : "—", mono: true },
    { header: "Gold Type", render: (h) => metaVal(h, "gold_type") },
  ],
};

const DEFAULT_COLS: ColDef[] = [
  { header: "Holding",   render: (h) => h.instrument_name },
  { header: "Type",      render: (h) => h.asset_class },
  { header: "Avg Buy",   render: (h) => h.avg_cost_paise != null ? formatINRShort(h.avg_cost_paise) : "—", mono: true },
  { header: "LTP / NAV", render: (h) => h.nav_paise != null ? formatINRShort(h.nav_paise) : "—", mono: true },
  { header: "P&L",       render: (h) => h.pl_paise != null ? `${h.pl_paise >= 0 ? "+" : ""}${formatINRShort(Math.abs(h.pl_paise))}` : "—", mono: true },
  { header: "P&L %",     render: (h) => h.pl_pct != null ? `${h.pl_pct >= 0 ? "+" : ""}${h.pl_pct.toFixed(1)}%` : "—", mono: true },
];

// ── Add Holding Modal ────────────────────────────────────────────────────────

function AddHoldingModal({ ownerId, onClose, onSuccess }: {
  ownerId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [form, setForm] = useState({
    asset_class: "EQUITY",
    instrument_name: "",
    units: "",
    purchase_price_inr: "",
    current_value_inr: "",
    nav_inr: "",
    valuation_date: new Date().toISOString().slice(0, 10),
  });
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (field === "asset_class") setMeta({});
    setForm((f) => ({ ...f, [field]: e.target.value }));
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.instrument_name.trim()) { setError("Instrument name is required."); return; }

    const inrToPaise = (v: string) => {
      const n = parseFloat(v.replace(/,/g, ""));
      return isNaN(n) ? null : Math.round(n * 100);
    };

    const metaFields = ASSET_META_FIELDS[form.asset_class] ?? [];
    const isin = metaFields.find((f) => f.key === "isin") ? (meta["isin"] || null) : null;

    const metadataOut: Record<string, unknown> = {};
    for (const fd of metaFields) {
      if (fd.key === "isin") continue;
      const raw = meta[fd.key];
      if (!raw) continue;
      if (fd.isPaise) {
        const n = parseFloat(raw.replace(/,/g, ""));
        if (!isNaN(n)) metadataOut[fd.key] = Math.round(n * 100);
      } else if (fd.type === "number") {
        const n = parseFloat(raw);
        if (!isNaN(n)) metadataOut[fd.key] = n;
      } else {
        metadataOut[fd.key] = raw;
      }
    }

    const body: CreateHoldingBody = {
      asset_class: form.asset_class,
      instrument_name: form.instrument_name.trim(),
      isin,
      units: SHOWS_UNITS.has(form.asset_class) && form.units ? parseFloat(form.units) : null,
      nav_paise: SHOWS_NAV.has(form.asset_class) ? inrToPaise(form.nav_inr) : null,
      purchase_price_paise: inrToPaise(form.purchase_price_inr),
      current_value_paise: inrToPaise(form.current_value_inr),
      valuation_date: form.valuation_date || null,
      metadata: Object.keys(metadataOut).length > 0 ? metadataOut : null,
    };

    setSubmitting(true);
    setError(null);
    try {
      await holdingsApi.create(ownerId, body);
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add holding.");
    } finally {
      setSubmitting(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "8px 10px", background: "var(--bg)",
    border: "1px solid var(--border)", borderRadius: 7, color: "var(--text)",
    fontSize: 13, fontFamily: "inherit", boxSizing: "border-box",
  };
  const labelStyle: React.CSSProperties = {
    fontSize: 11, color: "var(--text-3)", fontWeight: 600,
    textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4, display: "block",
  };

  const metaFields = ASSET_META_FIELDS[form.asset_class] ?? [];

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 14, padding: 24, width: 440, maxWidth: "90vw",
          maxHeight: "90vh", overflowY: "auto",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>Add Holding</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-3)", fontSize: 18, cursor: "pointer", padding: 4 }}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ display: "grid", gap: 12 }}>
            {/* Asset class */}
            <div>
              <label style={labelStyle}>Asset Class</label>
              <select value={form.asset_class} onChange={set("asset_class")} style={inputStyle}>
                {ASSET_CLASSES.map((ac) => (
                  <option key={ac} value={ac}>{TAB_LABELS[ac] ?? ac}</option>
                ))}
              </select>
            </div>

            {/* Instrument name */}
            <div>
              <label style={labelStyle}>Instrument Name *</label>
              <input
                placeholder="e.g. HDFC Bank Ltd, Axis Bluechip Fund"
                value={form.instrument_name} onChange={set("instrument_name")}
                style={inputStyle}
              />
            </div>

            {/* Units + LTP — only for unit-based asset classes */}
            {SHOWS_UNITS.has(form.asset_class) && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={labelStyle}>Units / Quantity</label>
                  <input type="number" placeholder="e.g. 100" value={form.units} onChange={set("units")} style={inputStyle} />
                </div>
                {SHOWS_NAV.has(form.asset_class) && (
                  <div>
                    <label style={labelStyle}>LTP / NAV (₹)</label>
                    <input type="number" placeholder="e.g. 1450.50" value={form.nav_inr} onChange={set("nav_inr")} style={inputStyle} />
                  </div>
                )}
              </div>
            )}

            {/* Amount invested + current value */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={labelStyle}>Amount Invested (₹)</label>
                <input type="number" placeholder="e.g. 100000" value={form.purchase_price_inr} onChange={set("purchase_price_inr")} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Current Value (₹)</label>
                <input type="number" placeholder="e.g. 145000" value={form.current_value_inr} onChange={set("current_value_inr")} style={inputStyle} />
              </div>
            </div>

            {/* Valuation date */}
            <div>
              <label style={labelStyle}>Valuation Date</label>
              <input type="date" value={form.valuation_date} onChange={set("valuation_date")} style={inputStyle} />
            </div>

            {/* Per-asset-class metadata fields */}
            {metaFields.length > 0 && (
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, display: "grid", gap: 12 }}>
                {metaFields.map((fd) => (
                  <div key={fd.key}>
                    <label style={labelStyle}>{fd.label}</label>
                    {fd.type === "select" ? (
                      <select
                        value={meta[fd.key] ?? ""}
                        onChange={(e) => setMeta((m) => ({ ...m, [fd.key]: e.target.value }))}
                        style={inputStyle}
                      >
                        <option value="">— select —</option>
                        {fd.options!.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input
                        type={fd.type}
                        placeholder={fd.placeholder}
                        maxLength={fd.key === "isin" ? 12 : undefined}
                        value={meta[fd.key] ?? ""}
                        onChange={(e) => setMeta((m) => ({ ...m, [fd.key]: e.target.value }))}
                        style={inputStyle}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div style={{ marginTop: 12, fontSize: 12, color: "oklch(0.66 0.18 25)", padding: "8px 10px", background: "oklch(0.66 0.18 25 / 0.08)", borderRadius: 6 }}>
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 18, justifyContent: "flex-end" }}>
            <button type="button" onClick={onClose}
              style={{ padding: "7px 16px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-2)", borderRadius: 7, cursor: "pointer", fontSize: 13, fontFamily: "inherit" }}>
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              style={{ padding: "7px 16px", border: "1px solid oklch(0.76 0.16 195 / 0.4)", background: "oklch(0.76 0.16 195 / 0.12)", color: "oklch(0.76 0.16 195)", borderRadius: 7, cursor: submitting ? "not-allowed" : "pointer", fontSize: 13, fontFamily: "inherit", opacity: submitting ? 0.6 : 1 }}>
              {submitting ? "Adding…" : "Add Holding"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function InvestmentsPage() {
  const { owner } = useAuth();
  const ownerIds = useOwnerIds();
  const queryClient = useQueryClient();
  useTimeRange(); // subscribe so tab state is globally in sync
  const { data: holdingsData, isLoading } = useMultiOwnerHoldings(ownerIds);

  const holdings = holdingsData ?? [];

  const assetClasses = useMemo(
    () => Array.from(new Set(holdings.map((h) => h.asset_class))),
    [holdings]
  );

  const [filter, setFilter] = useState<FilterType>("all");
  const [showAdd, setShowAdd] = useState(false);

  const filtered = filter === "all" ? holdings : holdings.filter((h) => h.asset_class === filter);

  const totalCurrentPaise = useMemo(() => holdings.reduce((s, h) => s + (h.current_value_paise ?? 0), 0), [holdings]);
  const totalInvestedPaise = useMemo(() => holdings.reduce((s, h) => s + (h.purchase_price_paise ?? 0), 0), [holdings]);
  const totalPLPaise = totalCurrentPaise - totalInvestedPaise;

  const sectors = useMemo(() => {
    if (totalCurrentPaise === 0) return [];
    const byClass = new Map<string, number>();
    for (const h of holdings) {
      const cls = h.asset_class;
      byClass.set(cls, (byClass.get(cls) ?? 0) + (h.current_value_paise ?? 0));
    }
    return Array.from(byClass.entries())
      .sort(([, a], [, b]) => b - a)
      .map(([cls, val]) => ({
        name: TAB_LABELS[cls] ?? cls.replace(/_/g, " "),
        pct: Math.round((val / totalCurrentPaise) * 100),
        color: assetColor(cls),
      }));
  }, [holdings, totalCurrentPaise]);

  const donutSegments = sectors.map((s) => ({ value: s.pct, color: s.color }));

  function handleAddSuccess() {
    setShowAdd(false);
    ownerIds.forEach((id) => queryClient.invalidateQueries({ queryKey: ["holdings", id] }));
  }

  const activeCols = filter === "all" ? DEFAULT_COLS : (ASSET_CLASS_COLS[filter] ?? DEFAULT_COLS);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Portfolio"
        subtitle={`${holdings.length} holding${holdings.length !== 1 ? "s" : ""} · Direct equity + mutual funds`}
        live
        tabs={<TimeRangeTabs />}
        actions={<ActionBtn color="oklch(0.76 0.16 195)" onClick={() => setShowAdd(true)}>+ Add Holding</ActionBtn>}
      />

      {showAdd && owner?.owner_id && (
        <AddHoldingModal
          ownerId={owner.owner_id}
          onClose={() => setShowAdd(false)}
          onSuccess={handleAddSuccess}
        />
      )}

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 14 }}>
          {[
            { label: "Portfolio Value",  val: formatINRShort(totalCurrentPaise),                                     color: "oklch(0.76 0.16 195)" },
            { label: "Today's P&L",      val: "—",                                                                  color: "var(--text-3)"         },
            { label: "Overall P&L",      val: totalPLPaise !== 0 ? formatINRShort(Math.abs(totalPLPaise)) : "—",    color: totalPLPaise >= 0 ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)" },
            { label: "XIRR",             val: "—",                                                                  color: "var(--text-3)"         },
            { label: "Invested",         val: formatINRShort(totalInvestedPaise),                                   color: "var(--text)"           },
          ].map((k) => (
            <div key={k.label} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px" }}>
              <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 6 }}>{k.label}</div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: k.color }}>{k.val}</div>
            </div>
          ))}
        </div>

        {/* Sector + allocation */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 14 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Asset Allocation</span>
            </div>
            {sectors.length > 0 ? (
              <>
                <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", gap: 1, marginBottom: 10 }}>
                  {sectors.map((s) => <div key={s.name} style={{ flex: s.pct, background: s.color, opacity: 0.8 }} />)}
                </div>
                <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                  {sectors.map((s) => (
                    <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <div style={{ width: 6, height: 6, borderRadius: "50%", background: s.color }} />
                      <span style={{ fontSize: 11, color: "var(--text-2)" }}>{s.name}</span>
                      <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{s.pct}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>No holdings ingested yet</div>
            )}
          </div>

          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 8 }}>Allocation</div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              {donutSegments.length > 0 ? (
                <Donut size={80} segments={donutSegments} />
              ) : (
                <Donut size={80} segments={[{ value: 1, color: "var(--border)" }]} />
              )}
            </div>
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          {(["all", ...assetClasses] as FilterType[]).map((k) => {
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
              >{tabLabel(k)}</button>
            );
          })}
        </div>

        {/* Holdings table */}
        {isLoading ? (
          <div style={{ fontSize: 13, color: "var(--text-3)", padding: "20px 0" }}>Loading holdings…</div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-3)", fontSize: 13 }}>
            No holdings found. Ingest a MF CAS or Zerodha statement to populate this view.
          </div>
        ) : (
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                  {activeCols.map((c) => (
                    <th key={c.header} style={{ textAlign: "left", padding: "8px 14px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", whiteSpace: "nowrap" }}>
                      {c.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((h) => {
                  const up = (h.pl_paise ?? 0) >= 0;
                  const gain = "oklch(0.73 0.16 145)";
                  const loss = "oklch(0.66 0.18 25)";
                  return (
                    <HoverRow key={h.id}>
                      {activeCols.map((c) => {
                        const val = c.render(h);
                        const isPlCol = c.header === "P&L" || c.header === "P&L %";
                        return (
                          <td key={c.header} style={{
                            padding: "10px 14px",
                            fontSize: c.header === "Holding" ? 13 : 12,
                            fontWeight: c.header === "Holding" ? 500 : undefined,
                            color: isPlCol
                              ? (val === "—" ? "var(--text-3)" : up ? gain : loss)
                              : c.header === "Holding" ? "var(--text)" : "var(--text-2)",
                            fontFamily: c.mono ? "JetBrains Mono, monospace" : "inherit",
                          }}>
                            {c.header === "Type" ? (
                              <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, background: assetColor(h.asset_class) + "18", color: assetColor(h.asset_class), fontWeight: 600, textTransform: "uppercase" }}>
                                {assetTypeLabel(h.asset_class)}
                              </span>
                            ) : val}
                          </td>
                        );
                      })}
                    </HoverRow>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function HoverRow({ children }: { children: React.ReactNode }) {
  const [hovered, setHovered] = useState(false);
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ borderBottom: "1px solid var(--border)", cursor: "pointer", background: hovered ? "rgba(255,255,255,0.025)" : "transparent" }}
    >
      {children}
    </tr>
  );
}

function ActionBtn({ children, color, onClick }: { children: React.ReactNode; color: string; onClick?: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ padding: "6px 14px", background: hovered ? color + "20" : color + "10", border: `1px solid ${color + "30"}`, borderRadius: 8, color, fontSize: 12, cursor: "pointer", fontFamily: "inherit", transition: "all 0.15s" }}
    >{children}</button>
  );
}
