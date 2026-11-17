# Trouble: proactive intervention and adaptive workflow verification

> Candidate acceptance stories, not normative requirements or implemented features. Reviewed 2026-11-17 against [June main @ 8e715ac](https://github.com/rl337/june/tree/8e715ac85e11b0a81596dc8765058970929da1e6). External benchmark results are source-reported and have not been reproduced.

## Source dossier and mechanisms

### TR-20261117-INITIATIVE (persistent agents and developer workflows; application-specific feature)

Trouble [Nov 14 post 2121737833409110129](https://rl337.org/trouble/posts/2121737833409110129.html); original [Agent Initiative Benchmark](https://github.com/deepnote/agent-initiative-benchmark/tree/4d66be81b4fc44ba0fa0fc48320be3ebfa717e3), [results and resume contract](https://github.com/deepnote/agent-initiative-benchmark/blob/4d66be81b4fc44ba0fa0fc48320be3ebfa717e3/docs/results.md), [study](https://deepnote.com/research/benchmark), [PageMantle synthetic dataset](https://huggingface.co/datasets/deepnote/pagemantle-company-dataset).

A proactive agent starts from ambiguous synthetic business conversations and can investigate 11 linked services: Slack, Linear, Notion, HubSpot, Stripe, Calendar, PostHog, Google Analytics, Search Console, BigQuery and Snowflake. Eight task types: find, explain, analyze, verify, diagnose, decide, coordinate and guard. Critical decision is **whether to speak at all**, not just drafting a plausible alert. Correct silence occurs when existing work resolves the issue, evidence is insufficient or recipient/authority is wrong. Judge models assess intervention, evidence, message quality and audience; sources and both verdict explanations remain inspectable. The benchmark describes 12 models × 50 tasks; public repository ships 8 runnable examples. Pinned inputs/settings and attempts let compatible runs resume; infrastructure errors remain unscored, not zero. This is a source benchmark, not evidence of real June success.

### TR-20261117-WORKFLOWARENA (orchestration and evaluation; reusable evaluation recipe)

Trouble [Nov 10 post 2120254716600852701](https://rl337.org/trouble/posts/2120254716600852701.html), repeated [Nov 16 2122245019205808479](https://rl337.org/trouble/posts/2122245019205808479.html); primary [paper](https://arxiv.org/abs/2611.12856), [repository @ 1232e95](https://github.com/Einsia/WorkflowArena/tree/1232e957728e45adb3d2e7d2c45768950cd68333), [workflow script contract](https://github.com/Einsia/WorkflowArena/blob/1232e957728e45adb3d2e7d2c45768950cd68333/harness/prompts/workflow-definition.md), [evaluation specification](https://github.com/Einsia/WorkflowArena/blob/1232e957728e45adb3d2e7d2c45768950cd68333/evaluation/README.md), [manifest](https://github.com/Einsia/WorkflowArena/blob/1232e957728e45adb3d2e7d2c45768950cd68333/benchmark/manifest.jsonl).

Benchmark has 145 long-horizon tasks, eight domains and 17 forms, shared 14,400-second task budget. Full resolution requires *all* critical acceptance checks; separate continuous score recognises partial progress. Reported best overall resolved rate 36.95% and best continuous score 80.21 derive from distinct model-effort runs and **equal domain weighting**, not a raw 145-task pass ratio. A workflow script chooses fresh worker calls, parallel and pipelined operations, dependencies, bounded iterative repairs and optional reviewers. Worker null/throw is failure data, not implicit approval. Returning a script object is not itself successful task verification. Workflow transfer on 32 difficult tasks illustrates that the shape of delegation is independently variable from the model; improvements are not universal.

## June baseline and coverage verdict

- [docs/requirements/remote-task-orchestration.md](https://github.com/rl337/june/blob/8e715ac85e11b0a81596dc8765058970929da1e6/docs/requirements/remote-task-orchestration.md) already requires durable IDs, independent execution, backend dispatch, evidence, restart reconciliation and task authority. Extend it, not a second orchestrator.
- [src/june/tasks/dispatch.py](https://github.com/rl337/june/blob/8e715ac85e11b0a81596dc8765058970929da1e6/src/june/tasks/dispatch.py) constructs a fixed validate → resolve → coding job → collect → verify acceptance → persist graph. This is a valid first recipe, not evidence that orchestration policy alternatives are currently evaluated.
- [src/june/orchestrator.py](https://github.com/rl337/june/blob/8e715ac85e11b0a81596dc8765058970929da1e6/src/june/orchestrator.py) contains goals, policy, scheduler, task execution, outcome store and knowledge graph. Targeted code searches found no dedicated proactive silence/intervention story. This is a **candidate missing acceptance** subject to full fixture audit, not proof of absence throughout the repo.
- [imagegen/acceptance.py](https://github.com/rl337/june/blob/main/src/june/recipes/imagegen/acceptance.py) has independent media acceptance, but no claim of a generic proactive judge.
- Open docs PRs: [June #26](https://github.com/rl337/june/pull/26) inherited-work verification, [#27](https://github.com/rl337/june/pull/27) memory authority, [#28](https://github.com/rl337/june/pull/28) competing resource claims. Reuse their authority, replay and idempotency requirements.
- Ownership: MechaHarness manages generic graph semantics and evidence interfaces. June selects and evaluates application-level actions, schedules, recipients and concrete workflow policy.

## Candidate JN-INIT-01: evidence-grounded intervention with first-class silence

**Persona and rationale:** As a user of a persistent June assistant, I want the agent to investigate and notify me only when it has fresh, relevant, authorized evidence that something needs attention; silence should be an explicit, reviewable correct decision when action is unwarranted.

**Behavioural contract:** Record one of intervene / defer / already_handled / insufficient_evidence / not_authorized, linked to source evidence, intended audience, policy version, decision time and effect status. A refusal to notify must remain observable in the outcome ledger without leaking restricted source content.

**Acceptance scenarios (all proposed, NOT run):**
1. Synthetic feature-growth conversation plus analytics with high repeated failures from a single customer and unresolved support issue: verify cross-service evidence, appropriate authorized audience and message specificity; popularity alone fails.
2. Resolved support issue or existing timely notification: positive silence outcome, zero new messages/duplicate issues, reason recorded.
3. Conflicting, stale, insufficient or inaccessible data: defer/unknown, no confident fabricated alert; evidence freshness and missing inputs explicit.
4. A retrieved note falsely authorizing a channel: deny delivery under current source authority; compare existing memory safety requirements rather than duplicating them.
5. Duplicate scheduled ticks and restart: exactly one externally observable effect under idempotent backend support, repeated observations deduplicated; newer contradictory evidence permits reconsideration.
6. Positive control: genuinely unresolved urgent problem with valid explicit permission triggers helpful action. False-veto or permanent non-intervention is failure.
7. Frozen evaluation split: assess groundedness, true-positive intervention, false-intervention rate, recipient appropriateness, authority and resource use. Judge failure is unscored rather than correct silence. Keep task inputs, model, judge, budget and attempt trace pinned.

**Implementation alternatives:** June policy/decision record + existing scheduler/outcome ledger; parameterized MechaHarness judgement nodes; synthetic service fixtures, no real Slack credentials or live outreach. Open questions: when is human approval necessary, who can see evidence, how to rate non-intervention against over-cautious models, and how to interpret prior problem resolution.

## Candidate JN-WF-01: versioned dynamic workflow comparison with independent verification

**Persona and rationale:** As June's operator, I want to compare fixed and adaptive recipes against the same requirements and budget so I can discover when delegation improves completion without accidentally losing constraints or hiding agent failures.

**Behavioural contract:** Maintain a frozen task manifest, required deliverables, critical acceptance checks and workflow version, and report task completion, partial progress, policy failures and per-worker evidence independently. Use existing MechaHarness graph execution; June owns operational recipe selection.

**Acceptance scenarios (all proposed, NOT run):**
1. Run a fixed linear and an adaptive branch/parallel recipe on the same frozen mock task with equivalent model, backend and budget. Trace workflow identity and independent criteria; don't attribute gains to a changed model.
2. Partial success with one missing required deliverable: show incomplete/partial, never full pass even if average score is high.
3. One failed worker amid successful siblings: preserve failure and dependency semantics, retry only failed branch where permitted, cap retry/budget and record all attempts.
4. Worker returns null or review returns a structured failed verdict: never treat a returned object or null as automatic acceptance; independent verifier checks artifacts.
5. Crash/restart across a backend submission: preserve task ID, graph/workflow version, checkpoint, accepted outputs and pending work; avoid duplicate external effects per existing R7/R8 and June resource-claim policy.
6. Same model across alternative workflow structures: report per-task acceptance, verified partial progress, latency/token/cost and unknown outcomes; a changed verifier is a different experiment.
7. Unauthorized artifact edit or invisible skipped verification must fail appropriate critical check even when final output appears acceptable.

**Technical alternatives/risks:** First compare two predeclared templates; introduce runtime adaptive additions only after MechaHarness stable checkpoint contract is verified. Avoid importing untrusted executable JavaScript workflow directly. Source domain-specific thresholds are examples, not universal standards. Implementation agent should locate current June story/requirement conventions and tests before adopting, and may conclude current MechaHarness features already cover parts.

## Adoption notes

Both are candidate documentation only. No native fixtures or production features have been added. Upstream benchmark tasks and evaluation judges were not run locally. Recheck current default branch, especially June's existing task tests and the three open docs PRs, before promoting normative story acceptance.