# Inspiration: OpenAI Dots and June's Always-On Operating Model

Status: proposed requirements, no implementation implied.

## Primary sources and provenance

- OpenAI, [Introducing dots](https://openai.com/index/introducing-dots/) (2026-09-29).
- OpenAI, [Getting started with your dot](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot).
- OpenAI, [Dots privacy, security and safety FAQs](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs).
- OpenAI, [GPT-6 Astra system card, Dots appendix](https://deploymentsafety.openai.com/gpt-6-astra/sec:appendix-sol-luna).
- Secondary synthesis: *Always-On Agent Architecture: 6 Layers That Turn a Chatbot Into an Agent That Works While You Sleep*, first-page screenshot attributed to @chooppylug1, supplied by user. This is not an OpenAI paper; original complete PDF not independently located.

The source materials describe a product and evaluations, not a drop-in reference implementation. Numeric evaluation findings below are OpenAI-reported and must be checked against exact methodology before being used as release gates.


## Interpretation and architectural decision
June is an always-on *control plane*, not an always-on loaded large model. Its persistent scheduler, event subscriptions, memory and goal registry continue operating when inference is unloaded. MechaHarness owns reusable execution and authorization mechanisms. home_network owns supporting services and health/backup plumbing.

## Requirements / user stories
1. **JUNE-DOTS-01 Standing goals and responsibility isolation.** As principal, I can create, pause, inspect and retire a standing goal. Each goal has its own owner, purpose, allowed sources, authority, budget, lifecycle, event cursor, context, and durable checkpoint references. Do not let permissions or untrusted evidence silently migrate between goals. *Acceptance:* unrelated goal B cannot inherit goal A's approval, even if June's memory mentions it. *Inspiration:* OpenAI Dots persistent goals; system-card cross-task boundary evaluation.
2. **JUNE-DOTS-02 Observe / Prepare / Execute separation.** Background research is read-only within explicit data-source permissions. Preparation may draft, plan and simulate. Execution requires capability-scoped authorization checked at action time. *Acceptance:* a scheduled research run cannot send a Slack message by invoking an alternative tool. *Inspiration:* Dots proactive research restrictions and Custom Rules.
3. **JUNE-DOTS-03 Idle research with model wake-up budgets.** Event-driven and scheduled observation can run without the primary Sparkstation model loaded. Trigger lightweight extraction or reasoning only when thresholds and resource budgets warrant it. *Acceptance:* an idle research cycle persists observations while main inference is unloaded; it never modifies external state.
4. **JUNE-DOTS-04 Explicit authorization lifecycle.** Record authority grant, scope, expiry, revocation and policy version. June can propose a grant, but cannot promote itself. *Acceptance:* revoking send permission while a job is paused prevents later send on resume. *Inspiration:* Dots rule configuration and system-card changing-authorization evaluation.
5. **JUNE-DOTS-05 Cross-channel memory with trust boundaries.** Preserve useful corrections and task state across channels, while tagging source, confidence, freshness, sensitivity, and trust. Memory of prior approval is evidence of history, never a reusable authorization token. *Acceptance:* a forwarded message or imported document cannot override standing rules.
6. **JUNE-DOTS-06 Reviewable deliverables.** Present proactive work as drafts or proposed actions with evidence, action history, uncertainty, and pending approvals. Explicitly distinguish 'stop future work' from 'undo prior external effects'. *Acceptance:* approval screen displays precise recipient, payload and effect before execution.
7. **JUNE-DOTS-07 Operational visibility.** Surface per-goal state, observation freshness, sleeping/running model status, errors, approval queue, missed schedules, and resumption state. *Acceptance:* missed scheduled work and stale observations are visible without opening logs.
8. **JUNE-DOTS-08 Regression scenarios.** Test standing-goal scope bleed, source injection, permission revocation, malicious tool text, and long-running task drift using MechaHarness test fixtures.

## Source evaluation notes
- OpenAI reports 0 scored successes in a specific simulated bulk-email injection evaluation covering 16,600 malicious emails in 100 rollouts. This does **not** mean prompt injection is solved.
- OpenAI reports moderate-severity scope violations of 8.6% with five intervening tasks and 19.7% with ten intervening tasks in one evaluation. Do not generalize as 'every ten-job agent drifts 2x'.
- The source reports 45/49 alignment passes in a changing-authorization evaluation, including 17/17 explicit changes. Ambiguous boundaries remain a concern.
- Reported evaluations motivate isolation and revocation tests; they are not project performance targets.

## Implementation boundary
June configures authority and manages goals, tasks, memory and user experience. MechaHarness enforces action gates, review, checkpoint and delegation contracts. The system must not require Kubernetes on Spark or reserve Spark unified memory for idle orchestration.

## TODO / open decisions
- [ ] Inspect existing June scheduler and goal state before adding schemas.
- [ ] Decide goal-scoped event cursor, memory partitioning and durable task metadata.
- [ ] Specify model wake-up thresholds and lightweight observation services.
- [ ] Define explicit approval UX for Telegram and web UI.
- [ ] Decide retention and redaction of cross-channel memory.
- [ ] Connect action authorization epochs to MechaHarness.
- [ ] Add an integration health and missed-job dashboard.

## Incremental plan
First ship durable goal isolation and observation-only background jobs; then approval boundaries and resumable authorization checks; finally proactive reporting and regression evaluation.
