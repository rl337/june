# MechaHarness: dynamic tool-loop + recipe-as-tool graphs

June-owned ask for the MechaHarness agent. Console zoom into tool
back-and-forths and nested recipes must come from **live ExecutionGraph
checkpoints and MH events**, not a second June observability graph.

Floor at time of writing: **mechaharness 0.5.0** (HF-05/07/08 landed in 0.4.1). Cross-links:
[`mechaharness-host-friction.md`](./mechaharness-host-friction.md) (HF-05,
HF-07, HF-08), [`interactive-chat-channels.md`](./interactive-chat-channels.md).

## Why this is MechaHarness’s job

MH already provides:

- Nested **static** subgraph execution (`GraphExecutor` subgraph nodes /
  `child_run_id` events).
- `RolloutGraph` as a **separate** observed topology projected from events.
- `ToolLoopHarness` as an **inference** stop family (`should_stop` on chat
  messages), not a graph recipe.
- Repeating nodes + `StopContract` at the linkage layer.

June still cannot:

1. Grow an **ExecutionGraph** as tool rounds are discovered (unknown N at bind).
2. Represent each LLM turn and each tool invocation as first-class `GraphNode`s
   (with optional child `subgraph` for nested recipes) that hosts can zoom.
3. Observe that topology through the blessed host entrypoint (HF-05 event tap).
4. Bind a child `GraphTemplate` / Agentic Recipe under a `tool_call` node so
   nested imagegen (etc.) appears under that tool in the checkpoint tree.

June evidence today:

- Opaque loop: `src/june/recipes/chat/engine.py` (`ChatEngine.tool_loop`) —
  N× (complete → tool_calls → tool results) inside one `june.chat.tool_loop`
  node (`src/june/recipes/chat/graph.py`).
- Nested recipe side call: `src/june/tools/imagegen.py` →
  `run_imagegen_recipe`, plus a parallel console soft lane /
  `imagegen_mirror` — rejected as durable architecture.

**Working rule:** do not grow permanent June wrappers that paint fake phases.
After MH ships HF-07/HF-08 (+ HF-05), June binds soft points and the console
reads checkpoints/events only.

---

## HF-07 — Dynamic tool-loop as ExecutionGraph nodes (P0)

### Ask

Ship an Agentic Recipe (or equivalent graph pattern) for a **bounded
conversational tool loop** whose **runtime topology is an ExecutionGraph**
(or a continuously checkpointed equivalent hosts can treat as one), not only
a post-hoc `RolloutGraph`.

Suggested node kinds (names flexible):

| Kind | Role |
|------|------|
| `llm_turn` | One model `complete` / inference step |
| `tool_call` | One tool invocation (args in, result out) |
| `tool_round` (optional) | Subgraph grouping one model response and its tool_calls |

Behavior:

- Stop when the model emits no tool calls (final natural-language answer).
- Bound by `StopContract` / `max_iterations` (and shared parent budget).
- Emit normal `graph_node_start` / `graph_node_end` (and nested subgraph
  events when a tool has a child graph).
- Parent container node (e.g. `tools`) checkpoint’s `subgraph` reflects
  completed and in-flight children so hosts can render zoom **without a
  side channel**.

### Soft points (host fills)

- Inference / model complete (structured `tool_calls` on the assistant message).
- Tool dispatch (string/JSON tools and/or HF-08 recipe tools).
- Message / carried state keys for the loop.
- Budgets and stop contract params.

### Acceptance

1. Host binds inference + tool soft points, runs one recipe, and can
   `checkpoint()` a tree shaped like:

   `tools → round_i → { llm_turn, tool_call* }`

   (exact ids flexible; nesting depth and edges must be present).
2. Unknown round count at bind time is supported (dynamic expand, repeating
   tile, or equivalent). **No** requirement that the host pre-unroll
   `max_tool_turns` no-op nodes.
3. Events alone are insufficient: a host that only consumes checkpoints must
   still see the growing interior under `tools`.
4. Works with the tapped host entrypoint once HF-05 lands (acceptance tests
   must not depend on June’s hand-wired `TappingEventLog`).

### Non-goals

- Channel adapters, web console UI, provider SDKs.
- Requiring a June-branded catalog id (`june.chat`) before a second host
  wants the same shape — prefer a generic name
  (e.g. `agentic.tool_loop`) if promoted.

---

## HF-08 — Nested recipe-as-tool (P0)

### Ask

Soft-point / host helper so a `tool_call` may **bind and run a child
`GraphTemplate` / Agentic Recipe**; the child run attaches under that
`tool_call` node as `subgraph` (MH nested run, shared budget ledger).

- Child checkpoint + events remain queryable via parent run /
  `child_run_id` linkage (same family as today’s static subgraph runner).
- Tool result returned to the LLM is derived from the child outcome
  (host-filled adapter), not a second private channel outside the graph.

### Acceptance

1. Example path: chat tool loop → `tool_call:generate_image` → child oneshot
   `prompt → generate → persist → verify` visible under that tool node after
   zoom (checkpoint tree, not only journal lines).
2. Nested spend aggregates on the shared budget; failure/soft-exhaustion
   surfaces on the parent `tool_call` status.
3. Works with the tapped host entrypoint (HF-05); June must not need a
   parallel “imagegen soft lane” on a console structure graph for topology.

### Non-goals

- Comfy / image backends, DocumentStore media persistence (June-owned).
- Forcing every string tool to be a GraphTemplate — only recipe-backed tools
  need subgraph attach; ordinary function tools remain leaf `tool_call` nodes.

---

## Dependency: HF-05

Event tapping on the blessed host executor (`host_graph_executor` or
successor) remains required so June can drop
`src/june/harness/execution.py` `build_graph_executor` dual path. HF-07/HF-08
acceptance tests MUST pass with that tapped entrypoint.

See HF-05 in [`mechaharness-host-friction.md`](./mechaharness-host-friction.md).

---

## Target topology (illustrative)

```text
chat / agent turn
  refine → context → tools → render
                      │
                      └─ tools.subgraph
                           round_0
                             llm_turn → tool_call:generate_image
                                            └─ imagegen oneshot
                                                 prompt → generate → persist → verify
                           round_1
                             llm_turn   (final; no tools)
```

Hosts zoom: four outer phases at a glance; interiors appear only when the
world camera is large enough on `tools` / `tool_call` nodes.

---

## June consumption (0.5.0 / HF-07+)

- `june.chat` tools node kind is `conversational_tool_loop` with
  `ConversationalToolLoopRunner` (complete + dispatch_tool soft points).
- `generate_image` returns tool JSON and stashes the child graph checkpoint for
  attach under the expanded `tool_call` node.
- Console `/api/chat` begins a chat instance with the live recipe checkpoint and
  taps MH events via `host_graph_executor(event_log=tapping_event_log(...))`.
- Parallel console imagegen soft lane and `imagegen_mirror` removed.

## Suggested MH agent test plan

- [ ] Offline unit: bind mock inference that returns one tool_call then a
      final answer; assert checkpoint nesting under `tools`.
- [ ] Offline unit: `tool_call` with child linear graph; assert child nodes
      present under tool node after run; assert `child_run_id` on events.
- [ ] Integration with tapped host executor (HF-05): host callback receives
      node start/end for llm_turn, tool_call, and nested child nodes in order.
- [ ] Budget: nested child spend visible on parent ledger.
- [ ] StopContract: loop aborts at `max_iterations` without unbounded growth.
