# Inspiration: Persistent Personal Agent Operating Model

Status: proposal; not implemented by this document.
Source: Hamza Khalid (@humzaakhalid), "100 Tips & Tricks for Building Your Personal AI Agent", X post, July 25 (as presented by the author). https://x.com/humzaakhalid/status/2080954210456334798?s=46
Source scope: numbered recommendations 1–85 and the concluding fifteen priority recommendations, as supplied in the source text. The author's anecdotes are not independently verified.

## Motivation
June is the always-on personal orchestrator. It should carry tasks, decisions, evidence, and corrections across sessions, while relying on MechaHarness for generic graph execution and enforced policy gates.

## Proposed requirements and user stories
- **JUNE-PA-01: Versioned operating constitution** (tips 1–4, 40, 80–81; priority 1–4). As principal, I can review versioned hard rules, behavioural preferences, identity, and explicit NOT-FOR boundaries. A conflicting lower-priority instruction cannot override hard policy. Keep capability map distinct from component map.
- **JUNE-PA-02: Domain memory with indexed retrieval** (tips 5–10, 12–13, 82; priority 5–6). As principal, I can inspect memories by domain, distinguish hypotheses from verified facts, and expire hot context and hypotheses. Use a readable index and selectively retrieve relevant context; retain event log, transactional state, knowledge graph and vector search rather than adopting Markdown-only storage.
- **JUNE-PA-03: Freshness and source-of-truth visibility** (tips 6–8, 65; priority 7–8). As principal, I see when an answer depends on old external data and whether it is authoritative or cached. Never silently treat an eight-day-old snapshot as live. Integrate MechaHarness provenance policy.
- **JUNE-PA-04: Session continuity and waiting queue** (tips 9, 22, 33–37). As principal, I can return after an interruption and see current work, decisions waiting on me, new changes, and automation failures. Closure has light/medium/full modes; hot context expires; durable task state does not.
- **JUNE-PA-05: Evidence-based earned autonomy** (tips 39–42, 69–71, 73; priority 11–14). As principal, I can grant narrowly scoped action permissions, inspect successful and corrected executions, and approve proposed promotions. June may prepare drafts without approval but must not send or take consequential actions beyond policy. Mobile/forwarded inputs carry trust labels.
- **JUNE-PA-06: Proactive observation pipeline** (tips 43–48, 75). As principal, I receive useful typed observations with confidence, evidence, and proposed next action, without repetitive interruptions. Suppressed observations remain reviewable; deterministic thresholds generate alerts. A dedicated brainstorm mode can surface the backlog on demand.
- **JUNE-PA-07: Corrections and development backlog** (tips 38, 48, 74, 77; priority 15). As principal, repeated corrections become proposed requirements, regression scenarios, or backlog entries rather than silently rewriting policy. Track correction frequency and disposition.
- **JUNE-PA-08: Skill discovery and output routing** (tips 17–22, 60–64, 68). As principal, I can find outputs, follow file links, and know why a skill activated. Skills declare triggers, exclusions, output contracts, and usage metrics. Output form adapts to mobile vs desktop without weakening policy.
- **JUNE-PA-09: Integration degradation and operations** (tips 11, 35–37, 65, 72, 75–79). As principal, I know when a connector is down, cached data is too old, a scheduled task missed its run, or backups failed. home_network provides service infrastructure; June owns user-facing status and recovery workflows.
- **JUNE-PA-10: Contextual contacts and knowledge** (tips 49–53, 66–67, 83). As principal, I can opt in to tiered relationship context and project knowledge stacks. Avoid collecting sensitive personal profiling without a clear purpose and retention controls.

## Architecture boundaries
MechaHarness owns generic graph recipes, authority enforcement, structured handoffs, checkpoint and test primitives. June owns policy configuration, session/task orchestration, memory, proactive decisions and the user-facing experience. home_network hosts persistent services and backup infrastructure, without consuming Sparkstation inference memory.

## Open questions / TODO
- [ ] Inventory June's current scheduler, event log, memory and UI to identify existing coverage.
- [ ] Specify the constitution schema and policy precedence with MechaHarness.
- [ ] Define memory truth status, timestamps, expiry, confidence and correction lineage.
- [ ] Define autonomy evidence, approval workflow, and permission revocation.
- [ ] Choose proactive observation budgets, thresholds, and quiet-hours handling.
- [ ] Decide Telegram/mobile trust and acknowledgement contract.
- [ ] Specify integration health and missed-schedule reporting.
- [ ] Define privacy and retention rules for contact and behavioural profiles.

## Suggested order
1. Constitution and source freshness.
2. Session continuity, waiting queue and automation health.
3. Typed proactive observations and correction capture.
4. Scoped autonomy promotion with audited approvals.
5. Skill/output audits and optional relationship workflows.

Attribution: Concepts adapted from Hamza Khalid's post above; June-specific designs are interpretations rather than direct claims from the author.
