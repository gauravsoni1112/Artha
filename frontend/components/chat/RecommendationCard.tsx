"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ReasoningTrace } from "./ReasoningTrace";
import { useRecommendationEvent } from "@/lib/queries";
import { useAuth } from "@/lib/auth";
import { confidenceColor, formatConfidence } from "@/lib/format";
import type { RecommendationResponse } from "@/lib/types";

interface Props {
  query: string;
  response: RecommendationResponse;
}

/** Pull the natural-language answer out of an agent output's result object. */
function extractAnswer(result: Record<string, unknown> | undefined): string {
  if (!result) return "";
  if (typeof result.answer === "string") return result.answer;
  return "";
}

/** Friendly label for an agent_id. */
function agentLabel(agentId: string): string {
  const map: Record<string, string> = {
    cashflow_agent: "Cashflow",
    goal_agent: "Goals",
    investment_agent: "Investments",
    risk_agent: "Risk",
    tax_agent: "Tax",
  };
  return map[agentId] ?? agentId;
}

export function RecommendationCard({ query, response }: Props) {
  const { owner } = useAuth();
  const [currentState, setCurrentState] = useState(response.state);
  const eventMutation = useRecommendationEvent(response.recommendation_id);

  const isDone =
    currentState === "ACCEPTED" ||
    currentState === "REJECTED" ||
    currentState === "MODIFIED";

  // Collect agent answers — skip failed agents
  const agentAnswers: { id: string; answer: string }[] =
    (response.agent_outputs_json ?? [])
      .filter((ao) => !ao.error && ao.response?.result)
      .map((ao) => ({
        id: ao.agent_id,
        answer: extractAnswer(ao.response?.result as Record<string, unknown>),
      }))
      .filter((a) => a.answer.length > 0);

  async function handleEvent(eventType: "ACCEPTED" | "REJECTED") {
    if (!owner) return;
    try {
      const result = await eventMutation.mutateAsync({
        event_type: eventType,
        actor_user_id: owner.owner_id,
        payload: {},
      });
      setCurrentState(result.current_state);
    } catch {
      // surfaced via mutation.isError
    }
  }

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      {/* Query echo */}
      <p className="text-xs italic text-muted-foreground line-clamp-2">&ldquo;{query}&rdquo;</p>

      {/* Primary content — natural language answers */}
      {agentAnswers.length > 0 ? (
        <div className="space-y-3">
          {agentAnswers.map(({ id, answer }) => (
            <div key={id}>
              {agentAnswers.length > 1 && (
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                  {agentLabel(id)}
                </p>
              )}
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{answer}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">No analysis available.</p>
      )}

      {/* Confidence pill — subtle, below the answer */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs font-medium ${confidenceColor(response.final_confidence)}`}>
          Confidence: {formatConfidence(response.final_confidence)}
        </span>
        <Badge variant="outline" className="text-xs py-0 h-4">
          {currentState}
        </Badge>
      </div>

      {/* Warnings */}
      {response.warnings.length > 0 && (
        <div className="space-y-1">
          {response.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-xs text-yellow-700 dark:text-yellow-400"
            >
              <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Gaps */}
      {response.gaps.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Data gaps:</p>
          {response.gaps.map((g, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-xs text-muted-foreground"
            >
              <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{g}</span>
            </div>
          ))}
        </div>
      )}

      {/* Reasoning trace — collapsed by default */}
      <ReasoningTrace response={response} />

      {/* Event error */}
      {eventMutation.isError && (
        <p className="text-xs text-red-500">
          {eventMutation.error instanceof Error
            ? eventMutation.error.message
            : "Failed to record event"}
        </p>
      )}

      {/* Actions */}
      {!isDone ? (
        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            onClick={() => handleEvent("ACCEPTED")}
            disabled={eventMutation.isPending}
            className="flex items-center gap-1.5"
          >
            {eventMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5" />
            )}
            Accept
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleEvent("REJECTED")}
            disabled={eventMutation.isPending}
            className="flex items-center gap-1.5"
          >
            <XCircle className="h-3.5 w-3.5" />
            Reject
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-sm pt-1">
          {currentState === "ACCEPTED" ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <span className="text-green-600 dark:text-green-400">Accepted</span>
            </>
          ) : (
            <>
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="text-red-600 dark:text-red-400">Rejected</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
