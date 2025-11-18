# Script Tests

This directory contains end-to-end and integration test scripts that are **not run via pytest**.

## Status

These tests are **excluded from pytest collection** (see `pyproject.toml` `norecursedirs` configuration).

## Requirements

These tests require:
- Running services (STT, TTS, LLM, etc.)
- Dependencies: `grpc`, `june_grpc_api`, `httpx`, etc.
- Some tests reference removed services (e.g., `gateway`) and may need updates

## Test Files

- `test_e2e_text_passthrough.py` - ⚠️ **OBSOLETE** - End-to-end text passthrough test (depends on removed gateway service, kept for reference only)
- `test_generate_stream.py` - LLM stream generation test
- `test_validate_tts_stt.py` - TTS/STT validation test
- `test_round_trip_alice*.py` - Round-trip voice message tests
- `test_pipeline_modes.py` - ⚠️ **OBSOLETE** - Pipeline mode tests (depends on removed gateway service, imports non-existent `test_round_trip_gateway`, kept for reference only)
- `test_single_word_fix.py` - Single word fix test
- `penetration_test.py` - ⚠️ **OBSOLETE** - Penetration testing script (tests removed gateway service, could be updated to test remaining services)
- `diagnose_test_failures.sh` - ⚠️ **OBSOLETE** - Diagnostic script (references removed gateway service, could be updated for remaining services)
- `run_tests_with_artifacts.sh` - ⚠️ **OBSOLETE** - Test orchestration script (starts gateway, runs gateway tests, collects gateway artifacts, could be updated for remaining services)

## Running These Tests

These tests should be run manually when services are running, or via the integration test service (see Phase 12-13 in REFACTOR_PLAN.md).

## TODO

- ✅ **COMPLETED:** Marked `test_e2e_text_passthrough.py` as obsolete (depends on removed gateway service)
- ✅ **COMPLETED:** Marked `test_pipeline_modes.py` as obsolete (depends on removed gateway service, imports non-existent module)
- ✅ **COMPLETED:** Marked `penetration_test.py` as obsolete (tests removed gateway service, could be updated to test remaining services)
- ✅ **COMPLETED:** Marked `diagnose_test_failures.sh` as obsolete (references removed gateway service, could be updated for remaining services)
- ✅ **COMPLETED:** Marked `run_tests_with_artifacts.sh` as obsolete (orchestrates gateway tests, could be updated for remaining services)
- ⏳ Ensure all dependencies are available when running via integration test service
- ⏳ Consider moving these to `tests/integration/` if they're meant to be integration tests
