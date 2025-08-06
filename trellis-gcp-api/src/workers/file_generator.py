#!/usr/bin/env python3
"""
File Generator - creates actual 3D model files and uploads to MinIO
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile
from minio import Minio
from minio.error import S3Error
import structlog

logger = structlog.get_logger(__name__)

class FileGenerator:
    """Generates actual 3D model files and uploads to MinIO."""
    
    def __init__(self, minio_endpoint="minio:9000", access_key="minioadmin", secret_key="minioadmin"):
        self.minio_client = Minio(
            minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False
        )
        
    async def generate_glb_file(self, job_id: str, prompt: str, output_path: str) -> str:
        """Generate a simple GLB file (mock implementation)."""
        
        # Create a simple GLB file with basic content
        glb_content = self._create_mock_glb(prompt)
        
        # Write to file
        with open(output_path, 'wb') as f:
            f.write(glb_content)
            
        return output_path
    
    def _create_mock_glb(self, prompt: str) -> bytes:
        """Create a mock GLB file content."""
        # This is a very basic mock - in reality you'd generate actual 3D content
        header = b'glTF'  # GLB header
        version = (2).to_bytes(4, 'little')
        length = (1000).to_bytes(4, 'little')  # File length
        
        # JSON chunk
        json_data = {
            "asset": {"version": "2.0"},
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
            "bufferViews": [{"buffer": 0, "byteLength": 36, "target": 34962}],
            "buffers": [{"byteLength": 36}],
            "_prompt": prompt,
            "_generated_at": datetime.utcnow().isoformat()
        }
        
        json_str = json.dumps(json_data, separators=(',', ':'))
        json_bytes = json_str.encode('utf-8')
        
        # Pad to 4-byte boundary
        padding = b'\x00' * (4 - (len(json_bytes) % 4)) if len(json_bytes) % 4 else b''
        json_bytes += padding
        
        json_chunk_length = len(json_bytes).to_bytes(4, 'little')
        json_chunk_type = b'JSON'
        
        # Binary chunk (minimal vertex data)
        binary_data = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80?\x00\x00\x80?\x00\x00\x00\x00\x00\x00\x80?\x00\x00\x80?\x00\x00\x80?'
        binary_chunk_length = len(binary_data).to_bytes(4, 'little')
        binary_chunk_type = b'BIN\x00'
        
        # Combine all parts
        glb_data = (header + version + length + 
                   json_chunk_length + json_chunk_type + json_bytes +
                   binary_chunk_length + binary_chunk_type + binary_data)
        
        return glb_data
    
    async def upload_to_minio(self, job_id: str, file_path: str, filename: str) -> str:
        """Upload file to MinIO and return public URL."""
        try:
            bucket_name = "trellis-output"
            object_name = f"{job_id}/{filename}"
            
            # Ensure bucket exists
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)
                # Set public read policy
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                        }
                    ]
                }
                self.minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
            
            # Upload file
            self.minio_client.fput_object(bucket_name, object_name, file_path)
            
            # Return public URL
            public_url = f"http://localhost:9100/{bucket_name}/{object_name}"
            
            logger.info(
                "File uploaded to MinIO",
                job_id=job_id,
                filename=filename,
                url=public_url
            )
            
            return public_url
            
        except S3Error as e:
            logger.error("Failed to upload to MinIO", job_id=job_id, error=str(e))
            raise
    
    async def generate_and_upload_file(self, job_id: str, prompt: str, format: str = "glb") -> dict:
        """Generate 3D file and upload to MinIO storage."""
        
        with tempfile.NamedTemporaryFile(suffix=f'.{format}', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            # Generate the file
            if format.lower() == "glb":
                await self.generate_glb_file(job_id, prompt, tmp_path)
            else:
                # For other formats, create a placeholder
                with open(tmp_path, 'w') as f:
                    f.write(f"# 3D Model generated from prompt: {prompt}\n")
                    f.write(f"# Job ID: {job_id}\n")
                    f.write(f"# Format: {format}\n")
                    f.write(f"# Generated at: {datetime.utcnow().isoformat()}\n")
            
            # Get file size
            file_size = Path(tmp_path).stat().st_size
            
            # Upload to MinIO
            filename = f"{job_id}_model.{format}"
            public_url = await self.upload_to_minio(job_id, tmp_path, filename)
            
            return {
                "format": format,
                "url": public_url,
                "size_bytes": file_size,
                "filename": filename
            }
            
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)


async def main():
    """Test the file generator."""
    generator = FileGenerator()
    
    test_job_id = "test-job-123"
    test_prompt = "A beautiful red dragon"
    
    result = await generator.generate_and_upload_file(test_job_id, test_prompt)
    print(f"Generated file: {result}")


if __name__ == "__main__":
    asyncio.run(main())