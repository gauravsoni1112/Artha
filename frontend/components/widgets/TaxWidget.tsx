"use client";

import React from "react";
import { FileText } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useProfile } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";

/** Estimate peak marginal slab under the new Indian tax regime (FY 2024–25). */
function estimateBracket(annualRupees: number): string {
  if (annualRupees <= 300_000) return "0%";
  if (annualRupees <= 600_000) return "5%";
  if (annualRupees <= 900_000) return "10%";
  if (annualRupees <= 1_200_000) return "15%";
  if (annualRupees <= 1_500_000) return "20%";
  return "30%";
}

export function TaxWidget() {
  const { owner } = useAuth();
  const { data: prof, isLoading } = useProfile(owner?.owner_id);

  const monthlyIncome = prof?.total_monthly_income_paise ?? 0;
  const annualIncomePaise = monthlyIncome * 12;
  const annualRupees = Math.floor(annualIncomePaise / 100);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">Tax</CardTitle>
        <FileText className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-28 mb-2" />
            <Skeleton className="h-4 w-36" />
          </>
        ) : monthlyIncome === 0 ? (
          <>
            <p className="text-2xl font-bold">₹—</p>
            <p className="text-xs text-muted-foreground mt-1">
              Add income in Settings → Profile
            </p>
          </>
        ) : (
          <>
            <p className="text-2xl font-bold">{formatINRShort(annualIncomePaise)}</p>
            <div className="flex items-center gap-2 mt-1">
              <p className="text-xs text-muted-foreground">Annual income</p>
              <Badge variant="secondary" className="text-xs">
                {estimateBracket(annualRupees)} slab
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Ask Artha for a full tax analysis →
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
