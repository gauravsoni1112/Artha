"use client";

import React, { useMemo, useState } from "react";
import { Download, Search, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useTransactions } from "@/lib/queries";
import { formatDate, formatINR } from "@/lib/format";

const PAGE_SIZE = 50;
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function TransactionsPage() {
  const { owner } = useAuth();
  const [search, setSearch] = useState("");
  const [txType, setTxType] = useState<"" | "CREDIT" | "DEBIT">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState(false);

  const filters = useMemo(
    () => ({
      search: search || undefined,
      transaction_type: (txType || undefined) as "CREDIT" | "DEBIT" | undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [search, txType, dateFrom, dateTo, page]
  );

  const { data: txns, isLoading, isFetching } = useTransactions(owner?.owner_id, filters);

  async function handleCsvExport() {
    if (!owner) return;
    setExporting(true);
    try {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("artha_token") : null;
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (txType) params.set("transaction_type", txType);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const qs = params.toString() ? `?${params}` : "";
      const res = await fetch(
        `${BASE_URL}/owners/${owner.owner_id}/transactions.csv${qs}`,
        { headers: { "X-Artha-Token": token ?? "" } }
      );
      if (!res.ok) throw new Error(res.statusText);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `transactions_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function resetFilters() {
    setSearch("");
    setTxType("");
    setDateFrom("");
    setDateTo("");
    setPage(0);
  }

  const hasFilters = !!(search || txType || dateFrom || dateTo);
  const canGoNext = txns?.length === PAGE_SIZE;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Transactions</h1>
          <p className="text-sm text-muted-foreground">Your full transaction ledger</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleCsvExport}
          disabled={exporting || !owner}
          className="flex items-center gap-1.5"
        >
          <Download className="h-4 w-4" />
          {exporting ? "Exporting…" : "Export CSV"}
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <div className="flex flex-wrap gap-2">
            {/* Search */}
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search description…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                className="pl-8"
              />
            </div>

            {/* Type filter */}
            <select
              value={txType}
              onChange={(e) => {
                setTxType(e.target.value as "" | "CREDIT" | "DEBIT");
                setPage(0);
              }}
              className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">All types</option>
              <option value="CREDIT">Credit</option>
              <option value="DEBIT">Debit</option>
            </select>

            {/* Date range */}
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(0);
              }}
              className="w-36"
              aria-label="From date"
            />
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(0);
              }}
              className="w-36"
              aria-label="To date"
            />

            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={resetFilters} className="gap-1">
                <X className="h-3.5 w-3.5" />
                Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className="text-left font-medium px-4 py-3 whitespace-nowrap">Date</th>
                  <th className="text-left font-medium px-4 py-3">Description</th>
                  <th className="text-left font-medium px-4 py-3 hidden md:table-cell">
                    Category
                  </th>
                  <th className="text-right font-medium px-4 py-3 whitespace-nowrap">Amount</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} className="border-b">
                      <td className="px-4 py-3">
                        <Skeleton className="h-4 w-20" />
                      </td>
                      <td className="px-4 py-3">
                        <Skeleton className="h-4 w-48" />
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <Skeleton className="h-4 w-24" />
                      </td>
                      <td className="px-4 py-3">
                        <Skeleton className="h-4 w-20 ml-auto" />
                      </td>
                    </tr>
                  ))
                ) : txns && txns.length > 0 ? (
                  txns.map((txn) => (
                    <tr
                      key={txn.id}
                      className="border-b last:border-0 hover:bg-muted/20 transition-colors"
                    >
                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {formatDate(txn.transaction_date)}
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        <p className="truncate">{txn.description}</p>
                        {txn.merchant && (
                          <p className="text-xs text-muted-foreground truncate">
                            {txn.merchant}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        {txn.category && (
                          <Badge variant="secondary" className="text-xs">
                            {txn.category}
                          </Badge>
                        )}
                      </td>
                      <td
                        className={`px-4 py-3 text-right font-medium tabular-nums whitespace-nowrap ${
                          txn.transaction_type === "CREDIT"
                            ? "text-green-600 dark:text-green-400"
                            : "text-foreground"
                        }`}
                      >
                        {txn.transaction_type === "CREDIT" ? "+" : "−"}
                        {formatINR(txn.amount_paise)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-muted-foreground text-sm"
                    >
                      {hasFilters
                        ? "No transactions match your filters"
                        : "No transactions yet — ingest some data to get started"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {!isLoading && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <p className="text-xs text-muted-foreground">
                {txns && txns.length > 0
                  ? `Showing ${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + txns.length}`
                  : "No results"}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0 || isFetching}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canGoNext || isFetching}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
