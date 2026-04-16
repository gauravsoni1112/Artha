"use client";

import React from "react";
import { useAuth } from "@/lib/auth";
import { Card, CardContent } from "@/components/ui/card";
import { NetWorthWidget } from "@/components/widgets/NetWorthWidget";
import { CashflowWidget } from "@/components/widgets/CashflowWidget";
import { GoalsWidget } from "@/components/widgets/GoalsWidget";
import { TaxWidget } from "@/components/widgets/TaxWidget";
import { RiskWidget } from "@/components/widgets/RiskWidget";
import { AskArtha } from "@/components/chat/AskArtha";

export default function DashboardPage() {
  const { owner } = useAuth();

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {owner ? `Hello, ${owner.name.split(" ")[0]}` : "Dashboard"}
        </h1>
        <p className="text-sm text-muted-foreground">
          Your financial overview at a glance
        </p>
      </div>

      {/* Split layout: widgets left, Ask Artha right */}
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        {/* Widget grid */}
        <div className="grid grid-cols-2 gap-4 content-start">
          <NetWorthWidget />
          <CashflowWidget />
          <GoalsWidget />
          <TaxWidget />
          <RiskWidget />
        </div>

        {/* Ask Artha panel */}
        <Card className="lg:sticky lg:top-4 lg:self-start">
          <CardContent className="pt-4 flex flex-col h-[520px]">
            <AskArtha />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
