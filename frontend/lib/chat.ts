"use client";
/**
 * useChatThread — persists the Artha AI conversation to localStorage so the
 * dashboard mini-launcher and the full /advisory/chat page share the same thread.
 *
 * The key is scoped to ownerId so different owners on the same browser
 * never share or see each other's conversation history.
 */
import { useState, useEffect, useCallback } from "react";
import type { ChatMessage } from "./types";

const MAX_MESSAGES = 120;

function threadKey(ownerId: string | null | undefined): string {
  return ownerId ? `artha_chat_v1_${ownerId}` : "artha_chat_v1_anon";
}

function persist(msgs: ChatMessage[], ownerId: string | null | undefined) {
  try {
    localStorage.setItem(threadKey(ownerId), JSON.stringify(msgs.slice(-MAX_MESSAGES)));
  } catch {}
}

export function useChatThread(ownerId: string | null | undefined) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setMessages([]);
    setHydrated(false);
    try {
      const raw = localStorage.getItem(threadKey(ownerId));
      if (raw) setMessages(JSON.parse(raw));
    } catch {}
    setHydrated(true);
  }, [ownerId]);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => {
      const next = [...prev, msg];
      persist(next, ownerId);
      return next;
    });
  }, [ownerId]);

  const updateMessage = useCallback((id: string, updates: Partial<ChatMessage>) => {
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id ? { ...m, ...updates } : m));
      persist(next, ownerId);
      return next;
    });
  }, [ownerId]);

  const clearThread = useCallback(() => {
    try {
      localStorage.removeItem(threadKey(ownerId));
    } catch {}
    setMessages([]);
  }, [ownerId]);

  return { messages, addMessage, updateMessage, clearThread, hydrated };
}
