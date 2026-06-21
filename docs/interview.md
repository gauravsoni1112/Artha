# Artha Agent Interview Questions And Answers

This document is a preparation guide for explaining the Artha agent and
orchestrator design in interviews or technical discussions. It includes common
questions, concise answers, and architecture-level decision justifications.

## 1. Short System Summary

### Q: Explain the Artha agent in one minute.

Artha is a tool-grounded personal finance agent. It uses LangGraph to separate
planning, execution, and reflection. The planner decomposes a user question into
structured steps. The executor runs each step through an assistant/tools loop,
where the LLM can request tools and LangGraph executes them. The reflector
scores the final answer and can trigger a bounded rerun if confidence is low.

For recommendation workflows, a separate orchestrator coordinates specialist
domain agents such as cashflow, investment, tax, goal, and risk. The
orchestrator handles scope, routing, dependency planning, fallback, confidence,
critic checks, synthesis, and audit persistence.

### Q: What problem is this architecture solving?

The main problem is safe and explainable financial reasoning. Users ask about
real money, so the system should not guess amounts. The design grounds answers
in backend tools, keeps tool inputs typed, records tool calls and traces, and
uses reflection and confidence scoring to make answer quality visible.

## 2. LangGraph Agent Architecture

### Q: Why did you use LangGraph instead of a simple LLM call?

A simple LLM call is hard to control for multi-step financial reasoning. It can
guess values, skip data lookup, or produce untraceable answers. LangGraph gives
explicit control flow:

```text
planner -> executor_loop -> reflector
```

It also supports conditional routing. In this system, the reflector can route
back to the executor when confidence is low.

### Q: What are the main nodes in your graph?

The outer graph has three main nodes:

```text
planner
executor_loop
reflect
```

The executor uses an inner subgraph:

```text
assistant
tools
```

So the full shape is:

```text
START
  -> planner
  -> executor_loop
  -> reflect
  -> END

reflect can route back to executor_loop when needs_rerun=True.
```

Inside the executor:

```text
assistant
  -> tools, if tool_calls exist
  -> assistant
  -> END, when no tool_calls exist
```

### Q: What is the difference between the outer graph and inner subgraph?

The outer graph manages high-level reasoning:

```text
plan the query
execute the plan
reflect on answer quality
possibly rerun
```

The inner subgraph manages tool use for a single plan step:

```text
assistant decides whether a tool is needed
ToolNode executes the tool
assistant reads the observation
assistant either calls another tool or answers
```

### Q: Is your agent ReAct?

The planner node is not ReAct. It is a structured decomposition node that
returns a JSON plan.

The executor subgraph is ReAct-like because it follows an LLM/action/observation
loop:

```text
assistant -> tool call -> tool observation -> assistant
```

However, it does not parse text like `Thought`, `Action`, and `Observation`.
It uses native LangChain tool calls through:

```python
llm.bind_tools(tools)
ToolNode(tools)
```

### Q: How does the graph decide when to stop?

The inner assistant/tools subgraph stops when the assistant returns an AI
message without `tool_calls`.

The outer graph stops when the reflector sets:

```python
needs_rerun = False
```

If the reflector thinks the answer is incomplete or confidence is below the
threshold, it can set:

```python
needs_rerun = True
```

Then the conditional edge routes back to `executor_loop`.

### Q: How do you prevent infinite loops?

There are two controls:

```text
AGENT_MAX_ITERATIONS
MAX_REFLECT_ITERATIONS
```

`AGENT_MAX_ITERATIONS` limits the assistant/tools recursion.  
`MAX_REFLECT_ITERATIONS` limits how many times reflection can rerun execution.

## 3. Planner Node

### Q: Does the planner use an LLM?

Yes. The planner uses an LLM with structured output:

```python
llm.with_structured_output(Plan)
```

It sends the user question plus a planner system prompt and expects a `Plan`
object.

### Q: What schema does the planner return?

The planner returns:

```python
class Plan(BaseModel):
    steps: list[str]
    reasoning: str
    confidence: float
    confidence_reason: str
```

Example:

