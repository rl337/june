# pyiv DI asks (June + MechaHarness)

Pull-based dependency-injection improvements. Promote a pattern into pyiv only
when more than one consumer needs it and the June/MechaHarness shape has
stabilized. Recipe / `GraphTemplate` definition modules MUST stay pyiv-free;
DI remains at the Config / host boundary.

## Current state

- MechaHarness: DI-first via `MechaHarnessConfig` + pyiv ≥ 0.4.2 (`Named` /
  `Matched` / `Key`, Completer/Judge flavors).
- June: file→settings→`Config` / `register_instance` prototype in
  `src/june/config/__init__.py` and `src/june/bootstrap.py`. The module
  already notes promotion into pyiv/pyiv-common only after the pattern
  stabilizes.

## Open asks

### PY-01 — File-backed Config helper

**Evidence:** June loads `config.yaml` / env overlays then binds a pyiv
`Config`. MechaHarness uses Settings / `SettingsConfig` for the OpenAPI path.

**Ask:** A small shared helper for “YAML/env → settings model → Config
hooks” once both hosts want the same shape. Until then, keep June’s prototype
local.

**Status:** incubating in June; do not promote yet.

### PY-02 — Mapping / dict injectability

**Evidence:** MechaHarness `GraphExecutor.fingerprint_parts` is assigned after
inject because optional Mapping types are not cleanly pyiv-injectable (host
side-door).

**Ask:** First-class support for injecting optional mapping-like config bags
(or an explicit `Key` pattern) so hosts do not mutate executors post-inject.

**Status:** open (MechaHarness-driven; June benefits when it adopts Config
inject for graphs).

### PY-03 — Host kit without constructor sprawl

**Evidence:** June’s `build_graph_executor` bypasses inject and hand-wires
many MH collaborators. MH’s blessed path is Config inject, but hosts still
override many hooks.

**Ask:** Keep expanding typed Config hooks rather than inventing string
registries. If pyiv needs ergonomics for “override a few bindings, keep
defaults,” prefer that over host-side factories that reimplement the injector.

**Status:** open; pairs with `docs/requirements/mechaharness-host-friction.md`
HF-01.

## Non-goals

- Importing pyiv from MechaHarness recipe definition modules.
- Moving June product policy or remote-task lifecycle into pyiv.
- Speculative DI framework features without a second concrete consumer.
