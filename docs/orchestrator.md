# Artha Orchestrator Reference

This document explains the orchestrator implementation for a developer who is new
to the codebase. It also includes an interviewer-style story at the end, with the
reasoning behind the main design decisions.

## 1. What The Orchestrator Does

The orchestrator is the coordination layer for financial recommendations.

It does not directly calculate spending, portfolio value, tax, risk, or goals.
Those calculations are handled by specialist domain agents. The orchestrator's
job is to decide:

- which data scope is allowed for the request
- which agents should be called
- in what order those agents should run
- how to handle agent failures
- how to combine confidence scores
- how to check consistency across agent outputs
- how to synthesize one final answer
- how to persist the full audit trail

The main API entry point is:

```text
api/routers/orchestrator.py
```

The primary endpoint is:

```text
POST /orchestrator/recommendation
```

High-level flow:

```text
request
  -> authenticate owner
  -> load user profile
  -> resolve data scope
  -> create immutable profile snapshot
  -> decompose query into an agent plan
  -> dispatch plan to domain agents
  -> compose baseline confidence
  -> run critic checks
  -> synthesize final answer
  -> write recommendation and events to database
  -> return response
```

## 2. Main Components

The orchestrator code lives under:

```text
services/orchestrator/
```

Important files:

```text
scope.py        -> resolves which owner_ids the request may access
registry.py     -> keeps an in-memory snapshot of agent registry rows
decompose.py    -> chooses which agents should answer the query
plan.py         -> defines the serializable Plan and AgentCall DAG
dispatch.py     -> calls domain agents over HTTP
breaker.py      -> circuit breaker state per agent
cache.py        -> Redis-backed response cache for failed agent calls
critic.py       -> deterministic consistency checks and confidence penalties
synthesizer.py  -> merges agent answers into one final response
audit.py        -> writes profile snapshots, recommendations, and events
metrics.py      -> OpenTelemetry metrics
```

## 3. End-To-End Request Lifecycle

### Step 1: Owner Authorization

The endpoint first checks that the authenticated owner matches the `owner_id` in
the request body.

If they do not match, the request is rejected with `403`.

This prevents one authenticated owner from requesting recommendations for
another owner.

### Step 2: Load User Profile

The orchestrator loads the user's profile from Postgres using SQLAlchemy.

The ORM row is converted into the Pydantic `UserProfile` model used by agents.

The profile includes fields such as:

```text
owner_id
name
risk_appetite
age
is_family_scope
total_monthly_income_paise
income_sources
emis
```

If no profile exists, the endpoint returns `404`.

### Step 3: Resolve Scope

Implemented in:

```text
services/orchestrator/scope.py
```

The orchestrator decides which `owner_id`s the agents are allowed to query.

There are two modes:

```text
individual scope -> only PRIMARY owner data
family scope     -> PRIMARY + SPOUSE + DEPENDENT data
```

Family scope is selected when either:

```text
profile.is_family_scope is true
```

or the query text clearly asks for a family/household view, using words like:

```text
family
household
spouse
wife
husband
joint
combined
together
dependents
```

The result is a `ScopeContext`:

```python
ScopeContext(
    allowed_owner_ids=[...],
    is_family_scope=True,
)
```

This is a key security decision. Agents do not decide access scope themselves.
They receive only the pre-filtered `allowed_owner_ids` from the orchestrator.

### Step 4: Create Profile Snapshot

Implemented in:

```text
services/orchestrator/audit.py
```

Before calling agents, the orchestrator creates a `UserProfileSnapshot`.

This freezes the user profile at request time.

Reason:

If the user's profile changes later, the old recommendation should still be
explainable and replayable based on the profile that existed when it was
generated.

### Step 5: Load Available Agents

Implemented in:

```text
services/orchestrator/registry.py
```

The orchestrator uses `AgentRegistryCache` to know which agents are available.

Important distinction:

```text
Agent registry cache is NOT Redis.
Agent registry cache is an in-memory Python dictionary.
Its source of truth is the Postgres agent_registry table.
```

On refresh, it queries Postgres:

```text
agent_registry table
```

and loads all agents whose status is not:

```text
DOWN
```

Then, for decomposition/planning, `list_available()` returns only agents whose
status is:

```text
HEALTHY
```

The registry cache is refreshed periodically by APScheduler, usually every
60 seconds.

So when we say "registry cache", we mean:

```text
Postgres -> periodic refresh -> in-memory registry snapshot
```