```json
{
  "steps": [
    "What was my category spending this month?",
    "What was my category spending last month?"
  ],
  "reasoning": "Comparison requires two period-specific lookups.",
  "confidence": 1.0,
  "confidence_reason": "The comparison periods are clear."
}
```

### Q: Why use structured output for the planner?

Structured output gives the rest of the graph a reliable contract. The executor
does not have to parse free-form text to figure out what to do. It receives a
typed `Plan` with steps, reasoning, and confidence.

### Q: What happens if the planner fails?

If the planner fails to produce valid structured output, it falls back to:

```python
Plan.trivial(question)
```

That means the original question becomes a single-step plan. The agent still
works, just without decomposition.

### Q: Why not let the executor decide everything directly?

The executor can choose tools, but it is not ideal for deciding the full
multi-step strategy. The planner separates strategic decomposition from tactical
tool use.

This makes the run easier to debug:

```text
What did the agent plan?
Which steps were executed?
Which tools were used for each step?
What did reflection think of the final answer?
```

## 4. Executor And Tool Calling

### Q: Does the agent directly call tools?

The LLM does not directly execute tools. It emits tool calls. LangGraph's
`ToolNode` executes the actual Python functions.

Flow:

```text
LLM assistant emits tool_calls
  -> should_continue routes to tools
  -> ToolNode executes the tool
  -> tool result is returned as observation
  -> assistant continues
```

### Q: What does `llm.bind_tools(tools)` do?

It exposes tool schemas to the model so the model can request a tool by name and
provide structured arguments.

Example:

```text
tool name: category_analysis
arguments: start_date, end_date, fiscal_year
```

The model chooses the call, but the backend executes it.

### Q: How are tool arguments validated?

Each tool has a Pydantic input schema in:

```text
services/agent/tools/registry.py
```

For example:

```python
class TransactionQueryInput(BaseModel):
    start_date: str | None
    end_date: str | None
    category: str | None
    account_id: str | None
    limit: int = 50
```

The schema defines the allowed arguments and descriptions for tool calling.

### Q: How do tools return data?

Tools return a `ToolResult`:

```python
class ToolResult(BaseModel):
    tool_name: str
    data: dict[str, Any]
    data_freshness: datetime
    query_params: dict[str, Any]
    currency: str = "INR"
    warnings: list[str]
```

The result is converted to compact JSON with:

```python
to_llm_str()
```

That JSON becomes the tool observation seen by the assistant.

### Q: Why force arithmetic through tools?

Financial arithmetic should be deterministic and auditable. The system prompt
tells the model not to compute amounts inline. Instead, it should call tools
such as:

```text
convert_amount
calculate_percentage
calculate_growth
calculate_compound_interest
```

This reduces calculation mistakes and keeps numeric operations traceable.

### Q: How do you prevent the LLM from accessing another user's data?

Tool wrappers bind `owner_id` server-side. Any `owner_id` supplied by the LLM is
discarded:

```python
kwargs.pop("owner_id", None)
```

Then the authenticated owner ID from the server is used. This prevents prompt
injection from changing the user scope.

### Q: Why is there no separate tool gateway?

The current tools are local Python functions with structured schemas and
server-side owner binding. A separate gateway would add complexity before it is
needed.

A tool gateway would make sense if:

```text
tools become remote services
multiple systems share the same tools
tool-level rate limits are needed
tool-level audit and policy checks are centralized
tool-specific retries and circuit breakers are needed
PII scanning must happen before and after every tool call
```

For now, the registry gives a controlled local tool surface.

## 5. Reflection

### Q: Why did you add a reflection node?

Financial answers need a quality gate. The first answer might miss a time range,
omit a key figure, fail to explain missing data, or be too vague. Reflection
reviews the draft answer and assigns a confidence score.

### Q: What schema does reflection return?

Reflection returns:

```python
class _LLMReflection(BaseModel):
    confidence_score: float
    is_complete: bool
    reflection_notes: str
```

### Q: When does reflection trigger a rerun?

Reflection triggers a rerun when:

```text
answer is incomplete
or confidence_score < REFLECTION_THRESHOLD
```

and:

