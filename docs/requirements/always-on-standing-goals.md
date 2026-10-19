# Always-on standing goals (requirements map)

Synthesis of:

- [`../inspiration/openai-dots-always-on-agent-inspiration.md`](../inspiration/openai-dots-always-on-agent-inspiration.md)
- [`../inspiration/personal-agent-reliability-inspiration.md`](../inspiration/personal-agent-reliability-inspiration.md)

Dots is the control-plane spine; Personal-Agent fills policy, memory, and ops. MechaHarness
enforces grants/checkpoints; June owns envelopes, grant epochs, observation jobs, and UX.

## Requirement → module map

| ID | Theme | June owners | Phase |
|----|-------|-------------|-------|
| DOTS-01 / PA-01 | Standing goal isolation + constitution hard rules | `goals/`, `policy/` | 1 |
| DOTS-02 / DOTS-03 | Observe / Prepare / Execute + idle observation | `control/`, `scheduler/`, `observe/` | 2 |
| DOTS-04 / PA-05 | Grant/expiry/revoke + autonomy metrics | `policy/`, `runner/`, remote dispatch | 3 |
| DOTS-05 / PA-02 / PA-03 | Cross-channel memory trust/freshness | `knowledge/`, `channels/` | 4 |
| DOTS-06 / PA-04 / PA-06 | Reviewable deliverables + waiting queue | `issues/`, console | 4 |
| DOTS-07 / PA-09 | Per-goal ops / missed schedules | console + control metrics | 4 |
| DOTS-08 / PA-07 | Regressions + correction→backlog | `tests/`, dreaming→issues | 5 |

## Acceptance anchors

1. Unrelated goal B cannot inherit goal A's approval/grants (DOTS-01).
2. Observe-only work cannot send or write external state (DOTS-02/03).
3. Revoking a grant while paused blocks later execute/send (DOTS-04).
4. Prior approval memory is evidence, never a reusable auth token (DOTS-05).
5. Missed schedules / stale observations are visible without raw logs (DOTS-07).

## Out of scope (v1)

Telegram trust contract, contact profiling (PA-10), skill marketplace (PA-08),
Sparkstation unload choreography beyond observe-without-LLM.
