"use client";

import React, { useState } from "react";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { useAuth } from "@/lib/auth";
import { useCreateGoal, useDeactivateGoal, useMultiOwnerGoals, usePatchGoal } from "@/lib/queries";
import { formatDate, formatINRShort } from "@/lib/format";
import type { FinancialGoal } from "@/lib/types";
import { useOwnerIds, useTimeRange, useViewMode } from "@/lib/viewmode";
import { TimeRangeTabs } from "@/components/layout/TimeRangeTabs";

// ── Category helpers ──────────────────────────────────────────
const CATEGORY_ICONS: Record<string, string> = {
  Home: "🏠", Emergency: "🛡️", Travel: "✈️", Education: "🎓",
  Retirement: "🌴", Vehicle: "🚗", Other: "💰",
};
const CATEGORIES = ["Emergency", "Education", "Retirement", "Home", "Vehicle", "Travel", "Other"];

function goalColor(pct: number): string {
  if (pct >= 100) return "oklch(0.73 0.16 145)";
  if (pct >= 60)  return "oklch(0.76 0.16 65)";
  if (pct >= 30)  return "oklch(0.66 0.18 25)";
  return "oklch(0.76 0.16 195)";
}

function goalIcon(category: string | null): string {
  return category ? (CATEGORY_ICONS[category] ?? "💰") : "💰";
}

// ── Goal form ─────────────────────────────────────────────────
interface GoalFormState {
  goal_name: string;
  target_rupees: string;
  current_rupees: string;
  target_date: string;
  category: string;
}

const BLANK: GoalFormState = { goal_name: "", target_rupees: "", current_rupees: "0", target_date: "", category: "" };

function formFromGoal(g: FinancialGoal): GoalFormState {
  return {
    goal_name: g.goal_name,
    target_rupees: String(Math.floor(g.target_amount_paise / 100)),
    current_rupees: String(Math.floor(g.current_amount_paise / 100)),
    target_date: g.target_date ?? "",
    category: g.category ?? "",
  };
}

