#!/usr/bin/env python3
"""
Main script to run load tests and generate reports.

Supports:
- Locust-based REST/WebSocket tests
- gRPC load tests
- Report generation and comparison
"""
import argparse
import subprocess
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """Load load test configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_locust_test(
    locust_file: str,
    host: str,
    users: int,
    spawn_rate: int,
    duration: str,
    output_dir: Path,
):
    """Run Locust load test."""
    logger.info(f"Running Locust test: {locust_file}")
    logger.info(f"  Host: {host}")
    logger.info(f"  Users: {users}, Spawn rate: {spawn_rate}, Duration: {duration}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate report filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"locust_report_{timestamp}"

    # Run Locust
    cmd = [
        "locust",
        "-f",
        locust_file,
        "--host",
        host,
        "--users",
        str(users),
        "--spawn-rate",
        str(spawn_rate),
        "--run-time",
        duration,
        "--headless",
        "--html",
        str(output_dir / f"{report_name}.html"),
        "--csv",
        str(output_dir / report_name),
        "--json",
        str(output_dir / f"{report_name}.json"),
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Locust test completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Locust test failed: {e}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return False


def run_grpc_test(config: dict, output_dir: Path):
    """Run gRPC load test."""
    logger.info("Running gRPC load test")

    grpc_config = config.get("services", {}).get("grpc", {})

    cmd = [
        sys.executable,
        "load_tests/grpc/grpc_load_test.py",
        "--inference-host",
        grpc_config.get("inference_api", {}).get("host", "localhost:50051"),
        "--stt-host",
        grpc_config.get("stt", {}).get("host", "localhost:50052"),
        "--tts-host",
        grpc_config.get("tts", {}).get("host", "localhost:50053"),
    ]

    # Get scenario config (use first available or default)
    scenario_name = (
        list(config.get("scenarios", {}).keys())[0]
        if config.get("scenarios")
        else "baseline"
    )
    scenario = config.get("scenarios", {}).get(scenario_name, {})

    cmd.extend(
        [
            "--users",
            str(scenario.get("users", 10)),
            "--duration",
            str(int(scenario.get("duration", "5m").rstrip("m")) * 60),
            "--spawn-rate",
            str(scenario.get("spawn_rate", 2)),
        ]
    )

    try:
        result = subprocess.run(cmd, check=True, cwd=Path(__file__).parent.parent)
        logger.info("gRPC test completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"gRPC test failed: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run load tests for June services")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config" / "load_test_config.yaml",
        help="Path to load test configuration file",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Scenario to run (baseline, target, ramp_up, spike, sustained)",
    )
    parser.add_argument(
        "--test-type",
        type=str,
        choices=["rest", "websocket", "grpc", "all"],
        default="all",
        help="Type of test to run",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "reports",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--host", type=str, help="Override Gateway host (default from config)"
    )

    args = parser.parse_args()

    # Load configuration
    if not args.config.exists():
        logger.error(f"Configuration file not found: {args.config}")
        return 1

    config = load_config(args.config)

    # Determine scenario
    scenario_name = args.scenario or "baseline"
    if scenario_name not in config.get("scenarios", {}):
        logger.error(f"Scenario '{scenario_name}' not found in configuration")
        return 1

    scenario = config["scenarios"][scenario_name]
    logger.info(f"Running scenario: {scenario_name}")
    logger.info(f"  Description: {scenario.get('description', 'N/A')}")

    # Get host
    host = args.host or config.get("services", {}).get("gateway", {}).get(
        "host", "http://localhost:8000"
    )

    # Create output directory
    output_dir = (
        args.output_dir / scenario_name / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Run REST tests
    if args.test_type in ["rest", "all"]:
        locust_file = Path(__file__).parent / "locust" / "gateway_rest.py"
        if locust_file.exists():
            success = run_locust_test(
                str(locust_file),
                host,
                scenario["users"],
                scenario["spawn_rate"],
                scenario["duration"],
                output_dir,
            )
            results["rest"] = success
        else:
            logger.warning(f"Locust file not found: {locust_file}")

    # Run WebSocket tests
    if args.test_type in ["websocket", "all"]:
        locust_file = Path(__file__).parent / "locust" / "gateway_websocket.py"
        if locust_file.exists():
            success = run_locust_test(
                str(locust_file),
                host,
                scenario["users"],
                scenario["spawn_rate"],
                scenario["duration"],
                output_dir,
            )
            results["websocket"] = success
        else:
            logger.warning(f"Locust file not found: {locust_file}")

    # Run gRPC tests
    if args.test_type in ["grpc", "all"]:
        success = run_grpc_test(config, output_dir)
        results["grpc"] = success

    # Summary
    print("\n" + "=" * 80)
    print("Load Test Summary")
    print("=" * 80)
    for test_type, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{test_type.upper()}: {status}")
    print(f"\nReports saved to: {output_dir}")
    print("=" * 80)

    # Return non-zero if any test failed
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
