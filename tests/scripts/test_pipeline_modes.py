#!/usr/bin/env python3
"""
Pipeline Mode Testing Script
Tests the pipeline in different modes:
1. Full Mock Mode - all services pass-through
2. STT/TTS Round-Trip Mode - real TTS/STT for audio validation
"""
import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.test_modes import TestMode, get_configuration, CONFIGURATIONS

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModeTester:
    """Tests pipeline in different modes."""
    
    def __init__(self):
        self.test_mode = TestMode.MODE
        
    def test_mock_mode(self) -> Dict[str, Any]:
        """Test full mock mode - all services pass-through."""
        logger.info("=" * 60)
        logger.info("TESTING: Full Mock Mode")
        logger.info("=" * 60)
        logger.info("All services running in pass-through mode")
        logger.info("Testing: Gateway → STT → Inference → TTS → Gateway")
        logger.info("")
        
        # This would use the comprehensive_pipeline_test.py
        # For now, return a placeholder
        return {
            "mode": "mock",
            "description": "Full mock pass-through mode",
            "status": "not_implemented",
            "note": "Use comprehensive_pipeline_test.py for this mode"
        }
    
    def test_roundtrip_mode(self) -> Dict[str, Any]:
        """Test STT/TTS round-trip mode via Gateway."""
        logger.info("=" * 60)
        logger.info("TESTING: STT/TTS Round-Trip Mode")
        logger.info("=" * 60)
        logger.info("TTS and STT services using real models")
        logger.info("Testing via Gateway: Text → TTS → Audio → Gateway → Audio → STT → Text")
        logger.info("Two conversions tested:")
        logger.info("  1. Input: Text → TTS → Audio (simulating user)")
        logger.info("  2. Output: Gateway Audio → STT → Text (validating response)")
        logger.info("")
        
        # Check if Alice dataset exists
        data_dir = os.getenv('JUNE_DATA_DIR', '/home/rlee/june_data')
        dataset_file = Path(data_dir) / 'datasets' / 'alice_in_wonderland' / 'alice_dataset.json'
        
        if not dataset_file.exists():
            logger.error(f"Dataset file not found: {dataset_file}")
            logger.info("Please run: poetry run -m essence generate-alice-dataset")
            return {
                "mode": "stt_tts_roundtrip",
                "status": "failed",
                "error": "Dataset not found"
            }
        
        # Import the Gateway round-trip tester
        try:
            from test_round_trip_gateway import GatewayRoundTripTester, load_dataset
            
            # Load dataset
            passages = load_dataset(dataset_file)
            if not passages:
                return {
                    "mode": "stt_tts_roundtrip",
                    "status": "failed",
                    "error": "No passages loaded"
                }
            
            # Create tester
            tts_address = os.getenv('TTS_SERVICE_ADDRESS', 'localhost:50053')
            stt_address = os.getenv('STT_SERVICE_ADDRESS', 'localhost:50052')
            gateway_url = os.getenv('GATEWAY_URL', 'http://localhost:8000')
            
            tester = GatewayRoundTripTester(
                tts_address=tts_address,
                stt_address=stt_address,
                gateway_url=gateway_url
            )
            
            # Run tests
            logger.info("Starting Gateway round-trip tests...")
            results = asyncio.run(tester.run_round_trip_test(passages, max_tests=100))
            
            return {
                "mode": "stt_tts_roundtrip",
                "status": "success" if results.get("status") != "failed" else "failed",
                "results": results
            }
            
        except ImportError as e:
            logger.error(f"Failed to import test module: {e}")
            return {
                "mode": "stt_tts_roundtrip",
                "status": "failed",
                "error": f"Import error: {e}"
            }
    
    def print_mode_summary(self):
        """Print current mode configuration."""
        logger.info("=" * 60)
        logger.info("CURRENT TEST MODE CONFIGURATION")
        logger.info("=" * 60)
        
        config = TestMode.get_config_summary()
        logger.info(f"Test Mode: {config['test_mode']}")
        logger.info(f"Gateway Mode: {config['gateway_mode']}")
        logger.info(f"Inference Mode: {config['inference_mode']}")
        logger.info(f"STT Mode: {config['stt_mode']}")
        logger.info(f"TTS Mode: {config['tts_mode']}")
        logger.info("")
        
        if config['test_mode'] == 'mock':
            logger.info("Mode: Full Mock")
            logger.info("  - All services pass-through")
            logger.info("  - Tests deployment and connectivity")
            logger.info("  - No real model inference")
        elif config['test_mode'] == 'stt_tts_roundtrip':
            logger.info("Mode: STT/TTS Round-Trip (via Gateway)")
            logger.info("  - TTS and STT use real models")
            logger.info("  - Gateway and Inference are mocked")
            logger.info("  - Tests: Text → TTS → Audio → Gateway → Audio → STT → Text")
            logger.info("  - Two conversions: Input (Text→TTS→STT) and Output (Audio→STT)")
        logger.info("=" * 60)

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test June Agent pipeline in different modes')
    parser.add_argument('--mode', choices=['mock', 'stt_tts_roundtrip', 'both'], 
                       default=None, help='Test mode to run')
    parser.add_argument('--show-config', action='store_true', 
                       help='Show current configuration and exit')
    
    args = parser.parse_args()
    
    # Create tester
    tester = ModeTester()
    
    # Show configuration
    if args.show_config:
        tester.print_mode_summary()
        # Show available configurations
        logger.info("\nAvailable Configurations:")
        for name, config in CONFIGURATIONS.items():
            logger.info(f"  {name}: {config['description']}")
        return 0
    
    # Determine which mode to test
    if args.mode:
        mode_to_test = args.mode
    else:
        # Use current environment mode
        mode_to_test = TestMode.MODE
    
    results = {}
    
    if mode_to_test == "both":
        # Test both modes
        logger.info("Testing both modes...\n")
        
        # Test mock mode
        logger.info("Setting to mock mode...")
        os.environ['JUNE_TEST_MODE'] = 'mock'
        results['mock'] = tester.test_mock_mode()
        
        logger.info("\n" + "=" * 60 + "\n")
        
        # Test round-trip mode
        logger.info("Setting to STT/TTS round-trip mode...")
        os.environ['JUNE_TEST_MODE'] = 'stt_tts_roundtrip'
        results['stt_tts_roundtrip'] = tester.test_roundtrip_mode()
        
    elif mode_to_test == "mock":
        tester.print_mode_summary()
        results['mock'] = tester.test_mock_mode()
        
    elif mode_to_test == "stt_tts_roundtrip":
        tester.print_mode_summary()
        results['stt_tts_roundtrip'] = tester.test_roundtrip_mode()
    
    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    for mode, result in results.items():
        status = result.get('status', 'unknown')
        logger.info(f"{mode}: {status}")
        if status == "failed" and 'error' in result:
            logger.info(f"  Error: {result['error']}")
    
    logger.info("=" * 60)
    
    # Save results
    data_dir = os.getenv('JUNE_DATA_DIR', '/home/rlee/june_data')
    results_file = Path(data_dir) / 'test_results' / 'mode_test_results.json'
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "test_mode": mode_to_test,
            "results": results
        }, f, indent=2)
    
    logger.info(f"\nResults saved to {results_file}")
    
    # Determine overall success
    all_success = all(r.get('status') == 'success' for r in results.values())
    return 0 if all_success else 1

if __name__ == "__main__":
    exit(main())

