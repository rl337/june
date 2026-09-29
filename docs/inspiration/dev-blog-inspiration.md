# Developer Blog Inspiration for June

> Living design notes for June as an application-level orchestrator and client of MechaHarness. External developer material is evidence and inspiration, not specification.

Last reviewed: 2026-09-29

## Purpose and ownership boundary

June is its own orchestrator. It owns the scheduler, task runner, document manager, knowledge graph, issue/work tracker, persistent goals, application policy, provider implementations, and the concrete decision about which reusable MechaHarness graph templates to instantiate, bind, sequence, schedule, and compose.

MechaHarness owns the reusable execution vocabulary beneath June: primitives, injectable protocols, graph execution semantics, linkage/validation, capability envelopes, context-provider interfaces, verification/delegation/advisor mechanisms, durable execution contracts, generic observability/evaluation hooks, and parameterized reusable graph-template definitions such as fan-out/aggregate, verify/repair, independent review, and environment repair.

June MUST NOT duplicate a generic MechaHarness primitive or template merely to own orchestration. Conversely, MechaHarness MUST NOT absorb June-specific scheduling, persistent-goal policy, knowledge/document semantics, issue workflow, or product-specific template composition.

A finding from the source corpus can therefore imply:
- a June-only orchestration requirement;
- a generic MechaHarness requirement consumed by June;
- distinct requirements on both sides of an interface; or
- no architectural change.

## Requirements

### 1. Persistent goals are first-class June state

**Sources**
- Cursor, **Build agents that run automatically** (2026-03-05): https://cursor.com/blog/automations
- Cursor, **Introducing Projects** (2026-09-10): https://cursor.com/blog/projects
- Cursor, **Cloud Agents and Cursor Harness Improvements** (2026-08-19): https://cursor.com/changelog/08-19-26
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code

**Requirements**
- A June goal MUST be able to outlive a chat/session and model context.
- Persistent goals MUST have durable identity, state, completion criteria, trigger/subscription state, priority, provenance, and links to active/completed MechaHarness runs.
- A goal MAY wake from schedules, external events, changed knowledge, issue/task transitions, child completion, or explicit user steering.
- Waking a goal SHOULD create or resume bounded task-runner work rather than simulate an indefinitely open conversation.
- User steering SHOULD be incorporated at safe orchestration boundaries and MUST be recorded as a state transition.

**MechaHarness boundary:** June consumes checkpoint/resume, graph-template and linkage interfaces. Goal persistence and wake policy remain June-owned.

### 2. Scheduler decides when work becomes runnable

**Sources**
- Cursor, **Build agents that run automatically** (2026-03-05): https://cursor.com/blog/automations
- Cursor, **Introducing Projects** (2026-09-10): https://cursor.com/blog/projects

**Requirements**
- June MUST own scheduling and event-trigger policy.
- The scheduler SHOULD unify clock schedules, condition/event wakes, retry/backoff, dependency completion and manually requested execution behind one runnable-work abstraction.
- Scheduling decisions SHOULD be durable and observable, including why a task woke and which goal/issue caused it.
- Duplicate or overlapping wakes SHOULD be coalesced when product semantics allow.
- Scheduling MUST NOT imply execution capability; the task runner still resolves the chosen MechaHarness graph against current providers, permissions and environment.

### 3. Task runner owns orchestration, MechaHarness owns execution

**Sources**
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- Cursor, **What we've learned building cloud agents** (2026-06-02): https://cursor.com/blog/cloud-agent-lessons
- Cursor, **Improved token efficiency for longer agent runs** (2026-09-23): https://cursor.com/blog/improved-token-efficiency

**Requirements**
For each runnable task, June SHOULD:
1. Load the persistent goal/task/issue state.
2. Select an appropriate reusable MechaHarness GraphTemplate or direct graph construction strategy.
3. Bind June tools, ContextProviders, model/provider capabilities, budgets and product policy.
4. Ask MechaHarness to resolve runtime linkage before substantive execution.
5. Execute/checkpoint through MechaHarness.
6. Translate structured results, verification state, failures and side effects back into June task/goal/issue state.
7. Decide whether to complete, reschedule, retry, create follow-up work, request user input, or escalate.

June owns steps 1, 2, 3, 6 and 7 as orchestration policy. MechaHarness owns generic semantics for graph instantiation/execution, linkage, envelopes, verification and checkpoints.

### 4. June owns concrete template composition, not generic template definitions

