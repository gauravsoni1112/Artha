"use client";

import React from "react";
import { Wallet } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useProfile, useGoals } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";

export function NetWorthWidget() {
  const { owner } = useAuth();
  const { data: prof, isLoading: pLoading } = useProfile(owner?.owner_id);
  const { data: goalsList, isLoading: gLoading } = useGoals(owner?.owner_id);

  const isLoading = pLoading || gLoading;

  const goalsSavings = goalsList
    ? goalsList.filter((g) => g.is_active).reduce((s, g) => s + g.current_amount_paise, 0)
    : 0;

  const monthlyIncome = prof?.total_monthly_income_paise ?? 0;
  const hasData = goalsSavings > 0 || monthlyIncome > 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">Net Worth</CardTitle>
        <Wallet className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-28 mb-2" />
            <Skeleton className="h-4 w-40" />
          </>
        ) : !hasData ? (
          <>
            <p className="text-2xl font-bold">₹—</p>
            <p className="text-xs text-muted-foreground mt-1">Add income &amp; goals in Settings</p>
          </>
        ) : (
          <>
            <p className="text-2xl font-bold">{formatINRShort(goalsSavings)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Saved toward goals
              {monthlyIncome > 0 && ` · ${formatINRShort(monthlyIncome)}/mo income`}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
