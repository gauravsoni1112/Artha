"use client";

import React, { useState } from "react";
import { Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatThread } from "@/components/chat/ChatThread";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { useChatThread } from "@/lib/chat";
import { useAskArtha } from "@/lib/queries";
import { useAuth } from "@/lib/auth";
import type { ChatMessage } from "@/lib/types";

function extractContent(response: import("@/lib/types").RecommendationResponse): string {
  const outputs = response.agent_outputs_json ?? [];
  const answers = outputs
    .filter((ao) => !ao.error && ao.response?.result)
    .map((ao) => {
      const result = ao.response?.result as Record<string, unknown>;
      return typeof result?.answer === "string" ? result.answer : "";
    })
    .filter(Boolean);
  return answers.join("\n\n") || "Analysis complete — see reasoning trace for details.";
}

export default function ChatPage() {
  const { owner } = useAuth();
  const { messages, addMessage, updateMessage, clearThread, hydrated } =
    useChatThread();
  const [input, setInput] = useState("");
  const mutation = useAskArtha();

  async function handleSubmit() {
    const query = input.trim();
    if (!query || !owner || mutation.isPending) return;
    setInput("");

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };
    addMessage(userMsg);

    const assistantId = crypto.randomUUID();

    try {
      const response = await mutation.mutateAsync({
        owner_id: owner.owner_id,
        query,
      });

      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: extractContent(response),
        timestamp: new Date().toISOString(),
        recommendation_id: response.recommendation_id,
        response,
      };
      addMessage(assistantMsg);
    } catch (err) {
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        error:
          err instanceof Error
            ? err.message
            : "Something went wrong. Please try again.",
      };
      addMessage(assistantMsg);
    }
  }

  // Follow-up chips submit directly without going through input state
  async function handleFollowUp(query: string) {
    if (!owner || mutation.isPending) return;

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

  if (!hydrated) return null;

  return (
    <div className="flex flex-col max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">Artha AI</h1>
            <p className="text-xs text-muted-foreground">
              Multi-agent financial advisor
            </p>
          </div>
        </div>
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-xs text-muted-foreground"
            onClick={clearThread}
          >
            <Trash2 className="h-3.5 w-3.5 mr-1.5" />
            Clear thread
          </Button>
        )}
      </div>

      {/* Thread */}
      <ChatThread
        messages={messages}
        isPending={mutation.isPending}
        onFollowUp={handleFollowUp}
        onUpdateMessage={updateMessage}
      />

      {/* Composer — sticky to bottom of scroll container */}
      <div className="sticky bottom-0 bg-background/95 backdrop-blur py-3 border-t">
        <ChatComposer
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          isPending={mutation.isPending}
          autoFocus
        />
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          Artha analyses your data across cashflow, goals, investments, tax &amp; risk agents.
        </p>
      </div>
    </div>
  );
}
