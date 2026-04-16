"use client";

import React, { useState } from "react";
import { Loader2, Pencil, Plus, Target, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useCreateGoal, useDeactivateGoal, useGoals, usePatchGoal } from "@/lib/queries";
import { formatDate, formatINR, formatINRShort, progressColor } from "@/lib/format";
import type { FinancialGoal } from "@/lib/types";

// ── Goal form ─────────────────────────────────────────────────────────────────

interface GoalFormState {
  goal_name: string;
  target_rupees: string;
  current_rupees: string;
  target_date: string;
  category: string;
}

const BLANK_FORM: GoalFormState = {
  goal_name: "",
  target_rupees: "",
  current_rupees: "0",
  target_date: "",
  category: "",
};

function formFromGoal(g: FinancialGoal): GoalFormState {
  return {
    goal_name: g.goal_name,
    target_rupees: String(Math.floor(g.target_amount_paise / 100)),
    current_rupees: String(Math.floor(g.current_amount_paise / 100)),
    target_date: g.target_date ?? "",
    category: g.category ?? "",
  };
}

const CATEGORIES = ["Emergency", "Education", "Retirement", "Home", "Vehicle", "Travel", "Other"];

interface GoalDialogProps {
  ownerId: string;
  editGoal?: FinancialGoal;
  onClose: () => void;
}

