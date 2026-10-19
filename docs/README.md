# June documentation

- **[Developer blog inspiration](inspiration/dev-blog-inspiration.md)** — living
  design notes and MUST/SHOULD/MAY requirements for June as a MechaHarness
  client (Agentic Recipe vocabulary).
- **[Remote task orchestration](requirements/remote-task-orchestration.md)** —
  bootstrap requirements for durable remote tasks.
- **[MechaHarness host friction](requirements/mechaharness-host-friction.md)** —
  June-sourced asks for a more readable MH host API.
- **[pyiv DI asks](requirements/pyiv-di-asks.md)** — pull-based DI promotion
  backlog shared with MechaHarness.
- **[Codegen integration suite](requirements/codegen-integration.md)** —
  containerized `june.codegen` / `.refine` / `.package` recipe E2E
  (offline DI completers + live JuneSpark; stdlib-only generated code).
- **[Imagegen integration suite](requirements/imagegen-integration.md)** —
  incubating `june.imagegen` against ComfyUI (Flux2 / Qwen Image).
- **[Interactive chat + channels](requirements/interactive-chat-channels.md)** —
  channel-agnostic `june.chat` recipe, `generate_image` tool, REST/console fronts.
- **[Eval research brief](inspiration/eval-research.md)** — application-level
  evaluation research handoff.
- **[OpenAI Dots always-on inspiration](inspiration/openai-dots-always-on-agent-inspiration.md)** —
  standing goals, Observe/Prepare/Execute, authorization revocation.
- **[Personal agent reliability inspiration](inspiration/personal-agent-reliability-inspiration.md)** —
  constitution, memory freshness, earned autonomy, proactive observations.
- **[Always-on standing goals](requirements/always-on-standing-goals.md)** —
  synthesis requirements map (DOTS + PA → June modules/phases).
- **[README](../README.md)** — project overview and setup.
- **[AGENTS.md](../AGENTS.md)** — guidance for agents working in this repo.

Companion harness documentation lives in the
[mechaharness](https://github.com/rl337/mechaharness) repository. Floor:
`mechaharness>=0.5.0` (requires `pyiv>=1.1.0`).
