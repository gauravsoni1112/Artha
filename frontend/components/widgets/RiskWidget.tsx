"use client";

import React from "react";
import { ShieldAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useProfile } from "@/lib/queries";

const RISK_BADGE: Record<string, string> = {
  conservative: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
  aggressive: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
};

export function RiskWidget() {
  const { owner } = useAuth();
  const { data: prof, isLoading } = useProfile(owner?.owner_id);

  const riskAppetite = prof?.risk_appetite ?? "moderate";
  const monthlyIncome = prof?.total_monthly_income_paise ?? 0;

  // Compute debt-to-income from emis_json
  const emis = (prof?.emis_json as Array<{ monthly_paise?: number }> | undefined) ?? [];
  const totalEMIPaise = emis.reduce((s, e) => s + (e.monthly_paise ?? 0), 0);
  const dti = monthlyIncome > 0 ? (totalEMIPaise / monthlyIncome) * 100 : null;

  function dtiColor(d: number) {
    if (d > 40) return "text-red-500";
    if (d > 20) return "text-yellow-500";
    return "text-green-500";
  }

  function dtiLabel(d: number) {
    if (d > 40) return "High";
    if (d > 20) return "Moderate";
    return "Healthy";
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">Risk</CardTitle>
        <ShieldAlert className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <>
            <Skeleton className="h-7 w-24 mb-2" />
            <Skeleton className="h-4 w-32" />
          </>
        ) : !prof ? (
          <>
            <p className="text-2xl font-bold">—</p>
            <p className="text-xs text-muted-foreground mt-1">
              Complete your profile to see risk
            </p>
          </>
        ) : (
          <>
            <div className="mb-2">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-1 text-sm font-medium capitalize ${RISK_BADGE[riskAppetite] ?? ""}`}
              >
                {riskAppetite}
              </span>
            </div>
            {dti !== null ? (
              <p className="text-xs text-muted-foreground">
                DTI: <span className={dtiColor(dti)}>{dti.toFixed(1)}% · {dtiLabel(dti)}</span>
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">No EMIs recorded</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