function GoalDialog({ ownerId, editGoal, onClose }: { ownerId: string; editGoal?: FinancialGoal; onClose: () => void }) {
  const [form, setForm] = useState<GoalFormState>(editGoal ? formFromGoal(editGoal) : BLANK);
  const [error, setError] = useState<string | null>(null);
  const createMut = useCreateGoal(ownerId);
  const patchMut  = usePatchGoal(ownerId);
  const isPending = createMut.isPending || patchMut.isPending;

  function set(f: keyof GoalFormState, v: string) { setForm((p) => ({ ...p, [f]: v })); setError(null); }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.goal_name.trim()) return setError("Goal name is required");
    const tp = parseInt(form.target_rupees, 10) * 100;
    if (!form.target_rupees || isNaN(tp) || tp <= 0) return setError("Target must be a positive number");
    const cp = parseInt(form.current_rupees || "0", 10) * 100;
    const payload = { goal_name: form.goal_name.trim(), target_amount_paise: tp, current_amount_paise: isNaN(cp) ? 0 : cp, target_date: form.target_date || undefined, category: form.category || undefined };
    try {
      if (editGoal) { await patchMut.mutateAsync({ goalId: editGoal.id, data: payload }); } else { await createMut.mutateAsync(payload); }
      onClose();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save goal"); }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5"><Label htmlFor="gn">Goal name *</Label><Input id="gn" value={form.goal_name} onChange={(e) => set("goal_name", e.target.value)} placeholder="e.g. Home down payment" /></div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label htmlFor="tr">Target (₹) *</Label><Input id="tr" type="number" min="1" value={form.target_rupees} onChange={(e) => set("target_rupees", e.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="cr">Current (₹)</Label><Input id="cr" type="number" min="0" value={form.current_rupees} onChange={(e) => set("current_rupees", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label htmlFor="td">Target date</Label><Input id="td" type="date" value={form.target_date} onChange={(e) => set("target_date", e.target.value)} /></div>
        <div className="space-y-1.5">
          <Label htmlFor="cat">Category</Label>
          <select id="cat" value={form.category} onChange={(e) => set("category", e.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="">Select…</option>{CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <div className="flex justify-end gap-2 pt-1">
        <DialogClose asChild><Button type="button" variant="outline" size="sm">Cancel</Button></DialogClose>
        <Button type="submit" size="sm" disabled={isPending}>{isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}{editGoal ? "Save changes" : "Create goal"}</Button>
      </div>
    </form>
  );
}

// ── Goal Card ─────────────────────────────────────────────────
function GoalCard({ goal, ownerId }: { goal: FinancialGoal; ownerId: string }) {
  const [editOpen, setEditOpen] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [hovered, setHovered] = useState(false);
  const deactivateMut = useDeactivateGoal(ownerId);

  const pct   = Math.round(goal.progress_pct);
  const color = goalColor(pct);
  const icon  = goalIcon(goal.category);
  const done  = pct >= 100;

  const daysLeft = goal.target_date
    ? Math.ceil((new Date(goal.target_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    : null;
  const etaText = done ? "Achieved!" : goal.target_date ? formatDate(goal.target_date) : "—";

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: "var(--surface)",
        border: `1px solid ${hovered ? color + "60" : done ? color + "50" : "var(--border)"}`,
        borderRadius: 14, padding: "20px 22px",
        cursor: "pointer", transition: "all 0.2s",
        transform: hovered ? "translateY(-1px)" : "none",
        position: "relative",
      }}
    >
      {done && (
        <div style={{ position: "absolute", top: 14, right: 14, background: "oklch(0.73 0.16 145 / 0.15)", color: "oklch(0.73 0.16 145)", fontSize: 11, padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>✓ Achieved</div>
      )}

      {/* Edit/Delete — top right when not done */}
      {!done && (
        <div style={{ position: "absolute", top: 14, right: 14, display: "flex", gap: 2 }} onClick={(e) => e.stopPropagation()}>
          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogTrigger asChild>
              <button style={{ width: 26, height: 26, borderRadius: 6, background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text-3)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Pencil size={11} />
              </button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Edit goal</DialogTitle><DialogDescription>Update goal details</DialogDescription></DialogHeader>
              <GoalDialog ownerId={ownerId} editGoal={goal} onClose={() => setEditOpen(false)} />
            </DialogContent>
          </Dialog>
          {confirmDel ? (
            <div style={{ display: "flex", gap: 2 }}>
              <button onClick={() => deactivateMut.mutate(goal.id)} style={{ padding: "3px 8px", background: "oklch(0.66 0.18 25 / 0.15)", border: "1px solid oklch(0.66 0.18 25 / 0.3)", borderRadius: 5, color: "oklch(0.66 0.18 25)", fontSize: 10, cursor: "pointer" }}>Confirm</button>
              <button onClick={() => setConfirmDel(false)} style={{ padding: "3px 8px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--text-3)", fontSize: 10, cursor: "pointer" }}>Cancel</button>
            </div>
          ) : (
            <button onClick={() => setConfirmDel(true)} style={{ width: 26, height: 26, borderRadius: 6, background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text-3)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Trash2 size={11} />
            </button>
          )}
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: color + "25", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>{icon}</div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{goal.goal_name}</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>Target: {formatINRShort(goal.target_amount_paise)}</div>
        </div>
      </div>

      {/* Progress */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 8 }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 22, color: "var(--text)", fontWeight: 500 }}>{formatINRShort(goal.current_amount_paise)}</span>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 16, fontWeight: 600, color }}>{pct}%</span>
      </div>
      <div style={{ height: 6, background: "var(--bg3)", borderRadius: 3, marginBottom: 14, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, background: color, borderRadius: 3, transition: "width 0.8s ease" }} />
      </div>

      {/* Meta */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {[
          ["Target Date", daysLeft !== null && daysLeft <= 0 ? "Overdue" : etaText],
          [done ? "Status" : "Category", done ? "✓ Achieved" : (goal.category ?? "General")],
        ].map(([lbl, val]) => (
          <div key={lbl} style={{ background: "var(--bg3)", borderRadius: 7, padding: "8px 10px" }}>
            <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 3 }}>{lbl}</div>
            <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", color: done && lbl === "Status" ? "oklch(0.73 0.16 145)" : "var(--text-2)" }}>{val}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────
export default function GoalsPage() {
  const { owner } = useAuth();
  const { isFamily } = useViewMode();
  const ownerIds = useOwnerIds();
  useTimeRange(); // subscribe so TimeRangeTabs reflects global state

  const { data: goalsList, isLoading } = useMultiOwnerGoals(ownerIds);
  const [createOpen, setCreateOpen] = useState(false);

  const activeGoals = goalsList?.filter((g) => g.is_active) ?? [];
  const onTrack = activeGoals.filter((g) => g.progress_pct >= 40).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Goals"
        subtitle={`${activeGoals.length} active · ${onTrack} on track${isFamily ? " · Family" : ""}`}
        tabs={<TimeRangeTabs />}
        actions={
          !isFamily && (
            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
                <button
                  style={{ padding: "6px 14px", background: "oklch(0.76 0.16 65 / 0.1)", border: "1px solid oklch(0.76 0.16 65 / 0.3)", borderRadius: 8, color: "oklch(0.76 0.16 65)", fontSize: 12, cursor: "pointer", fontFamily: "inherit", display: "flex", alignItems: "center", gap: 6 }}
                >
                  <Plus size={13} />New Goal
                </button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>New goal</DialogTitle><DialogDescription>Create a new financial goal</DialogDescription></DialogHeader>
                <GoalDialog ownerId={owner?.owner_id ?? ""} onClose={() => setCreateOpen(false)} />
              </DialogContent>
            </Dialog>
          )
        }
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {isLoading ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px 22px", height: 180, animation: "pulse-dot 2s ease-in-out infinite" }} />
            ))}
          </div>
        ) : activeGoals.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 300, gap: 12 }}>
            <div style={{ fontSize: 32 }}>🎯</div>
            <div style={{ fontSize: 16, color: "var(--text-2)", fontWeight: 500 }}>No active goals yet</div>
            <div style={{ fontSize: 13, color: "var(--text-3)" }}>Click New Goal to get started</div>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
            {activeGoals.map((g) => (
              <GoalCard key={g.id} goal={g} ownerId={g.owner_id} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
