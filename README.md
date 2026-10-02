# June

June is an **application-level orchestrator** and a client of
[MechaHarness](https://github.com/rl337/mechaharness).

It owns persistent goals, scheduling, task-runner policy, documents, knowledge,
issues, and the concrete decision about which reusable MechaHarness graph
templates to instantiate, bind, sequence, and compose.

MechaHarness owns the reusable execution vocabulary: graph templates, linkage,
capability envelopes, checkpoints, verification, and generic eval hooks.

> MechaHarness owns reusable graph grammar and patterns; June writes and stores
> the concrete sentences.

## Status

Scaffold aligned to `docs/inspiration/dev-blog-inspiration.md`. The previous
voice (STT/TTS), Telegram/Discord, todorama/MCP, Switchboard, and in-process
agentic-loop stacks have been removed so this repository can concentrate on
orchestration.

## Layout

```
src/june/
  control/      # June control graph: timed queue, ≤100ms tick, cron/polls
  budget.py     # select MechaHarness BudgetPolicy for child graph runs
  goals/        # persistent goals
  scheduler/    # wake / runnable-work policy
  runner/       # orchestration around MechaHarness runs
  harness/      # MechaHarness client adapters
  documents/    # document index / provenance
  knowledge/    # knowledge graph (June state)
  issues/       # durable work ledger
  policy/       # versioned orchestration / autonomy policy
  orchestrator.py
  cli.py
docs/inspiration/dev-blog-inspiration.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"
# Optional MechaHarness client dependency (BudgetPolicy / GraphExecutor):
# pip install -e ".[harness]"   # mechaharness>=0.2.0
# Web graph console:
# pip install -e ".[harness,console]"
june status
june goal-create "First vertical slice" --criteria "runner writes goal/issue state"
pytest
```

## Control graph entrypoint

`june run` is the single long-lived process. It boots the incubating
`june.control` graph with a timed work queue:

- recurring cron tick + Telegram/Discord/webapp poll nodes (adapters stubbed)
- max tick **100ms**; sleeps `min(100ms, time_until_next_job)` when idle
- due `execute_work` jobs bind/run through the task runner / MechaHarness client

```bash
june --data-dir /tmp/june-data run --max-steps 5
# or until Ctrl-C:
june --data-dir /tmp/june-data run
```

## Web console (container)

The console renders MechaHarness execution as a **scene** with **foreground**
(hard/soft graph nodes that compose the selected node) and **background**
(context, bindings, advisor material as soft round-rect nodes). The active node
glows; recently finished nodes dim as execution moves.

```bash
pip install -e ".[container]"
june serve --demo-graph
# open http://localhost:8080
```

Docker:

```bash
docker compose up --build
```

Environment:

- `JUNE_DATA_DIR` — durable JSON state (default in container: `/data`)
- `JUNE_CONSOLE_DEMO=1` — run a sample graph on startup

Task payloads may set `execute_graph: true` so the task runner drives a live
`GraphExecutor` run (events stream to the console when using `june serve`).

`june serve` also boots a **cron graph** (`june.console.cron`) with **10s** and
**60s** bucket subgraphs whose `june.event_log` nodes append to the left-docked
**Event log** view (MechaHarness lifecycle events + console log lines).

## First vertical slice

```bash
june --data-dir /tmp/june-data goal-create "Ship harness binding" --criteria "marked complete"
# copy goal id from output
june --data-dir /tmp/june-data wake <goal-id> --task "bind template" --complete
june --data-dir /tmp/june-data status
june --data-dir /tmp/june-data dream
```

## Boundary

| June owns | MechaHarness owns |
|---|---|
| Scheduler / wake policy | Bounded, resumable execution |
| Task lifecycle & template selection | GraphTemplate registry, GraphExecutor, LinkageResolver |
| Documents / KG / issues / goals | ContextProvider protocol, checkpoints, traces |
| Product autonomy & Advisor triggers | CapabilityEnvelope, Advisor interface |
| Concrete template bindings | Reusable parameterized templates |

See the inspiration doc for requirements language and the monitoring protocol
for how this boundary evolves.
