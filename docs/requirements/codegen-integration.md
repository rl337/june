# Codegen integration suite

Bootstrap for a growing **containerized** June recipe integration suite.

## Goal

Prove incubating Agentic Recipes under `june.codegen*` can:

1. ask a completer (live JuneSpark reason/heavy model, or a fixed offline stub)
   to write Python for a fixed coding problem;
2. extract script(s) from the model response;
3. execute against deterministic stdin fixtures;
4. verify stdout matches expected results;
5. (refine) diagnose failures and repair with a second generation pass;
6. (package) produce a runnable multi-file package (`python -m …`).

This is application-level evaluation of June recipes, not a MechaHarness unit
test. MechaHarness supplies `host_graph_executor` / graph run plumbing.

## Recipes

| Recipe | Graph | Role |
|--------|-------|------|
| `june.codegen` | prompt → generate → extract → execute → verify | One-shot single file |
| `june.codegen.refine` | … → diagnose → refine_prompt → repair_* → verify | Two-pass repair |
| `june.codegen.package` | prompt → generate → extract_files → execute_module → verify | Multi-file package |

## Problems

| Id | Kind | Notes |
|----|------|-------|
| `sum_multiples_3_or_5` | script | Project Euler #1 style |
| `rpn_eval` | script | RPN with truncating `/`; oneshot+bug fails, refine repairs |
| `word_stats_pkg` | package | `wordstats/__main__.py` + `wordstats/stats.py` |

## Stdlib-only rule

All generated code MUST use the **Python standard library only** — no third-party
imports. Enforced in problem prompts, an AST check after extract /
`extract_files`, and offline reference solutions. Intra-package imports (e.g.
`from wordstats.stats import …`) are allowed for package recipes.

## Layout

| Path | Role |
|------|------|
| `src/june/recipes/codegen/` | Incubating recipes (problem, graph, runners, completers) |
| `tests/integration/` | E2E suite (`@pytest.mark.integration`) |
| `integration/Dockerfile` | Suite image |
| `integration/run.sh` | `offline` / `live` / `all` entrypoint |
| `integration/docker-compose.yml` | Compose overlay |
| `artifacts/` | Gitignored host outputs; mounted at `/artifacts` in the container |

## How to run

```bash
# Always-on offline path (fixed / scripted completers) — used by CI
./integration/run.sh offline

# Live JuneSpark (heavy/reason model must be loaded on the endpoint)
JUNESPARK_BASE_URL=http://host.docker.internal:8000/v1 \
JUNESPARK_MODEL=... \
  ./integration/run.sh live
```

Default `pytest` ignores `tests/integration` so unit CI stays fast.

After a run, inspect `artifacts/codegen/<test_name>/` on the host. The harness
writes a full bundle for scrutiny (override root with
`JUNE_INTEGRATION_ARTIFACTS` if needed):

- `turns.json` / `turns.jsonl` — completer request/response turns (live includes API payload)
- `events.json` / `events.jsonl` — full MechaHarness event log
- `graph.json` — final execution graph
- `prompt.txt`, `refine_prompt.txt` (refine), `raw_response.txt`, `script.py`
- `files/` — extracted package tree (package recipe)
- `execute_results.json`, `execute_command.json`, `failures.json`
- `diagnostics.json`, `access_checks.json`, `node_statuses.json`
- `checkpoint.sqlite`, `result.json`, `MANIFEST.md`

## Growth rules

- Add new `CodingProblem` values + `tests/integration/test_codegen_*.py` cases.
- Keep problems deterministic and executable in the slim Python container
  (**stdlib only** unless the suite image explicitly installs more — generated
  code itself must remain stdlib-only).
- Prefer incubating recipes in June; promote generic skeletons to MechaHarness
  only with reuse evidence (`docs/requirements/mechaharness-host-friction.md`).
- Live tests stay behind `@pytest.mark.junespark_live` and skip without
  `JUNESPARK_BASE_URL`.
- Every successful recipe case must assert host contracts via
  `tests/integration/harness_assertions.py`: **cost** (`budget_spent` /
  `budget_level`), **permissions** (`core:access_check` + `core:graph.execute`),
  **observability** (exact event-type skeleton, per-node start/end order,
  attempt=1, checkpoint durability), and **inference efficiency** (oneshot /
  package = 1 turn; refine = 1 if first pass ok else 2). Include a
  denied-without-grant case when adding a new recipe family.
- Nodes use `max_attempts=1` so failed verify does not retry the same artifact;
  repair belongs in `june.codegen.refine`.
- For refine: prove offline contrast (oneshot fails with buggy script; refine
  succeeds with scripted bad→good completer).