**Sources**
- Claude, **Introducing dynamic workflows in Claude Code** (2026-05-28): https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude, **A harness for every task: dynamic workflows in Claude Code** (2026-06-02): https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code

**Requirements**
- June SHOULD prefer reusable MechaHarness GraphTemplates for generally useful patterns.
- June MUST own the product decision about which templates are selected, parameterized, sequenced and nested for a goal.
- June-specific workflows MAY be represented as configuration/composition over reusable templates.
- A June-specific composition SHOULD migrate into MechaHarness only when it becomes a genuinely reusable parameterized execution pattern independent of June semantics.
- June SHOULD NOT fork generic templates merely to adjust application policy that can be expressed through parameters/providers.

This is the central seam: **MechaHarness owns reusable graph grammar and patterns; June writes the sentences.**

### 5. Document manager is a durable information substrate

**Sources**
- Cursor, **Dynamic context discovery** (2026-01-06): https://cursor.com/blog/dynamic-context-discovery
- Claude, **The new rules of context engineering for Claude 5 generation models** (2026-07-24): https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models

**Requirements**
- June MUST own document lifecycle, identity, metadata, versioning and product-level access semantics.
- Documents SHOULD be discoverable through lightweight indices/descriptions before full payload retrieval.
- Retrieval MUST preserve provenance and version identity.
- June SHOULD expose documents to MechaHarness through ContextProvider-style adapters rather than injecting an undifferentiated corpus.
- Large document payloads SHOULD be loaded just in time and only for the execution scope that needs them.
- A task SHOULD be able to persist references to documents without copying their contents into durable graph state.

### 6. Knowledge graph is June state, not harness context

**Sources**
- Cursor, **Dynamic context discovery** (2026-01-06): https://cursor.com/blog/dynamic-context-discovery
- Claude, **The new rules of context engineering for Claude 5 generation models** (2026-07-24): https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models

**Requirements**
- June MUST own knowledge entities, relations, provenance, confidence, temporal validity and update policy.
- The KG SHOULD expose discovery/query surfaces separately from materialized context payloads.
- MechaHarness executions SHOULD receive scoped KG results through a provider contract; they SHOULD NOT receive the entire remembered world by default.
- New facts proposed by model executions SHOULD carry provenance and SHOULD pass June-defined promotion/validation policy before becoming durable authoritative knowledge.
- June SHOULD distinguish event/history records, retrieved evidence, inferred facts and stable knowledge rather than collapsing them into one memory bucket.

### 7. Issue tracker is the durable work ledger

**Sources**
- Cursor, **Introducing Projects** (2026-09-10): https://cursor.com/blog/projects
- Claude, **Running an AI-native engineering org** (2026-06-03): https://claude.com/blog/running-an-ai-native-engineering-org
- Claude, **How Anthropic runs large-scale code migrations with Claude Code** (2026-07-16): https://claude.com/blog/ai-code-migration

**Requirements**
- June MUST own durable issues/tasks representing actionable work.
- Issues SHOULD support status, priority, dependencies/blockers, parent/subtask relationships, provenance, current owner/worker, history and links to goals/documents/knowledge/execution runs.
- A MechaHarness run SHOULD be treated as execution of work, not as the canonical work record.
- Structured run failures MAY create/update issues according to June policy.
- Repeated failure classes SHOULD be linkable across issues/runs so June can identify process-level problems.

### 8. Orchestration policy is revisable product policy

**Sources**
- Claude, **Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence** (2026-04-02): https://claude.com/blog/harnessing-claudes-intelligence
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness
- Cursor, **Improved token efficiency for longer agent runs** (2026-09-23): https://cursor.com/blog/improved-token-efficiency

**Requirements**
- June orchestration rules SHOULD be explicit/versioned rather than dispersed through prompts.
- Each substantial policy SHOULD identify the product failure mode it addresses.
- June SHOULD be able to compare policy variants against retained tasks/traces.
- Model/runtime improvements SHOULD trigger retirement tests for orchestration scaffolding.
- A policy that no longer improves June-level outcomes SHOULD be removable without modifying MechaHarness primitives.

### 9. Autonomy decisions combine June consequence policy with MechaHarness enforcement

**Sources**
- Cursor, **Governing agent autonomy with Auto-review** (2026-06-11): https://cursor.com/blog/agent-autonomy-auto-review
- Cursor, **Implementing a secure sandbox for local agents** (2026-02-18): https://cursor.com/blog/agent-sandboxing
- Claude, **How Anthropic secures its AI-native software development lifecycle** (2026-07-21): https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle

