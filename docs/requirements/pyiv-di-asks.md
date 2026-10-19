# pyiv DI asks (June + MechaHarness)

Pull-based dependency-injection improvements. Promote a pattern into pyiv only
when more than one consumer needs it and the June/MechaHarness shape has
stabilized. Recipe / `GraphTemplate` definition modules MUST stay pyiv-free;
DI remains at the Config / host boundary.

## Current state

- MechaHarness 0.5.0: DI-first via `MechaHarnessConfig` + **pyiv ≥ 1.1.0**
  (`Named` / `Matched` / `Key`, Completer/Judge flavors, injectable
  `AsyncHttpClient`, use-case stdlib doubles for `Environment` / time / files /
  log / clock).
- June: file→settings→`Config` / `register_instance` prototype in
  `src/june/config/__init__.py` and `src/june/bootstrap.py`. `JuneConfig`
  registers the same leaf injectables and loads yaml/env through
  `Environment` + `Filesystem`. Providers default to pyiv `HttpClient`
  (`UrllibHttpClient`; tests may inject `MemoryHttpClient` or httpx).

## Open asks

### PY-01 — File-backed Config helper

**Evidence:** June loads `config.yaml` / env overlays then binds a pyiv
`Config`. MechaHarness uses Settings / `SettingsConfig` for the OpenAPI path.

**Ask:** A small shared helper for “YAML/env → settings model → Config
hooks” once both hosts want the same shape. Until then, keep June’s prototype
local (now reads env/files via injectables).

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

**Evidence:** June formerly bypassed inject and hand-wired many MH
collaborators. MH’s blessed path is Config inject + `host_graph_executor`.

**Ask:** Keep expanding typed Config hooks rather than inventing string
registries. If pyiv needs ergonomics for “override a few bindings, keep
defaults,” prefer that over host-side factories that reimplement the injector.

**Status:** **largely closed for June** by MH 0.4 host_kit + pyiv 1.1
`override` / stdlib doubles; remaining residue is HF-06 clone helpers, not DI.

## Landed (keep for archaeology)

- pyiv 1.0 `HttpClient` / `AsyncHttpClient` (+ Memory doubles) — June providers
  and MH inference/judge HTTP.
- pyiv 1.1 use-case stdlib surfaces (`files`, `time`, `process`, `log`, …) —
  registered on `JuneConfig` and `MechaHarnessConfig`.
- pyiv 0.4.3 catalog multibinds / `contribute_map` / `catalog_keys` — MH recipe
  / backend / harness membership.

## Non-goals

- Importing pyiv from MechaHarness recipe definition modules.
- Moving June product policy or remote-task lifecycle into pyiv.
- Speculative DI framework features without a second concrete consumer.
