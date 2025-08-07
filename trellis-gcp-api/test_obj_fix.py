#!/usr/bin/env python3
"""Test OBJ file generation with fixed formatting."""

import asyncio
import tempfile
import os
from pathlib import Path

# Add the source directory to path
import sys
sys.path.insert(0, '/mnt/c/Users/上畑成龍/desktop/dev/3d-model-env/trellis-gcp-api')

from src.workers.cpu_ai_generator import CPUAIGenerator

async def test_obj_generation():
    """Test OBJ file generation."""
    
    generator = CPUAIGenerator()
    
    # Create temporary file for output
    with tempfile.NamedTemporaryFile(suffix='.obj', delete=False) as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        print("Testing OBJ file generation...")
        
        # Generate OBJ file
        result_path = await generator.generate_3d_from_text(
            job_id="test_obj_fix",
            prompt="test crystal structure",
            output_path=tmp_path,
            format="obj"
        )
        
        print(f"Generated OBJ file at: {result_path}")
        
        # Check file exists and has content
        if os.path.exists(result_path):
            file_size = os.path.getsize(result_path)
            print(f"File size: {file_size} bytes")
            
            # Read first few lines to check format
            with open(result_path, 'r') as f:
                first_lines = f.readlines()[:10]
            
            print("First 10 lines of OBJ file:")
            for i, line in enumerate(first_lines):
                print(f"{i+1:2d}: {repr(line)}")
            
            # Check for proper newlines (should be actual newlines, not escaped)
            has_proper_newlines = all('\n' in line for line in first_lines if line.strip())
            has_escaped_newlines = any('\\n' in line.replace('\n', '') for line in first_lines)
            
            print(f"Has proper newlines: {has_proper_newlines}")
            print(f"Has escaped \\n literals: {has_escaped_newlines}")
            
            if not has_escaped_newlines:
                print("✅ OBJ file format is correct!")
            else:
                print("❌ OBJ file still has escaped newline literals")
        else:
            print("❌ OBJ file was not created")
            
    except Exception as e:
        print(f"❌ Error during OBJ generation: {e}")
        
    finally:
        # Clean up
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

if __name__ == "__main__":
    asyncio.run(test_obj_generation())