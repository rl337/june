# Imagegen integration suite (ComfyUI)

Incubating Agentic Recipe family for text-to-image against the JuneSpark
**ComfyUI** media backend (vLLM remains the text OpenAI-compat surface).

## Discovered host (2026-10-12)

- ComfyUI `0.37.2` at `http://192.168.1.21:8188`
- Diffusion models include `flux2_dev_fp8mixed.safetensors` and
  `qwen_image_2.1_int8_convrot.safetensors` / `qwen_image_2512_fp8_e4m3fn.safetensors`
- Matching VAE / text-encoder weights and Lightning/Turbo LoRAs are present

## Recipes

| Recipe | Graph | Role |
|--------|-------|------|
| `june.imagegen` | prompt → generate → persist → verify | One-shot T2I |
| `june.imagegen.critique_refine` | goal → craft → generate → VL checklist → refine? → verify | Semantic dual-backend refine (single repair) |
| `june.imagegen.evaluate_criteria` | expand spec → VL score → summarize | Standalone criteria evaluator |
| `june.imagegen.criteria_refine` | host loop: craft → (gen → evaluate_criteria → refine?)×N → verify | Compose refine with configurable retries |

Soft points:

- `ImageGenerator` — offline `FixedImageGenerator`; live `ComfyImageGenerator` (JuneSpark Comfy)
- `PromptCrafter` — text LLM (local LM Studio Qwen)
- `VisionCritic` — multimodal VL checklist (required/forbidden elements)
- `ImageEvaluator` — offline `FixedImageEvaluator`; live `BoundEvaluateCriteria`
  (binds `evaluate_criteria`)
- `max_retries` — repair attempts after the first generate (default `2`; total
  rounds = `max_retries + 1`)
- `backend` — `qwen_image` or `flux2` workflow builders in
  `src/june/recipes/imagegen/workflows.py`

`critique_refine` is **semantic-only** (object checklist) with one optional repair.
It is not an artifact / geometry gate. Prefer `criteria_refine` when structure
criteria and a multi-attempt retry loop are needed.

### `evaluate_criteria` + `criteria_refine` compose

`criteria_refine` does **not** hard-code expand/score nodes. June owns a host
compose loop that binds `june.imagegen.evaluate_criteria` on each attempt
(HF-03: no MechaHarness nest tile yet):

1. Craft initial image prompt.
2. For attempt `0 .. max_retries`: generate → `evaluator.evaluate(...)` → if fail
   and retries remain, craft refined prompt from failed criteria.
3. Verify PNG bytes + final criteria pass.

Offline: `test_imagegen_criteria_refine_offline_retry_loop` (fail×2 then pass).  
Live problem: `HAND_FIVE_FINGERS` (`test_imagegen_criteria_refine_live_hand_fingers`).  
Override retries with `JUNE_CRITERIA_MAX_RETRIES`.

### Acceptance-criteria eval (thinking model → VL)

Standalone fixture path (also the soft point behind `BoundEvaluateCriteria`):

1. Heavy text model expands the image prompt into explicit criteria
   (`JunesparkAcceptanceSpecCrafter`) — including **structure** constraints for
   physical objects (exactly one coherent bike, well-formed forks/wheels, …).
2. Same text model audits that those criteria would cover the fixture’s
   `known_anomalies` (`JunesparkCoverageAuditor`).
3. VL scores each criterion on the malformed image (`JunesparkCriteriaScorer`)
   and we check failures cite the right defect (`score_trigger_alignment`).

Live test: `test_bike_acceptance_criteria_catch_malformed_fixture`  
Artifacts: `artifacts/imagegen/test_bike_acceptance_criteria_catch_malformed_fixture/`

Observed: thinking model (`qwen3.6-35b`) reliably emits structure criteria that
**cover** the known bike anomalies. `qwen3-vl-8b` often **soft-passes** those
structure rows; `google/gemma-4-31b-qat` as `JUNE_VL_SCORE_MODEL` fails them
with the right evidence (duplicated handlebars / ghost frame). Default the
fixture eval’s VL scorer to Gemma until a stricter VL is available.


## Workflows

- **Qwen Image 2.1** — `UNETLoader` + `CLIPLoader(type=qwen_image)` +
  `TextEncodeQwenImage21` (no reference images) + `KSampler` + `VAEDecode`
- **Flux2** — `UNETLoader` + `CLIPLoader(type=flux2)` + `CLIPTextEncode` +
  `FluxGuidance` + `EmptyFlux2LatentImage` + `KSampler` + `VAEDecode`

