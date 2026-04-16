"use client";

import React, { useMemo } from "react";
import { AlertCircle, CheckCircle2, Info, ShieldAlert, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useAccounts, useProfile, useTransactions } from "@/lib/queries";
import { formatINR, formatINRShort } from "@/lib/format";

// ── Risk colour helpers ───────────────────────────────────────────────────────

function dtiColor(dti: number) {
  if (dti > 40) return { bar: "bg-red-500", text: "text-red-600 dark:text-red-400", label: "High risk" };
  if (dti > 20) return { bar: "bg-yellow-500", text: "text-yellow-600 dark:text-yellow-400", label: "Moderate" };
  return { bar: "bg-green-500", text: "text-green-600 dark:text-green-400", label: "Healthy" };
}


const RISK_STYLE: Record<string, { badge: string; label: string }> = {
  conservative: {
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
    label: "Conservative",
  },
  moderate: {
    badge: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
    label: "Moderate",
  },
  aggressive: {
    badge: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
    label: "Aggressive",
  },
};

const APPETITE_DESC: Record<string, string> = {
  conservative: "Prioritises capital preservation. Lower risk assets, stable returns.",
  moderate: "Balanced approach. Mix of growth and stability.",
  aggressive: "Seeks maximum growth. Higher volatility tolerated.",
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RiskPage() {
  const { owner } = useAuth();
  const { data: prof, isLoading: profLoading } = useProfile(owner?.owner_id);
  const { data: accountsList, isLoading: acctLoading } = useAccounts(owner?.owner_id);

  // Last 3 months transactions for emergency fund calc
  const threeMonthsAgo = useMemo(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 3);
    return d.toISOString().slice(0, 10);
  }, []);
  const { data: recentTxns, isLoading: txnLoading } = useTransactions(owner?.owner_id, {
    date_from: threeMonthsAgo,
    transaction_type: "DEBIT",
    limit: 500,
  });

  const isLoading = profLoading || acctLoading || txnLoading;

  // Debt-to-income ratio
  const monthlyIncome = prof?.total_monthly_income_paise ?? 0;
  const emis = (prof?.emis_json as Array<{ monthly_paise?: number }> | undefined) ?? [];
  const totalEMIPaise = emis.reduce((s, e) => s + (e.monthly_paise ?? 0), 0);
  const dti = monthlyIncome > 0 ? (totalEMIPaise / monthlyIncome) * 100 : null;

  // Emergency fund: avg monthly expenses × 6
  const avgMonthlyExpensePaise = useMemo(() => {
    if (!recentTxns || recentTxns.length === 0) return 0;
    const total = recentTxns.reduce((s, t) => s + t.amount_paise, 0);
    return Math.floor(total / 3); // 3 months avg
  }, [recentTxns]);
  const recommendedEFPaise = avgMonthlyExpensePaise * 6;

  // Diversification: unique account types
  const accountTypes = useMemo(() => {
    const types = new Set((accountsList ?? []).map((a) => a.account_type));
    return Array.from(types);
  }, [accountsList]);
  const diversificationScore = Math.min(accountTypes.length * 20, 100); // simple: 5+ types = 100%

  const riskAppetite = prof?.risk_appetite ?? "moderate";
  const riskStyle = RISK_STYLE[riskAppetite] ?? RISK_STYLE.moderate;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Risk</h1>
        <p className="text-sm text-muted-foreground">Your financial risk profile and key indicators</p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="pt-4">
                <Skeleton className="h-4 w-32 mb-3" />
                <Skeleton className="h-8 w-24 mb-2" />
                <Skeleton className="h-2 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !prof ? (
        <Card>
          <CardContent className="py-10 text-center">
            <ShieldAlert className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-40" />
            <p className="text-muted-foreground text-sm">
              Complete your profile in Settings to see your risk assessment.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {/* 1. Risk appetite */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Risk Appetite
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <span
                className={`inline-flex items-center rounded-full px-3 py-1.5 text-sm font-medium ${riskStyle.badge}`}
              >
                {riskStyle.label}
              </span>
              <p className="text-xs text-muted-foreground">
                {APPETITE_DESC[riskAppetite]}
              </p>
              {prof.age && (
                <p className="text-xs text-muted-foreground">Age: {prof.age}</p>
              )}
            </CardContent>
          </Card>

          {/* 2. Debt-to-income */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Debt-to-Income Ratio
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {dti === null ? (
                <p className="text-sm text-muted-foreground">
                  Add income and EMIs in Settings → Profile.
                </p>
              ) : (
                <>
                  <div className="flex items-end gap-2">
                    <p className={`text-3xl font-bold tabular-nums ${dtiColor(dti).text}`}>
                      {dti.toFixed(1)}%
                    </p>
                    <p className={`text-sm mb-1 ${dtiColor(dti).text}`}>
                      {dtiColor(dti).label}
                    </p>
                  </div>
                  <Progress
                    value={Math.min(dti, 100)}
                    indicatorClassName={dtiColor(dti).bar}
                  />
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    <p>Monthly EMIs: {formatINRShort(totalEMIPaise)}</p>
                    <p>Monthly income: {formatINRShort(monthlyIncome)}</p>
                    <p className="mt-1">
                      {dti > 40
                        ? "DTI above 40% — consider reducing debt before new commitments."
                        : dti > 20
                        ? "DTI between 20–40% — manageable, but watch new debt."
                        : "DTI below 20% — healthy debt load."}
                    </p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* 3. Emergency fund */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Emergency Fund Target
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {avgMonthlyExpensePaise === 0 ? (
                <div className="flex items-start gap-2 text-sm text-muted-foreground">
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <p>No expense data in the last 3 months. Ingest transactions to calculate.</p>
                </div>
              ) : (
                <>
                  <div>
                    <p className="text-2xl font-bold">
                      {formatINRShort(recommendedEFPaise)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Recommended 6-month emergency fund
                    </p>
                  </div>
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    <p>Avg monthly expenses (3-mo): {formatINR(avgMonthlyExpensePaise)}</p>
                    <p>
                      Based on {recentTxns?.length ?? 0} debit transactions since{" "}
                      {threeMonthsAgo}
                    </p>
                  </div>
                  <div className="flex items-start gap-2 text-xs text-muted-foreground bg-muted/30 rounded p-2">
                    <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    <p>
                      This is a target, not your current balance. Connect a savings account
                      for real tracking.
                    </p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* 4. Portfolio diversification */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Account Diversification
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {accountTypes.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No accounts. Add some in Settings → Accounts.
                </p>
              ) : (
                <>
                  <div className="flex items-end gap-2">
                    <p className="text-3xl font-bold">{accountTypes.length}</p>
                    <p className="text-sm text-muted-foreground mb-1">account type(s)</p>
                  </div>
                  <Progress
                    value={diversificationScore}
                    indicatorClassName={
                      diversificationScore >= 60
                        ? "bg-green-500"
                        : diversificationScore >= 40
                        ? "bg-yellow-500"
                        : "bg-red-500"
                    }
                  />
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {accountTypes.map((t) => (
                      <span
                        key={t}
                        className="inline-flex items-center rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {diversificationScore >= 80
                      ? "Well diversified across account types."
                      : diversificationScore >= 60
                      ? "Reasonable diversification — consider adding more asset classes."
                      : "Limited diversification — spreading across more asset classes reduces risk."}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Indicators legend */}
      <Card className="border-dashed">
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              Healthy
            </div>
            <div className="flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 text-yellow-500" />
              Moderate risk
            </div>
            <div className="flex items-center gap-1.5">
              <XCircle className="h-3.5 w-3.5 text-red-500" />
              High risk
            </div>
            <p className="ml-auto">
              For a detailed risk assessment, Ask Artha → &ldquo;What&apos;s my risk profile?&rdquo;
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
