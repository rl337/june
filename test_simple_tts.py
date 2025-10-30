#!/usr/bin/env python3
"""
Simple TTS test script to verify espeak functionality.
"""
import subprocess
import tempfile
import os
import sys

def test_espeak():
    """Test espeak functionality."""
    print("Testing espeak...")
    
    # Test text
    test_text = "Hello, this is a test of the text to speech system."
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        temp_path = temp_file.name
    
    try:
        # Run espeak command
        cmd = [
            'espeak',
            '-s', '16000',  # Sample rate
            '-w', temp_path,
            test_text
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"espeak failed: {result.stderr}")
            return False
        
        # Check if file was created and has content
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            print(f"✅ espeak test successful! Generated {os.path.getsize(temp_path)} bytes")
            return True
        else:
            print("❌ espeak test failed: No output file created")
            return False
            
    except Exception as e:
        print(f"❌ espeak test failed: {e}")
        return False
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.unlink(temp_path)

if __name__ == "__main__":
    success = test_espeak()
    sys.exit(0 if success else 1)



