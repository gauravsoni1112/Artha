"use client";

import React, { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Building2,
  Coins,
  FileText,
  Shield,
  Users,
} from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import {
  useAccounts,
  useAddGold,
  useAddInsurance,
  useAddITR,
  useAddRealEstate,
  useCreateAccount,
  useCreateGoal,
  useCreateProfile,
  useDeactivateAccount,
  useDeactivateGoal,
  useFamilyMembers,
  useGoals,
  usePatchAccount,
  usePatchGoal,
  usePatchProfile,
  useProfile,
} from "@/lib/queries";
import { formatDate, formatINRShort, progressColor } from "@/lib/format";
import type { Account, FinancialGoal } from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────────────
// Profile tab
// ─────────────────────────────────────────────────────────────────────────────

function ProfileTab({ ownerId }: { ownerId: string }) {
  const { data: profileData, isLoading } = useProfile(ownerId);
  const patchProfile = usePatchProfile(ownerId);
  const createProfile = useCreateProfile(ownerId);

  const [risk, setRisk] = useState<string>("");
  const [age, setAge] = useState<string>("");
  const [income, setIncome] = useState<string>("");
  const [isDirty, setIsDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // EMI list editor
  const [emis, setEmis] = useState<Array<{ label: string; amount_rupees: string; remaining_months: string }>>([]);
  const [emisLoaded, setEmisLoaded] = useState(false);

  React.useEffect(() => {
    if (profileData && !isDirty) {
      setRisk(profileData.risk_appetite);
      setAge(profileData.age != null ? String(profileData.age) : "");
      setIncome(String(Math.floor(profileData.total_monthly_income_paise / 100)));
      if (!emisLoaded) {
        setEmis(
          ((profileData.emis_json ?? []) as Array<{ label: string; amount_paise: number; remaining_months?: number }>).map(
            (e) => ({
              label: e.label ?? "",
              amount_rupees: String(Math.floor(e.amount_paise / 100)),
              remaining_months: String(e.remaining_months ?? ""),
            })
          )
        );
        setEmisLoaded(true);
      }
    }
  }, [profileData, isDirty, emisLoaded]);

  function markDirty() {
    setIsDirty(true);
    setSuccess(false);
    setError(null);
  }

  function addEMI() {
    setEmis((prev) => [...prev, { label: "", amount_rupees: "", remaining_months: "" }]);
    markDirty();
  }

  function removeEMI(i: number) {
    setEmis((prev) => prev.filter((_, idx) => idx !== i));
    markDirty();
  }

  function updateEMI(i: number, field: "label" | "amount_rupees" | "remaining_months", val: string) {
    setEmis((prev) => prev.map((e, idx) => (idx === i ? { ...e, [field]: val } : e)));
    markDirty();
  }

  async function handleSave() {
    setError(null);
    const incomeRupees = parseInt(income || "0", 10);
    if (isNaN(incomeRupees) || incomeRupees < 0) return setError("Monthly income must be a non-negative number");

    const ageVal = age ? parseInt(age, 10) : undefined;
    if (age && (isNaN(ageVal!) || ageVal! < 0 || ageVal! > 120)) return setError("Age must be between 0 and 120");

    const emisJson = emis
      .filter((e) => e.label.trim() && e.amount_rupees)
      .map((e) => ({
        label: e.label.trim(),
        amount_paise: parseInt(e.amount_rupees, 10) * 100,
        remaining_months: e.remaining_months ? parseInt(e.remaining_months, 10) : undefined,
      }));

    try {
      await patchProfile.mutateAsync({
        risk_appetite: risk as "conservative" | "moderate" | "aggressive",
        age: ageVal,
        total_monthly_income_paise: incomeRupees * 100,
        emis_json: emisJson,
      });
      setIsDirty(false);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3 max-w-lg">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
      </div>
    );
  }

  if (!profileData) {
    return (
      <Card>
        <CardContent className="py-12 text-center space-y-3">
          <p className="text-muted-foreground">No profile found.</p>
          {createProfile.isError && (
            <p className="text-sm text-red-500">
              {createProfile.error instanceof Error ? createProfile.error.message : "Failed to create profile"}
            </p>
          )}
          <Button
            onClick={() => createProfile.mutate({ risk_appetite: "moderate", total_monthly_income_paise: 0 })}
            disabled={createProfile.isPending}
          >
            {createProfile.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Create profile
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6 max-w-lg">
      {/* Basic info */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Basic information
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="risk_appetite">Risk appetite</Label>
            <select
              id="risk_appetite"
              value={risk}
              onChange={(e) => { setRisk(e.target.value); markDirty(); }}
              className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="age">Age</Label>
              <Input
                id="age"
                type="number"
                min="0"
                max="120"
                value={age}
                onChange={(e) => { setAge(e.target.value); markDirty(); }}
                placeholder="e.g. 32"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="income">Monthly income (₹)</Label>
              <Input
                id="income"
                type="number"
                min="0"
                value={income}
                onChange={(e) => { setIncome(e.target.value); markDirty(); }}
                placeholder="e.g. 150000"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* EMIs */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              EMIs / Loan repayments
            </CardTitle>
            <Button variant="ghost" size="sm" className="gap-1 h-7 text-xs" onClick={addEMI}>
              <Plus className="h-3 w-3" /> Add EMI
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {emis.length === 0 && (
            <p className="text-sm text-muted-foreground">No EMIs configured.</p>
          )}
          {emis.map((emi, i) => (
            <div key={i} className="flex gap-2 items-end">
              <div className="flex-1 space-y-1">
                <Label className="text-xs text-muted-foreground">Label</Label>
                <Input
                  value={emi.label}
                  onChange={(e) => updateEMI(i, "label", e.target.value)}
                  placeholder="Home loan"
                  className="h-8 text-sm"
                />
              </div>
              <div className="w-28 space-y-1">
                <Label className="text-xs text-muted-foreground">Amount (₹)</Label>
                <Input
                  type="number"
                  min="1"
                  value={emi.amount_rupees}
                  onChange={(e) => updateEMI(i, "amount_rupees", e.target.value)}
                  placeholder="25000"
                  className="h-8 text-sm"
                />
              </div>
              <div className="w-24 space-y-1">
                <Label className="text-xs text-muted-foreground">Months left</Label>
                <Input
                  type="number"
                  min="1"
                  value={emi.remaining_months}
                  onChange={(e) => updateEMI(i, "remaining_months", e.target.value)}
                  placeholder="120"
                  className="h-8 text-sm"
                />
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0"
                onClick={() => removeEMI(i)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {success && <p className="text-sm text-green-600">Profile saved successfully.</p>}

      <Button onClick={handleSave} disabled={!isDirty || patchProfile.isPending}>
        {patchProfile.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
        Save changes
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Goals tab (reuse logic from /goals page, condensed table view)
// ─────────────────────────────────────────────────────────────────────────────

interface GoalFormState {
  goal_name: string;
  target_rupees: string;
  current_rupees: string;
  target_date: string;
  category: string;
}

const BLANK_GOAL: GoalFormState = { goal_name: "", target_rupees: "", current_rupees: "0", target_date: "", category: "" };
const CATEGORIES = ["Emergency", "Education", "Retirement", "Home", "Vehicle", "Travel", "Other"];

function formFromGoal(g: FinancialGoal): GoalFormState {
  return {
    goal_name: g.goal_name,
    target_rupees: String(Math.floor(g.target_amount_paise / 100)),
    current_rupees: String(Math.floor(g.current_amount_paise / 100)),
    target_date: g.target_date ?? "",
    category: g.category ?? "",
  };
}

function GoalFormFields({
  ownerId,
  editGoal,
  onClose,
}: { ownerId: string; editGoal?: FinancialGoal; onClose: () => void }) {
  const [form, setForm] = useState<GoalFormState>(editGoal ? formFromGoal(editGoal) : BLANK_GOAL);
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
      return setError("Target must be a positive number");
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
        <Label htmlFor="g_name">Goal name *</Label>
        <Input id="g_name" value={form.goal_name} onChange={(e) => set("goal_name", e.target.value)} placeholder="e.g. Home down payment" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Target (₹) *</Label>
          <Input type="number" min="1" step="1" value={form.target_rupees} onChange={(e) => set("target_rupees", e.target.value)} placeholder="1000000" />
        </div>
        <div className="space-y-1.5">
          <Label>Current (₹)</Label>
          <Input type="number" min="0" step="1" value={form.current_rupees} onChange={(e) => set("current_rupees", e.target.value)} placeholder="0" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Target date</Label>
          <Input type="date" value={form.target_date} onChange={(e) => set("target_date", e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>Category</Label>
          <select value={form.category} onChange={(e) => set("category", e.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="">Select…</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <div className="flex justify-end gap-2 pt-1">
        <DialogClose asChild>
          <Button type="button" variant="outline" size="sm">Cancel</Button>
        </DialogClose>
        <Button type="submit" size="sm" disabled={isPending}>
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {editGoal ? "Save" : "Create"}
        </Button>
      </div>
    </form>
  );
}

function GoalsTab({ ownerId }: { ownerId: string }) {
  const { data: goalsList, isLoading } = useGoals(ownerId);
  const deactivate = useDeactivateGoal(ownerId);
  const [createOpen, setCreateOpen] = useState(false);
  const [editGoal, setEditGoal] = useState<FinancialGoal | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const activeGoals = goalsList?.filter((g) => g.is_active) ?? [];

  if (isLoading) return (
    <div className="space-y-2">
      {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{activeGoals.length} active {activeGoals.length === 1 ? "goal" : "goals"}</p>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" /> Add goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New goal</DialogTitle>
              <DialogDescription>Create a new financial goal to track</DialogDescription>
            </DialogHeader>
            <GoalFormFields ownerId={ownerId} onClose={() => setCreateOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      {activeGoals.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No active goals. Click <strong>Add goal</strong> to get started.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {activeGoals.map((g) => (
            <Card key={g.id}>
              <CardContent className="py-3 px-4">
                <div className="flex items-center gap-3">
                  {/* Progress bar */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-medium truncate">{g.goal_name}</span>
                        {g.category && <Badge variant="secondary" className="text-xs shrink-0">{g.category}</Badge>}
                      </div>
                      <span className="text-xs text-muted-foreground shrink-0 ml-2">
                        {formatINRShort(g.current_amount_paise)} / {formatINRShort(g.target_amount_paise)}
                      </span>
                    </div>
                    <Progress value={g.progress_pct} indicatorClassName={progressColor(g.progress_pct)} className="h-1.5" />
                  </div>

                  {/* Actions */}
                  <div className="flex gap-1 shrink-0">
                    <Dialog open={editGoal?.id === g.id} onOpenChange={(o) => !o && setEditGoal(null)}>
                      <DialogTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditGoal(g)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Edit goal</DialogTitle>
                          <DialogDescription>Update goal details</DialogDescription>
                        </DialogHeader>
                        <GoalFormFields ownerId={ownerId} editGoal={g} onClose={() => setEditGoal(null)} />
                      </DialogContent>
                    </Dialog>

                    {confirmId === g.id ? (
                      <div className="flex gap-1 items-center">
                        <Button variant="destructive" size="sm" className="h-7 text-xs"
                          disabled={deactivate.isPending}
                          onClick={() => { deactivate.mutate(g.id); setConfirmId(null); }}>
                          {deactivate.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Confirm"}
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setConfirmId(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setConfirmId(g.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Accounts tab
// ─────────────────────────────────────────────────────────────────────────────

const ACCOUNT_TYPES = ["SAVINGS", "CHECKING", "CREDIT_CARD", "DEMAT", "PPF", "NPS", "MUTUAL_FUND", "FIXED_DEPOSIT", "OTHER"];

function AccountFormFields({
  ownerId,
  editAccount,
  onClose,
}: { ownerId: string; editAccount?: Account; onClose: () => void }) {
  const [form, setForm] = useState({
    account_type: editAccount?.account_type ?? "",
    institution: editAccount?.institution ?? "",
    nickname: editAccount?.nickname ?? "",
    account_number: "",
  });
  const [error, setError] = useState<string | null>(null);
  const create = useCreateAccount(ownerId);
  const patch = usePatchAccount(ownerId);
  const isPending = create.isPending || patch.isPending;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.account_type) return setError("Account type is required");
    if (!form.institution.trim()) return setError("Institution is required");
    try {
      if (editAccount) {
        await patch.mutateAsync({
          accountId: editAccount.id,
          data: {
            account_type: form.account_type,
            institution: form.institution.trim(),
            nickname: form.nickname.trim() || undefined,
          },
        });
      } else {
        await create.mutateAsync({
          account_type: form.account_type,
          institution: form.institution.trim(),
          nickname: form.nickname.trim() || undefined,
          account_number: form.account_number.trim() || undefined,
        });
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save account");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label>Account type *</Label>
        <select
          value={form.account_type}
          onChange={(e) => setForm((f) => ({ ...f, account_type: e.target.value }))}
          className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Select…</option>
          {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label>Institution *</Label>
        <Input
          value={form.institution}
          onChange={(e) => setForm((f) => ({ ...f, institution: e.target.value }))}
          placeholder="e.g. HDFC Bank"
        />
      </div>
      <div className="space-y-1.5">
        <Label>Nickname</Label>
        <Input
          value={form.nickname}
          onChange={(e) => setForm((f) => ({ ...f, nickname: e.target.value }))}
          placeholder="e.g. Salary account"
        />
      </div>
      {!editAccount && (
        <div className="space-y-1.5">
          <Label>Account number (optional — stored hashed)</Label>
          <Input
            value={form.account_number}
            onChange={(e) => setForm((f) => ({ ...f, account_number: e.target.value }))}
            placeholder="xxxx xxxx xxxx 1234"
          />
        </div>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}
      <div className="flex justify-end gap-2 pt-1">
        <DialogClose asChild>
          <Button type="button" variant="outline" size="sm">Cancel</Button>
        </DialogClose>
        <Button type="submit" size="sm" disabled={isPending}>
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {editAccount ? "Save" : "Add account"}
        </Button>
      </div>
    </form>
  );
}

function AccountsTab({ ownerId }: { ownerId: string }) {
  const { data: accountsList, isLoading } = useAccounts(ownerId);
  const deactivate = useDeactivateAccount(ownerId);
  const [createOpen, setCreateOpen] = useState(false);
  const [editAccount, setEditAccount] = useState<Account | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (isLoading) return (
    <div className="space-y-2">
      {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
    </div>
  );

  const activeAccounts = (accountsList ?? []).filter((a) => a.is_active);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{activeAccounts.length} active {activeAccounts.length === 1 ? "account" : "accounts"}</p>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" /> Add account
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New account</DialogTitle>
              <DialogDescription>Add a financial account to track</DialogDescription>
            </DialogHeader>
            <AccountFormFields ownerId={ownerId} onClose={() => setCreateOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      {activeAccounts.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No accounts yet. Click <strong>Add account</strong> to get started.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {activeAccounts.map((a) => (
            <Card key={a.id}>
              <CardContent className="py-3 px-4">
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{a.institution}</span>
                      <Badge variant="outline" className="text-xs">{a.account_type.replace(/_/g, " ")}</Badge>
                    </div>
                    {a.nickname && <p className="text-xs text-muted-foreground mt-0.5">{a.nickname}</p>}
                    <p className="text-xs text-muted-foreground">Added {formatDate(a.created_at)}</p>
                  </div>

                  <div className="flex gap-1 shrink-0">
                    <Dialog open={editAccount?.id === a.id} onOpenChange={(o) => !o && setEditAccount(null)}>
                      <DialogTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditAccount(a)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Edit account</DialogTitle>
                          <DialogDescription>Update account details</DialogDescription>
                        </DialogHeader>
                        <AccountFormFields ownerId={ownerId} editAccount={a} onClose={() => setEditAccount(null)} />
                      </DialogContent>
                    </Dialog>

                    {confirmId === a.id ? (
                      <div className="flex gap-1 items-center">
                        <Button variant="destructive" size="sm" className="h-7 text-xs"
                          disabled={deactivate.isPending}
                          onClick={() => { deactivate.mutate(a.id); setConfirmId(null); }}>
                          {deactivate.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Remove"}
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setConfirmId(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setConfirmId(a.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Static data tab (4 sub-sections via inner tabs)
// ─────────────────────────────────────────────────────────────────────────────

function SubmitResult({ result }: { result: { records_passed: number; records_quarantined: number } | null }) {
  if (!result) return null;
  return (
    <div className="rounded-md border border-green-200 bg-green-50 dark:bg-green-950 dark:border-green-800 p-3 text-sm">
      <p className="font-medium text-green-800 dark:text-green-200">Submitted successfully</p>
      <p className="text-green-700 dark:text-green-300 text-xs mt-0.5">
        {result.records_passed} record(s) passed · {result.records_quarantined} quarantined
      </p>
    </div>
  );
}

function InsuranceForm({ ownerId, accountOptions }: { ownerId: string; accountOptions: Account[] }) {
  const mutation = useAddInsurance(ownerId);
  const [form, setForm] = useState({
    account_id: "",
    policy_name: "",
    insurer: "",
    policy_type: "LIFE",
    sum_assured_rupees: "",
    annual_premium_rupees: "",
    policy_start_date: "",
    policy_end_date: "",
    nominees: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ records_passed: number; records_quarantined: number } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    if (!form.account_id) return setError("Select an account");
    if (!form.policy_name.trim()) return setError("Policy name is required");
    const sumPaise = parseInt(form.sum_assured_rupees, 10) * 100;
    const premPaise = parseInt(form.annual_premium_rupees, 10) * 100;
    if (isNaN(sumPaise) || sumPaise <= 0) return setError("Sum assured must be positive");
    if (isNaN(premPaise) || premPaise <= 0) return setError("Annual premium must be positive");
    try {
      const res = await mutation.mutateAsync({
        account_id: form.account_id,
        policy_name: form.policy_name.trim(),
        insurer: form.insurer.trim(),
        policy_type: form.policy_type,
        sum_assured_paise: sumPaise,
        annual_premium_paise: premPaise,
        policy_start_date: form.policy_start_date,
        policy_end_date: form.policy_end_date || undefined,
        nominees: form.nominees ? form.nominees.split(",").map((s) => s.trim()).filter(Boolean) : [],
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
      <AccountSelect value={form.account_id} options={accountOptions} onChange={(v) => setForm((f) => ({ ...f, account_id: v }))} />
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Policy name *</Label>
          <Input value={form.policy_name} onChange={(e) => setForm((f) => ({ ...f, policy_name: e.target.value }))} placeholder="HDFC Life Plan" />
        </div>
        <div className="space-y-1.5">
          <Label>Insurer</Label>
          <Input value={form.insurer} onChange={(e) => setForm((f) => ({ ...f, insurer: e.target.value }))} placeholder="HDFC Life" />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Policy type</Label>
        <select value={form.policy_type} onChange={(e) => setForm((f) => ({ ...f, policy_type: e.target.value }))} className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {["LIFE", "HEALTH", "VEHICLE", "TERM", "ULIP", "OTHER"].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Sum assured (₹) *</Label>
          <Input type="number" min="1" value={form.sum_assured_rupees} onChange={(e) => setForm((f) => ({ ...f, sum_assured_rupees: e.target.value }))} placeholder="5000000" />
        </div>
        <div className="space-y-1.5">
          <Label>Annual premium (₹) *</Label>
          <Input type="number" min="1" value={form.annual_premium_rupees} onChange={(e) => setForm((f) => ({ ...f, annual_premium_rupees: e.target.value }))} placeholder="25000" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Start date *</Label>
          <Input type="date" value={form.policy_start_date} onChange={(e) => setForm((f) => ({ ...f, policy_start_date: e.target.value }))} />
        </div>
        <div className="space-y-1.5">
          <Label>End date</Label>
          <Input type="date" value={form.policy_end_date} onChange={(e) => setForm((f) => ({ ...f, policy_end_date: e.target.value }))} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Nominees (comma-separated)</Label>
        <Input value={form.nominees} onChange={(e) => setForm((f) => ({ ...f, nominees: e.target.value }))} placeholder="Spouse, Child" />
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <SubmitResult result={result} />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
        Submit insurance entry
      </Button>
    </form>
  );
}

function RealEstateForm({ ownerId, accountOptions }: { ownerId: string; accountOptions: Account[] }) {
  const mutation = useAddRealEstate(ownerId);
  const [form, setForm] = useState({
    account_id: "", property_name: "", property_type: "RESIDENTIAL",
    purchase_date: "", purchase_rupees: "", current_value_rupees: "",
    address: "", loan_rupees: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ records_passed: number; records_quarantined: number } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setResult(null);
    if (!form.account_id) return setError("Select an account");
    if (!form.property_name.trim()) return setError("Property name is required");
    const purchasePaise = parseInt(form.purchase_rupees, 10) * 100;
    const currentPaise = parseInt(form.current_value_rupees, 10) * 100;
    if (isNaN(purchasePaise) || purchasePaise <= 0) return setError("Purchase price must be positive");
    if (isNaN(currentPaise) || currentPaise <= 0) return setError("Current value must be positive");
    try {
      const res = await mutation.mutateAsync({
        account_id: form.account_id,
        property_name: form.property_name.trim(),
        property_type: form.property_type,
        purchase_date: form.purchase_date,
        purchase_price_paise: purchasePaise,
        current_value_paise: currentPaise,
        address: form.address.trim() || undefined,
        loan_outstanding_paise: form.loan_rupees ? parseInt(form.loan_rupees, 10) * 100 : 0,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
      <AccountSelect value={form.account_id} options={accountOptions} onChange={(v) => setForm((f) => ({ ...f, account_id: v }))} />
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Property name *</Label>
          <Input value={form.property_name} onChange={(e) => setForm((f) => ({ ...f, property_name: e.target.value }))} placeholder="Flat 2B, Bandra" />
        </div>
        <div className="space-y-1.5">
          <Label>Property type</Label>
          <select value={form.property_type} onChange={(e) => setForm((f) => ({ ...f, property_type: e.target.value }))} className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {["RESIDENTIAL", "COMMERCIAL", "PLOT", "OTHER"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Purchase date *</Label>
        <Input type="date" value={form.purchase_date} onChange={(e) => setForm((f) => ({ ...f, purchase_date: e.target.value }))} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label>Purchase price (₹) *</Label>
          <Input type="number" min="1" value={form.purchase_rupees} onChange={(e) => setForm((f) => ({ ...f, purchase_rupees: e.target.value }))} placeholder="5000000" />
        </div>
        <div className="space-y-1.5">
          <Label>Current value (₹) *</Label>
          <Input type="number" min="1" value={form.current_value_rupees} onChange={(e) => setForm((f) => ({ ...f, current_value_rupees: e.target.value }))} placeholder="7000000" />
        </div>
        <div className="space-y-1.5">
          <Label>Loan outstanding (₹)</Label>
          <Input type="number" min="0" value={form.loan_rupees} onChange={(e) => setForm((f) => ({ ...f, loan_rupees: e.target.value }))} placeholder="2000000" />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Address</Label>
        <Input value={form.address} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} placeholder="Flat 2B, Building Name, City" />
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <SubmitResult result={result} />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
        Submit real estate entry
      </Button>
    </form>
  );
}

function GoldForm({ ownerId, accountOptions }: { ownerId: string; accountOptions: Account[] }) {
  const mutation = useAddGold(ownerId);
  const [form, setForm] = useState({
    account_id: "", gold_type: "PHYSICAL", purchase_date: "",
    quantity_grams: "", purchase_rupees: "", current_value_rupees: "", description: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ records_passed: number; records_quarantined: number } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setResult(null);
    if (!form.account_id) return setError("Select an account");
    const grams = parseFloat(form.quantity_grams);
    if (isNaN(grams) || grams <= 0) return setError("Quantity must be positive");
    const purchasePaise = parseInt(form.purchase_rupees, 10) * 100;
    const currentPaise = parseInt(form.current_value_rupees, 10) * 100;
    if (isNaN(purchasePaise) || purchasePaise <= 0) return setError("Purchase price must be positive");
    if (isNaN(currentPaise) || currentPaise <= 0) return setError("Current value must be positive");
    try {
      const res = await mutation.mutateAsync({
        account_id: form.account_id,
        gold_type: form.gold_type,
        purchase_date: form.purchase_date,
        quantity_grams: grams,
        purchase_price_paise: purchasePaise,
        current_value_paise: currentPaise,
        description: form.description.trim() || undefined,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
      <AccountSelect value={form.account_id} options={accountOptions} onChange={(v) => setForm((f) => ({ ...f, account_id: v }))} />
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Gold type</Label>
          <select value={form.gold_type} onChange={(e) => setForm((f) => ({ ...f, gold_type: e.target.value }))} className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {["PHYSICAL", "DIGITAL", "SOVEREIGN_BOND", "ETF", "OTHER"].map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>Purchase date *</Label>
          <Input type="date" value={form.purchase_date} onChange={(e) => setForm((f) => ({ ...f, purchase_date: e.target.value }))} />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label>Quantity (grams) *</Label>
          <Input type="number" min="0.01" step="0.01" value={form.quantity_grams} onChange={(e) => setForm((f) => ({ ...f, quantity_grams: e.target.value }))} placeholder="50" />
        </div>
        <div className="space-y-1.5">
          <Label>Purchase price (₹) *</Label>
          <Input type="number" min="1" value={form.purchase_rupees} onChange={(e) => setForm((f) => ({ ...f, purchase_rupees: e.target.value }))} placeholder="300000" />
        </div>
        <div className="space-y-1.5">
          <Label>Current value (₹) *</Label>
          <Input type="number" min="1" value={form.current_value_rupees} onChange={(e) => setForm((f) => ({ ...f, current_value_rupees: e.target.value }))} placeholder="350000" />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Description</Label>
        <Input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="e.g. Jewellery purchased for wedding" />
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <SubmitResult result={result} />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
        Submit gold entry
      </Button>
    </form>
  );
}

function ITRForm({ ownerId, accountOptions }: { ownerId: string; accountOptions: Account[] }) {
  const mutation = useAddITR(ownerId);
  const [form, setForm] = useState({
    account_id: "", fiscal_year: "2024-25",
    gross_income_rupees: "", taxable_income_rupees: "", tax_paid_rupees: "",
    tds_rupees: "", itr_filed: false,
    deductions_80c_rupees: "", deductions_80d_rupees: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ records_passed: number; records_quarantined: number } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setResult(null);
    if (!form.account_id) return setError("Select an account");
    if (!/^\d{4}-\d{2}$/.test(form.fiscal_year)) return setError("Fiscal year must be YYYY-YY format");
    const grossPaise = parseInt(form.gross_income_rupees, 10) * 100;
    const taxablePaise = parseInt(form.taxable_income_rupees, 10) * 100;
    const taxPaise = parseInt(form.tax_paid_rupees, 10) * 100;
    if (isNaN(grossPaise) || grossPaise < 0) return setError("Gross income must be non-negative");
    try {
      const res = await mutation.mutateAsync({
        account_id: form.account_id,
        fiscal_year: form.fiscal_year,
        gross_income_paise: grossPaise,
        taxable_income_paise: isNaN(taxablePaise) ? grossPaise : taxablePaise,
        tax_paid_paise: isNaN(taxPaise) ? 0 : taxPaise,
        tds_paise: form.tds_rupees ? parseInt(form.tds_rupees, 10) * 100 : 0,
        itr_filed: form.itr_filed,
        deductions_80c_paise: form.deductions_80c_rupees ? parseInt(form.deductions_80c_rupees, 10) * 100 : 0,
        deductions_80d_paise: form.deductions_80d_rupees ? parseInt(form.deductions_80d_rupees, 10) * 100 : 0,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
      <AccountSelect value={form.account_id} options={accountOptions} onChange={(v) => setForm((f) => ({ ...f, account_id: v }))} />
      <div className="space-y-1.5">
        <Label>Fiscal year (YYYY-YY) *</Label>
        <Input value={form.fiscal_year} onChange={(e) => setForm((f) => ({ ...f, fiscal_year: e.target.value }))} placeholder="2024-25" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Gross income (₹) *</Label>
          <Input type="number" min="0" value={form.gross_income_rupees} onChange={(e) => setForm((f) => ({ ...f, gross_income_rupees: e.target.value }))} placeholder="1500000" />
        </div>
        <div className="space-y-1.5">
          <Label>Taxable income (₹)</Label>
          <Input type="number" min="0" value={form.taxable_income_rupees} onChange={(e) => setForm((f) => ({ ...f, taxable_income_rupees: e.target.value }))} placeholder="1275000" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Tax paid (₹)</Label>
          <Input type="number" min="0" value={form.tax_paid_rupees} onChange={(e) => setForm((f) => ({ ...f, tax_paid_rupees: e.target.value }))} placeholder="150000" />
        </div>
        <div className="space-y-1.5">
          <Label>TDS (₹)</Label>
          <Input type="number" min="0" value={form.tds_rupees} onChange={(e) => setForm((f) => ({ ...f, tds_rupees: e.target.value }))} placeholder="120000" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>80C deductions (₹)</Label>
          <Input type="number" min="0" value={form.deductions_80c_rupees} onChange={(e) => setForm((f) => ({ ...f, deductions_80c_rupees: e.target.value }))} placeholder="150000" />
        </div>
        <div className="space-y-1.5">
          <Label>80D deductions (₹)</Label>
          <Input type="number" min="0" value={form.deductions_80d_rupees} onChange={(e) => setForm((f) => ({ ...f, deductions_80d_rupees: e.target.value }))} placeholder="25000" />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="itr_filed"
          checked={form.itr_filed}
          onChange={(e) => setForm((f) => ({ ...f, itr_filed: e.target.checked }))}
          className="h-4 w-4 rounded border-input"
        />
        <Label htmlFor="itr_filed" className="cursor-pointer">ITR filed</Label>
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <SubmitResult result={result} />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
        Submit ITR entry
      </Button>
    </form>
  );
}

// Shared account selector used in all static data forms
function AccountSelect({
  value,
  options,
  onChange,
}: { value: string; options: Account[]; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1.5">
      <Label>Account *</Label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">Select account…</option>
        {options.map((a) => (
          <option key={a.id} value={a.id}>
            {a.institution} — {a.account_type.replace(/_/g, " ")}{a.nickname ? ` (${a.nickname})` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

function StaticDataTab({ ownerId }: { ownerId: string }) {
  const { data: accountsList } = useAccounts(ownerId);
  const [expanded, setExpanded] = useState<string>("insurance");
  const accounts = (accountsList ?? []).filter((a) => a.is_active);

  const sections = [
    { key: "insurance", label: "Insurance", icon: Shield, component: InsuranceForm },
    { key: "real-estate", label: "Real Estate", icon: Building2, component: RealEstateForm },
    { key: "gold", label: "Gold", icon: Coins, component: GoldForm },
    { key: "itr", label: "ITR / Tax", icon: FileText, component: ITRForm },
  ];

  return (
    <div className="space-y-3 max-w-2xl">
      <p className="text-sm text-muted-foreground">
        Submit static asset data to improve recommendation accuracy. Each submission creates an immutable audit record.
      </p>
      {sections.map(({ key, label, icon: Icon, component: Form }) => (
        <Card key={key}>
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-3 text-left"
            onClick={() => setExpanded(expanded === key ? "" : key)}
          >
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium text-sm">{label}</span>
            </div>
            {expanded === key ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )}
          </button>
          {expanded === key && (
            <CardContent className="pt-0 pb-4">
              <Form ownerId={ownerId} accountOptions={accounts} />
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Family tab
// ─────────────────────────────────────────────────────────────────────────────

function FamilyTab({ ownerId }: { ownerId: string }) {
  const { data: members, isLoading } = useFamilyMembers(ownerId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
      </div>
    );
  }

  const list = members ?? [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Family members share financial scope for recommendations. Contact your admin to add or remove members.
      </p>

      {list.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No family members linked to this account.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {list.map((m) => (
            <Card key={String(m.owner_id)}>
              <CardContent className="py-3 px-4">
                <div className="flex items-center gap-3">
                  <Users className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{m.name}</span>
                      <Badge variant="secondary" className="text-xs">{m.role}</Badge>
                      {m.is_admin && <Badge variant="outline" className="text-xs">Admin</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground">Added {formatDate(m.created_at)}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { owner } = useAuth();
  const ownerId = owner?.owner_id ?? "";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your profile, goals, accounts, and financial data</p>
      </div>

      <Tabs defaultValue="profile">
        <TabsList className="mb-4">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="goals">Goals</TabsTrigger>
          <TabsTrigger value="accounts">Accounts</TabsTrigger>
          <TabsTrigger value="static-data">Static Data</TabsTrigger>
          <TabsTrigger value="family">Family</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          {ownerId ? <ProfileTab ownerId={ownerId} /> : <Skeleton className="h-40 w-full max-w-lg" />}
        </TabsContent>

        <TabsContent value="goals">
          {ownerId ? <GoalsTab ownerId={ownerId} /> : <Skeleton className="h-40 w-full" />}
        </TabsContent>

        <TabsContent value="accounts">
          {ownerId ? <AccountsTab ownerId={ownerId} /> : <Skeleton className="h-40 w-full" />}
        </TabsContent>

        <TabsContent value="static-data">
          {ownerId ? <StaticDataTab ownerId={ownerId} /> : <Skeleton className="h-40 w-full" />}
        </TabsContent>

        <TabsContent value="family">
          {ownerId ? <FamilyTab ownerId={ownerId} /> : <Skeleton className="h-40 w-full" />}
        </TabsContent>
      </Tabs>
    </div>
  );
}
