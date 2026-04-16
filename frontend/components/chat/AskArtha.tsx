"use client";

import React, { useRef, useState } from "react";
import { Loader2, RefreshCw, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RecommendationCard } from "./RecommendationCard";
import { useAskArtha } from "@/lib/queries";
import { useAuth } from "@/lib/auth";
import type { RecommendationResponse } from "@/lib/types";

const QUICK_CHIPS = [
  "Should I increase my SIP by ₹10k?",
  "Am I on track for my goals?",
  "What's my tax liability this year?",
  "Is my emergency fund adequate?",
  "How diversified is my portfolio?",
];

export function AskArtha() {
  const { owner } = useAuth();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ q: string; r: RecommendationResponse } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mutation = useAskArtha();

  async function submit(q: string) {
    const trimmed = q.trim();
    if (!trimmed || !owner) return;
    setResult(null);
    try {
      const res = await mutation.mutateAsync({ owner_id: owner.owner_id, query: trimmed });
      setResult({ q: trimmed, r: res });
    } catch {
      // error shown via mutation.isError
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    submit(query);
  }

  function handleChip(chip: string) {
    setQuery(chip);
    submit(chip);
  }

  function handleReset() {
    setResult(null);
    setQuery("");
    mutation.reset();
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Ask Artha</h2>
        </div>
        {result && (
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleReset}>
            <RefreshCw className="h-3 w-3 mr-1" />
            New
          </Button>
        )}
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 flex flex-col">
        {mutation.isPending && (
          <div className="flex flex-col items-center justify-center flex-1 gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
            <p className="text-sm">Analysing across agents…</p>
          </div>
        )}

        {mutation.isError && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center flex-1 gap-2">
            <p className="text-sm text-red-500 text-center px-4">
              {mutation.error instanceof Error
                ? mutation.error.message
                : "Something went wrong. Try again."}
            </p>
            <Button variant="outline" size="sm" onClick={handleReset}>
              Try again
            </Button>
          </div>
        )}

        {result && !mutation.isPending && (
          <div className="flex-1 overflow-y-auto pr-0.5">
            <RecommendationCard query={result.q} response={result.r} />
          </div>
        )}

        {!result && !mutation.isPending && !mutation.isError && (
          <div className="flex flex-col items-center justify-center flex-1 gap-4 text-muted-foreground">
            <p className="text-sm text-center px-2 leading-relaxed">
              Ask a question about your finances. Artha will analyse your data across all domain agents.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {QUICK_CHIPS.map((chip) => (
                <button
                  key={chip}
                  onClick={() => handleChip(chip)}
                  className="text-xs bg-secondary text-secondary-foreground rounded-full px-3 py-1.5 hover:bg-secondary/80 transition-colors text-left"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2 shrink-0">
        <Textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask about your finances…"
          className="min-h-[56px] max-h-[120px]"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(query);
            }
          }}
        />
        <Button
          type="submit"
          disabled={!query.trim() || mutation.isPending}
          size="icon"
          className="shrink-0 h-14 w-10"
        >
          {mutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </form>
    </div>
  );
}