not Redis.

Each registry entry can include:

```text
agent_id
endpoint
capabilities
status
timeout_ms
cache_ttl_hours
```

### Step 6: Decompose Query Into Plan

Implemented in:

```text
services/orchestrator/decompose.py
services/orchestrator/plan.py
```

The decomposer converts the natural-language query into a `Plan`.

A `Plan` is a serializable DAG made of `AgentCall` objects.

Example `AgentCall`:

```python
AgentCall(
    agent_id="cashflow_agent",
    allowed_owner_ids=[...],
    context={},
    depends_on=[],
)
```

Supported domain agents:

```text
cashflow_agent
investment_agent
tax_agent
goal_agent
risk_agent
```

The decomposer first uses regex rules.

Examples:

```text
spending, budget, expense, income -> cashflow_agent
portfolio, SIP, stock, mutual fund -> investment_agent
tax, ITR, 80C, deduction -> tax_agent
goal, retirement, corpus -> goal_agent
risk, insurance, emergency fund, debt -> risk_agent
```

If rules match, the system uses the rule-based plan.

If zero rules match, it falls back to an LLM planner using `LLMRole.PLANNER`.

Reason:

Most queries can be routed cheaply and predictably with rules. Vague questions
like "Am I doing okay financially?" may need LLM routing.

If the LLM fails, returns invalid output, invents unknown agent IDs, or creates
a dependency cycle, the decomposer safely falls back to available agents.

### Step 7: Add Agent Dependencies

Some agents need other agents to run first.

Current dependency table:

```python
_AGENT_DEPENDENCIES = {
    "goal_agent": ["cashflow_agent", "investment_agent"],
    "risk_agent": ["cashflow_agent"],
}
```

Meaning:

```text
goal_agent needs cashflow and investment context
risk_agent needs cashflow context
```

Example:

```text
Query:
Can I increase my SIP to reach my retirement goal?

Matched:
goal_agent

Automatically added:
cashflow_agent
investment_agent

Plan:
cashflow_agent      no dependencies
investment_agent    no dependencies
goal_agent          depends_on cashflow_agent and investment_agent
```

The plan is saved later in:

```text
recommendations.plan_json
```

This makes the orchestration decision auditable.

### Step 8: Dispatch Plan To Agents

Implemented in:

```text
services/orchestrator/dispatch.py
```

The dispatcher executes the plan.

Steps with no dependencies can run concurrently through `asyncio.gather`.

Steps with dependencies run after the dependency steps complete.

For each agent call, dispatch does:

```text
1. Check circuit breaker.
2. Look up agent endpoint and timeout in registry cache.
3. Build AgentRequest.
4. POST to {agent_endpoint}/run.
5. If live call succeeds, return PRIMARY result and cache it.
6. If live call fails, try Redis response cache.
7. If cache hit is fresh, return SECONDARY result.
8. If cache hit is stale, return TERTIARY result.
9. If no cache exists, return FAILURE.
```

The request sent to each agent includes:

```python
AgentRequest(
    query=query,
    context={
        "allowed_owner_ids": [...]
    },
    user_profile=user_profile,
    trace_id=trace_id,
)
```

The service-to-service HTTP call includes:

```text
X-Artha-Agent-Secret
```

### Step 9: Circuit Breaker

Implemented in:

```text
services/orchestrator/breaker.py
```

The circuit breaker protects the orchestrator from repeatedly calling an agent
that is failing.

States:

```text
CLOSED     -> normal operation
OPEN       -> fail fast; do not call the agent
HALF_OPEN  -> allow one probe after cooldown
```

Default config:

```text
failure_threshold = 5
open_duration_seconds = 30
half_open_probe_count = 1
```

Behavior:

```text
CLOSED:
  calls are allowed
  failures increment failure_count

after 5 consecutive failures:
  breaker moves to OPEN

OPEN:
  calls are blocked
  dispatch immediately returns FAILURE

after 30 seconds:
  breaker moves to HALF_OPEN
  one probe call is allowed

HALF_OPEN success:
  breaker moves back to CLOSED

HALF_OPEN failure:
  breaker moves back to OPEN
```

Important distinction:

```text
Current circuit breaker memory is in-process memory.
It is not Redis.
```

The code is designed so a Redis-backed breaker could replace it later for
multi-instance deployments.

### Step 10: Agent Response Cache

Implemented in:

```text
services/orchestrator/cache.py
```