function GoalDialog({ ownerId, editGoal, onClose }: GoalDialogProps) {
  const [form, setForm] = useState<GoalFormState>(
    editGoal ? formFromGoal(editGoal) : BLANK_FORM
  );
  const [error, setError] = useState<string | null>(null);

  const createMutation = useCreateGoal(ownerId);
  const patchMutation = usePatchGoal(ownerId);
  const isPending = createMutation.isPending || patchMutation.isPending;

  function set(field: keyof GoalFormState, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.goal_name.trim()) return setError("Goal name is required");
    const targetPaise = parseInt(form.target_rupees, 10) * 100;
    if (!form.target_rupees || isNaN(targetPaise) || targetPaise <= 0)
      return setError("Target amount must be a positive number");

    const currentPaise = parseInt(form.current_rupees || "0", 10) * 100;
    const payload = {
      goal_name: form.goal_name.trim(),
      target_amount_paise: targetPaise,
      current_amount_paise: isNaN(currentPaise) ? 0 : currentPaise,
      target_date: form.target_date || undefined,
      category: form.category || undefined,
    };

    try {
      if (editGoal) {
        await patchMutation.mutateAsync({ goalId: editGoal.id, data: payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save goal");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="goal_name">Goal name *</Label>
        <Input
          id="goal_name"
          value={form.goal_name}
          onChange={(e) => set("goal_name", e.target.value)}
          placeholder="e.g. Home down payment"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="target_rupees">Target (₹) *</Label>
          <Input
            id="target_rupees"
            type="number"
            min="1"
            step="1"
            value={form.target_rupees}
            onChange={(e) => set("target_rupees", e.target.value)}
            placeholder="1000000"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="current_rupees">Current (₹)</Label>
          <Input
            id="current_rupees"
            type="number"
            min="0"
            step="1"
            value={form.current_rupees}
            onChange={(e) => set("current_rupees", e.target.value)}
            placeholder="0"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="target_date">Target date</Label>
          <Input
            id="target_date"
            type="date"
            value={form.target_date}
            onChange={(e) => set("target_date", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="category">Category</Label>
          <select
            id="category"
            value={form.category}
            onChange={(e) => set("category", e.target.value)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">Select…</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <DialogClose asChild>
          <Button type="button" variant="outline" size="sm">
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" size="sm" disabled={isPending}>
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {editGoal ? "Save changes" : "Create goal"}
        </Button>
      </div>
    </form>
  );
}

// ── Goal card ─────────────────────────────────────────────────────────────────

interface GoalCardProps {
  goal: FinancialGoal;
  ownerId: string;
}

function GoalCard({ goal, ownerId }: GoalCardProps) {
  const [editOpen, setEditOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deactivateMutation = useDeactivateGoal(ownerId);

  const daysLeft = goal.target_date
    ? Math.ceil(
        (new Date(goal.target_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
      )
    : null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="text-base truncate">{goal.goal_name}</CardTitle>
            {goal.category && (
              <Badge variant="secondary" className="text-xs mt-1">
                {goal.category}
              </Badge>
            )}
          </div>
          <div className="flex gap-1 shrink-0">
            {/* Edit */}
            <Dialog open={editOpen} onOpenChange={setEditOpen}>
              <DialogTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7">
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Edit goal</DialogTitle>
                  <DialogDescription>Update goal details</DialogDescription>
                </DialogHeader>
                <GoalDialog
                  ownerId={ownerId}
                  editGoal={goal}
                  onClose={() => setEditOpen(false)}
                />
              </DialogContent>
            </Dialog>

            {/* Delete */}
            {confirmDelete ? (
              <div className="flex items-center gap-1">
                <Button
                  variant="destructive"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={deactivateMutation.isPending}
                  onClick={() => deactivateMutation.mutate(goal.id)}
                >
                  {deactivateMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    "Confirm"
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Amounts */}
        <div className="flex items-end justify-between">
          <div>
            <p className="text-2xl font-bold">
              {formatINRShort(goal.current_amount_paise)}
            </p>
            <p className="text-xs text-muted-foreground">
              of {formatINR(goal.target_amount_paise)}
            </p>
          </div>
          <span
            className={`text-lg font-semibold tabular-nums ${progressColor(goal.progress_pct).replace("bg-", "text-")}`}
          >
            {Math.round(goal.progress_pct)}%
          </span>
        </div>

        {/* Progress bar */}
        <Progress
          value={goal.progress_pct}
          indicatorClassName={progressColor(goal.progress_pct)}
        />

        {/* Target date */}
        {goal.target_date && (
          <p className="text-xs text-muted-foreground">
            Target: {formatDate(goal.target_date)}
            {daysLeft !== null && daysLeft > 0 && (
              <span className="ml-1">({daysLeft} days left)</span>
            )}
            {daysLeft !== null && daysLeft <= 0 && (
              <span className="ml-1 text-red-500">(overdue)</span>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GoalsPage() {
  const { owner } = useAuth();
  const { data: goalsList, isLoading } = useGoals(owner?.owner_id);
  const [createOpen, setCreateOpen] = useState(false);

  const activeGoals = goalsList?.filter((g) => g.is_active) ?? [];
  const totalSaved = activeGoals.reduce((s, g) => s + g.current_amount_paise, 0);
  const totalTarget = activeGoals.reduce((s, g) => s + g.target_amount_paise, 0);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Goals</h1>
          <p className="text-sm text-muted-foreground">Track and manage your financial goals</p>
        </div>

        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              Add goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New goal</DialogTitle>
              <DialogDescription>Create a new financial goal to track</DialogDescription>
            </DialogHeader>
            <GoalDialog
              ownerId={owner?.owner_id ?? ""}
              onClose={() => setCreateOpen(false)}
            />
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary */}
      {!isLoading && activeGoals.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground mb-1">Active goals</p>
              <p className="text-2xl font-bold">{activeGoals.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground mb-1">Total saved</p>
              <p className="text-2xl font-bold">{formatINRShort(totalSaved)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground mb-1">Total target</p>
              <p className="text-2xl font-bold">{formatINRShort(totalTarget)}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Goals grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="pt-4 space-y-3">
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-2 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : activeGoals.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <Target className="h-10 w-10 mx-auto mb-3 text-muted-foreground opacity-40" />
            <p className="text-muted-foreground">No active goals yet.</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click <strong>Add goal</strong> to get started.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {activeGoals.map((g) => (
            <GoalCard key={g.id} goal={g} ownerId={owner?.owner_id ?? ""} />
          ))}
        </div>
      )}
    </div>
  );
}
