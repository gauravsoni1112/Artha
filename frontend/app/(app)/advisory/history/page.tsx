"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  History,
  Loader2,
  Lock,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import {
  useAdminAuditLog,
  useIngestionRuns,
  useMyRecommendations,
  useQuarantine,
  useRecommendationEvent,
  useResolveQuarantine,
} from "@/lib/queries";
import { formatConfidence, formatDate, confidenceColor } from "@/lib/format";
import type { AuditRecommendation, RecommendationSummary } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function ingestionStatusBadge(status: string) {
  if (status === "COMPLETED")
    return (
      <Badge className="bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300 border-0">
        <CheckCircle2 className="h-3 w-3 mr-1" />
        Completed
      </Badge>
    );
  if (status === "FAILED")
    return (
      <Badge className="bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300 border-0">
        <XCircle className="h-3 w-3 mr-1" />
        Failed
      </Badge>
    );
  return (
    <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300 border-0">
      <Clock className="h-3 w-3 mr-1" />
      {status}
    </Badge>
  );
}

function recStateBadge(state: string) {
  const map: Record<string, string> = {
    GENERATED: "bg-secondary text-secondary-foreground border-0",
    SURFACED: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300 border-0",
    ACCEPTED: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300 border-0",
    REJECTED: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300 border-0",
    MODIFIED: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300 border-0",
  };
  return (
    <Badge className={map[state] ?? "border-0 bg-secondary text-secondary-foreground"}>
      {state}
    </Badge>
  );
}

// ── Ingestion tab ─────────────────────────────────────────────────────────────

