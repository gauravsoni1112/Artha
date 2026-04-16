"use client";

import React, { useMemo } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useCurrentMonthTransactions } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";

export function CashflowWidget() {
  const { owner } = useAuth();
  const { data: txns, isLoading } = useCurrentMonthTransactions(owner?.owner_id);

  const { income, expense, chartData } = useMemo(() => {
    if (!txns || txns.length === 0) return { income: 0, expense: 0, chartData: [] };

    let inc = 0;
    let exp = 0;
    const dayMap = new Map<string, { income: number; expense: number }>();

    for (const t of txns) {
      const day = t.transaction_date.slice(8, 10); // "01"…"31"
      if (!dayMap.has(day)) dayMap.set(day, { income: 0, expense: 0 });
      const entry = dayMap.get(day)!;
      if (t.transaction_type === "CREDIT") {
        entry.income += t.amount_paise;
        inc += t.amount_paise;
      } else {
        entry.expense += t.amount_paise;
        exp += t.amount_paise;
      }
    }

    const chart = Array.from(dayMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, v]) => ({
        day,
        income: Math.floor(v.income / 100),
        expense: Math.floor(v.expense / 100),
      }));

    return { income: inc, expense: exp, chartData: chart };
  }, [txns]);

  const net = income - expense;
  const isPositive = net >= 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Monthly Cashflow
        </CardTitle>
        {!isLoading && txns && txns.length > 0 && (
          isPositive
            ? <TrendingUp className="h-4 w-4 text-green-500" />
            : <TrendingDown className="h-4 w-4 text-red-500" />
        )}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-28 mb-2" />
            <Skeleton className="h-12 w-full" />
          </>
        ) : !txns || txns.length === 0 ? (
          <>
            <p className="text-2xl font-bold">₹—</p>
            <p className="text-xs text-muted-foreground mt-1">No transactions this month</p>
          </>
        ) : (
          <>
            <p className={`text-2xl font-bold ${isPositive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
              {isPositive ? "+" : ""}{formatINRShort(net)}
            </p>
            <p className="text-xs text-muted-foreground mt-1 mb-2">
              {formatINRShort(income)} in · {formatINRShort(expense)} out
            </p>
            {chartData.length > 0 && (
              <ResponsiveContainer width="100%" height={48}>
                <BarChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                  <Bar dataKey="income" fill="#22c55e" radius={[2, 2, 0, 0]} maxBarSize={6} />
                  <Bar dataKey="expense" fill="#ef4444" radius={[2, 2, 0, 0]} maxBarSize={6} />
                  <Tooltip
                    contentStyle={{ fontSize: 10, padding: "2px 6px" }}
                    formatter={(v) => [`₹${Number(v).toLocaleString("en-IN")}`, ""]}
                    labelFormatter={(l) => `Day ${l}`}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
