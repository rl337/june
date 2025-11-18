#!/usr/bin/env python3
"""
Test script for GenerateStream gRPC endpoint.

Tests streaming text generation from the inference API.
"""
import asyncio
import sys
import time
import grpc
from typing import List

# Add project root to path
sys.path.insert(0, '/app')

from june_grpc_api.llm_pb2 import (
    GenerationRequest,
    GenerationParameters,
    Context,
)
from june_grpc_api import llm_pb2_grpc


async def test_generate_stream(
    channel: grpc.aio.Channel,
    prompt: str = "Write a short poem about coding.",
    max_tokens: int = 100,
    temperature: float = 0.7,
) -> List[str]:
    """Test GenerateStream endpoint."""
    client = llm_pb2_grpc.LLMInferenceStub(channel)
    
    request = GenerationRequest(
        prompt=prompt,
        params=GenerationParameters(
            max_tokens=max_tokens,
            temperature=temperature,
        ),
        context=Context(),
    )
    
    print(f"Testing GenerateStream with prompt: {prompt[:50]}...")
    print(f"Parameters: max_tokens={max_tokens}, temperature={temperature}")
    print("-" * 80)
    
    tokens = []
    start_time = time.time()
    first_token_time = None
    
    try:
        async for chunk in client.GenerateStream(request, timeout=300.0):
            if first_token_time is None and chunk.token:
                first_token_time = time.time()
                time_to_first_token = first_token_time - start_time
                print(f"\n[Time to first token: {time_to_first_token:.2f}s]")
            
            if chunk.token:
                print(chunk.token, end="", flush=True)
                tokens.append(chunk.token)
            
            if chunk.is_final:
                elapsed = time.time() - start_time
                total_tokens = len(tokens)
                tokens_per_second = total_tokens / elapsed if elapsed > 0 else 0
                
                print(f"\n\n[Finished]")
                print(f"Total tokens: {total_tokens}")
                print(f"Total time: {elapsed:.2f}s")
                print(f"Tokens/second: {tokens_per_second:.2f}")
                print(f"Finish reason: {chunk.finish_reason}")
                break
    except grpc.RpcError as e:
        print(f"\n[Error] gRPC error: {e.code()} - {e.details()}")
        return []
    except Exception as e:
        print(f"\n[Error] {type(e).__name__}: {e}")
        return []
    
    return tokens


async def main():
    """Main test function."""
    # Connect to inference API
    inference_api_url = "inference-api:50051"
    
    print("=" * 80)
    print("Testing GenerateStream Endpoint")
    print("=" * 80)
    print(f"Connecting to: {inference_api_url}")
    print()
    
    async with grpc.aio.insecure_channel(inference_api_url) as channel:
        # Test 1: Short prompt
        print("\n[Test 1: Short prompt]")
        tokens1 = await test_generate_stream(
            channel,
            prompt="Say hello in one sentence.",
            max_tokens=50,
            temperature=0.7,
        )
        
        print("\n" + "=" * 80)
        
        # Test 2: Longer prompt
        print("\n[Test 2: Longer prompt]")
        tokens2 = await test_generate_stream(
            channel,
            prompt="Write a haiku about artificial intelligence.",
            max_tokens=50,
            temperature=0.8,
        )
        
        print("\n" + "=" * 80)
        
        # Test 3: Coding prompt
        print("\n[Test 3: Coding prompt]")
        tokens3 = await test_generate_stream(
            channel,
            prompt="Write a Python function to calculate fibonacci numbers.",
            max_tokens=100,
            temperature=0.5,
        )
        
        print("\n" + "=" * 80)
        print("\n[All tests completed]")
        
        # Summary
        print("\nSummary:")
        print(f"  Test 1 tokens: {len(tokens1)}")
        print(f"  Test 2 tokens: {len(tokens2)}")
        print(f"  Test 3 tokens: {len(tokens3)}")


if __name__ == "__main__":
    asyncio.run(main())
