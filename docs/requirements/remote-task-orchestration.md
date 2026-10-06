# Remote Task Orchestration Bootstrap Requirements

## Purpose

This document defines the first implementation slice that turns June into the durable orchestration service behind a remote ChatGPT/OpenAI bridge.

The immediate target is deliberately narrower than autonomous local inference:

1. a user can initiate work from ChatGPT on a phone;
2. the remote bridge calls June;
3. June durably records and schedules the work;
4. June dispatches implementation work to an external agent backend such as Cursor;
5. the external run continues independently of the originating chat request;
6. June observes and persists its state, logs, artifacts, and terminal result;
7. a later chat can query or cancel that same work by durable identifier.

Local Spark inference, autonomous strategic planning, and full project decomposition are **not prerequisites** for this slice. Strategic reasoning may remain on the ChatGPT/frontier-model side while June provides durable execution.

## Current baseline

As of `main` when this document was written, June already has useful pieces:

- `june run` is a long-running control process.
- `ControlGraph` owns a durable timed queue and a <=100 ms control tick.
- `Scheduler` persists runnable work, schedules, retries, and wake history.
- `TaskRunner` binds June work to MechaHarness templates and can execute a `GraphExecutor` run.
- goals, issues, documents, knowledge, outcomes, policy, templates, and queue state are persisted beneath `JUNE_DATA_DIR`.
- the web console can run beside the control loop and display MechaHarness execution.
- Docker Compose already gives June a persistent `/data` volume.

These are the foundation. This slice should extend them rather than introduce a parallel task-controller service.

## Gaps in the current implementation

### 1. Remote task intake is not a first-class API

The control graph contains a stubbed webapp poller, but June does not expose a small authenticated service contract suitable for MCP/remote bridge calls.

### 2. Task execution is synchronous

`Orchestrator._on_execute_work()` calls `TaskRunner.run()` directly. `wake_goal()` also runs the task synchronously for CLI use.

A coding-agent job may run for minutes or hours. The June control tick must not be occupied for the lifetime of an external agent run.

### 3. Runnable work and durable execution are conflated

`RunnableWork` describes scheduler input, while `TaskOutcome` describes an immediate result. June needs a durable execution/run entity whose lifecycle survives process restarts and remote-client disconnects.

### 4. There is no execution-backend abstraction for external agents

The existing `MechaHarnessClient` realizes MechaHarness graphs, but there is no June-owned interface for dispatching long-running work to Cursor or another implementation backend and polling/cancelling it later.

### 5. There is no durable log/artifact contract

Outcomes link graph run IDs, but remote callers need stable access to task status, bounded log output, artifacts, commits/branches/PR references, and failure information.

### 6. Current JSON persistence needs a concurrency policy

`JsonStore` performs whole-file read/modify/write operations. Once the HTTP/MCP intake path, web console, and control loop can all mutate state, June must prevent lost updates and partial writes. This slice does not require a database migration, but it does require safe serialization/atomicity.

### 7. Restart recovery is not defined for in-flight external work

A long-running June process must be able to restart and reconcile submitted/running external jobs rather than forgetting them or blindly launching duplicates.

## Architectural boundary

The intended bootstrap architecture is:

```text
ChatGPT on phone
      |
      | remote plugin / MCP bridge
      v
June remote task API
      |
      v
June durable task + scheduler state
      |
      v
MechaHarness execution graph
      |
      v
External execution backend
      |
      +---- Cursor agent
      +---- future local worker
      +---- future Spark-backed node
```

The **orchestration itself should remain represented as a MechaHarness graph**. Remote intake creates durable June work; June selects/binds the appropriate graph; a graph node delegates implementation to an execution backend; subsequent graph/control work observes completion and advances state.

June owns concrete task/project state and backend selection. MechaHarness owns reusable graph execution semantics. Cursor is an execution resource, not June's state store.

## Functional requirements

### R1. Durable task identity

June MUST create a stable `task_id` before external execution begins.

A task MUST persist at least:

- task ID;
- optional goal and issue IDs;
- human-readable instruction;
- acceptance criteria;
- repository/workspace reference;
- requested execution backend;
- lifecycle state;
- creation/update timestamps;
- attempt count;
- external backend run ID when available;
- MechaHarness run ID(s);
- result summary;
- error/failure classification;
- artifact references.

