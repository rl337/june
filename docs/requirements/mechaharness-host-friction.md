# MechaHarness host-API friction ledger

June-sourced asks for a more readable MechaHarness host surface. This is not
June permanent architecture: each item should either land as a MechaHarness
interface improvement or be explicitly declined with rationale.

Floor at time of writing: **mechaharness 0.5.0** (pyiv ≥ 1.1 HTTP + stdlib DI;
host kit + Agentic Recipes + HF-05/07/08). Durable resume /
`EffectfulGraphNodeRunner` / `CheckpointStore` exist since 0.3.0; 0.4.0 adds
`mechaharness.host_kit`; 0.4.1 adds tapped `host_graph_executor`,
`conversational_tool_loop`, and `embed_recipe_as_tool`; 0.5.0 requires Config-
injected `DateTimeService` / `Environment` / `AsyncHttpClient` and drops
hand-wired Config getter service caches.

## Working rule

Every June MechaHarness call site MUST either:

1. read as a recipe bind + run story a human can follow, or
2. point here with a short comment / doc cross-link describing the simpler
   host API June wants.

Do not grow permanent June wrappers that hide debts MechaHarness should fix.

## Asks

### HF-01 — Host executor kit (P0)

**June evidence:** formerly `src/june/harness/execution.py` `build_graph_executor`
hand-wired EventLog, AccessPolicy, LinkageResolver, failure/escalation,
checkpoint store, and `NoopCrashProbe`.

**Ask:** Blessed path remains `MechaHarnessConfig` → `inject(GraphExecutor)`,
with a small host helper for the common case.

**Status:** **landed in mechaharness 0.4.0** via `host_graph_executor`. June
console / `MechaHarnessClient` / remote-task now all use host_kit (0.5
adoption closed the dual hand-wired path).

### HF-02 — Effectful submit-once helper (P0)

**June evidence:** formerly a local `CodingJobEffectfulRunner` reimplemented
`reconcile` / `dispatch` / `observe`.

**Ask:** Thin host-facing adapter for submit-once / complete-on-accept /
never-silent-redispatch.

**Status:** **landed in mechaharness 0.4.0** as `SubmitOnceEffectfulRunner`.
June `make_coding_job_runner` is a thin `submit=` binding over that helper.

### HF-03 — Catalog bind / tile for linear remote-task shape (P1)

**June evidence:** `build_remote_task_graph` hand-builds
`ExecutionGraph` + `DependencyEdge` sequences; `june.remote_task` is a
June-incubated recipe candidate, not an MH catalog id.

**Ask:** After reuse evidence, promote only the generic skeleton (validate →
effectful external dispatch → collect/verify soft points) into an MH Agentic
Recipe. Until then, keep incubation in June.

**Status:** open (incubation intentional; not a merge blocker for remote-task A–C).

### HF-04 — Typed run result / less graph digging (P1)

**June evidence:** orchestrator used to scrape
`result.graph.nodes["coding_job"].payload["external_run_id"]`.

**Ask:** Stable host-facing outcome accessors for effectful node results.

**Status:** **landed in mechaharness 0.4.0** as `effectful_external_handle`.
Remote-task dispatch uses it.

### HF-05 — Single host entrypoint for runners + checkpoints + effects (P1)

**June evidence:** Happy path uses `MechaHarnessClient.bind_template` /
`execute`; remote-task / chat / console cron used to dual-path through
hand-wired executors for event taps.

**Ask:** One Config-injected entrypoint that also supports event tapping so
June can drop the dual path.

**Status:** **landed in mechaharness 0.4.1** via `tapping_event_log` /
`host_graph_executor(event_log=...)`. June chat, console cron, and
`MechaHarnessClient.execute` all use it (0.5 adoption).

### HF-06 — Subgraph clone-from-checkpoint (P2)

**June evidence:** `src/june/harness/cron_graph.py` remaps ids / copies nodes
when spawning console cron/chat instances.

**Ask:** MH helper to clone a checkpointed subgraph under a new run id with
stable namespacing (`instance_key` / tile semantics).

**Status:** open.

### HF-07 — Dynamic tool-loop as ExecutionGraph nodes (P0)

**June evidence:** `ChatEngine.tool_loop` hides N× LLM/tool rounds inside one
`june.chat.tool_loop` node; console cannot zoom into turns without a side
channel.

**Ask:** Bounded conversational tool-loop recipe whose runtime topology is an
ExecutionGraph (`llm_turn` / `tool_call` / optional `tool_round`), with parent
`tools.subgraph` reflecting children for host zoom.

**Status:** **landed in mechaharness 0.4.1** as
`ConversationalToolLoopTemplate` + `ConversationalToolLoopRunner`. June
`june.chat` tools node binds that runner; see
[`mechaharness-dynamic-tool-graph.md`](./mechaharness-dynamic-tool-graph.md).

### HF-08 — Nested recipe-as-tool (P0)

**June evidence:** `generate_image` formerly called `run_imagegen_recipe` as a
side effect with a parallel console soft lane.

**Ask:** Soft-point so a `tool_call` may bind/run a child GraphTemplate;
child checkpoint attaches under that node (`child_run_id`, shared budget).

**Status:** **landed in mechaharness 0.4.1** as `embed_recipe_as_tool`; June
attaches the live imagegen checkpoint under the expanded `tool_call` node.
Parallel console imagegen soft lane removed.

## Related pyiv asks

See `docs/requirements/pyiv-di-asks.md`. DI improvements that unblock HF-01 /
HF-05 should land in pyiv when both June and MechaHarness need them; recipe
modules must stay pyiv-free.

## Declined / not June’s job

- Cursor SDK shapes, June `task_id` lifecycle, MCP/HTTP bridge, home-LAN
  topology — June-owned; do not push into MechaHarness.
- Full “await external job until complete” inside MH for remote coding —
  June control observe/reconcile owns post-accept lifecycle for the bootstrap.
