"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { formatConfidence } from "@/lib/format";
import type { RecommendationResponse } from "@/lib/types";

interface Props {
  response: RecommendationResponse;
}

export function ReasoningTrace({ response }: Props) {
  const [open, setOpen] = useState(false);
  const { plan_json, agent_outputs_json, final_output } = response;

  const hasTrace =
    (plan_json?.steps?.length ?? 0) > 0 ||
    (agent_outputs_json?.length ?? 0) > 0;

  if (!hasTrace) return null;

  return (
    <div className="mt-3 border rounded-md overflow-hidden text-xs">
      <button
        className="flex w-full items-center justify-between px-3 py-2 bg-muted/40 hover:bg-muted/60 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="font-medium">Reasoning trace</span>
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>

      {open && (
        <div className="px-3 py-3 space-y-4 bg-muted/10">
          {/* Plan steps */}
          {plan_json && plan_json.steps.length > 0 && (
            <div>
              <p className="font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                Plan
              </p>
              <div className="space-y-1">
                {plan_json.steps.map((step, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
                    <span className="font-mono">{step.agent_id}</span>
                    {step.depends_on.length > 0 && (
                      <span className="text-muted-foreground">
                        after {step.depends_on.join(", ")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Agent outputs */}
          {agent_outputs_json && agent_outputs_json.length > 0 && (
            <div>
              <p className="font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                Agents
              </p>
              <div className="space-y-2">
                {agent_outputs_json.map((ao, i) => (
                  <div key={i} className="border-l-2 border-border pl-2.5 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {ao.error ? (
                        <XCircle className="h-3 w-3 text-red-500 shrink-0" />
                      ) : (
                        <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
                      )}
                      <span className="font-medium font-mono">{ao.agent_id}</span>
                      {ao.response && (
                        <Badge variant="secondary" className="text-xs py-0 h-4">
                          {formatConfidence(ao.response.confidence)}
                        </Badge>
                      )}
                      <Badge variant="outline" className="text-xs py-0 h-4">
                        {ao.fallback_tier}
                      </Badge>
                      {ao.response?.fallback_used && (
                        <Badge variant="outline" className="text-xs py-0 h-4 border-yellow-400 text-yellow-600">
                          fallback
                        </Badge>
                      )}
                    </div>
                    {ao.error && (
                      <p className="text-red-500 pl-4">{ao.error}</p>
                    )}
                    {ao.response?.warnings?.map((w, j) => (
                      <div key={j} className="flex items-start gap-1 text-yellow-600 dark:text-yellow-400 pl-4">
                        <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                        <span>{w}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Critic summary */}
          <div>
            <p className="font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
              Critic
            </p>
            <p>
              Baseline:{" "}
              <span className="font-medium">
                {formatConfidence(final_output.baseline_confidence)}
              </span>
              {final_output.total_penalty > 0 && (
                <>
                  {" "}→ Penalty:{" "}
                  <span className="text-red-500">
                    −{formatConfidence(final_output.total_penalty)}
                  </span>
                </>
              )}
              {" "}→ Final:{" "}
              <span className="font-medium">
                {formatConfidence(final_output.final_confidence ?? response.final_confidence)}
              </span>
            </p>
            {final_output.consistency_flags?.map((f, i) => (
              <div key={i} className="flex items-start gap-1 text-yellow-600 dark:text-yellow-400 mt-1">
                <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                <span>{f.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