```text
reflect_count < MAX_REFLECT_ITERATIONS
```

### Q: What are the risks of LLM-based reflection?

The reflector is still an LLM, so it can be wrong. It may overestimate or
underestimate answer quality. That is why reruns are bounded and why domain
agents also use grounding checks for numeric claims.

### Q: Can reflection increase confidence?

In the chat agent, reflection assigns a score to the draft answer. In the
orchestrator critic, confidence can only be lowered. The distinction is useful:
the chat reflector evaluates answer quality, while the orchestrator critic
applies deterministic penalties after agent responses are collected.

## 6. Memory And Persistence

### Q: What does your LangGraph state contain?

The outer graph state is:

```python
class PlanState(TypedDict):
    messages: list
    plan: Plan | None
    step_observations: list[str]
    confidence_score: float | None
    reflection_notes: str | None
    needs_rerun: bool
    reflect_count: int
```

### Q: What is conversation memory in this system?

Conversation memory is stored in Postgres through:

```text
ChatSession
AgentRun
```

Each run stores the user message, assistant response, tool calls, message trace,
scratchpad, confidence, reflection notes, and timing metadata.

### Q: Do you replay full chat history?

Not currently. If a session has a stored summary, the agent injects that summary
as a `SystemMessage`. Full message replay is reserved for future expansion.

### Q: What is the difference between memory, cache, and audit?

Memory:

```text
Conversation/session context used by the chat agent.
```

Cache:

```text
Temporary fallback data, such as Redis agent response cache.
```

Audit:

```text
Permanent records used for replayability and compliance, such as
recommendation plans, agent outputs, final confidence, and events.
```

## 7. Orchestrator

### Q: What is the difference between the agent and the orchestrator?

The LangGraph agent answers an interactive chat message for one owner/session.

The orchestrator coordinates recommendation generation across multiple
specialist domain agents. It handles scope, routing, dispatch, fallback,
confidence, critic checks, synthesis, and audit persistence.

### Q: Why do you need specialist agents?

Financial advice spans multiple domains:

```text
cashflow
investments
tax
goals
risk
```

Each domain has different tools and reasoning needs. Specialist agents keep
tool choice focused and reduce the chance of irrelevant tool use.

### Q: How does the orchestrator choose agents?

The orchestrator uses rule-based matching first. For example:

```text
spending, budget, transaction -> cashflow_agent
portfolio, SIP, stock -> investment_agent
tax, ITR, deduction -> tax_agent
goal, retirement, corpus -> goal_agent
risk, insurance, debt -> risk_agent
```

If no rules match, it falls back to an LLM planner that selects from registered
agents.

### Q: Why use rule-based routing before LLM routing?

Most financial queries have obvious keywords. Rule-based routing is fast,
cheap, deterministic, and easy to debug. LLM fallback is useful for vague
queries like:

```text
Am I doing okay financially?
```

This gives a balance between predictability and flexibility.

### Q: What is the orchestrator Plan?

The orchestrator plan is a serializable DAG:

```python
class AgentCall:
    agent_id: str
    allowed_owner_ids: list[uuid.UUID]
    context: dict[str, Any]
    depends_on: list[str]

class Plan:
    original_query: str
    steps: list[AgentCall]
    plan_id: uuid.UUID
    created_at: datetime
```

Steps without dependencies can run in parallel. Steps with dependencies wait.

### Q: Why does `goal_agent` depend on cashflow and investment?

Goal recommendations often need current surplus and portfolio data. For example,
to answer whether the user can increase SIPs, the goal agent needs cashflow
capacity and investment context.

Dependency:

```python
"goal_agent": ["cashflow_agent", "investment_agent"]
```

### Q: How does scope resolution work?

The orchestrator resolves allowed owner IDs before calling any agent.

Modes:

```text
individual scope -> PRIMARY owner only
family scope -> PRIMARY + SPOUSE + DEPENDENT
```

Agents receive only `allowed_owner_ids`; they do not decide access scope.

## 8. Fallback And Reliability

### Q: What happens if a domain agent is down?

The dispatcher first checks the circuit breaker. If calls are allowed, it tries
the live HTTP call. On failure, it checks Redis for the last successful cached
response.

