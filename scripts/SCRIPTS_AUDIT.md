# Scripts Directory Audit - Phase 11

This document categorizes all scripts in the `scripts/` directory according to Phase 11 guidelines.

**Last Updated:** 2024-11-18

## Guidelines
- **Scripts (`scripts/`):** Only for shell scripts that help with passing complex options to container runs or other tools
- **Commands (`essence/commands/`):** All reusable tools that users/agents might run via `poetry run -m essence <command-name>`
- **Tests (`tests/`):** All test code, runnable via pytest

## Current Scripts Inventory

### ✅ Keep as Scripts (Infrastructure/Automation)

These are shell scripts for infrastructure setup, automation, or complex container operations:

1. **`setup_docker.sh`** ✅ KEEP
   - **Purpose:** Infrastructure setup script for Docker environment
   - **Reason:** Infrastructure automation script
   - **Status:** Active

2. **`setup_docker_permissions.sh`** ✅ KEEP
   - **Purpose:** Infrastructure setup script for Docker permissions
   - **Reason:** Infrastructure automation script
   - **Status:** Active

3. **`refactor_agent_loop.sh`** ✅ KEEP
   - **Purpose:** Automation script for running refactoring agent in a loop
   - **Reason:** Infrastructure automation script
   - **Status:** Active

4. **`run_all_checks.sh`** ✅ KEEP
   - **Purpose:** Automation script for running all health checks
   - **Reason:** Infrastructure automation script
   - **Status:** Active

5. **`run_benchmarks.sh`** ✅ KEEP
   - **Purpose:** Shell wrapper for complex container operations (calls run_benchmarks.py)
   - **Reason:** Infrastructure script that orchestrates container runs
   - **Status:** Active (but should call command instead of script)

6. **`review_sandbox.sh`** ✅ KEEP
   - **Purpose:** Shell wrapper for review_sandbox command
   - **Reason:** Infrastructure script wrapper
   - **Status:** Active (already updated to call command)

7. **`deploy_audio_services.sh`** ✅ KEEP
   - **Purpose:** Infrastructure deployment script for audio services
   - **Reason:** Infrastructure deployment automation
   - **Status:** Active

### 🔄 Convert to Commands (Reusable Python Tools)

These are reusable Python tools that should be converted to commands:

1. **`download_qwen3.py`** ✅ MERGED INTO COMMAND
   - **Purpose:** Download Qwen3-30B-A3B-Thinking-2507 model in container
   - **Action:** ✅ Merged into `essence/commands/download_models.py` (enhanced to support MODEL_CACHE_DIR and HUGGINGFACE_TOKEN)
   - **Reason:** Reusable tool for model management
   - **Priority:** Medium (functionality already exists in download-models command)
   - **Status:** ✅ COMPLETED
   - **Note:** ✅ Enhanced download-models command to support container paths via MODEL_CACHE_DIR env var, added HUGGINGFACE_TOKEN support, added model existence check

2. **`generate_alice_dataset.py`** ✅ CONVERTED TO COMMAND
   - **Purpose:** Generate Alice's Adventures in Wonderland dataset for audio testing
   - **Action:** ✅ Created `essence/commands/generate_alice_dataset.py` (command name: `generate-alice-dataset`)
   - **Reason:** Reusable tool for dataset generation
   - **Priority:** Low (used for testing)
   - **Status:** ✅ COMPLETED
   - **Note:** ✅ Updated references in run_checks.sh, run_tests_with_artifacts.sh, and test scripts

3. **`run_benchmarks.py`** ✅ CONVERTED TO COMMAND
   - **Purpose:** Orchestrate benchmark evaluation with sandboxed execution
   - **Action:** ✅ Created `essence/commands/run_benchmarks.py` (command name: `run-benchmarks`)
   - **Reason:** Reusable tool for running benchmarks
   - **Priority:** High (actively used)
   - **Status:** ✅ COMPLETED
   - **Note:** ✅ `run_benchmarks.sh` updated to call the command

### 📦 Move to Tests (Test Utilities)

These are test utilities that should be moved to `tests/scripts/`:

1. **`diagnose_test_failures.sh`** 📦 MOVE TO TESTS
   - **Purpose:** Comprehensive diagnostic script for test artifact failures
   - **Action:** Move to `tests/scripts/diagnose_test_failures.sh`
   - **Reason:** Test utility for debugging test failures
   - **Status:** ⏳ TODO