**Requirements**
- June SHOULD classify product actions by consequence and user intent.
- June SHOULD decide when work requires approval, stronger verification, restricted capability, postponement or denial.
- MechaHarness MUST remain responsible for mechanically enforcing the capability envelope/grants supplied for a run.
- June MUST NOT rely on prompts alone to implement hard security boundaries.
- Approval frequency, reversals, denied actions and unnecessary interruptions SHOULD be observable as product metrics.

### 10. Advisor usage is orchestrated by June but executed through a generic interface

**Sources**
- Claude Code Docs, **Escalate hard decisions with the advisor tool** (reviewed 2026-09-29): https://code.claude.com/docs/en/advisor

**Requirements**
- June MAY request sparse Advisor consultation at high-value decision boundaries.
- June MAY contribute product-level triggers such as consequential goal mutation, repeated task failure, conflicting knowledge, expensive external side effects or high-consequence completion.
- June SHOULD choose the context/evidence references appropriate to the product decision.
- The Advisor interface, non-binding guidance semantics, capability routing, budget enforcement and observability SHOULD remain generic MechaHarness facilities.
- June SHOULD record whether advice changed orchestration and whether the eventual outcome improved.

### 11. Sleep/dreaming is a June self-improvement workflow

**Sources**
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness
- Claude, **How Anthropic runs large-scale code migrations with Claude Code** (2026-07-16): https://claude.com/blog/ai-code-migration

**Requirements**
- June SHOULD mine durable traces, issues, task outcomes and knowledge changes for recurring failure/opportunity classes during offline/scheduled maintenance.
- Dreaming MAY propose new orchestration policies, retrieval rules, gotchas, template compositions, model-routing preferences or candidate training/evaluation data.
- Proposed changes MUST remain proposals until evaluated against retained cases and relevant safety/correctness constraints.
- Generic improvements to MechaHarness SHOULD be proposed across the repository boundary rather than silently implemented as June-only forks.
- June SHOULD preserve provenance from observed failure → hypothesis → experiment → promoted/retired change.

### 12. June-level outcome measurement spans multiple MechaHarness runs

**Sources**
- Cursor, **How we compare model quality in Cursor** (2026-03-11): https://cursor.com/blog/cursorbench
- Cursor, **Continually improving our agent harness** (2026-04-30): https://cursor.com/blog/continually-improving-agent-harness

**Requirements**
- June MUST be able to evaluate goal/task success independently of whether an individual graph run succeeded.
- Product evaluation SHOULD include correctness, goal completion, elapsed wall time, model/compute use, retries, coordination churn, user interruptions, approval burden and persistent-state quality where relevant.
- June SHOULD correlate these outcomes with MechaHarness graph/harness versions and orchestration-policy versions.
- A successful graph that advances the wrong goal state MUST be representable as an orchestration failure.

## Cross-repository interface ledger

| June concern | June owns | Expected MechaHarness surface |
|---|---|---|
| Scheduler | wake/event/retry policy | bounded/resumable execution entry points |
| Task runner | task lifecycle and graph selection | GraphTemplate registry, GraphExecutor, LinkageResolver |
| Documents | lifecycle/index/version/access semantics | ContextProvider protocol |
| Knowledge graph | graph schema, provenance, promotion/query policy | scoped ContextProvider protocol |
| Issue tracker | durable work model and transitions | structured execution/failure/trace outputs |
| Persistent goals | identity, triggers, completion policy | checkpoints, OutcomeContract-compatible signals |
| Concrete orchestration | template selection/binding/composition | reusable parameterized GraphTemplates |
| Autonomy | product consequence/approval policy | grants, CapabilityEnvelope, verification primitives |
| Advisor use | product triggers and evidence selection | Advisor / AdvisorPolicy |
| Dreaming | mining, hypotheses, promotion workflow | traces, HarnessExperiment/eval hooks |

## Monitoring protocol

When refreshing this document:
1. Read this file and the MechaHarness companion inspiration document from each repository's current `main`.
2. Enumerate new Claude/Anthropic developer-blog entries, relevant Claude Code documentation, and Cursor developer-blog entries since the latest represented review.
3. Classify every material finding as June-only, MechaHarness-only, both with distinct interface requirements, or neither.
4. Do not duplicate a generic MechaHarness requirement here. State the June-side consumption/policy requirement and cross-repository interface instead.
5. Add only net-new requirements, meaningful refinements, contradictions, retirements, or evidence that materially changes priority.
6. Every changed inspiration-derived requirement MUST name source title, date when available, and canonical URL.
7. Prefer testable MUST/SHOULD/MAY language.
8. If June has no material change, create no June branch/PR merely because MechaHarness changed.
9. If June changes, update only this file on a branch from current `main`, verify a non-empty diff, and open a draft PR whose body explains why the change belongs in June.
10. Cross-reference a paired MechaHarness change when the finding modifies the interface boundary.

