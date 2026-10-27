# Cursor Agent SDK: knowledge-to-change review for June

**Reviewed:** 2026-10-27  
**Classification:** June only (application-level workflow); no new MechaHarness primitive proposed  
**Source:** Rustam Lalkaka, Cursor, [Introducing the Agent SDK](https://cursor.com/blog/agent-sdk), published 2026-10-20. The concrete example is the team's `kb-reviewer` in the article's “Build around your workflow” section.

## Source observation, not a dependency recommendation

Cursor's Agent SDK packages event-driven managed agents as version-controlled code, with tools, policies, subagents, evaluations, event replay, and deployment options. Cursor describes an internal `kb-reviewer` built in about a day: it checks each PR against recorded lessons, identifies contradictions, cites the underlying knowledge entry, and asks engineers to reconcile the mismatch.

**The useful product surface is not the SDK.** It is a change-review obligation that makes a durable knowledge base actionable at code-change boundaries. June can express this with its existing scheduler, knowledge/documents, issue ledger, and MechaHarness graph integration; Cursor remains an optional execution backend.

## Current repository fit (checked 2026-10-27)

- `docs/inspiration/dev-blog-inspiration.md` §§2, 3, 6–9, 13 already assigns event wakes, durable knowledge/provenance, issue tracking, concrete graph composition, and outcome measurement to June.
- `src/june/knowledge/__init__.py` has `KnowledgeFact` with authority, confidence, validity, and provenance; it can query scoped authoritative facts. This is **not** yet a PR/change consistency review service.
- `src/june/issues/__init__.py` supports issues linked to knowledge IDs and run IDs, so actionable findings need no second issue tracker.
- `docs/requirements/remote-task-orchestration.md` defines durable remote work, asynchronous execution, acceptance verification, and backend-agnostic artifacts. It does not define a knowledge-backed PR review.
- MechaHarness already specifies `ContextProvider` scoping, verification phases, independent review, structured outcomes, durable resume, and replay/testing patterns in `docs/inspiration/dev-blog-inspiration.md` and related requirements. **Do not add a new generic MechaHarness requirement** for this one host workflow.
- June PRs #21 (personal-agent reliability) and #22 (always-on goals) address general safety/standing work; this proposal is narrower: comparing a concrete code change against scoped, versioned authoritative lessons.

## Proposed June requirement: JUNE-KCR-01

June SHOULD support a named, June-incubated `june.knowledge_change_review` workflow that:

1. **Receives** a change event (initially a GitHub PR opened/synchronised/reopened event or an explicit review request) with repository identity, base/head commit SHAs, diff/changed-file references, and delivery ID.
2. **Resolves** repository/project scope and loads relevant *authoritative, currently valid* knowledge facts and documents through June's existing knowledge/document services. Retrieval MUST respect access policy and carry knowledge IDs, versions, and provenance. Absence of relevant knowledge is a valid no-finding result, not permission to hallucinate rules.
3. **Runs** a bounded MechaHarness verification/review graph against the changed content and scoped evidence. Prefer deterministic checks for explicit invariants; model-based semantic comparison may propose contradictions but MUST not silently promote inferred facts to authoritative policy.
4. **Returns** a structured `KnowledgeChangeReview` with event ID, commit SHA, knowledge snapshot/version IDs, findings, evidence refs, confidence/uncertainty, and outcome `clear | findings | inconclusive | failed`. Each finding MUST cite a specific source knowledge/document version and relevant changed file/hunk. Distinguish contradiction from stale or superseded guidance.
5. **Publishes** a review artifact and optionally a comment/check result through an explicitly authorized adapter. Create or update a June issue only when June's policy says a finding requires follow-up. No automatic approval, rejection, merge, or code mutation is implied by this requirement.
6. **Persists** trigger lineage, policy/recipe version, knowledge snapshot, run ID, and findings so a later reviewer can explain and reproduce the result. Duplicate deliveries and retries MUST NOT create duplicate comments or issues; a new head SHA is a new review version.

**Scope boundary:** June owns event subscriptions, knowledge authority and validity, repository mappings, finding severity, publication, and escalation. MechaHarness owns the generic review execution, scoped context and outcome machinery. Do not introduce a Cursor SDK runtime requirement or a MechaHarness `kb-reviewer` special case.

## Minimal executable user-story tests

| Story | Given | Expected |
| --- | --- | --- |
| KCR-01 contradiction | An authoritative, in-scope lesson forbids a pattern introduced by a PR | `findings` with lesson ID/version and changed-file/hunk citation; no autonomous merge action |
| KCR-02 compatible | A change does not conflict with any relevant valid lessons | `clear`, preserving checked commit and knowledge snapshot |
| KCR-03 stale lesson | An old lesson has expired or been superseded | No active contradiction from the obsolete lesson; review may report stale evidence separately |
| KCR-04 scope/ACL | A lesson belongs to another project or is inaccessible | It is not included in model context or exposed in findings |
| KCR-05 uncertain semantic match | A model suspects conflict without grounded evidence | `inconclusive` or a clearly uncertain finding; never an invented citation |
| KCR-06 redelivery/rebase | Same event is delivered twice, then PR head changes | Same head produces one logical review/publication; new head produces a distinct version |
| KCR-07 replay | Recorded event, diff and knowledge snapshot are replayed with the same recipe/policy | Stable structured result for deterministic portions; model variance measured rather than claimed deterministic |
| KCR-08 review publication | Adapter lacks permission or publishing fails | Review remains durable, publication status reflects failure, no unauthorized side effect |

Start with an offline fixture containing one PR diff and two versioned lessons. Then wire the event adapter, scoped retrieval, MechaHarness recipe, and publication adapter in that order. Measure false positives, unsupported citations, stale-knowledge alerts, review latency/cost, and engineer-confirmed usefulness before enabling broad automatic triggers.

## Relationship to other work

This is **not** the standing component telemetry watcher from the previous Anthropic source-control review. That watcher surveys operational evidence over time; this workflow reacts to a code change and checks consistency against recorded knowledge. They can share June's scheduler and issue ledger without sharing a bespoke agent runtime.

## Attribution

- Primary source: [Cursor, “Introducing the Agent SDK” (2026-10-20)](https://cursor.com/blog/agent-sdk). Specifically the description of `kb-reviewer`, event-driven agents, source-cited findings, evals and replay.
- Repository grounding: [June developer-blog inspiration](../inspiration/dev-blog-inspiration.md), [June remote task orchestration](../requirements/remote-task-orchestration.md), [MechaHarness developer-blog inspiration](https://github.com/rl337/mechaharness/blob/main/docs/inspiration/dev-blog-inspiration.md).
