"use client";

import React from "react";
import { Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useGoals } from "@/lib/queries";
import { progressColor } from "@/lib/format";

export function GoalsWidget() {
  const { owner } = useAuth();
  const { data: goalsList, isLoading } = useGoals(owner?.owner_id);

  const activeGoals = goalsList?.filter((g) => g.is_active) ?? [];
  const topGoals = activeGoals.slice(0, 3);
  const avgProgress =
    activeGoals.length > 0
      ? activeGoals.reduce((s, g) => s + g.progress_pct, 0) / activeGoals.length
      : 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">Goals</CardTitle>
        <Target className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-16 mb-3" />
            <Skeleton className="h-4 w-full mb-2" />
            <Skeleton className="h-4 w-full mb-2" />
            <Skeleton className="h-4 w-3/4" />
          </>
        ) : activeGoals.length === 0 ? (
          <>
            <p className="text-2xl font-bold">0</p>
            <p className="text-xs text-muted-foreground mt-1">
              No active goals — create one in Settings
            </p>
          </>
        ) : (
          <>
            <div className="flex items-baseline gap-2 mb-3">
              <p className="text-2xl font-bold">{activeGoals.length}</p>
              <p className="text-sm text-muted-foreground">
                active · {Math.round(avgProgress)}% avg
              </p>
            </div>
            <div className="space-y-2">
              {topGoals.map((goal) => (
                <div key={goal.id}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="truncate max-w-[130px]">{goal.goal_name}</span>
                    <span className="text-muted-foreground shrink-0 ml-2">
                      {Math.round(goal.progress_pct)}%
                    </span>
                  </div>
                  <Progress
                    value={goal.progress_pct}
                    indicatorClassName={progressColor(goal.progress_pct)}
                  />
                </div>
              ))}
              {activeGoals.length > 3 && (
                <p className="text-xs text-muted-foreground">
                  +{activeGoals.length - 3} more
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