## Source ledger: Claude / Anthropic

Reviewed through 2026-09-29:
- **Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence** — 2026-04-02 — https://claude.com/blog/harnessing-claudes-intelligence
- **How and when to use subagents in Claude Code** — 2026-04-07 — https://claude.com/blog/subagents-in-claude-code
- **Seeing like an agent: how we design tools in Claude Code** — 2026-04-10 — https://claude.com/blog/seeing-like-an-agent
- **Introducing dynamic workflows in Claude Code** — 2026-05-28 — https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- **A harness for every task: dynamic workflows in Claude Code** — 2026-06-02 — https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- **Lessons from building Claude Code: How we use skills** — 2026-06-03 — https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- **Running an AI-native engineering org** — 2026-06-03 — https://claude.com/blog/running-an-ai-native-engineering-org
- **Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents** — 2026-06-18 — https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
- **Loop engineering: Getting started with loops** — 2026-06-30 — https://claude.com/blog/getting-started-with-loops
- **How Anthropic runs large-scale code migrations with Claude Code** — 2026-07-16 — https://claude.com/blog/ai-code-migration
- **How Anthropic secures its AI-native software development lifecycle** — 2026-07-21 — https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle
- **How Datadog built a "universal machine tool" for Claude Code** — 2026-07-21 — https://claude.com/blog/how-datadog-built-a-universal-machine-tool-for-claude-code
- **Building verification loops in Claude Code with skills** — 2026-07-22 — https://claude.com/blog/building-verification-loops-in-claude-code-with-skills
- **The new rules of context engineering for Claude 5 generation models** — 2026-07-24 — https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models
- **Agentic coding is straining CI. Here's how we scaled test impact analysis at Anthropic** — 2026-09-14 — https://claude.com/blog/agentic-coding-is-straining-ci-heres-how-we-scaled-test-impact-analysis-at-anthropic
- **Coding sessions are longer and use more context. Claude Opus 5.5 is built with that in mind.** — 2026-09-24 — https://claude.com/blog/claude-opus-5-5-built-for-coding-sessions-that-use-more-context
- **Escalate hard decisions with the advisor tool** — Claude Code Docs, reviewed 2026-09-29 — https://code.claude.com/docs/en/advisor

Watch source: https://claude.com/blog-category/claude-code

## Source ledger: Cursor

Reviewed through 2026-09-29:
- **Dynamic context discovery** — 2026-01-06 — https://cursor.com/blog/dynamic-context-discovery
- **Subagents, Skills, and Image Generation** — 2026-01-22 — https://cursor.com/changelog/2-4
- **Implementing a secure sandbox for local agents** — 2026-02-18 — https://cursor.com/blog/agent-sandboxing
- **Cursor agents can now control their own computers** — 2026-02-24 — https://cursor.com/blog/agent-computer-use
- **Build agents that run automatically** — 2026-03-05 — https://cursor.com/blog/automations
- **How we compare model quality in Cursor** — 2026-03-11 — https://cursor.com/blog/cursorbench
- **Continually improving our agent harness** — 2026-04-30 — https://cursor.com/blog/continually-improving-agent-harness
- **What we've learned building cloud agents** — 2026-06-02 — https://cursor.com/blog/cloud-agent-lessons
- **Governing agent autonomy with Auto-review** — 2026-06-11 — https://cursor.com/blog/agent-autonomy-auto-review
- **Cloud Agents and Cursor Harness Improvements** — 2026-08-19 — https://cursor.com/changelog/08-19-26
- **Introducing Projects** — 2026-09-10 — https://cursor.com/blog/projects
- **Improved token efficiency for longer agent runs** — 2026-09-23 — https://cursor.com/blog/improved-token-efficiency

Watch source: https://cursor.com/blog

## Provenance note

This bootstrap intentionally establishes June's side of the MechaHarness/June boundary. Future changes should be incremental. When an article affects both systems, the two documents should describe different sides of the same interface rather than echoing the same requirement.