2. **`run_tests_with_artifacts.sh`** 📦 MOVE TO TESTS
   - **Purpose:** Run tests with artifact collection
   - **Action:** Move to `tests/scripts/run_tests_with_artifacts.sh` or convert to pytest
   - **Reason:** Test utility
   - **Status:** ⏳ TODO

3. **`set_test_mode.sh`** 📦 MOVE TO TESTS
   - **Purpose:** Set test mode configuration (mock, stt_tts_roundtrip, etc.)
   - **Action:** Move to `tests/scripts/set_test_mode.sh` or convert to pytest fixture
   - **Reason:** Test utility for configuring test environment
   - **Status:** ⏳ TODO
   - **Note:** References removed services (GATEWAY_MODE) - needs update

4. **`penetration_test.py`** 📦 MOVE TO TESTS
   - **Purpose:** Automated penetration testing for June Agent system
   - **Action:** Move to `tests/scripts/penetration_test.py` or `tests/security/penetration_test.py`
   - **Reason:** Security testing utility
   - **Status:** ⏳ TODO
   - **Note:** References removed services (gateway) - needs update

### ❌ Remove (Obsolete)

These scripts are obsolete and should be removed:

1. **`build_inference_core_wheel.sh`** ✅ REMOVED
   - **Purpose:** Build inference-core wheel package
   - **Reason:** Obsolete after Poetry migration (no longer using wheel builds)
   - **Status:** ✅ COMPLETED

2. **`build_june_grpc_api_wheel.sh`** ✅ REMOVED
   - **Purpose:** Build june-grpc-api wheel package
   - **Reason:** Obsolete after Poetry migration (no longer using wheel builds)
   - **Status:** ✅ COMPLETED
   - **Note:** ✅ Updated scripts/run_all_checks.sh to remove wheel building step

## Already Completed

### ✅ Converted to Commands (Completed)
- `review_sandbox.py` → `essence/commands/review_sandbox.py` ✅
- `monitor_gpu.py` → `essence/commands/monitor_gpu.py` ✅
- `verify_qwen3_quantization.py` → `essence/commands/verify_qwen3.py` ✅
- `download_models.py` → `essence/commands/download_models.py` ✅
- `benchmark_qwen3_performance.py` → `essence/commands/benchmark_qwen3.py` ✅

### ✅ Moved to Tests (Completed)
- `test_*.py` files → `tests/scripts/` ✅ (8 files moved)
- `run_audio_tests.sh` → `tests/scripts/` ✅
- `test_artifact_collection.sh` → `tests/scripts/` ✅
- `test_audio_services.sh` → `tests/scripts/` ✅
- `validate_stt.sh` → `tests/scripts/` ✅

### ✅ Removed (Completed)
- `validate_gateway.sh` - Gateway service removed ✅
- `test_round_trip_gateway.py` - Gateway service removed ✅
- `optimize_database_queries.py` - Database removed ✅
- `encrypt_existing_data.py` - Obsolete ✅
- `profile_performance.py` - Duplicate of benchmark_qwen3_performance.py ✅

## Summary

**Current State:**
- **Keep as Scripts:** 7 scripts (all infrastructure/automation)
- **Convert to Commands:** ✅ All Python tools converted (3 completed: run_benchmarks, download_qwen3 merged, generate_alice_dataset)
- **Move to Tests:** 4 scripts (test utilities)
- **Remove:** 2 scripts (obsolete build scripts)

**Total Remaining Tasks:**
- ✅ All conversions to commands completed
- 4 moves to tests
- 2 removals

## Conversion Priority

1. **✅ High Priority - COMPLETED:**
   - ✅ `run_benchmarks.py` → Command (actively used)

2. **✅ Medium Priority - COMPLETED:**
   - ✅ `download_qwen3.py` → Merged into download-models command

3. **✅ Low Priority - COMPLETED:**
   - ✅ `generate_alice_dataset.py` → Command (used for testing)

**All command conversions completed!** Remaining tasks:
   - Test utilities migration
   - Obsolete script removal

## Notes

- All test utilities should eventually be in `tests/scripts/` or converted to pytest
- Build scripts are obsolete after Poetry migration
- Some scripts reference removed services (gateway, postgres) and need updates
- Shell wrappers like `run_benchmarks.sh` should call commands instead of Python scripts directly