Submitting a task MUST return after durable acceptance. It MUST NOT wait for implementation completion.

### R2. Explicit lifecycle

The initial lifecycle MUST distinguish at least:

`accepted -> queued -> dispatching -> running -> succeeded | failed | cancelled | needs_attention`

Recovery MAY temporarily use a `reconciling` state.

State transitions MUST be persisted and observable. Terminal states MUST be idempotent.

### R3. Remote service surface

June MUST expose a transport-neutral application service that can be wrapped by HTTP/MCP without putting protocol details into the orchestrator.

The first surface SHOULD support:

- `submit_task`
- `get_task`
- `list_tasks`
- `cancel_task`
- `get_task_logs`
- `list_task_artifacts`
- `get_status`

The HTTP/MCP adapter MUST call this application service rather than manipulate scheduler/store internals directly.

### R4. Asynchronous dispatch

The control loop MUST remain responsive while external implementation is running.

Dispatching a task MUST produce or record an external run handle and return control to June. Observation of that handle MUST happen through later scheduled work, event delivery, or both.

No long-lived Cursor process may block the <=100 ms control-loop architecture.

### R5. Execution backend interface

June MUST define a backend interface with semantics equivalent to:

- submit(spec) -> external run handle
- status(handle) -> normalized execution state
- logs(handle, cursor/limit) -> bounded log records
- artifacts(handle) -> normalized artifact references
- cancel(handle) -> cancellation result
- reconcile(handle) -> normalized state after June restart

The interface MUST not be named or shaped so narrowly that only Cursor can implement it.

A Cursor backend MAY be the first concrete implementation.

### R6. MechaHarness graph integration

External-agent dispatch MUST be reachable through a reusable MechaHarness graph/node contract rather than bypassing the graph system.

The first implementation graph SHOULD make the phases visible, for example:

```text
validate task
    -> resolve workspace
    -> dispatch external agent
    -> await/observe external run
    -> collect result
    -> verify acceptance criteria
    -> persist outcome
```

Waiting MUST be resumable. A graph must not consume a worker thread merely to sleep until Cursor finishes.

### R7. Scheduling and observation

June MUST schedule observation/reconciliation work for non-terminal external runs.

Polling cadence MUST be configurable and SHOULD back off for long-running tasks.

Duplicate observation jobs MUST be safe. Duplicate dispatch MUST be prevented through persisted dispatch state/idempotency.

### R8. Restart recovery

At startup June MUST identify tasks in non-terminal states and reconcile them with their execution backend.

Recovery MUST NOT automatically create a second external run merely because June cannot immediately determine the first run's state.

Unresolvable jobs MUST move to `needs_attention` with diagnostic information.

### R9. Logs and artifacts

Logs MUST be bounded/paginated so a remote ChatGPT call cannot accidentally return an unbounded process log.

Artifact records SHOULD contain:

- artifact ID/type;
- task ID;
- backend reference;
- local path or remote reference;
- size when known;
- created timestamp;
- optional content type;
- optional Git commit/branch/PR metadata.

June MUST treat artifacts as durable references. The first slice does not require copying every artifact into June's data directory.

### R10. Cancellation

Cancellation MUST be idempotent.

June MUST distinguish:

- cancellation requested;
- backend cancellation confirmed;
- task already terminal;
- backend cannot cancel / state unknown.

A remote client disconnect MUST NOT cancel a task.

### R11. Acceptance criteria and verification

Remote task submission MUST support explicit acceptance criteria.

The execution result MUST preserve enough evidence for a later MechaHarness verification node or frontier-model reviewer to decide whether the criteria were met.

Backend process success alone MUST NOT imply project/task success.

### R12. Safe persistence

All June state writes MUST be safe under concurrent API/control/console access.

For the JSON-store phase this requires, at minimum:

- process-local serialization of mutations;
- atomic write-via-temp-and-rename;
- no unsynchronized read/modify/write sequences for the same collection.

If multi-process writers are required, migrate the affected task/run state to SQLite or another transactional store rather than relying on process-local locking.

### R13. Authentication and network boundary

June SHOULD listen only on the trusted container/LAN interface required by the remote bridge.

The public Internet MUST NOT receive direct access to June's raw API, Docker socket, shell, or worker hosts.