Result tiers:

```text
PRIMARY   -> live call succeeded
SECONDARY -> fresh cached response
TERTIARY  -> stale cached response
FAILURE   -> no usable response
```

### Q: Why use a circuit breaker?

If an agent is repeatedly failing, calling it again wastes time and slows down
requests. The circuit breaker lets the orchestrator fail fast and rely on cache
or mark a data gap.

### Q: What is Redis used for?

Redis stores the last successful domain-agent response. It is used only as a
fallback when a live agent call fails.

It is not the agent registry cache. The registry cache is in-memory and backed
by Postgres.

### Q: Why not fail the whole recommendation if one agent fails?

A financial recommendation may still be useful with partial data. The system
records missing agents as gaps, lowers confidence, and communicates uncertainty
instead of failing the entire request.

## 9. Confidence And Critic

### Q: How is confidence calculated?

Each agent returns confidence from `0.0` to `1.0`. The orchestrator converts it
to a percentage, applies fallback-tier penalties, excludes failures, and
averages the active results.

Then the critic can lower confidence further.

### Q: What does the critic check?

The critic checks deterministic consistency issues:

```text
surplus mismatch across agents
net worth mismatch across agents
goal target years vs risk time horizon mismatch
unknown schema versions
missing agent outputs
```

### Q: Can the critic increase confidence?

No. The critic can only lower confidence. This keeps confidence adjustments
explainable and conservative.

### Q: Why only lower confidence?

The baseline confidence comes from the agents and fallback composition. The
critic is a quality-control layer. Its job is to find problems, not to make the
answer seem more certain than the underlying agents reported.

## 10. Security And Privacy

### Q: How do you prevent prompt injection?

The most important control is separating user text from trusted server context.

Examples:

```text
owner_id is bound server-side
tool schemas restrict arguments
tools query through backend functions, not arbitrary SQL from the LLM
orchestrator resolves scope before agent calls
```

### Q: Can the LLM choose arbitrary SQL?

No. The LLM can only choose registered tools with structured arguments. The tool
implementation performs the actual database query.

### Q: What data is sent to cloud LLMs?

The code has privacy utilities for anonymization, PII scanning, token mapping,
and detokenization. For cloud-bound calls, messages can be scrubbed before they
leave the environment, and detokenized after the response.

### Q: Why is audit important for a financial assistant?

Financial advice needs traceability. If a recommendation is questioned later,
the system should show:

```text
what profile snapshot was used
what plan was created
which agents were called
which tools were used
what each agent returned
how confidence was calculated
what warnings were produced
```

## 11. Architecture Decision Questions

### Q: Why separate planner, executor, and reflector?

Each part has a different responsibility:

```text
planner -> strategy
executor -> data gathering and answer generation
reflector -> quality check
```

Separating them makes the system easier to test, debug, and explain.

### Q: Why not use one big agent with all tools?

One big agent with all tools is harder to control. It increases the chance of
irrelevant tool calls and makes debugging more difficult. Specialist agents keep
tool access focused by domain.

### Q: Why not hard-code all flows?

Hard-coded flows are predictable but brittle. They work for known queries but
struggle with natural language variety. The chosen design uses deterministic
rules where they are reliable and LLM planning where flexibility is useful.

### Q: Why use Pydantic?

Pydantic gives typed contracts for planner output, reflection output, tool
inputs, tool results, and agent envelopes. This makes failures easier to catch
and reduces ad hoc parsing.

### Q: Why use LangChain tools and LangGraph ToolNode?

LangChain tools provide standard structured tool definitions. LangGraph ToolNode
handles tool execution and routing cleanly inside the graph. This avoids writing
a custom tool-call parser and executor.

### Q: Why use Postgres?

Postgres is used for durable application data:

```text
user profiles
chat sessions
agent runs
recommendations
profile snapshots
recommendation events
agent registry source of truth
```

These records need persistence, relational integrity, and queryability.

### Q: Why use Redis?

Redis is used for temporary operational cache, especially last successful
agent responses. It is fast and has natural TTL behavior, which fits fallback
cache use cases.

