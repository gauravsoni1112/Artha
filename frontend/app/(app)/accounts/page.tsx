"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { TimeRangeTabs } from "@/components/layout/TimeRangeTabs";
import { Sparkline } from "@/components/charts/Sparkline";
import { useMultiOwnerAccounts, useMultiOwnerTransactions } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";
import { getTimeRangeDates, useOwnerIds, useTimeRange } from "@/lib/viewmode";

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

function accountColor(type: string): string {
  const colors: Record<string, string> = {
    SAVINGS: "oklch(0.73 0.16 145)", CURRENT: "oklch(0.73 0.16 145)",
    BROKER: "oklch(0.76 0.16 195)",
    MUTUAL_FUND: "oklch(0.6 0.12 270)",
    CREDIT_CARD: "oklch(0.66 0.18 25)",
    FIXED_DEPOSIT: "oklch(0.76 0.16 65)",
    LOAN: "oklch(0.66 0.18 25)",
  };
  return colors[type] ?? "oklch(0.6 0.12 280)";
}

function accountTypeName(type: string): string {
  const names: Record<string, string> = {
    SAVINGS: "Savings", CURRENT: "Current", SALARY: "Salary",
    BROKER: "Broker", DEMAT: "Demat",
    MUTUAL_FUND: "Mutual Fund",
    CREDIT_CARD: "Credit Card",
    FIXED_DEPOSIT: "Fixed Deposit",
    LOAN: "Loan",
    PPF: "PPF", NPS: "NPS",
  };
  return names[type] ?? type;
}

export default function AccountsPage() {
  const ownerIds = useOwnerIds();
  const { timeRange } = useTimeRange();

  const { data: accountsList, isLoading } = useMultiOwnerAccounts(ownerIds);

  const txnFilters = useMemo(() => ({ ...getTimeRangeDates(timeRange), limit: 300 }), [timeRange]);
  const { data: recentTxns } = useMultiOwnerTransactions(ownerIds, txnFilters);

  // Build per-account 7-day sparkline anchored to current balance.
  // Points show what the balance was each day: currentBalance - (net flow from that day onward).
  const accountSparklines = useMemo(() => {
    const map = new Map<string, number[]>();
    if (!recentTxns?.length || !accountsList?.length) return map;

    // Build 7 day date array (oldest first)
    const days: string[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(); d.setDate(d.getDate() - i);
      days.push(d.toISOString().slice(0, 10));
    }

    // Group txns by account and date
    const byAccount = new Map<string, Map<string, number>>();
    for (const t of recentTxns) {
      // ISO date strings sort/compare correctly lexicographically
      const day = t.transaction_date.slice(0, 10);
      if (!byAccount.has(t.account_id)) byAccount.set(t.account_id, new Map());
      const dayMap = byAccount.get(t.account_id)!;
      const delta = t.transaction_type === "CREDIT" ? t.amount_paise : -t.amount_paise;
      dayMap.set(day, (dayMap.get(day) ?? 0) + delta);
    }

    // Anchor sparkline to current balance_paise: work backward from today
    const acctBalances = new Map(accountsList.map((a) => [a.id, a.balance_paise ?? 0]));
    Array.from(byAccount.entries()).forEach(([acctId, dayMap]) => {
      const currentBalRupees = (acctBalances.get(acctId) ?? 0) / 100;
      // Sum of net flow over all 7 days
      const totalFlow = days.reduce((s, d) => s + (dayMap.get(d) ?? 0), 0) / 100;
      // startBalance is what the balance was before this 7-day window
      const startBalance = currentBalRupees - totalFlow;
      let cumulative = startBalance;
      const points = days.map((d) => {
        cumulative += (dayMap.get(d) ?? 0) / 100;
        return cumulative;
      });
      map.set(acctId, points);
    });
    return map;
  }, [recentTxns, accountsList]);

  const accounts = accountsList ?? [];
  const totalLiquid = accounts
    .filter((a) => !["LOAN", "CREDIT_CARD"].includes(a.account_type))
    .reduce((s, a) => s + (a.balance_paise ?? 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Accounts"
        subtitle={`${accounts.length} linked account${accounts.length !== 1 ? "s" : ""} · Net liquid ${formatINRShort(totalLiquid)}`}
        tabs={<TimeRangeTabs />}
        actions={<ActionBtn color="oklch(0.76 0.16 195)">+ Link Account</ActionBtn>}
      />
      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {isLoading && (
          <div style={{ fontSize: 13, color: "var(--text-3)", padding: "20px 0" }}>Loading accounts…</div>
        )}

        {!isLoading && accounts.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-3)", fontSize: 13 }}>
            No accounts linked yet. Use the ingestion pipeline to import your statements.
          </div>
        )}

        {accounts.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {accounts.map((a) => {
              const color = accountColor(a.account_type);
              const balPaise = a.balance_paise ?? 0;
              const isCredit = ["LOAN", "CREDIT_CARD"].includes(a.account_type);
              const sparkData = accountSparklines.get(a.id) ?? [0, 0, 0, 0, 0, 0, 0];
              const latestTxnDate = recentTxns
                ?.filter((t) => t.account_id === a.id)
                .map((t) => t.transaction_date)
                .sort()
                .at(-1);
              const subText = latestTxnDate
                ? `Last txn ${new Date(latestTxnDate).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}`
                : a.nickname ?? accountTypeName(a.account_type);

              return (
                <AccountCard
                  key={a.id}
                  icon={accountIcon(a.account_type)}
                  name={a.nickname ?? a.institution}
                  num="••••"
                  bal={`${balPaise < 0 ? "−" : ""}${formatINRShort(Math.abs(balPaise))}`}
                  sub={subText}
                  synced={!!latestTxnDate}
                  data={sparkData}
                  color={color}
                  type={accountTypeName(a.account_type)}
                  credit={isCredit}
                />
              );
            })}
          </div>
        )}
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
