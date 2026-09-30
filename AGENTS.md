# Agent guidelines for June

June is an **orchestrator** and a **MechaHarness client**, not a voice stack and
not a second harness.

## Authority

1. `docs/inspiration/dev-blog-inspiration.md` is the refinement target.
2. Legacy code that reappears from history is evidence, not authority. Replace,
   consolidate, or retire when it conflicts with the target split.
3. Do not reintroduce todorama/MCP embedding, Switchboard, STT/TTS services,
   Telegram/Discord voice pipelines, or an in-process think→plan→execute loop
   that duplicates MechaHarness execution.

## Ownership

**June:** scheduler, task runner, documents, knowledge graph, issues, persistent
goals, application policy, provider implementations, concrete graph realization
and template selection/binding/composition.

**MechaHarness:** reusable primitives/protocols, graph semantics/linkage,
capability/context/verification/delegation/advisor interfaces, checkpoints,
generic eval/observability, parameterized `GraphTemplate` definitions.

A MechaHarness template is abstract. June fills soft points (tools, providers,
prompts/skills, model choices, budgets, persistence adapters, goal/issue state,
policies). The resulting executable graph belongs in June even though
MechaHarness validates and runs it.

## Working rules

- Prefer feature branches; keep commits focused on one orchestration concern.
- Incubate graph patterns in June until evidence justifies promotion into
  MechaHarness. Do not premature-generalize.
- Do not open a June PR merely because MechaHarness changed; only when June-side
  consumption/policy requirements change.
- Keep dependencies lean. Inference backends, GPU containers, and messaging
  infrastructure are out of scope for this repository.

## First vertical slice

Persistent goal + scheduler wake → task runner → bind MechaHarness template →
translate results back into goal/issue state.