function IngestionTab() {
  const { data: runs, isLoading, refetch, isFetching } = useIngestionRuns(50);

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : !runs || runs.length === 0 ? (
        <div className="py-10 text-center text-muted-foreground">
          <History className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No ingestion runs yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left font-medium px-4 py-3">Source</th>
                <th className="text-left font-medium px-4 py-3">Trigger</th>
                <th className="text-left font-medium px-4 py-3">Status</th>
                <th className="text-right font-medium px-4 py-3">Fetched</th>
                <th className="text-right font-medium px-4 py-3">Passed</th>
                <th className="text-right font-medium px-4 py-3">Quarantined</th>
                <th className="text-left font-medium px-4 py-3 hidden md:table-cell">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b last:border-0 hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3 font-medium">{run.source}</td>
                  <td className="px-4 py-3 text-muted-foreground">{run.trigger_type}</td>
                  <td className="px-4 py-3">{ingestionStatusBadge(run.status)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{run.records_fetched}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-green-600 dark:text-green-400">
                    {run.records_passed}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-red-600 dark:text-red-400">
                    {run.records_quarantined}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap hidden md:table-cell">
                    {formatDate(run.started_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Quarantine tab ────────────────────────────────────────────────────────────

function QuarantineTab() {
  const { owner } = useAuth();
  const [filterStatus, setFilterStatus] = useState("PENDING_REVIEW");
  const { data: records, isLoading, refetch, isFetching } = useQuarantine(filterStatus);
  const resolveMutation = useResolveQuarantine();

  if (!owner?.is_admin) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        <Lock className="h-8 w-8 mx-auto mb-2 opacity-40" />
        <p className="text-sm">Quarantine review requires admin access.</p>
      </div>
    );
  }

  async function handleResolve(id: string, status: string) {
    await resolveMutation.mutateAsync({ id, status });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="PENDING_REVIEW">Pending review</option>
          <option value="RESOLVED">Resolved</option>
          <option value="REJECTED">Rejected</option>
        </select>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : !records || records.length === 0 ? (
        <div className="py-10 text-center text-muted-foreground">
          <CheckCircle2 className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">
            {filterStatus === "PENDING_REVIEW"
              ? "No records pending review."
              : `No ${filterStatus.toLowerCase()} records.`}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {records.map((rec) => (
            <Card key={rec.id}>
              <CardContent className="pt-3 pb-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline" className="text-xs">
                        {rec.failure_stage}
                      </Badge>
                      <Badge
                        className={`text-xs border-0 ${
                          rec.quarantine_status === "PENDING_REVIEW"
                            ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300"
                            : rec.quarantine_status === "RESOLVED"
                            ? "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300"
                            : "bg-secondary text-secondary-foreground"
                        }`}
                      >
                        {rec.quarantine_status}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      {rec.raw_date_text && <span>Date: {rec.raw_date_text}</span>}
                      {rec.raw_amount_text && <span>Amount: {rec.raw_amount_text}</span>}
                      <span>{formatDate(rec.created_at)}</span>
                    </div>
                    {Array.isArray(rec.failure_reasons) && rec.failure_reasons.length > 0 && (
                      <div className="space-y-0.5 mt-1">
                        {(rec.failure_reasons as string[]).slice(0, 3).map((r, i) => (
                          <div key={i} className="flex items-start gap-1 text-xs text-red-600 dark:text-red-400">
                            <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                            <span>{String(r)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {filterStatus === "PENDING_REVIEW" && (
                    <div className="flex gap-1.5 shrink-0">
                      <Button
                        size="sm"
                        className="h-7 text-xs"
                        disabled={resolveMutation.isPending}
                        onClick={() => handleResolve(rec.id, "RESOLVED")}
                      >
                        {resolveMutation.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          "Resolve"
                        )}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        disabled={resolveMutation.isPending}
                        onClick={() => handleResolve(rec.id, "REJECTED")}
                      >
                        Reject
                      </Button>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Recommendation row with inline accept/reject ──────────────────────────────

function RecommendationRow({
  rec,
}: {
  rec: RecommendationSummary | AuditRecommendation;
}) {
  const { owner } = useAuth();
  const [state, setState] = useState(rec.current_state);
  const eventMutation = useRecommendationEvent(rec.id);
  const isDone = state === "ACCEPTED" || state === "REJECTED" || state === "MODIFIED";

  async function handleEvent(eventType: "ACCEPTED" | "REJECTED") {
    if (!owner) return;
    try {
      const result = await eventMutation.mutateAsync({
        event_type: eventType,
        actor_user_id: owner.owner_id,
        payload: {},
      });
      setState(result.current_state);
    } catch {
      /* surfaced via isError */
    }
  }

  const confidence = rec.composite_confidence;
  const query = rec.query;

  return (
    <tr className="border-b last:border-0 hover:bg-muted/20 transition-colors">
      <td className="px-4 py-3 max-w-xs">
        <p className="truncate text-sm" title={query}>
          {query}
        </p>
      </td>
      <td className="px-4 py-3">
        <span className={`text-sm font-semibold tabular-nums ${confidenceColor(confidence)}`}>
          {formatConfidence(confidence)}
        </span>
      </td>
      <td className="px-4 py-3">{recStateBadge(state)}</td>
      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap hidden md:table-cell text-xs">
        {formatDate(rec.created_at)}
      </td>
      <td className="px-4 py-3">
        {!isDone ? (
          <div className="flex gap-1.5">
            <Button
              size="sm"
              className="h-7 text-xs"
              disabled={eventMutation.isPending}
              onClick={() => handleEvent("ACCEPTED")}
            >
              {eventMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                "Accept"
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={eventMutation.isPending}
              onClick={() => handleEvent("REJECTED")}
            >
              Reject
            </Button>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">{state}</span>
        )}
      </td>
    </tr>
  );
}

// ── Recommendations tab ───────────────────────────────────────────────────────

function RecommendationsTab() {
  const { owner } = useAuth();
  const isAdmin = owner?.is_admin ?? false;

  // Admin sees all owners; regular user sees their own
  const adminQuery = useAdminAuditLog({ limit: 50 });
  const myQuery = useMyRecommendations({ limit: 50 });

  const { data, isLoading, refetch, isFetching } = isAdmin ? adminQuery : myQuery;

  const recs = (data ?? []) as Array<RecommendationSummary | AuditRecommendation>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        {isAdmin && (
          <Badge variant="secondary" className="text-xs">Admin view — all owners</Badge>
        )}
        <div className="ml-auto">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : recs.length === 0 ? (
        <div className="py-10 text-center text-muted-foreground">
          <History className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No recommendations yet.</p>
          <p className="text-xs mt-1">Use Ask Artha on the Dashboard to generate one.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left font-medium px-4 py-3">Query</th>
                <th className="text-left font-medium px-4 py-3">Confidence</th>
                <th className="text-left font-medium px-4 py-3">State</th>
                <th className="text-left font-medium px-4 py-3 hidden md:table-cell">Date</th>
                <th className="text-left font-medium px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {recs.map((rec) => (
                <RecommendationRow key={rec.id} rec={rec} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdvisoryHistoryPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Advisory &amp; History</h1>
        <p className="text-sm text-muted-foreground">
          Ingestion runs, quarantine records, and recommendation history
        </p>
      </div>

      <Tabs defaultValue="ingestion">
        <TabsList>
          <TabsTrigger value="ingestion">Ingestion</TabsTrigger>
          <TabsTrigger value="quarantine">Quarantine</TabsTrigger>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
        </TabsList>

        <TabsContent value="ingestion" className="mt-4">
          <IngestionTab />
        </TabsContent>

        <TabsContent value="quarantine" className="mt-4">
          <QuarantineTab />
        </TabsContent>

        <TabsContent value="recommendations" className="mt-4">
          <RecommendationsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
