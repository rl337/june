# Trouble inspiration: starting-state robustness for inherited coding work

Status: **non-normative research and candidate June acceptance stories**.
Reviewed: 2026-10-29. Owner: **June** (application-level remote task dispatch, external coding agents, durable task state and acceptance policy).
Capability ID: **TR-20261029-RESIDUAL-START**.

## Sources and fidelity

- Trouble: https://rl337.org/trouble/posts/2115549189211894235.html ; archived JSON: https://github.com/rl337/trouble/blob/main/posts/2026/10/28/2115549189211894235.json ; original: https://x.com/EricDBrownDsC/status/2115549189211894235 .
- Li et al., *SWE-Residual: Evaluating Starting-State Robustness of Coding Agents*, submitted 2026-10-19, v1: https://arxiv.org/html/2610.25899v1 ; abstract https://arxiv.org/abs/2610.25899 ; source and benchmark code https://github.com/userljz/SWE-Residual .
- Key upstream sections: §3 task formulation and four-stage Residualization; §5 paired clean/residual evaluation and acceptance bias; Appendix B state reconstruction and validation; Appendix D acceptance-bias measures.

**Source claim, not June measurement:** SWE-Residual pairs 198 inherited residual states from 111 tasks in DeepSWE/Terminal-Bench with the original task requests and hidden verifiers. A predecessor agent declared the task complete, made persistent changes, but failed the original verifier. The successor gets only the original request and modified starting state, not the predecessor trajectory or explicit failure feedback. Five evaluated agents lost 20.6–53.5 percentage points on DeepSWE and 20.6–34.9 points on Terminal-Bench compared with matched clean starts. Among failed DeepSWE continuations, 58.9–88.2% ended with exactly the same tests still failing. The authors call the tendency to treat inherited work as the scope of the remaining task **acceptance bias**. The median DeepSWE residual state already passed 98.4% of tests, making “looks mostly done” a poor acceptance signal. The paper's benchmark is domain-specific and does not establish that June currently has the same failure rate.

**Mechanism:** Construct clean and residual starts for the same task, with the same request, verifier and budgets. Residualization: (1) generate predecessor attempts and capture terminal state; (2) filter for submitted-as-done but failing, changed, non-infrastructure-failure states; (3) review for task-directed coherent work and consistent verifier; (4) reconstruct the residual environment and revalidate that the original verifier still fails. For repository tasks, replay a binary-safe patch at the original base commit; for machine tasks, replay state-changing interactions and checkpoint the environment. Evaluate a successor without telling it which inherited files are wrong. Compare paired success and inspect unchanged failing tests and left-out files. This isolates starting-state effects from the original request.

## June baseline and ownership

- https://github.com/rl337/june/blob/main/docs/requirements/remote-task-orchestration.md already specifies durable task IDs, asynchronous external backend, restart reconciliation, logs/artifacts, and **R11 acceptance criteria**: backend process success must not imply task success; sufficient evidence must survive for verification.
- The same document's R8 requires recovery without duplicate external dispatch. R7 requires safe duplicate observation. R6 requires graph-visible dispatch, collection and verification through MechaHarness.
- https://github.com/rl337/june/blob/main/src/june/recipes/codegen/run.py currently reports verified, failures, run_results, events, checkpoint information and a verified-aware status for incubating codegen recipes. This is evidence of a verification surface, **not** evidence of a starting-state audit for externally inherited repository work.
- https://github.com/rl337/june/blob/main/docs/inspiration/dev-blog-inspiration.md requires June to translate MechaHarness verification outcomes into persistent task/goal/issue state and choose follow-up, retry, reschedule or escalation.
- Open PR https://github.com/rl337/june/pull/25 concerns knowledge-aware change review, not the same as re-verifying inherited code against the original request. Review it before designing shared verification nodes.

**Coverage decision: B/C.** General acceptance verification is already required and partly represented in code. The missing *specified test dimension* is independently checking apparent-complete inherited work and comparing paired clean/residual starts. Do not create a second task service or claim R11 is absent. This is an **extension to R11 and its acceptance fixtures**, plus an evaluation story, not a new orchestrator.

## Candidate JN-RESIDUAL-01: independently verify inherited completion

**Persona and outcome:** As an operator handing a coding task to June after a prior agent or human has made changes, I want June to evaluate the full original request against the current repository state before accepting a completion claim, so that partially correct inherited work is not mistaken for a finished task.

**Setup:** A durable task with explicit original acceptance criteria, a repository/workspace base revision, an external backend handle, and a modified worktree from a predecessor that reported “done”. The residual state passes most ordinary checks but fails one hidden/independent acceptance check; a control state passes all checks. Include a second case where the predecessor supplied no history, only modified files. The verifier has access to a trusted acceptance specification and a deterministic sandboxed fake backend.

**Action:** June dispatches or resumes the task. Before transitioning to succeeded, it executes a graph-visible independent verification stage against the original requirements and current artifacts, records evidence per criterion, and either succeeds, requests repair, or moves to needs_attention according to policy.

