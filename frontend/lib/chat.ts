"use client";
/**
 * useChatThread — persists the Artha AI conversation to localStorage so the
 * dashboard mini-launcher and the full /advisory/chat page share the same thread.
 */
import { useState, useEffect, useCallback } from "react";
import type { ChatMessage } from "./types";

const THREAD_KEY = "artha_chat_v1";
const MAX_MESSAGES = 120;

function persist(msgs: ChatMessage[]) {
  try {
    localStorage.setItem(THREAD_KEY, JSON.stringify(msgs.slice(-MAX_MESSAGES)));
  } catch {}
}

export function useChatThread() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(THREAD_KEY);
      if (raw) setMessages(JSON.parse(raw));
    } catch {}
    setHydrated(true);
  }, []);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => {
      const next = [...prev, msg];
      persist(next);
      return next;
    });
  }, []);

  const updateMessage = useCallback((id: string, updates: Partial<ChatMessage>) => {
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id ? { ...m, ...updates } : m));
      persist(next);
      return next;
    });
  }, []);

  const clearThread = useCallback(() => {
    try {
      localStorage.removeItem(THREAD_KEY);
    } catch {}
    setMessages([]);
  }, []);

  return { messages, addMessage, updateMessage, clearThread, hydrated };
}
