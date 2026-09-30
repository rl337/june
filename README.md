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
  goals/        # persistent goals
  scheduler/    # wake / runnable-work policy
  runner/       # orchestration around MechaHarness runs
  harness/      # MechaHarness client adapters
  documents/    # document index / provenance
  knowledge/    # knowledge graph (June state)
  issues/       # durable work ledger
  policy/       # versioned orchestration / autonomy policy
  cli.py
docs/inspiration/dev-blog-inspiration.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# Install MechaHarness from its repo if not published yet:
# pip install -e ../mechaharness
june status
pytest
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
