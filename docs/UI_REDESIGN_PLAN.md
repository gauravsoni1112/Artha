# Artha UI Redesign & Investments Plan

Consolidated plan for upgrading the Artha dashboard from a basic KPI-tile
layout into a productive financial cockpit, and for unlocking the Zerodha +
MF CAS data that is currently under-utilized.

Status: **planning / pre-implementation**
Owner: Gaurav
Last updated: 2026-04-19

---

## 1. Why this redesign

The current dashboard (`frontend/app/(app)/page.tsx`) has five equal-size
widgets in a 2-col grid plus a sticky 380px `Ask Artha` panel. Problems:

- **"Net Worth" widget is mislabeled** — it shows the sum of goal current
  amounts, not actual assets minus liabilities.
- **Empty states are dead ends** — every widget ends with "create one in
  Settings" as text, no CTAs.
- **No drill-down** — tiles are not clickable.
- **Orphan 5th tile** breaks the 2-col grid.
- **Cashflow sparkline is 48px** — decorative, not useful.
- **Sticky chat panel eats ~25% of viewport permanently.**
- **No deltas, comparisons, or proactive insights** — every number is absolute
  and passive.
- **No surfacing of ingestion status or recent activity.**
- **Zerodha + MF CAS data is barely used** despite being a key differentiator.

---

## 2. Target experience

A **three-layer cockpit**:

