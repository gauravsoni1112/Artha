"use client";

import React, { useMemo } from "react";
import { FileText, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useProfile } from "@/lib/queries";
import { formatINR, formatINRShort } from "@/lib/format";

// ── Tax computation (new regime FY 2024-25) ───────────────────────────────────

interface Slab {
  from: number;
  to: number;
  rate: number;
  tax: number;
}

interface TaxResult {
  grossIncome: number;
  standardDeduction: number;
  taxableIncome: number;
  slabs: Slab[];
  subtotal: number;
  cess: number;
  totalTax: number;
  effectiveRate: number;
  rebate87A: boolean;
}

const STANDARD_DEDUCTION_RUPEES = 75_000;

function computeNewRegimeTax(annualIncomeRupees: number): TaxResult {
  const grossIncome = annualIncomeRupees;
  const standardDeduction = Math.min(STANDARD_DEDUCTION_RUPEES, grossIncome);
  const taxableIncome = Math.max(0, grossIncome - standardDeduction);

  const SLAB_LIMITS = [
    { limit: 300_000, rate: 0 },
    { limit: 600_000, rate: 0.05 },
    { limit: 900_000, rate: 0.10 },
    { limit: 1_200_000, rate: 0.15 },
    { limit: 1_500_000, rate: 0.20 },
    { limit: Infinity, rate: 0.30 },
  ];

  const slabs: Slab[] = [];
  let prevLimit = 0;
  let subtotal = 0;

  for (const { limit, rate } of SLAB_LIMITS) {
    if (taxableIncome <= prevLimit) break;
    const slabFrom = prevLimit;
    const slabTo = Math.min(taxableIncome, limit === Infinity ? taxableIncome : limit);
    const taxable = slabTo - slabFrom;
    const tax = Math.round(taxable * rate);
    slabs.push({ from: slabFrom, to: slabTo, rate, tax });
    subtotal += tax;
    prevLimit = limit === Infinity ? taxableIncome : limit;
  }

  // Section 87A: full rebate if taxable income ≤ ₹7L
  const rebate87A = taxableIncome <= 700_000;
  if (rebate87A) subtotal = 0;

  // 4% Health & Education Cess
  const cess = Math.round(subtotal * 0.04);
  const totalTax = subtotal + cess;
  const effectiveRate = grossIncome > 0 ? (totalTax / grossIncome) * 100 : 0;

  return {
    grossIncome,
    standardDeduction,
    taxableIncome,
    slabs,
    subtotal,
    cess,
    totalTax,
    effectiveRate,
    rebate87A,
  };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TaxPage() {
  const { owner } = useAuth();
  const { data: prof, isLoading } = useProfile(owner?.owner_id);

  const monthlyIncome = prof?.total_monthly_income_paise ?? 0;
  const annualIncomePaise = monthlyIncome * 12;
  const annualIncomeRupees = Math.floor(annualIncomePaise / 100);

  const tax = useMemo(
    () => (annualIncomeRupees > 0 ? computeNewRegimeTax(annualIncomeRupees) : null),
    [annualIncomeRupees]
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tax</h1>
        <p className="text-sm text-muted-foreground">
          Estimated tax under the new regime (FY 2024–25)
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="pt-4">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-8 w-28" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !prof || monthlyIncome === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <FileText className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-40" />
            <p className="text-muted-foreground text-sm">
              Add your income in Settings → Profile to see tax estimates.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground mb-1">Annual income</p>
                <p className="text-2xl font-bold">{formatINRShort(annualIncomePaise)}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {formatINRShort(monthlyIncome)}/mo
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground mb-1">Estimated tax</p>
                <p className="text-2xl font-bold">
                  {tax ? formatINRShort(tax.totalTax * 100) : "₹0"}
                </p>
                {tax?.rebate87A && (
                  <Badge variant="secondary" className="text-xs mt-1">
                    87A rebate applied
                  </Badge>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground mb-1">Effective rate</p>
                <p className="text-2xl font-bold">
                  {tax ? tax.effectiveRate.toFixed(1) : "0"}%
                </p>
                <p className="text-xs text-muted-foreground mt-1">of gross income</p>
              </CardContent>
            </Card>
          </div>

          {/* Slab breakdown */}
          {tax && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Slab breakdown (new regime)
                </CardTitle>
              </CardHeader>
              <CardContent>
                {/* Income flow */}
                <div className="text-sm space-y-1 mb-4 pb-4 border-b">
                  <div className="flex justify-between">
                    <span>Gross annual income</span>
                    <span className="font-medium tabular-nums">
                      {formatINR(annualIncomePaise)}
                    </span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Standard deduction</span>
                    <span className="tabular-nums">
                      − {formatINR(tax.standardDeduction * 100)}
                    </span>
                  </div>
                  <div className="flex justify-between font-medium">
                    <span>Taxable income</span>
                    <span className="tabular-nums">
                      {formatINR(tax.taxableIncome * 100)}
                    </span>
                  </div>
                </div>

                {/* Slabs */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left font-medium py-2 pr-4">Income slab</th>
                        <th className="text-right font-medium py-2 pr-4">Rate</th>
                        <th className="text-right font-medium py-2">Tax</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tax.slabs.map((s, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="py-2 pr-4 text-muted-foreground">
                            {formatINRShort(s.from * 100)} – {s.to === tax.taxableIncome ? formatINRShort(s.to * 100) : formatINRShort(s.to * 100)}
                          </td>
                          <td className="py-2 pr-4 text-right">{(s.rate * 100).toFixed(0)}%</td>
                          <td className="py-2 text-right tabular-nums">
                            {formatINR(s.tax * 100)}
                          </td>
                        </tr>
                      ))}
                      <tr className="border-t">
                        <td className="py-2 pr-4 text-muted-foreground">
                          Health &amp; Education Cess (4%)
                        </td>
                        <td className="py-2 pr-4 text-right">4%</td>
                        <td className="py-2 text-right tabular-nums">
                          {formatINR(tax.cess * 100)}
                        </td>
                      </tr>
                      <tr className="font-semibold">
                        <td className="py-2 pr-4" colSpan={2}>
                          Total estimated tax
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {formatINR(tax.totalTax * 100)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Note */}
                <div className="flex items-start gap-2 mt-4 text-xs text-muted-foreground bg-muted/30 rounded-md p-3">
                  <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <p>
                    Estimate is based on new tax regime FY 2024–25 with ₹75,000 standard deduction.
                    Does not account for HRA, LTA, 80C or other deductions under the old regime.
                    Consult a CA for accurate filing.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Ask Artha CTA */}
          <Card className="border-dashed">
            <CardContent className="pt-4 pb-4 text-center text-sm">
              <p className="text-muted-foreground">
                For capital gains, 80C optimisation, and ITR guidance
              </p>
              <p className="font-medium mt-1">
                Ask Artha → &ldquo;What&apos;s my tax liability and how can I optimise it?&rdquo;
              </p>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
