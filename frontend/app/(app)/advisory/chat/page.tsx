"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Trash2 } from "lucide-react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { ChatThread } from "@/components/chat/ChatThread";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { useChatThread } from "@/lib/chat";
import { useAskArtha } from "@/lib/queries";
import { useAuth } from "@/lib/auth";
import type { ChatMessage } from "@/lib/types";

const SUGGESTION_PROMPTS = [
  { icon: "⚖️", text: "Should I rebalance my portfolio?" },
  { icon: "🧾", text: "What's my tax liability this FY?" },
  { icon: "📉", text: "Tax-efficient way to exit ₹2L in July" },
  { icon: "🎯", text: "Am I on track for my goals?" },
  { icon: "💡", text: "What if I stop my SIP in ICICI Bluechip?" },
  { icon: "📊", text: "Compare my XIRR vs Nifty 50" },
];

function extractContent(response: import("@/lib/types").RecommendationResponse): string {
  if (response.synthesized_answer?.trim()) return response.synthesized_answer.trim();
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

function ChatPageInner() {
  const { owner } = useAuth();
  const { messages, addMessage, updateMessage, clearThread, hydrated } = useChatThread(owner?.owner_id);
  const [input, setInput] = useState("");
  const mutation = useAskArtha();
  const searchParams = useSearchParams();

  // Pre-fill from ?q= param (from AskArthaModal)
  useEffect(() => {
    const q = searchParams.get("q");
    if (q && hydrated) setInput(q);
  }, [searchParams, hydrated]);

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
      const response = await mutation.mutateAsync({ owner_id: owner.owner_id, query });
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
        error: err instanceof Error ? err.message : "Something went wrong. Please try again.",
      });
    }
  }

  async function handleFollowUp(query: string) {
    if (!owner || mutation.isPending) return;
    addMessage({ id: crypto.randomUUID(), role: "user", content: query, timestamp: new Date().toISOString() });
    const assistantId = crypto.randomUUID();
    try {
      const response = await mutation.mutateAsync({ owner_id: owner.owner_id, query });
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
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      <ScreenHeader
        title="Ask Artha"
        subtitle="Multi-agent financial advisor"
        actions={
          messages.length > 0 ? (
            <button
              onClick={clearThread}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 12px", background: "transparent",
                border: "1px solid var(--border)", borderRadius: 8,
                color: "var(--text-3)", fontSize: 12, cursor: "pointer", fontFamily: "inherit",
              }}
            >
              <Trash2 size={12} />
              Clear thread
            </button>
          ) : undefined
        }
      />

      {/* Thread or empty state */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 24px" }}>
        {messages.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 24 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>✦</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>What would you like to know?</div>
              <div style={{ fontSize: 13, color: "var(--text-3)" }}>Artha analyses your cashflow, goals, investments, tax &amp; risk</div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8, maxWidth: 560, width: "100%" }}>
              {SUGGESTION_PROMPTS.map((p, i) => (
                <SuggestionChip key={i} icon={p.icon} text={p.text} onClick={() => { setInput(p.text); }} />
              ))}
            </div>
          </div>
        ) : (
          <ChatThread
            messages={messages}
            isPending={mutation.isPending}
            onFollowUp={handleFollowUp}
            onUpdateMessage={updateMessage}
          />
        )}
      </div>

      {/* Composer */}
      <div style={{ padding: "12px 24px 20px", borderTop: "1px solid var(--border)", background: "var(--bg)" }}>
        <ChatComposer
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          isPending={mutation.isPending}
          autoFocus
        />
        <p style={{ marginTop: 8, textAlign: "center", fontSize: 10, color: "var(--text-3)" }}>
          Artha analyses your data across cashflow, goals, investments, tax &amp; risk agents.
        </p>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageInner />
    </Suspense>
  );
}

function SuggestionChip({ icon, text, onClick }: { icon: string; text: string; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
        background: hovered ? "var(--surface)" : "var(--bg2)",
        border: `1px solid ${hovered ? "var(--border-bright)" : "var(--border)"}`,
        borderRadius: 10, cursor: "pointer", textAlign: "left",
        transition: "all 0.15s", fontFamily: "inherit",
      }}
    >
      <span style={{ fontSize: 16, flexShrink: 0 }}>{icon}</span>
      <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.4 }}>{text}</span>
    </button>
  );
}