The bridge-facing adapter MUST authenticate requests using the mechanism selected by the OpenAI/plugin deployment.

Secrets MUST come from environment/secret mounts and MUST NOT be persisted in task payloads, logs, graph checkpoints, or Git.

### R14. Policy boundary

Remote submission MUST pass through June's existing policy/autonomy machinery before consequential execution.

The backend abstraction MUST receive an explicit capability/workspace envelope. A task instruction MUST NOT implicitly grant arbitrary access to the host or home network.

### R15. Observability

The existing web console SHOULD show remote tasks and external runs alongside MechaHarness graph activity.

At minimum expose:

- queued/running/terminal task counts;
- current task state;
- backend and external run ID;
- last state transition;
- retry/reconciliation events;
- failure reason;
- linked MechaHarness run IDs.

## Initial API shape

The precise transport is intentionally deferred, but the application-level request can begin approximately as:

```json
{
  "instruction": "Implement the requested change",
  "acceptance_criteria": [
    "tests pass",
    "result is committed to a task branch"
  ],
  "workspace": {
    "repository": "rl337/june",
    "base_ref": "main"
  },
  "backend": "cursor",
  "goal_id": null,
  "issue_id": null,
  "metadata": {}
}
```

The synchronous response should be small:

```json
{
  "task_id": "<durable-id>",
  "state": "accepted"
}
```

Everything after acceptance is asynchronous.

## Proposed implementation slices

### Slice A: durable remote task model

Add the durable task/run records, lifecycle transitions, task service, safe persistence behavior, and tests. No Cursor dependency is required.

Acceptance: a task can be submitted, survives process restart, queried, listed, and cancelled without invoking an external backend.

### Slice B: asynchronous backend contract

Add the execution-backend protocol plus a deterministic fake backend. Integrate dispatch/observe/reconcile jobs with the scheduler/control graph.

Acceptance: fake multi-step jobs continue across control ticks and June restart without blocking or duplicate dispatch.

### Slice C: MechaHarness external-execution graph

Represent dispatch, observation, collection, and verification as graph-visible/resumable work.

Acceptance: the console and checkpoints make external execution state visible, and waiting does not block the control loop.

### Slice D: Cursor backend

Implement the first real backend using the supported Cursor agent mechanism selected for the home deployment.

Acceptance: June can dispatch a repository task, recover its status, collect logs/artifacts, cancel it, and survive a June restart while the Cursor run continues.

### Slice E: remote bridge adapter

Expose the task service through the MCP/HTTP surface required by the OpenAI secure bridge.

Acceptance: from a ChatGPT phone conversation, submit a task to June, disconnect, later query the same task ID, and retrieve its terminal result/artifacts.

### Slice F: home-network deployment

Update the home-network deployment so the OpenAI bridge targets June, with persistent storage and only the minimum required LAN/container connectivity.

Acceptance: no inbound Internet port to June or worker hosts is required.

## Non-goals for this bootstrap

The following are explicitly deferred:

- requiring Spark Station inference;
- making June autonomously choose long-horizon project strategy;
- replacing ChatGPT/Astra strategic reasoning;
- building a general distributed worker scheduler;
- multi-tenant operation;
- arbitrary remote shell access;
- making Cursor state the source of truth;
- migrating all June persistence to a database solely for this feature;
- implementing training or model-selection optimization.

## End-to-end acceptance test

The milestone is complete when this scenario works:

1. June is running continuously on the home infrastructure.
2. From ChatGPT on a phone, the user submits a coding task through the remote bridge.
3. June immediately returns a durable task ID.
4. June records the task and dispatches it through a MechaHarness graph to the Cursor execution backend.
5. The originating phone interaction can end without affecting execution.
6. Cursor continues the implementation on the user's infrastructure.
7. June may restart while the external run is active and subsequently reconciles it without duplicate dispatch.
8. A later ChatGPT conversation queries the durable task ID and receives current state/logs.
9. On completion, June exposes the resulting artifacts and Git references.
10. June records verification evidence separately from backend process success.

This is the first useful bootstrap of June as an orchestrator: **dumb-but-durable before locally intelligent**. Frontier models may continue to decide what work should happen; June guarantees that the work itself has identity, lifecycle, persistence, execution, recovery, and observable results.
