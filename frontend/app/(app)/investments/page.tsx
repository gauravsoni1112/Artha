"use client";

import React, { useMemo } from "react";
import { TrendingUp } from "lucide-react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useAccounts, useTransactions } from "@/lib/queries";
import { formatDate, formatINR } from "@/lib/format";

const COLORS = [
  "#6366f1", "#8b5cf6", "#a855f7", "#ec4899",
  "#f43f5e", "#f97316", "#eab308", "#22c55e", "#0ea5e9",
];

const INVESTMENT_KEYWORDS = ["invest", "mutual", "equity", "sip", "nps", "ppf", "bond", "demat"];

export default function InvestmentsPage() {
  const { owner } = useAuth();
  const { data: accountsList, isLoading: acctLoading } = useAccounts(owner?.owner_id);
  const { data: txns, isLoading: txnLoading } = useTransactions(owner?.owner_id, { limit: 200 });

  const allAccounts = useMemo(() => accountsList ?? [], [accountsList]);

  // Group accounts by type for pie chart
  const pieData = useMemo(() => {
    const map = new Map<string, number>();
    for (const a of allAccounts) {
      map.set(a.account_type, (map.get(a.account_type) ?? 0) + 1);
    }
    return Array.from(map.entries()).map(([name, value]) => ({ name, value }));
  }, [allAccounts]);

  // Investment-category transactions
  const investmentTxns = useMemo(
    () =>
      (txns ?? []).filter((t) => {
        const cat = t.category?.toLowerCase() ?? "";
        const desc = t.description.toLowerCase();
        return INVESTMENT_KEYWORDS.some((k) => cat.includes(k) || desc.includes(k));
      }),
    [txns]
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Investments</h1>
        <p className="text-sm text-muted-foreground">Holdings and portfolio allocation</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Allocation chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Accounts by Type
            </CardTitle>
          </CardHeader>
          <CardContent>
            {acctLoading ? (
              <Skeleton className="h-52 w-full" />
            ) : pieData.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-52 text-muted-foreground text-sm">
                <TrendingUp className="h-8 w-8 mb-2 opacity-30" />
                No accounts. Add some in Settings.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={210}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={52}
                    outerRadius={82}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v) => [`${v} account(s)`, ""]}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Account list */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Accounts ({allAccounts.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {acctLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : allAccounts.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4">
                No accounts. Add some in Settings → Accounts.
              </p>
            ) : (
              <div className="space-y-1 max-h-52 overflow-y-auto">
                {allAccounts.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center justify-between py-2 border-b last:border-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {a.nickname ?? a.institution}
                      </p>
                      {a.nickname && (
                        <p className="text-xs text-muted-foreground truncate">
                          {a.institution}
                        </p>
                      )}
                    </div>
                    <Badge variant="secondary" className="text-xs ml-2 shrink-0">
                      {a.account_type}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Investment transactions */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Investment Activity
          </CardTitle>
        </CardHeader>
        <CardContent>
          {txnLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : investmentTxns.length === 0 ? (
            <div className="py-6 text-center text-muted-foreground">
              <TrendingUp className="h-8 w-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No investment-category transactions found.</p>
              <p className="text-xs mt-1">
                Try asking Artha: &ldquo;Analyse my portfolio&rdquo;
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left font-medium py-2 pr-4">Date</th>
                    <th className="text-left font-medium py-2 pr-4">Description</th>
                    <th className="text-left font-medium py-2 pr-4">Category</th>
                    <th className="text-right font-medium py-2">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {investmentTxns.slice(0, 20).map((t) => (
                    <tr key={t.id} className="border-b last:border-0">
                      <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">
                        {formatDate(t.transaction_date)}
                      </td>
                      <td className="py-2 pr-4 max-w-[200px]">
                        <p className="truncate">{t.description}</p>
                      </td>
                      <td className="py-2 pr-4">
                        {t.category && (
                          <Badge variant="secondary" className="text-xs">
                            {t.category}
                          </Badge>
                        )}
                      </td>
                      <td
                        className={`py-2 text-right tabular-nums whitespace-nowrap ${
                          t.transaction_type === "CREDIT"
                            ? "text-green-600 dark:text-green-400"
                            : "text-foreground"
                        }`}
                      >
                        {t.transaction_type === "CREDIT" ? "+" : "−"}
                        {formatINR(t.amount_paise)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Ask Artha CTA */}
      <Card className="border-dashed">
        <CardContent className="pt-4 pb-4 text-center">
          <p className="text-sm text-muted-foreground">
            For XIRR, rebalancing and portfolio attribution
          </p>
          <p className="text-sm font-medium mt-1">
            Ask Artha → &ldquo;Analyse my portfolio performance&rdquo;
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
