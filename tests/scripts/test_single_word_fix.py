#!/usr/bin/env python3
"""Quick test to verify single-word recognition fix."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from test_validate_tts_stt import TtsSttValidator

async def main():
    is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"
    
    if is_docker:
        tts_address = os.getenv("TTS_URL", "tts:50053").replace("grpc://", "")
        stt_address = os.getenv("STT_URL", "stt:50052").replace("grpc://", "")
    else:
        tts_address = os.getenv("TTS_URL", "localhost:50053").replace("grpc://", "")
        stt_address = os.getenv("STT_URL", "localhost:50052").replace("grpc://", "")
    
    validator = TtsSttValidator(tts_address=tts_address, stt_address=stt_address, tolerance="contains")
    
    # Test problematic words
    test_words = ["World", "Hello", "Test", "Yes", "No", "Go", "Stop"]
    
    print("Testing single-word recognition:")
    print("-" * 60)
    passed = 0
    for word in test_words:
        success, input_text, output_text = await validator.test_tts_round_trip(word, verbose=True)
        if success:
            passed += 1
        print()
    
    print(f"Results: {passed}/{len(test_words)} passed")
    sys.exit(0 if passed == len(test_words) else 1)

if __name__ == "__main__":
    asyncio.run(main())


