import React from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { DispatchedAgentOutput, PlanJson } from "@/lib/types";

const AGENT_LABELS: Record<string, string> = {
  cashflow_agent: "Cashflow",
  goal_agent: "Goals",
  investment_agent: "Investments",
  risk_agent: "Risk",
  tax_agent: "Tax",
};

interface Props {
  isPending: boolean;
  planned?: PlanJson;
  outputs?: DispatchedAgentOutput[];
}

export function AgentTimeline({ isPending, planned, outputs }: Props) {
  const agentIds =
    planned?.steps.map((s) => s.agent_id) ??
    outputs?.map((o) => o.agent_id) ??
    [];

  if (agentIds.length === 0) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin shrink-0" />
        <span>Consulting agents…</span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {agentIds.map((agentId) => {
        const output = outputs?.find((o) => o.agent_id === agentId);
        const label = AGENT_LABELS[agentId] ?? agentId;

        let icon: React.ReactNode;
        let colorClass: string;

        if (!output && isPending) {
          icon = <Loader2 className="h-3 w-3 animate-spin" />;
          colorClass = "text-muted-foreground";
        } else if (output?.error) {
          icon = <XCircle className="h-3 w-3" />;
          colorClass = "text-red-500";
        } else if (output?.response) {
          icon = <CheckCircle2 className="h-3 w-3" />;
          colorClass = "text-green-500 dark:text-green-400";
        } else {
          icon = <Loader2 className="h-3 w-3 animate-spin" />;
          colorClass = "text-muted-foreground";
        }

        return (
          <span
            key={agentId}
            className={`flex items-center gap-1 text-xs font-medium ${colorClass}`}
          >
            {icon}
            {label}
          </span>
        );
      })}
    </div>
  );
}
