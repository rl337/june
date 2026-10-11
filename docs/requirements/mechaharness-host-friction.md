# MechaHarness host-API friction ledger

June-sourced asks for a more readable MechaHarness host surface. This is not
June permanent architecture: each item should either land as a MechaHarness
interface improvement or be explicitly declined with rationale.

Floor at time of writing: **mechaharness 0.4.0** (host kit + Agentic Recipes).
Durable resume / `EffectfulGraphNodeRunner` / `CheckpointStore` exist since
0.3.0; 0.4.0 adds `mechaharness.host_kit`.

## Working rule

Every June MechaHarness call site MUST either:

1. read as a recipe bind + run story a human can follow, or
2. point here with a short comment / doc cross-link describing the simpler
   host API June wants.

Do not grow permanent June wrappers that hide debts MechaHarness should fix.

## Asks

### HF-01 — Host executor kit (P0)

**June evidence:** `src/june/harness/execution.py` `build_graph_executor`
hand-wires EventLog, AccessPolicy, LinkageResolver, failure/escalation,
checkpoint store, and `NoopCrashProbe` for paths that need event tapping.

**Ask:** Blessed path remains `MechaHarnessConfig` → `inject(GraphExecutor)`,
with a small host helper for the common case.

**Status:** **partially landed in mechaharness 0.4.0** via
`host_graph_executor`. Remote-task dispatch uses it. Remaining debt: console /
`MechaHarnessClient` still use hand-wired `build_graph_executor` for
`TappingEventLog` (see HF-05).

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
`execute`; remote-task uses `host_graph_executor`; cron/console still use
`run_graph` / hand-wired executor for event taps.

**Ask:** One Config-injected entrypoint that also supports event tapping so
June can drop the dual path.

**Status:** open (remote-task path improved; console path remains).

### HF-06 — Subgraph clone-from-checkpoint (P2)

**June evidence:** `src/june/harness/cron_graph.py` remaps ids / copies nodes
when spawning console cron/chat instances.

**Ask:** MH helper to clone a checkpointed subgraph under a new run id with
stable namespacing (`instance_key` / tile semantics).

**Status:** open.

## Related pyiv asks

See `docs/requirements/pyiv-di-asks.md`. DI improvements that unblock HF-01 /
HF-05 should land in pyiv when both June and MechaHarness need them; recipe
modules must stay pyiv-free.

## Declined / not June’s job

- Cursor SDK shapes, June `task_id` lifecycle, MCP/HTTP bridge, home-LAN
  topology — June-owned; do not push into MechaHarness.
- Full “await external job until complete” inside MH for remote coding —
  June control observe/reconcile owns post-accept lifecycle for the bootstrap.