This cache is Redis-backed.

It is different from the agent registry cache.

Response cache purpose:

```text
If a live agent call fails, reuse the last successful response for the same
agent/query/user/scope combination.
```

Cache key includes:

```text
agent_id
query
user_profile.owner_id
allowed_owner_ids
```

Key format:

```text
artha:agent:{agent_id}:{sha256_digest}
```

Stored value:

```json
{
  "response": {},
  "cached_at": "ISO datetime",
  "ttl_hours": 6
}
```

Redis expiry is:

```text
2 * cache_ttl_hours
```

This allows two fallback tiers:

```text
SECONDARY -> cache age <= cache_ttl_hours
TERTIARY  -> cache age > cache_ttl_hours but Redis key still exists
```

### Step 11: Fallback Tiers

Defined in:

```text
libs/confidence/tier.py
```

Fallback tiers describe how the orchestrator got an agent response:

```text
PRIMARY   -> live HTTP call succeeded
SECONDARY -> fresh Redis cached response used
TERTIARY  -> stale Redis cached response used
FAILURE   -> no usable response
```

Confidence penalties:

```text
PRIMARY   -> 0 percentage point penalty
SECONDARY -> -10 percentage points
TERTIARY  -> -25 percentage points
FAILURE   -> excluded from average and recorded as a gap
```

This is separate from an agent's internal data freshness. The orchestrator tier
describes the reliability of the transport/fallback path.

### Step 12: Compose Baseline Confidence

Implemented in:

```text
libs/confidence/composition.py
```

Each agent returns confidence as a `0.0` to `1.0` value.

The composer:

```text
1. excludes FAILURE agents
2. records FAILURE agents as gaps
3. converts active confidence to 0-100 scale
4. applies fallback tier penalties
5. averages the adjusted active confidence values
```

Example:

```text
cashflow_agent:
  confidence = 0.90
  tier = PRIMARY
  adjusted = 90

goal_agent:
  confidence = 0.80
  tier = SECONDARY
  adjusted = 80 - 10 = 70

risk_agent:
  tier = FAILURE
  excluded from average
  added to gaps

baseline confidence = average(90, 70) = 80
gaps = ["risk_agent"]
```

This baseline confidence is not final. The critic can lower it.

### Step 13: Critic

Implemented in:

```text
services/orchestrator/critic.py
```

The critic performs deterministic quality checks after all agent responses are
collected.

Important invariant:

```text
The critic can only lower confidence.
It never raises confidence.
```

Current checks:

```text
surplus_paise mismatch across agents
net_worth_paise mismatch across agents
goal target_years vs risk time_horizon_years mismatch
unknown schema_version
missing agent outputs
```

Penalty schedule:

```text
5 percentage points per FAILURE/gap agent
5 percentage points per inconsistency
3 percentage points per unknown schema version
maximum critic penalty = 30 percentage points
```

Final confidence:

```python
final_confidence = max(0, baseline.score - total_penalty)
```

This design gives predictable, explainable confidence changes.

### Step 14: Synthesizer

Implemented in:

```text
services/orchestrator/synthesizer.py
```

The synthesizer merges multiple agent answers into one user-facing response.

It uses:

```text
LLMRole.SYNTHESIZER
```

It includes only useful, tool-backed agent responses.

It skips an agent when:

```text
the fallback tier is FAILURE
the response is missing
the agent returned text but did not use tools
the answer is empty
```

Reason:

An agent that did not use tools may have produced unsupported text. The
synthesizer treats that as unreliable instead of presenting it as financial
analysis.

If the synthesis LLM fails, the orchestrator falls back to plain concatenation
of usable agent answers.

For cloud LLM routing, the synthesizer can anonymize messages using:

```text
TokenMap
anonymiser
PII scanner
detokenisation
```

### Step 15: Audit Write

Implemented in:

```text
services/orchestrator/audit.py
```

The orchestrator writes an immutable recommendation header plus an initial event.

Stored in `recommendations`:

```text
owner_id
snapshot_id
query
plan_json
agent_outputs_json
final_output_json
composite_confidence
current_state
```

Stored in `recommendation_events`:

```text
recommendation_id
event_type = GENERATED
actor_user_id = null
payload = {"plan_id": "..."}
```

The recommendation is append-only in spirit:

```text
recommendations stores the generated result
recommendation_events stores lifecycle transitions
```

Later transitions, such as accept/reject/surface, are added as events.

## 4. Cache And Memory Summary

