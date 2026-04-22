"use client";

import React from "react";
import { useRequireAuth } from "@/lib/auth";
import { Sidebar } from "@/components/layout/Sidebar";
import { AskArthaModal } from "@/components/chat/AskArthaModal";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  useRequireAuth();

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        overflow: "hidden",
        position: "relative",
        zIndex: 1,
      }}
    >
      <Sidebar />
      <main
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {children}
      </main>
      <AskArthaModal />
    </div>
  );
}