1. **Headline strip** — live one-liner ("You're ₹12k under budget · 3 goals on
   track · tax due Jul 31") + global time-range control.
2. **Insights strip** — proactive, dismissable nudges (tax-loss harvest, LTCG
   window, anomalies, concentration risk, cash drag).
3. **Tile grid** — variable-sized tiles with deltas, drill-down on click, and
   a hero (Cashflow OR Portfolio depending on user context).

Chat moves from a sticky column to a **Cmd-K modal + slide-in drawer**,
reclaiming horizontal space.

Wireframes for all of this live in Section 7.

---

## 3. Phased roadmap

### Phase A — Correctness & clickability  (1–2 days)

Goal: make the current layout trustworthy before redesigning it.

- [ ] Fix `NetWorthWidget` to compute true net worth
      (`assets - liabilities`, where assets = cash + equity LTP×qty + MF NAV×units).
- [ ] Make every widget clickable (wrap in `Link`, add subtle `→` affordance
      on hover). Target routes:
      - NetWorth → `/investments`
      - Cashflow → `/transactions?range=thisMonth`
      - Goals → `/goals`
      - Tax → `/tax`
      - Risk → `/risk`
- [ ] Replace empty-state text with primary CTA buttons that deep-link to the
      relevant Settings / Goals / Accounts screen.
- [ ] Add **vs-last-period deltas** on NetWorth, Cashflow, Goals pace, Tax
      liability (▲/▼ + absolute + %).

### Phase B — Insights & quick actions  (2–3 days)

Goal: transform dashboard from "report" to "cockpit".

- [ ] Insights strip component: dismissable cards, fed by
      `risk_agent` + `tax` engine + anomaly stage outputs.
      Initial sources: large-txn flags, STCG/LTCG windows, SIP bounces,
      concentration risk, cash drag.
- [ ] Live headline ("Good morning, Gaurav · FY 25-26 · <insight>") replacing
      the generic subheader.
- [ ] Quick actions row or TopBar dropdown:
      `Upload statement` · `Add manual txn` · `Ask Artha…` (templated prompts).
- [ ] Recent activity / ingestion status block (last sync, txns ingested,
      failures). Uses `ingestion_runs` table.

### Phase C — Layout & chat redesign  (3–5 days)

Goal: deliver the cockpit feel.

- [ ] 12-col responsive grid with variable tile spans.
- [ ] Promote Cashflow to **hero tile** (2-col span, real 120px chart,
      category breakdown tooltip, MoM delta).
- [ ] Add **6th tile: Accounts / Liquidity** to balance the grid.
- [ ] Global time-range control (`M | Q | FY | Custom`) propagated to
      time-scoped widgets.
- [ ] Replace sticky Ask Artha panel with:
      - Floating pill bottom-right when idle.
      - `⌘K` opens centered modal with suggested + recent prompts.
      - Active conversation = right-side slide-in drawer (480px).
- [ ] Mobile layout (<768px): stacked tiles, insights carousel, fixed bottom
      Ask Artha bar.

### Phase D — Investments unlock  (5–8 days)

Goal: turn Zerodha + MF CAS data into the product's strongest page.

See Section 5 for full spec.

---

## 4. Investments — why this is the biggest lever

Zerodha holdings and MF CAS are already ingested, but the dashboard only
surfaces them indirectly. Users currently have no reason to open
`/investments`. Fixing this:

- Makes the "Net Worth" number real.
- Unlocks the highest-ROI proactive insights (tax-loss harvest, LTCG
  windows, rebalance nudges).
- Is where the multi-agent system (`allocation_agent`, `risk_agent`,
  planner/critic) becomes visible to users.

### 4.1 Dashboard-level additions

- Portfolio hero tile (value + today's P&L + 30d sparkline + XIRR vs Nifty +
  allocation mini-donut + top movers + drift indicator).
- Today's unrealized P&L in insights strip.

### 4.2 New insight types

1. **Tax-loss harvesting** — "₹32k unrealized loss in XYZ offsets ₹58k STCG."
2. **LTCG window unlock** — "HDFCBANK crosses 1yr holding on May 12."
3. **Concentration risk** — "Top 3 holdings = 58% of equity."
4. **Cash drag** — "₹2.4L idle >30d in savings. Liquid fund ~7%."
5. **SIP health** — missed/bounced SIPs, underperforming schemes.
6. **Sector over-exposure** — aggregate direct eq + MF holdings.
7. **Dividend / corp-action calendar** — record dates, bonus, splits.

### 4.3 Chat-integrated flows

- "Should I rebalance?" → orchestrator runs `allocation_agent` + `risk_agent`
  and returns specific buy/sell deltas.
- "Tax-efficient exit" → given `I need ₹2L in July`, planner picks which
  holdings to sell to minimize tax.
- "What if I stop SIP X?" → scenario sim using projected XIRR.

---

## 5. `/investments` page spec

### 5.1 Overview tab

- KPI row: `Value · Unrealized P&L · Realized FY · XIRR`
- Insights strip (scoped to investments).
- Performance chart vs Nifty 50 benchmark (1M / 3M / 6M / 1Y / 3Y / ALL).
- Allocation donut (current vs target, with drift warning + Rebalance CTA).
- Sector exposure bar chart (aggregated across direct equity + MF).

### 5.2 Equity tab (holdings table)

Columns: `Symbol · Qty · Avg · LTP · Value · Day% · Unrealized P&L · Tax status`.

Tax status = `✓ LT eligible` / `⏳ LT in Nd` / `✗ ST` / `✗ ST (loss)`.

Row click → **holding drawer**:

- Tax-lots (FIFO), with LT/ST status per lot.
- Transaction history for this symbol.
- `Sell preview` CTA → modal (see 5.4).
- `Ask Artha about this holding` CTA (scoped chat).

### 5.3 Mutual Funds tab

- Holdings table: scheme, units, NAV, value, XIRR, category.
- SIP block: active/bounced/underperforming SIPs with next debit date.

### 5.4 Sell-preview modal

Input qty + expected price → shows:
- FIFO tax-lot plan (editable).
- Estimated LTCG/STCG breakdown.
- Net proceeds after tax.
- **Smarter alternative** ("Wait 23 days: both lots become LT → save ₹68").
- `Copy order to Kite` (since we don't place orders) + `Ask Artha for alt`.

---

## 6. Data / backend prerequisites

Most of these are needed before investment features can ship.

- [ ] **Live LTP feed** — Zerodha Kite ticker (websocket) or delayed quotes.
      Without this, portfolio value is stale. Decide: tick or poll every N min.
- [ ] **AMFI daily NAV ingestion** — free, updated ~11pm IST. Cron via
      APScheduler.
- [ ] **Benchmark index series** — Nifty 50 close prices for XIRR-vs-benchmark
      chart.
- [ ] **Target allocation** — new per-owner setting (`equity/debt/mf/cash/gold`
      target %).
- [ ] **Tax-lot engine** — FIFO lot tracking per holding for accurate LTCG/STCG
      (likely exists partially; verify and extend).
- [ ] **XIRR service** — compute across all cashflows (buy, sell, dividend,
      SIP) per scope (overall / equity / MF / per-holding).
- [ ] **Sector metadata** — map symbol → sector; for MFs, use scheme portfolio
      disclosure.

---

## 7. Wireframes

Wireframes (ASCII) for the following views were produced in the design
conversation and should be referenced before implementation:

- Current dashboard (baseline).
- Proposed desktop dashboard (1440px+) with insights strip, hero Cashflow,
  6-tile grid, recent activity + quick ask row.
- Cmd-K chat pattern (idle pill, modal, slide-in drawer).
- Mobile dashboard (<768px).
- Dashboard Portfolio hero tile.
- `/investments` Overview tab.
- `/investments` Equity tab with row drawer.
- `/investments` MF tab.
- Sell-preview modal.

These are preserved in the design-review chat. Before each Phase task, copy
the relevant wireframe into the PR description as the design spec.

---

## 8. Interaction & design principles

These apply to every widget, table, and drawer built under this plan:

1. **Every number has a delta or context.** Absolute + relative, never naked.
2. **Every tile is a doorway.** Clickable, with a subtle `→` on hover.
3. **Empty states are CTAs, not epitaphs.** Always offer a next action.
4. **Proactive > passive.** Insights strip is the first thing below the
   header — it earns its spot by replacing reactive hunting.
5. **Tax status is first-class.** Surfaced wherever a sellable asset is
   listed.
6. **Agent output should be visible, not hidden in chat.** Insights come
   from agents; the chat is for conversation, not reporting.
7. **Chat is always one keystroke away (`⌘K`), never in the way.**
8. **Scoped chat beats global chat.** Every drawer has an "Ask Artha about
   this" button that seeds the composer with context.

---

## 9. Open questions

- [ ] Live quotes: Kite websocket vs delayed REST — licensing + rate limits?
- [ ] Should target allocation be user-set or suggested by `allocation_agent`
      based on risk profile?
- [ ] Do we render XIRR at holding level (expensive, many cashflows) or just
      at scheme / portfolio level?
- [ ] Sell-preview: copy-to-Kite vs deep-link to Kite's order form with
      pre-filled params — which is feasible?
- [ ] Insights strip: max 3 cards or scrollable? Ranking logic owner?

---

## 10. Suggested build order

1. **Phase A** (correctness) — unblocks everything; fixes the single most
   visible bug (wrong net worth).
2. **Data prerequisites**: NAV ingestion + LTP feed + tax-lot verification.
   Can run in parallel with Phase A.
3. **Phase D slice 1**: Portfolio hero tile + Overview tab KPI row +
   allocation donut. Delivers visible value fast.
4. **Phase B** (insights + quick actions) once at least 2–3 insight types
   have data.
5. **Phase D slice 2**: Equity tab + holdings drawer + sell preview.
6. **Phase C** (layout + Cmd-K chat) as the final polish pass — doing it
   last avoids re-theming work.

---

## Appendix: files likely to change

- `frontend/app/(app)/page.tsx` — dashboard layout.
- `frontend/components/widgets/*.tsx` — all widgets (net worth, cashflow,
  goals, tax, risk + new portfolio + accounts + insights strip).
- `frontend/components/layout/{Sidebar,TopBar}.tsx` — quick actions, Cmd-K
  trigger, time-range control.
- `frontend/components/chat/*.tsx` — Cmd-K modal + drawer.
- `frontend/app/(app)/investments/*` — full rebuild.
- `api/` — new endpoints for portfolio valuation, tax-lots, XIRR, insights.
- `services/` — NAV ingestion, LTP poller, XIRR service, tax-lot engine.
- `libs/schemas/db_models.py` — `target_allocation`, `ltp_cache`, NAV tables.
