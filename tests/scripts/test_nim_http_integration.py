#!/usr/bin/env python3
"""
Test script to verify LLMClient HTTP integration with NVIDIA NIM.

This script tests that LLMClient can successfully connect to and use
NIM's HTTP/OpenAI-compatible API endpoint.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from essence.agents.llm_client import LLMClient


def test_nim_http_integration():
    """Test LLMClient with NIM HTTP endpoint."""
    print("=" * 60)
    print("Testing LLMClient HTTP Integration with NVIDIA NIM")
    print("=" * 60)
    print()

    # Use NIM HTTP endpoint
    nim_url = os.getenv("NIM_URL", "http://nim-qwen3:8000")
    model_name = os.getenv("NIM_MODEL_NAME", "Qwen/Qwen3-32B-A3B-Thinking-2507")
    
    print(f"NIM URL: {nim_url}")
    print(f"Model: {model_name}")
    print()

    try:
        # Initialize LLMClient with HTTP endpoint
        print("Initializing LLMClient...")
        client = LLMClient(
            llm_url=nim_url,
            model_name=model_name,
            max_context_length=131072,
            temperature=0.7,
            max_tokens=100,  # Short response for testing
        )
        print("✅ LLMClient initialized")
        print()

        # Test simple generation
        print("Testing text generation...")
        test_prompt = "Say 'Hello, this is a test' and nothing else."
        print(f"Prompt: {test_prompt}")
        print()

        response_chunks = list(
            client.generate(
                prompt=test_prompt,
                system_prompt="You are a helpful assistant.",
                temperature=0.7,
                max_tokens=50,
                stream=False,
            )
        )
        
        response = "".join(response_chunks) if response_chunks else ""
        
        if response:
            print(f"✅ Response received: {response[:200]}...")
            print()
            print("=" * 60)
            print("✅ SUCCESS: LLMClient HTTP integration works!")
            print("=" * 60)
            return 0
        else:
            print("❌ ERROR: No response received")
            return 1

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        if 'client' in locals():
            try:
                client.cleanup()
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")


if __name__ == "__main__":
    sys.exit(test_nim_http_integration())
