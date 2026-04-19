"use client";
import React, { useEffect, useRef } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isPending: boolean;
  placeholder?: string;
  autoFocus?: boolean;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  isPending,
  placeholder,
  autoFocus,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-focus on mount when requested
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  // Auto-grow textarea up to ~5 lines
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !isPending) onSubmit();
    }
  }

  return (
    <div className="flex items-end gap-2 rounded-xl border bg-card px-3 py-2 shadow-sm focus-within:ring-1 focus-within:ring-ring transition-shadow">
      <Textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={
          placeholder ??
          "Ask about your finances… (Enter to send · Shift+Enter for new line)"
        }
        rows={1}
        className="min-h-[36px] max-h-[160px] resize-none border-0 bg-transparent p-0 text-sm shadow-none focus-visible:ring-0"
      />
      <Button
        type="button"
        size="icon"
        className="h-8 w-8 shrink-0 rounded-lg"
        disabled={!value.trim() || isPending}
        onClick={onSubmit}
        aria-label="Send"
      >
        {isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}