This is the most important reference section if you are explaining the system.

### Agent Registry Cache

```text
Type:
  in-memory Python dictionary

Source of truth:
  Postgres agent_registry table

Purpose:
  know which agents exist, their health, capabilities, endpoint, timeout, TTL

Refresh:
  periodic APScheduler refresh, usually every 60 seconds

Redis?
  no
```

Flow:

```text
Postgres agent_registry
  -> registry.refresh()
  -> in-memory AgentRegistryCache
  -> decomposer and dispatcher read from memory
```

### Agent Response Cache

```text
Type:
  Redis

Source of truth:
  last successful AgentResponse written after live agent success

Purpose:
  fallback when live agent HTTP call fails

Used by:
  dispatch.py

Redis?
  yes
```

Flow:

```text
live agent success
  -> store AgentResponse in Redis

future live agent failure
  -> try Redis response cache
  -> return SECONDARY or TERTIARY if found
```

### Circuit Breaker Memory

```text
Type:
  in-memory Python state

Source of truth:
  local process memory

Purpose:
  stop repeatedly calling failing agents

Redis?
  no, not currently
```

The code is structured so this could be replaced with a Redis-backed
implementation later.

### Audit Memory

```text
Type:
  Postgres

Stores:
  profile snapshots
  recommendation plans
  agent outputs
  critic result
  synthesized answer
  lifecycle events

Purpose:
  replayability, explainability, compliance, debugging
```

### LLM Context

```text
Type:
  temporary request context

Used by:
  LLM planner fallback
  synthesizer

Persisted?
  not as conversation memory
  final plan/output is persisted in audit tables
```

## 5. Decisions The Orchestrator Makes

The orchestrator makes the following decisions:

```text
Authentication:
  Is the caller allowed to request this owner_id?

Scope:
  Should agents see only the primary owner or family/household owner_ids?

Agent availability:
  Which agents are healthy enough to use?

Routing:
  Which domain agents should answer this query?

Dependency planning:
  Are prerequisite agents needed?

Execution:
  Which agents can run in parallel?
  Which agents must wait?

Failure handling:
  Should the live call be skipped because the circuit breaker is open?
  Should Redis fallback be used?

Fallback classification:
  Is the result PRIMARY, SECONDARY, TERTIARY, or FAILURE?

Confidence:
  How should cached or stale responses affect confidence?

Critic:
  Are there missing agents, inconsistent values, or unknown schemas?

Synthesis:
  Which agent responses are safe to include in the final answer?

Persistence:
  What plan, outputs, confidence, warnings, and state should be stored?
```

## 6. Design Justifications

### Why Use An Orchestrator?

The domain agents are specialized. One agent should not need to know how to
coordinate every other agent.

The orchestrator centralizes cross-agent responsibilities:

```text
routing
access scope
fallback
confidence composition
audit
observability
```

This keeps individual agents focused on their financial domain.

### Why Use A Serializable Plan?

The `Plan` is stored as JSON.

That gives:

```text
debuggability
replayability
auditability
visibility into routing decisions
future support for dependency chains
```

If a recommendation is questioned later, we can inspect exactly which agents
were selected and why the execution order looked the way it did.

### Why Rule-Based Routing Before LLM Routing?

Most financial queries contain obvious keywords.

Rule-based routing is:

```text
fast
cheap
predictable
easy to debug
```

LLM fallback is reserved for vague or ambiguous queries.

This gives a good balance:

```text
deterministic fast path
flexible fallback path
```

### Why Keep Registry In Memory Instead Of Querying Postgres Every Time?

Agent registry data changes slowly compared with recommendation requests.

Reading it from memory:

```text
reduces DB load
reduces request latency
keeps routing fast
```

Postgres remains the source of truth. The in-memory cache is only a periodically
refreshed snapshot.

### Why Use Redis For Agent Responses?

Agent responses are runtime fallback data.

Redis is a better fit because:

```text
fast lookup
natural TTL support
temporary operational cache
not part of the permanent audit trail
```

The permanent record still goes to Postgres after the recommendation is created.

### Why Use Circuit Breakers?

If an agent is down, repeatedly calling it wastes time and slows every request.

The circuit breaker lets the orchestrator fail fast and rely on cache or mark a
gap instead of blocking on repeated network failures.

### Why Have A Critic?

Agents may produce individually valid answers that conflict with each other.

The critic handles cross-agent quality checks.

