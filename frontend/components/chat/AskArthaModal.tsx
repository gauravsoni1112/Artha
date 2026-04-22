"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

const PROMPTS = [
  { icon: "⚖️", bg: "rgba(0,200,180,0.1)", text: "Should I rebalance my portfolio?" },
  { icon: "🧾", bg: "rgba(255,160,60,0.1)", text: "What's my tax liability this FY?" },
  { icon: "📉", bg: "rgba(240,80,80,0.1)", text: "Tax-efficient way to exit ₹2L in July" },
  { icon: "🎯", bg: "rgba(160,100,240,0.1)", text: "Am I on track for my goals?" },
  { icon: "💡", bg: "rgba(0,180,220,0.1)", text: "What if I stop my SIP in ICICI Bluechip?" },
  { icon: "📊", bg: "rgba(100,200,100,0.1)", text: "Compare my XIRR vs Nifty 50" },
];

export function AskArthaModal() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();

  const handleOpen = useCallback(() => setOpen(true), []);
  const handleClose = useCallback(() => { setOpen(false); setQuery(""); }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", handler);
    // Expose open fn globally so other components can trigger it
    (window as unknown as Record<string, unknown>).__openArthaModal = handleOpen;
    return () => window.removeEventListener("keydown", handler);
  }, [handleOpen, handleClose]);

  function handleSubmit(text: string) {
    if (!text.trim()) return;
    handleClose();
    router.push(`/advisory/chat?q=${encodeURIComponent(text.trim())}`);
  }

  const filtered = PROMPTS.filter(
    (p) => !query || p.text.toLowerCase().includes(query.toLowerCase())
  );

  if (!open) {
    return (
      <div
        onClick={handleOpen}
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "linear-gradient(135deg, oklch(0.35 0.16 195), oklch(0.3 0.12 250))",
          border: "1px solid var(--cyan-glow)",
          boxShadow: "0 0 24px var(--cyan-glow), 0 8px 32px rgba(0,0,0,0.5)",
          borderRadius: 50,
          padding: "10px 18px 10px 14px",
          cursor: "pointer",
          zIndex: 100,
          animation: "pill-float 4s ease-in-out infinite",
          transition: "all 0.2s",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.animation = "none";
          (e.currentTarget as HTMLDivElement).style.boxShadow =
            "0 0 36px var(--cyan-glow), 0 12px 40px rgba(0,0,0,0.6)";
          (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLDivElement).style.animation = "pill-float 4s ease-in-out infinite";
          (e.currentTarget as HTMLDivElement).style.boxShadow =
            "0 0 24px var(--cyan-glow), 0 8px 32px rgba(0,0,0,0.5)";
          (e.currentTarget as HTMLDivElement).style.transform = "none";
        }}
      >
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: "50%",
            background: "var(--cyan)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
          }}
        >
          ✦
        </div>
        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>Ask Artha</span>
        <span
          style={{
            fontFamily: "var(--font-jetbrains-mono), monospace",
            fontSize: 10,
            color: "var(--text-3)",
            background: "rgba(255,255,255,0.08)",
            border: "1px solid var(--border-bright)",
            padding: "2px 6px",
            borderRadius: 4,
          }}
        >
          ⌘K
        </span>
      </div>
    );
  }

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) handleClose(); }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(8px)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        animation: "fade-in 0.15s ease",
      }}
    >
      <div
        style={{
          width: 580,
          maxWidth: "90vw",
          background: "var(--bg2)",
          border: "1px solid var(--border-bright)",
          borderRadius: 16,
          overflow: "hidden",
          boxShadow: "0 0 60px oklch(0.76 0.16 195 / 0.15), 0 40px 80px rgba(0,0,0,0.6)",
          animation: "modal-in 0.2s ease",
        }}
      >
        {/* Search bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span style={{ color: "var(--text-3)", fontSize: 16 }}>✦</span>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(query); }}
            placeholder="Ask Artha anything about your finances…"
            style={{
              flex: 1,
              background: "none",
              border: "none",
              outline: "none",
              fontFamily: "var(--font-space-grotesk), sans-serif",
              fontSize: 15,
              color: "var(--text)",
              caretColor: "var(--cyan)",
            }}
          />
          <span
            onClick={handleClose}
            style={{
              fontSize: 11,
              color: "var(--text-3)",
              fontFamily: "var(--font-jetbrains-mono), monospace",
              padding: "3px 7px",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            Esc
          </span>
        </div>

        {/* Suggestions */}
        <div style={{ padding: 12, maxHeight: 400, overflowY: "auto" }}>
          <div
            style={{
              fontSize: 10,
              color: "var(--text-3)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              padding: "6px 8px 4px",
            }}
          >
            Suggested
          </div>
          {filtered.map((p, i) => (
            <PromptItem key={i} {...p} onClick={() => handleSubmit(p.text)} />
          ))}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "10px 16px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: 16,
          }}
        >
          {[["↩", "to send"], ["↑↓", "navigate"], ["Esc", "close"]].map(([key, hint]) => (
            <span
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                fontSize: 11,
                color: "var(--text-3)",
                fontFamily: "var(--font-jetbrains-mono), monospace",
              }}
            >
              <span
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 3,
                  padding: "1px 5px",
                  fontSize: 10,
                }}
              >
                {key}
              </span>
              {hint}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function PromptItem({
  icon,
  bg,
  text,
  onClick,
}: {
  icon: string;
  bg: string;
  text: string;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 10px",
        borderRadius: 8,
        cursor: "pointer",
        background: hovered ? "var(--surface-hover)" : "transparent",
        transition: "background 0.1s",
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: 7,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 13,
          flexShrink: 0,
          background: bg,
        }}
      >
        {icon}
      </div>
      <span style={{ fontSize: 13, color: hovered ? "var(--text)" : "var(--text-2)", flex: 1, transition: "color 0.1s" }}>
        {text}
      </span>
      <span style={{ fontSize: 12, color: "var(--text-3)" }}>→</span>
    </div>
  );
}