**Acceptance anchors:**
1. Predecessor status, commit message, existing tests and the successor's own “done” message are **claims**, not proof of task acceptance.
2. Every original acceptance criterion is evaluated or explicitly marked unverified with a reason. A missing criterion is not treated as passing because the inherited diff appears complete.
3. The verifier can inspect changed **and unchanged** files relevant to the requirement, so a predecessor's omitted file cannot become an invisible scope boundary.
4. A residual state failing one independent criterion cannot transition to succeeded even if the backend exits successfully and 98% of ordinary checks pass; the task persists exact failed criterion IDs, artifacts, evidence and next action.
5. The control state that genuinely meets all criteria succeeds without unnecessary destructive rewrites. A no-op completion is allowed only when verified.
6. After June restart, the same task ID and acceptance obligations survive; duplicate observation/reconciliation must not create duplicate external dispatch or erase failed evidence.
7. If the independent verifier is unavailable, the task becomes needs_attention/unverified rather than succeeded. Permission-denied artifacts remain protected.
8. A second backend continuation receives the original request and explicit verification failures according to June policy, while its inherited workspace is treated as untrusted evidence, not a source of new authority.

**Failure and adversarial cases:** malicious predecessor summary; stale test results from another commit; a file omitted from the predecessor diff; a passing local test suite with failing hidden acceptance; verifier timeout; partial logs; dirty worktree; non-reproducible external state; reviewer falsely claiming a command was run. Require artifact IDs, revision identities, and evidence references.

**Where to implement later:** Extend R11 of docs/requirements/remote-task-orchestration.md and the existing task/verification graph, not a parallel review service. The MechaHarness reusable verify/repair and checkpoint primitives should carry the graph semantics; June owns acceptance policy, task status and backend selection. Use a deterministic fake external backend for acceptance before introducing Cursor/Spark integration.

## Candidate JN-RESIDUAL-02: paired clean-start / residual-start agent evaluation

**Persona and outcome:** As a June maintainer selecting external coding agents and verification recipes, I want a reproducible evaluation that compares the same task from clean and inherited-partial states, so that choosing an agent solely by clean-start success does not hide handoff fragility.

**Setup:** A small local corpus of tasks with original request, base commit, independent verifier, and one or more residual-state patches. Residual patches must be from plausible earlier attempts that modified the task, were reported complete, and still fail the verifier. Keep at least one easy clean-start task, one nearly complete residual, one missing-file residual and one misleading predecessor summary. Record source hash, task ID, model/backend, recipe/config fingerprint, environment, tool versions and budget.

**Action:** Run the same backend/recipe against each task's clean and residual start with the same request, verifier and budget. Optionally run a third condition with explicit predecessor feedback to measure the value of handoff information separately. Keep repeated runs and independent starting worktrees; do not leak hidden tests to the agent.

**Acceptance anchors:**
1. Each residual fixture is reconstructed from the recorded base and reverified as failing before the agent begins; malformed or unexpectedly passing residuals are rejected from the corpus.
2. The runner emits per-task clean success, residual success, residual gap, attempts, tool calls, tokens, time, unchanged failing criteria, and changed/omitted files. Aggregate scores weight tasks explicitly and do not mix multiple residuals into an unreported average.
3. A synthetic fake agent that accepts inherited code without inspection fails the residual fixture while succeeding from clean; a verifier-aware fake agent can repair the seeded defect.
4. Model or tool version changes are recorded as separate conditions. No claim of improvement is made without paired comparable results and uncertainty/replicate information.
5. Evaluation results link back to the original acceptance story and external artifacts; failures can become June issues without duplicating the same task or PR.
6. The benchmark remains optional for regular user tasks; it is an evaluation and recipe-selection instrument, not an always-on expensive production check.

**Implementation choices to evaluate:** full hidden-test verifier versus rubric/checklist with a judge; patch-based worktree reconstruction versus container snapshots; trusted independent verifier versus model-based reviewer; which criteria can be deterministic. Model judgment should not be the sole authority for command execution or source revision identity.

## Related discoveries and non-duplicates

- Trouble https://rl337.org/trouble/posts/2115471476581130611.html ; *Knowing When to Stop* https://arxiv.org/abs/2610.31895 . June's dev-blog requirements already include escalation/retry; inspect current task lifecycle and MechaHarness budget outcomes before proposing a new stop/escalation story.
- Trouble https://rl337.org/trouble/posts/2115685301678907769.html about duplicate writes. June R7/R8 and MechaHarness transactional durable resume already specify idempotent observation/dispatch; an additional user story requires a demonstrated test gap.
- Trouble https://rl337.org/trouble/posts/2115427316553904129.html about cross-agent memory. Source was not fully retrieved in this pass; do not assert a gap from the social summary alone.

## Implementing-agent checklist

Read current R11/R8 and relevant June test fixtures, refresh PR #25, locate the actual external-backend and graph-visible verification nodes, identify authoritative acceptance sources, then implement native June acceptance fixtures using a fake backend. Preserve original request and acceptance provenance across resume. Compare source benchmark methodology to the target environment; avoid copying external benchmark data without checking license and reproducibility. Update normative requirements and tests only after the candidate story is accepted.

Ledger: rl337/trouble state/inspiration-watch-ledger.json, capability TR-20261029-RESIDUAL-START. This PR is documentation-only; it does not modify execution semantics.

Cross-repository discovery ledger draft PR: https://github.com/rl337/trouble/pull/38 . Other resulting draft PRs: https://github.com/rl337/mechaharness/pull/37 , https://github.com/rl337/project-template/pull/1 , https://github.com/rl337/june/pull/26 .