It is deterministic and only lowers confidence, which keeps it explainable.

### Why Synthesize At The End?

Multiple specialist answers can be fragmented.

The user should receive one coherent response, not five disconnected agent
outputs.

The synthesizer turns tool-backed findings into a readable final answer while
preserving warnings and data gaps.

## 7. Interviewer-Style Story

Here is how I would explain the orchestrator in an interview.

The orchestrator is the central coordination layer for our multi-agent personal
finance system. When a user asks a question like "Can I increase my SIP and
still meet my emergency fund target?", the orchestrator does not try to answer
that directly. Instead, it treats the question as a workflow.

First, it authenticates the owner and loads the user's financial profile from
Postgres. Then it resolves the access scope. This is important because a user
might be asking only about their own finances, or they might be asking about the
family's combined finances. The orchestrator makes that decision up front and
passes only the allowed owner IDs to agents. That way, authorization logic is
centralized rather than duplicated across every agent.

Next, it creates a profile snapshot. I added this because recommendations need
to be explainable later. If the user changes their income, EMI, or risk profile
tomorrow, yesterday's recommendation should still be reproducible based on
yesterday's profile.

After that, the orchestrator checks which agents are available. This comes from
the agent registry cache. One thing I would be very clear about is that this is
not Redis. The agent registry cache is an in-memory Python dictionary. Its
source of truth is the Postgres `agent_registry` table, and a scheduler refreshes
that memory snapshot periodically. We use this because registry data changes
slowly, and reading it from memory keeps request-time routing fast.

Then the query is decomposed into a plan. The fast path is rule-based routing:
if the query mentions spending or budget, we route to the cashflow agent; if it
mentions SIPs or portfolio, we route to the investment agent; if it mentions
taxes, we route to the tax agent; and so on. If no rule matches, we use an LLM
planner fallback for vague questions like "Am I financially healthy?". This
keeps the common path cheap and deterministic while still handling ambiguous
queries.

The plan is represented as a small DAG. That matters because some agents depend
on others. For example, the goal agent may need cashflow and investment context,
and the risk agent may need cashflow context. The orchestrator automatically
adds those dependency agents and records the plan as JSON. That gives us an
audit trail of the routing decision.

Once the plan is ready, the dispatcher executes it. Independent agents run in
parallel. Dependent agents run after their prerequisites. Before calling each
agent, the dispatcher checks a circuit breaker. If an agent has failed too many
times recently, the breaker opens and the orchestrator skips the live call. This
prevents one unhealthy service from slowing down every recommendation request.

If the live HTTP call succeeds, the result is marked `PRIMARY` and the
successful response is stored in Redis. If the live call fails, the orchestrator
looks in the Redis response cache. This is the second important cache distinction:
agent responses are cached in Redis, but registry metadata is cached in memory.
If Redis has a fresh cached response, we return it as `SECONDARY`. If Redis has a
stale response that is still within the extended expiry window, we return it as
`TERTIARY`. If there is no usable cache entry, the agent result is marked
`FAILURE`.

After dispatch, the orchestrator composes confidence. A live primary response
gets no penalty. A fresh cached response gets a 10 percentage point penalty. A
stale cached response gets a 25 percentage point penalty. Failed agents are
excluded from the average and recorded as gaps. This gives us a baseline
confidence score.

Then the critic runs. The critic is deterministic and can only reduce
confidence. It checks for missing agents, inconsistent surplus or net worth
values, mismatched time horizons, and unknown schema versions. I like this
design because it separates agent-level confidence from cross-agent quality. An
agent may be confident in its own answer, but the overall recommendation should
still be penalized if different agents disagree.

Finally, the synthesizer turns the agent outputs into a single answer for the
user. It only includes tool-backed responses. If an agent returned text without
using tools, the synthesizer treats that as unreliable and skips it. If the
synthesis LLM fails, the system falls back to concatenating usable agent
answers, so the recommendation pipeline does not fail just because the final
language-generation step failed.

At the end, the orchestrator writes everything to Postgres: the frozen profile
snapshot, the plan JSON, raw agent outputs, critic result, final confidence,
synthesized answer, and the initial `GENERATED` event. That gives us a complete
audit trail and makes the system much easier to debug, replay, and explain.

In short, I would describe the orchestrator as a reliable workflow manager for
financial intelligence. It handles routing, scope, execution, fallback,
confidence, quality checks, synthesis, and audit, while keeping the actual
financial calculations inside specialized agents.

