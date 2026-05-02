"use client";
/**
 * AskArtha — dashboard mini-launcher.
 *
 * Shows the most recent exchange from the shared thread, with a composer
 * to continue the conversation. Clicking "Open chat" navigates to
 * /advisory/chat for the full threaded experience.
 */
import React, { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatComposer } from "./ChatComposer";
import { AgentTimeline } from "./AgentTimeline";
import { useChatThread } from "@/lib/chat";
import { useAskArtha } from "@/lib/queries";
import { useAuth } from "@/lib/auth";
import { confidenceColor, formatConfidence } from "@/lib/format";
import type { RecommendationResponse } from "@/lib/types";

const QUICK_CHIPS = [
  "Should I increase my SIP by ₹10k?",
  "Am I on track for my goals?",
  "What's my tax liability this year?",
  "Is my emergency fund adequate?",
];

function extractContent(response: RecommendationResponse): string {
  if (response.synthesized_answer?.trim()) return response.synthesized_answer.trim();
  const outputs = response.agent_outputs_json ?? [];
  const answers = outputs
    .filter((ao) => !ao.error && ao.response?.result)
    .map((ao) => {
      const result = ao.response?.result as Record<string, unknown>;
      return typeof result?.answer === "string" ? result.answer : "";
    })
    .filter(Boolean);
  return answers.join("\n\n") || "Analysis complete.";
}

export function AskArtha() {
  const { owner } = useAuth();
  const { messages, addMessage, clearThread, hydrated } = useChatThread(owner?.owner_id);
  const [input, setInput] = useState("");
  const mutation = useAskArtha();

  // Find the last assistant message to preview
  const lastPair = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") {
        const assistant = messages[i];
        const user = messages[i - 1]?.role === "user" ? messages[i - 1] : null;
        return { user, assistant };
      }
    }
    return null;
  })();

  async function handleSubmit() {
    const query = input.trim();
    if (!query || !owner || mutation.isPending) return;
    setInput("");

    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    });

    const assistantId = crypto.randomUUID();
    try {
      const response = await mutation.mutateAsync({
        owner_id: owner.owner_id,
        query,
      });
      addMessage({
        id: assistantId,
        role: "assistant",
        content: extractContent(response),
        timestamp: new Date().toISOString(),
        recommendation_id: response.recommendation_id,
        response,
      });
    } catch (err) {
      addMessage({
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        error: err instanceof Error ? err.message : "Something went wrong.",
      });
    }
  }

  function handleChip(chip: string) {
    setInput(chip);
    // submit after state settles
    setTimeout(() => {
      if (!owner || mutation.isPending) return;
      const query = chip.trim();
      addMessage({
        id: crypto.randomUUID(),
        role: "user",
        content: query,
        timestamp: new Date().toISOString(),
      });
      const assistantId = crypto.randomUUID();
      mutation
        .mutateAsync({ owner_id: owner.owner_id, query })
        .then((response) =>
          addMessage({
            id: assistantId,
            role: "assistant",
            content: extractContent(response),
            timestamp: new Date().toISOString(),
            recommendation_id: response.recommendation_id,
            response,
          })
        )
        .catch((err) =>
          addMessage({
            id: assistantId,
            role: "assistant",
            content: "",
            timestamp: new Date().toISOString(),
            error: err instanceof Error ? err.message : "Something went wrong.",
          })
        );
      setInput("");
    }, 0);
  }

  if (!hydrated) return null;

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Ask Artha</h2>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={clearThread}
              title="Clear thread"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" asChild>
            <Link href="/advisory/chat">
              Open chat
              <ArrowUpRight className="h-3 w-3" />
            </Link>
          </Button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {mutation.isPending && (
          <div className="flex flex-col gap-3 pt-2">
            {lastPair?.user && (
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2 text-xs text-primary-foreground">
                  {lastPair.user.content}
                </div>
              </div>
            )}
            <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
              <span>Analysing across agents…</span>
            </div>
          </div>
        )}

        {!mutation.isPending && lastPair && (
          <div className="flex flex-col gap-2.5 pt-1">
            {/* Last user query */}
            {lastPair.user && (
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2 text-xs text-primary-foreground leading-relaxed">
                  {lastPair.user.content}
                </div>
              </div>
            )}

            {/* Last assistant answer */}
            <div className="rounded-2xl rounded-tl-sm border bg-card/50 px-3.5 py-3 text-xs leading-relaxed space-y-2 shadow-sm">
              {lastPair.assistant.error ? (
                <p className="text-red-500">{lastPair.assistant.error}</p>
              ) : (
                <>
                  <p className="whitespace-pre-wrap line-clamp-6">
                    {lastPair.assistant.content}
                  </p>
                  {lastPair.assistant.response && (
                    <div className="flex items-center gap-2 pt-1 border-t">
                      <span
                        className={`font-medium tabular-nums ${confidenceColor(
                          lastPair.assistant.response.final_confidence
                        )}`}
                      >
                        {formatConfidence(
                          lastPair.assistant.response.final_confidence
                        )}{" "}
                        confidence
                      </span>
                      <span className="text-muted-foreground">·</span>
                      <AgentTimeline
                        isPending={false}
                        outputs={lastPair.assistant.response.agent_outputs_json}
                      />
                    </div>
                  )}
                </>
              )}
            </div>

            {messages.length > 2 && (
              <Link
                href="/advisory/chat"
                className="text-center text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                View full conversation ({Math.floor(messages.length / 2)} exchanges) →
              </Link>
            )}
          </div>
        )}

        {!mutation.isPending && !lastPair && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground py-6">
            <p className="text-xs text-center px-2 leading-relaxed">
              Ask a question about your finances. Artha will analyse your data across all domain agents.
            </p>
            <div className="flex flex-wrap gap-1.5 justify-center">
              {QUICK_CHIPS.map((chip) => (
                <button
                  key={chip}
                  onClick={() => handleChip(chip)}
                  disabled={mutation.isPending}
                  className="text-xs bg-secondary text-secondary-foreground rounded-full px-3 py-1.5 hover:bg-secondary/80 transition-colors text-left disabled:opacity-50"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="shrink-0">
        <ChatComposer
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          isPending={mutation.isPending}
          placeholder="Ask about your finances…"
        />
      </div>
    </div>
  );
}