## How to run

```bash
# Offline (fixture PNG) — always on with integration suite
pytest -o addopts= -m 'integration and not junespark_live and not comfy_live and not vision_live' \
  tests/integration

# Live oneshot Comfy (do not starve an interactive queue)
COMFY_BASE_URL=http://192.168.1.21:8188 \
  pytest -o addopts= -m comfy_live tests/integration/test_imagegen_still_life.py

# Live critique-refine: LM Studio text+VL + JuneSpark Comfy
COMFY_BASE_URL=http://192.168.1.21:8188 \
JUNESPARK_BASE_URL=http://127.0.0.1:1234/v1 \
JUNE_TEXT_MODEL=qwen/qwen3.6-35b-a3b \
JUNE_VL_MODEL=qwen/qwen3-vl-8b \
  pytest -o addopts= -m 'comfy_live and vision_live' \
  tests/integration/test_imagegen_critique_refine.py

# Forced repair path (incomplete first prompt → VL fail → refine → regen)
# same env as above; test name:
#   test_imagegen_critique_refine_live_repairs

# Criteria-refine compose loop (configurable retries; hands / structure)
COMFY_BASE_URL=http://192.168.1.21:8188 \
JUNESPARK_BASE_URL=http://127.0.0.1:1234/v1 \
JUNE_TEXT_MODEL=qwen/qwen3.6-35b-a3b \
JUNE_VL_SCORE_MODEL=google/gemma-4-31b-qat \
JUNE_CRITERIA_MAX_RETRIES=2 \
  pytest -o addopts= -m 'comfy_live and vision_live' \
  tests/integration/test_imagegen_criteria_refine.py
```

Artifacts land under `artifacts/imagegen/<test>/`. Repair runs also write
`image_00.png` / `image_01.png`, `critique_00.json`, and `image_prompt_0{0,1}.txt`.
Criteria-refine also writes `attempts.json` and `acceptance_spec.json`.

Dual-backend split: Comfy owns pixels; LM Studio owns craft + VL / criteria
evaluate.

## Anomaly fixtures (eval only — gate not green)

Committed controls for a future artifact gate:

| Fixture | Role |
|---------|------|
| `tests/fixtures/imagegen/rain_bike_hydrant_malformed.png` (+ `_front.png`) | Negative: checklist-complete, geometrically broken |
| `tests/fixtures/imagegen/rain_bike_clean_positive.png` | Positive: clean bike must not be rejected |

Element checklist can pass the negative while forks/handlebars are duplicated and
the front wheel is melted. Qwen3-VL-8B often reports `malformed=false` / “minor
distortion” on that image — so it cannot yet drive generate→detect→retry.

### Acceptance bar (must be green before `artifact_retry`)

Helpers: `june.recipes.imagegen.anomaly_eval`.

- **Negative:** model `malformed=true` **and** an explicit structural mention
  (duplicate forks/handlebars and/or incomplete/melted front wheel) — not vague
  “slight distortion”.
- **Positive:** `malformed=false` on `rain_bike_clean_positive`.
- **Metric:** all of N paired trials at fixed temperature pass; majority vote
  agrees. No severity-coerce that turns “medium + good” into a hard fail.

Live characterization / self-consistency probes (do not assert bar green):

- `test_anomaly_critic_characterization_malformed_fixture`
- `test_anomaly_gate_eval_self_consistency` → writes `artifacts/imagegen/.../eval.json`

Observed (2026-10-12):

- `qwen/qwen3-vl-8b` (K=3): `bar_green=false` — positive clean (3/3), but
  negative never model-`malformed` (0/3); text denied defects (“no duplicated
  parts”).
- `google/gemma-4-31b-qat` (K=2, ~3 min): catches the negative well
  (`malformed=true` + explicit duplicate handlebars/forks) but fails the
  positive control (`positive_pass=false` both trials) — too aggressive, bar
  still red.

If the bar stays red: prefer best-of-N generation + a preference/ranker soft
point over binary detect→retry. A dedicated `june.imagegen.artifact_retry`
recipe is deferred until `bar_green` is true.

## Growth rules

- Prefer Comfy native prompt/queue API (not OpenAI `/v1/images/generations`).
- Keep verify stdlib-only (PNG magic + size) unless the suite image grows.
- Do not submit heavy live jobs while an interactive Comfy queue is occupied.
- Promote reusable Comfy client helpers to MechaHarness only with reuse evidence.
- Do not wire anomaly retry into `critique_refine` until the artifact-gate bar is green.

