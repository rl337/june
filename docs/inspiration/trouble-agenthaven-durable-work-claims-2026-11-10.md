# Trouble inspiration: durable, resource-scoped work claims for parallel coding agents

**Research date:** 2026-11-10. **Status:** candidate June requirements, **not** adopted normative policy or implementation. **Stable capability:** TR-20261110-AGENT-CLAIMS. **Classification:** agent orchestration/execution control + persistent-agent developer workflows; reusable orchestration improvement / acceptance-test proposal. **Proposed owner:** June. Generic graph constraints, effect admission, policy/authorization envelopes and checkpoints stay in MechaHarness.

## Discovery, upstream mechanism, and source map

- Trouble public discovery: https://rl337.org/trouble/posts/2119423357770748378.html (post ID `2119423357770748378`, 2026-11-08).
- Original author/project: https://github.com/laaielichter/AgentHaven ; primary [workboard documentation](https://github.com/laaielichter/AgentHaven/blob/main/README.md).
- Concrete implementation: [`src/store.js`](https://github.com/laaielichter/AgentHaven/blob/main/src/store.js), especially `withLock`, `reap`, `claimInLock`, `claimTask`, `blocker`, `nextTask`, and `assertCanFinish`; [`src/checks.js`](https://github.com/laaielichter/AgentHaven/blob/main/src/checks.js) for commit-addressed check receipts; [`src/workboard.js`](https://github.com/laaielichter/AgentHaven/blob/main/src/workboard.js) for `alive`, `next`, `claim`, `handoff`, and `scope`; [board tests](https://github.com/laaielichter/AgentHaven/blob/main/test/board.test.js) and [security tests](https://github.com/laaielichter/AgentHaven/blob/main/test/guard.test.js).
- Research source is a live, evolving upstream default branch; pin its commit before lifting code or interpreting a later test result. These descriptions are observations from source inspection, not proof that all advertised behaviours work.

**Upstream mechanism:** AgentHaven stores tasks with status, dependencies, skills, claimed files, assignee and expiring lease. Its `nextTask` filters out not-ready work (dependency, skill and file claims), then chooses by priority/creation time and can claim atomically. `claimTask` goes through the same guarded mutation. `withLock` protects a workspace JSON file using a short-lived filesystem lock and atomic file replacement. `alive` renews presence/leases; `reap` releases stale claims. Repeated expiry, review rejection or handoff can trigger escalation. Its external check runner captures a receipt associated with the actual git commit SHA, tests, dirty-state and command results. Human-configured checks and independent reviewers are more credible than an agent declaring its own tests passed. These are useful *design examples*, not a recommendation to copy its file-lock storage or fixed 30-minute TTL into June.

The distinct insight is **parallel work must reserve conflicting resources durably, not only deduplicate repeated starts of the same job**. A branch/worktree is isolation of changes, not proof that two agents will not modify incompatible assumptions. Claims are scheduling and conflict hints; MechaHarness-granted tool authority is a separate security boundary. Claims must never confer access.

## Audit of June as of 2026-11-10

| Current surface | Verified coverage | Specific limitation / no-duplication decision |
| --- | --- | --- |
| [`docs/requirements/remote-task-orchestration.md`](https://github.com/rl337/june/blob/main/docs/requirements/remote-task-orchestration.md), R1–R12 | Durable task ID, repository/workspace field, async external runs, backend reconcile, acceptance evidence, cancellation, JSON concurrency policy | Does not specify workspace/path *collision-aware admission*, lease ownership, heartbeat fencing or cross-task mutation conflict. Extend, do not re-create task execution |
| [`src/june/tasks/__init__.py`](https://github.com/rl337/june/blob/main/src/june/tasks/__init__.py) | `RemoteTask` persists workspace, backend, attempt, lifecycle, external handle, artifacts and transitions | Inspected dataclass has no explicit claim owner, lease/epoch, resource-claim set or conflict report |
| [`src/june/tasks/worker.py`](https://github.com/rl337/june/blob/main/src/june/tasks/worker.py) | `BackgroundGraphWorker._inflight` prevents a duplicate *process-local key* | Does not coordinate different tasks/backends or outlive restart |
| [`src/june/scheduler/__init__.py`](https://github.com/rl337/june/blob/main/src/june/scheduler/__init__.py) | Durable runnable queue, dependency wake, coalescing by goal/issue/reason | No repo/file-claim arbitration in inspected queue |
| [`src/june/tasks/dispatch.py`](https://github.com/rl337/june/blob/main/src/june/tasks/dispatch.py) | Existing `validate_task → resolve_workspace → coding_job → collect_result → verify_acceptance → persist_outcome` graph and MechaHarness effectful submission | New admission should be attached to existing phases; do **not** create a second graph or a competing job runner |
| [`AGENTS.md`](https://github.com/rl337/june/blob/main/AGENTS.md) | Explicit ownership boundary with MechaHarness | Resource scheduling/worker coordination belongs here; generic graph effects do not |

Search of the current default branch found no June `claimTask` equivalent, workspace-lease specification or direct worktree admission contract. That is *search-and-file-inspection evidence*, not an exhaustive proof of absence. Prior proposals in [June PR #26](https://github.com/rl337/june/pull/26) and [PR #27](https://github.com/rl337/june/pull/27) cover inherited-work verification and memory authority, respectively; avoid duplicating them. R7/R8 already cover retry/recovery. Acceptance story should focus narrowly on **cross-task conflicting resource admission**.

## Proposed user story JN-CLAIM-01: Coordinate competing repository tasks with durable resource claims

**Persona:** June operator maintaining several coding agents, or a human using June to delegate simultaneous changes.

**Narrative:** As an operator, I want June to hold and resolve temporary claims on the repository files or other explicitly declared work resources that a coding task plans to modify, so two agents cannot both be admitted to conflicting work without a visible decision, while healthy independent tasks continue concurrently. If a worker dies or loses connectivity, claims must be reconciled and eventually reclaimed without silently launching another copy of an external effect.

**Motivation / failure to reproduce:** Task A and task B are different UUIDs and therefore evade the `BackgroundGraphWorker` duplicate-key guard. Both target `src/app/config.py` through different external backends. Without resource-level arbitration they may each pass task validation, diverge in independent worktrees, and present incompatible results. Conversely, work in `src/app/config.py` and `docs/help.md` should not be serialized merely because both share one repository.

**Acceptance contract (candidate, to be translated into June's native requirement/test suite when adopted):**

1. **Admit non-overlapping tasks:** Given two queued tasks in the same repository with disjoint canonical claimed resource sets and satisfied dependencies, when two workers request admission, both receive independent durable grant identifiers and execute. A third task that conflicts with one receives a typed `waiting_on_resource`/equivalent reason, current claimant reference and policy-safe recheck point; it is not treated as failed.
2. **Only one active conflicting claim:** Given two distinct tasks claiming the same normalized path or overlapping declared path scope, parallel admission attempts produce one successful owner and one blocked result. No transient window ever reports both as owners; test a concurrent interleaving, not only sequential unit steps. Directory, path traversal, casing/symlink and glob semantics must be explicitly specified for the actual workspace.
3. **Lease fencing and stale resume:** Every granted claim has durable task, workspace, resource scope, owner, expiry, and monotonic generation/epoch. After an authorized heartbeat, its expiry advances. When a prior claimant expires and another task is admitted, a delayed heartbeat/submit from the old generation must be rejected. A restart must reconcile existing backend runs **before** reassigning an ambiguous claim; an unknown backend outcome enters `needs_attention`, not blind duplication.
4. **Release and escalation:** Completion, confirmed cancellation, explicit handoff and reconciled loss update the claim consistently and trigger waiting work. An operator sees who blocks whom and why. Repeated failed/rejected/expired claims should surface a bounded escalation, not an unbounded retry loop. Claim expiry must not mean the external process stopped; handle orphaned edits explicitly.
5. **Security boundary:** A valid claim conveys reservation priority only, not tool credentials, repository permission, access to unclaimed files, approval rights, or authority to edit protected tests. Revalidate MechaHarness/June authorization at the actual effect boundary; resource claim ≠ capability grant.
6. **Acceptance verification independence:** Existing R11 verification remains authoritative. Proposed optional receipt records `task_id, commit_sha, command identity, result, dirty state`, and review must reject stale receipts after a new commit. Do not let the submitting agent forge verified status. This subcase may be tracked as an extension to an existing R11 test rather than a separate feature story.

**Deterministic fixture matrix:** (a) same file/different task IDs, interleaved race; (b) disjoint file scopes; (c) overlapping parent directories/globs; (d) heartbeat just before expiry; (e) old owner returns after reclaim; (f) process restart with running external handle; (g) cancellation confirmed/unknown; (h) symlink alias and absolute/path traversal; (i) malicious memory note asserting a claim; (j) stale verified receipt after commit changed. Assert zero duplicate active owners for conflicting scopes and no duplicate backend submission. Unknown authorization or unknown backend liveness must fail safely without starving unrelated tasks. Include false-positive contention metrics.

**Expected artefacts:** a stable repository/workspace identity contract, claim record schema, conflict reason and observable lifecycle/heartbeat hooks, scenario fixtures, and a June-native story/requirement mapping. Do not change MechaHarness' graph executor to own the queue.

## Design options and unanswered questions

- **Granularity:** exact paths vs directory/glob scopes vs semantic module scopes; only enforce what the selected backend can genuinely report. A coarse repo-wide lock is simpler but reduces concurrency.
- **Durability:** a serializable SQLite-backed claim table, an atomic journal, or extended JSON store with compare-and-swap; plain thread-local dictionaries are insufficient across workers/restarts. Choose based on June's actual persistence migrations.
- **Locking versus git worktrees:** worktrees isolate filesystem edits; path claims prevent logical overlap. Conflict scanning may use git diff snapshots as a *second* defence. Validate declared scopes against actual changes after execution, but never assume a declared scope is a sandbox.
- **Lease ownership versus external reality:** revoking a lease without ensuring an old worker is fenced does not make its side effects disappear. Distinguish *admission eligibility* from *termination confirmation*.
- **Multiple backends:** include Cursor and a fake second worker; ensure the contract is backend-neutral.

## Follow-up implementation-agent investigation

Read the **latest** June task service, persistence transaction semantics, worker scheduler and tests; inspect open PRs for any overlapping claim/policy work; map the above to existing R1/R7/R8/R11 and June native acceptance conventions. Trace exactly where admission happens before `june.coding_job`. Design a storage and fencing strategy supported by actual backend handles. Implement only after the story is accepted. Report which guarantees are deterministic, which depend on backend cooperation, and what failure cases must remain `needs_attention`. Keep generic MechaHarness contract evolution separate and evidence-driven.

## External evidence limitations

Upstream AgentHaven code is inspected but its tests were **not executed** here; no claim of numerical reliability is made. This dossier is a requirements proposal, not a PR to change runtime or existing accepted fixtures. Source material is interpreted rather than copied.