### Q: Why use HTTP between orchestrator and domain agents?

HTTP gives service isolation. Each domain agent can be deployed, scaled, and
monitored independently. The orchestrator only needs the common
`AgentRequest`/`AgentResponse` contract.

### Q: Why use an in-memory registry cache?

Agent registry data changes slowly. Reading it from memory reduces database
load and request latency. Postgres remains the source of truth, while the
in-memory cache is a periodically refreshed snapshot.

### Q: Why use a serializable DAG plan?

A DAG plan gives visibility into routing and execution order. It can be stored
as JSON for audit and replay.

It also supports future dependency chains where one agent may need another
agent's result before running.

### Q: Why have both response cache and audit storage?

They serve different purposes.

Response cache:

```text
temporary Redis fallback for live failures
```

Audit storage:

```text
permanent Postgres record for replay, debugging, compliance, and lifecycle
tracking
```

### Q: Why synthesize at the end?

Specialist agents return separate domain findings. Users should receive one
coherent answer. The synthesizer merges useful, tool-backed outputs and includes
caveats from confidence and critic checks.

### Q: Why skip agent answers that used no tools?

In this architecture, useful financial answers should be grounded in tool data.
If an agent returns text without tool use, it may be unsupported. The
synthesizer treats that as unreliable and omits it.

### Q: Why not let agents decide family scope themselves?

Scope is a security decision and should be centralized. The orchestrator
resolves allowed owner IDs and passes them to agents. Agents should not expand
access based on LLM interpretation.

### Q: Why store message traces and scratchpad?

They help debug behavior:

```text
what the model saw
which tools it requested
what observations came back
how the answer was formed
why confidence was assigned
```

This is especially useful when investigating bad answers.

### Q: What would you improve next?

Strong next steps:

```text
extract inline graph nodes into separate builder functions
wire AgentAnswer as the final structured output
add a tool gateway if tools become remote/shared
add stronger tool failure handling inside the chat agent
add full conversation replay or retrieval memory
add more deterministic critic checks
add tests for graph routing and reflection reruns
```

## 12. Deep-Dive Follow-Up Questions

### Q: What happens if the planner chooses a bad plan?

The executor may still answer using tools, but the answer could be incomplete.
Reflection helps catch low-quality answers. For stronger validation, the system
could add plan validators that check whether each step maps to available tools.

### Q: What happens if a tool returns no data?

The system prompt instructs the assistant to explain why data may be missing and
suggest ingesting the relevant document. Tool warnings can also be surfaced in
the answer.

### Q: What happens if a tool returns wrong data?

The current system assumes backend tools are trusted. For cross-agent
recommendations, the critic can detect some inconsistencies. For individual
tool correctness, tests and data validation are needed at the tool layer.

### Q: How do you measure agent quality?

Possible metrics:

```text
tool-call success rate
reflection confidence
rerun count
grounding failures
latency per node
agent fallback tier
critic penalties
user accept/reject events
```

### Q: How do you handle latency?

Latency is controlled by:

```text
single-step plans for simple questions
recursion limits
bounded reflection retries
parallel dispatch in the orchestrator
HTTP connection reuse
registry cache
Redis fallback
```

### Q: How do you debug a wrong answer?

Check:

```text
planner output
messages_trace
tool_calls
tool observations
scratchpad
reflection_notes
confidence_score
domain-agent outputs
critic warnings
audit records
```

### Q: What is the most important safety feature?

Server-side owner binding and centralized scope resolution. The LLM can request
tools, but it cannot choose another user's identity or expand data scope.

## 13. Strong Closing Answer

If asked to summarize the design decision:

```text
The architecture separates strategy, execution, verification, and orchestration.
The planner creates structured steps, the executor gathers real data through
typed tools, the reflector checks answer quality, and the orchestrator
coordinates specialist agents with fallback, confidence, critic checks, and
audit. We chose this flow because financial answers need grounding,
traceability, and safety. LangGraph gives explicit control flow, Pydantic gives
schema contracts, Postgres gives durable auditability, Redis gives fast fallback
cache, and server-side owner binding protects user data.
```

