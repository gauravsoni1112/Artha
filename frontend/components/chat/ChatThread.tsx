"use client";
import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Info,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentTimeline } from "./AgentTimeline";
import { ReasoningTrace } from "./ReasoningTrace";
import { useRecommendationEvent } from "@/lib/queries";
import { useAuth } from "@/lib/auth";
import type { ChatMessage, DispatchedAgentOutput, RecommendationResponse } from "@/lib/types";

// ── Constants ──────────────────────────────────────────────────────────────────

const AGENT_LABELS: Record<string, string> = {
  cashflow_agent: "Cashflow",
  goal_agent: "Goals",
  investment_agent: "Investments",
  risk_agent: "Risk",
  tax_agent: "Tax",
};

const FOLLOW_UP_POOL: Record<string, string> = {
  cashflow_agent: "Break down my spending by category this month",
  goal_agent: "Which of my goals needs the most attention right now?",
  investment_agent: "Is my portfolio allocation balanced for my risk appetite?",
  risk_agent: "What's my biggest financial risk right now?",
  tax_agent: "What deductions am I not using this year?",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function extractAnswer(result: Record<string, unknown> | undefined): string {
  if (!result) return "";
  if (typeof result.answer === "string") return result.answer;
  return "";
}

function agentAnswers(
  outputs: DispatchedAgentOutput[]
): { id: string; label: string; answer: string }[] {
  return outputs
    .filter((ao) => !ao.error && ao.response?.result)
    .map((ao) => ({
      id: ao.agent_id,
      label: AGENT_LABELS[ao.agent_id] ?? ao.agent_id,
      answer: extractAnswer(ao.response?.result as Record<string, unknown>),
    }))
    .filter((a) => a.answer.length > 0);
}

function suggestFollowUps(response: RecommendationResponse): string[] {
  const responded = (response.agent_outputs_json ?? [])
    .filter((ao) => !ao.error && ao.response)
    .map((ao) => ao.agent_id);
  return responded
    .map((id) => FOLLOW_UP_POOL[id])
    .filter(Boolean)
    .slice(0, 3) as string[];
}

// ── Confidence ring ────────────────────────────────────────────────────────────

function ConfidenceRing({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const r = 13;
  const circ = 2 * Math.PI * r;
  const filled = circ * Math.max(0, Math.min(1, value));
  const strokeColor =
    value >= 0.75 ? "#22c55e" : value >= 0.5 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative inline-flex items-center justify-center w-9 h-9 shrink-0">
      <svg width="36" height="36" viewBox="0 0 36 36" aria-hidden>
        <circle
          cx="18" cy="18" r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          className="text-muted/40"
        />
        <circle
          cx="18" cy="18" r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circ}`}
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span
        className="absolute text-[9px] font-bold tabular-nums"
        style={{ color: strokeColor }}
      >
        {pct}%
      </span>
    </div>
  );
}

// ── User bubble ────────────────────────────────────────────────────────────────

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%]">
        <div className="rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>
        <p className="mt-1 text-right text-[10px] text-muted-foreground">
          {new Date(message.timestamp).toLocaleTimeString("en-IN", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}

// ── Assistant bubble ───────────────────────────────────────────────────────────

interface AssistantBubbleProps {
  message: ChatMessage;
  isLast: boolean;
  onFollowUp: (query: string) => void;
  onUpdateMessage: (id: string, updates: Partial<ChatMessage>) => void;
}

function AssistantBubble({
  message,
  isLast,
  onFollowUp,
  onUpdateMessage,
}: AssistantBubbleProps) {
  const { owner } = useAuth();
  const [currentState, setCurrentState] = useState(
    message.response?.state ?? "GENERATED"
  );
  const [copied, setCopied] = useState(false);
  const eventMutation = useRecommendationEvent(
    message.recommendation_id ?? null
  );

  const response = message.response;
  const isDone =
    currentState === "ACCEPTED" ||
    currentState === "REJECTED" ||
    currentState === "MODIFIED";

  const answers = response ? agentAnswers(response.agent_outputs_json ?? []) : [];
  const followUps = isLast && response ? suggestFollowUps(response) : [];

  async function handleEvent(eventType: "ACCEPTED" | "REJECTED") {
    if (!owner) return;
    try {
      const result = await eventMutation.mutateAsync({
        event_type: eventType,
        actor_user_id: owner.owner_id,
        payload: {},
      });
      setCurrentState(result.current_state);
      if (message.response) {
        onUpdateMessage(message.id, {
          response: { ...message.response, state: result.current_state },
        });
      }
    } catch {
      /* error surfaced via eventMutation.isError */
    }
  }

  async function handleCopy() {
    const text = answers.map((a) => a.answer).join("\n\n");
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  }

  if (message.error) {
    return (
      <div className="flex gap-3">
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
          <XCircle className="h-4 w-4 text-red-500" />
        </div>
        <div className="rounded-2xl rounded-tl-sm border border-red-200 dark:border-red-800 bg-card px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {message.error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      {/* Avatar */}
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
      </div>

      <div className="flex-1 min-w-0 space-y-3">
        {/* Answer sections */}
        {answers.length > 0 ? (
          <div className="rounded-2xl rounded-tl-sm border bg-card px-4 py-3 space-y-3 shadow-sm">
            {answers.length === 1 ? (
              <p className="text-sm leading-relaxed whitespace-pre-wrap">
                {answers[0].answer}
              </p>
            ) : (
              answers.map(({ id, label, answer }) => (
                <div key={id}>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    {label}
                  </p>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{answer}</p>
                </div>
              ))
            )}

            {/* Warnings */}
            {(response?.warnings ?? []).length > 0 && (
              <div className="space-y-1 pt-1 border-t">
                {response!.warnings.map((w, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-1.5 text-xs text-yellow-700 dark:text-yellow-400"
                  >
                    <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Data gaps */}
            {(response?.gaps ?? []).length > 0 && (
              <div className="space-y-1 pt-1 border-t">
                <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Data gaps
                </p>
                {response!.gaps.map((g, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-1.5 text-xs text-muted-foreground"
                  >
                    <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    <span>{g}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-2xl rounded-tl-sm border bg-card px-4 py-3 shadow-sm">
            <p className="text-sm text-muted-foreground italic">No analysis available.</p>
          </div>
        )}

        {/* Meta row: confidence + agent pills + copy */}
        {response && (
          <div className="flex items-center gap-2 flex-wrap px-1">
            <ConfidenceRing value={response.final_confidence} />
            <div className="flex-1 min-w-0">
              <AgentTimeline
                isPending={false}
                planned={response.plan_json}
                outputs={response.agent_outputs_json}
              />
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
              onClick={handleCopy}
              title="Copy answer"
            >
              {copied ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        )}

        {/* Reasoning trace */}
        {response && <ReasoningTrace response={response} />}

        {/* Accept / Reject */}
        {response && !isDone && (
          <div className="flex items-center gap-2 px-1">
            <Button
              size="sm"
              className="h-7 text-xs"
              disabled={eventMutation.isPending}
              onClick={() => handleEvent("ACCEPTED")}
            >
              {eventMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
              )}
              Accept
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={eventMutation.isPending}
              onClick={() => handleEvent("REJECTED")}
            >
              <XCircle className="h-3.5 w-3.5 mr-1" />
              Reject
            </Button>
            {eventMutation.isError && (
              <span className="text-xs text-red-500">Failed to record</span>
            )}
          </div>
        )}

        {response && isDone && (
          <div className="flex items-center gap-1.5 px-1 text-xs">
            {currentState === "ACCEPTED" ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                <span className="text-green-600 dark:text-green-400">Accepted</span>
              </>
            ) : (
              <>
                <XCircle className="h-3.5 w-3.5 text-red-500" />
                <span className="text-red-600 dark:text-red-400">Rejected</span>
              </>
            )}
          </div>
        )}

        {/* Follow-up chips */}
        {followUps.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            {followUps.map((chip) => (
              <button
                key={chip}
                onClick={() => onFollowUp(chip)}
                className="rounded-full border border-border bg-background px-3 py-1.5 text-xs text-foreground/80 hover:bg-accent hover:text-accent-foreground transition-colors text-left"
              >
                {chip}
              </button>
            ))}
          </div>
        )}

        <p className="px-1 text-[10px] text-muted-foreground">
          {new Date(message.timestamp).toLocaleTimeString("en-IN", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}

// ── Loading bubble ─────────────────────────────────────────────────────────────

function LoadingBubble() {
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
      </div>
      <div className="rounded-2xl rounded-tl-sm border bg-card px-4 py-3 shadow-sm space-y-2">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin shrink-0" />
          <span>Analysing across agents…</span>
        </div>
        {/* Animated dots */}
        <div className="flex gap-1 pl-6">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────

const QUICK_CHIPS = [
  "Should I increase my SIP by ₹10k?",
  "Am I on track for my goals?",
  "What's my tax liability this year?",
  "Is my emergency fund adequate?",
  "How diversified is my portfolio?",
];

function EmptyState({ onChip }: { onChip: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-6 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
        <Sparkles className="h-7 w-7 text-primary" />
      </div>
      <div className="space-y-1.5 max-w-sm">
        <h3 className="text-base font-semibold">Ask Artha anything</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Your AI financial advisor — ask about cash flow, goals, investments,
          tax, or risk and get a reasoned, multi-agent answer.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 justify-center max-w-md">
        {QUICK_CHIPS.map((chip) => (
          <button
            key={chip}
            onClick={() => onChip(chip)}
            className="rounded-full border border-border bg-background px-3.5 py-1.5 text-sm text-foreground/80 hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main export ────────────────────────────────────────────────────────────────

interface ChatThreadProps {
  messages: ChatMessage[];
  isPending: boolean;
  onFollowUp: (query: string) => void;
  onUpdateMessage: (id: string, updates: Partial<ChatMessage>) => void;
}

export function ChatThread({
  messages,
  isPending,
  onFollowUp,
  onUpdateMessage,
}: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever messages change or loading starts/stops
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isPending]);

  if (messages.length === 0 && !isPending) {
    return <EmptyState onChip={onFollowUp} />;
  }

  return (
    <div className="space-y-6 py-4">
      {messages.map((msg, idx) =>
        msg.role === "user" ? (
          <UserBubble key={msg.id} message={msg} />
        ) : (
          <AssistantBubble
            key={msg.id}
            message={msg}
            isLast={idx === messages.length - 1}
            onFollowUp={onFollowUp}
            onUpdateMessage={onUpdateMessage}
          />
        )
      )}

      {isPending && <LoadingBubble />}

      {/* Scroll anchor */}
      <div ref={bottomRef} />
    </div>
  );
}
