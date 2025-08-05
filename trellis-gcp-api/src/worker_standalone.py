#!/usr/bin/env python3
"""
Simple Worker Process for TRELLIS Job Processing

This worker polls the Redis queue for pending jobs and processes them.
For development/testing, it uses mock processing instead of actual TRELLIS.
"""

import asyncio
import json
import sys
import os
import time
from pathlib import Path
from datetime import datetime
import tempfile

import structlog
import redis

from models.base import JobStatus, JobType, OutputFormat
from repositories.job_repository import get_job_repository
from utils.config import get_settings


class SimpleWorker:
    """Simple worker that processes jobs from Redis queue"""
    
    def __init__(self):
        self.settings = get_settings()
        self.job_repository = get_job_repository()
        self.redis_client = None
        self.logger = structlog.get_logger(__name__)
        
    async def start(self):
        """Start the worker process"""
        try:
            # Connect to Redis
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
            
            # Test connection
            self.redis_client.ping()
            self.logger.info("Connected to Redis successfully")
            
            # Start processing loop
            await self.process_jobs()
            
        except Exception as e:
            self.logger.error("Failed to start worker", error=str(e))
            raise
    
    async def process_jobs(self):
        """Main job processing loop"""
        self.logger.info("Worker started - polling for jobs...")
        
        while True:
            try:
                # Get all pending jobs from repository
                jobs = await self.job_repository.list_jobs(page=1, page_size=100)
                
                pending_jobs = [job for job in jobs['jobs'] if job.status == JobStatus.PENDING]
                
                if pending_jobs:
                    self.logger.info(f"Found {len(pending_jobs)} pending jobs")
                    
                    for job in pending_jobs:
                        try:
                            await self.process_single_job(job)
                        except Exception as e:
                            self.logger.error("Failed to process job", job_id=job.job_id, error=str(e))
                            # Mark job as failed
                            await self.job_repository.update_status(job.job_id, JobStatus.FAILED)
                            await self.job_repository.update_error_message(job.job_id, str(e))
                else:
                    # No jobs, wait before next poll
                    await asyncio.sleep(5)
                    
            except Exception as e:
                self.logger.error("Error in processing loop", error=str(e))
                await asyncio.sleep(5)
    
    async def process_single_job(self, job):
        """Process a single job"""
        self.logger.info("Processing job", job_id=job.job_id, job_type=job.job_type)
        
        # Update status to processing
        await self.job_repository.update_status(job.job_id, JobStatus.PROCESSING)
        await self.job_repository.update_started_at(job.job_id, datetime.utcnow())
        
        try:
            # Mock processing with progress updates
            await self.mock_trellis_processing(job)
            
            # Mark as completed
            await self.job_repository.update_status(job.job_id, JobStatus.COMPLETED)
            await self.job_repository.update_completed_at(job.job_id, datetime.utcnow())
            
            self.logger.info("Job completed successfully", job_id=job.job_id)
            
        except Exception as e:
            self.logger.error("Job processing failed", job_id=job.job_id, error=str(e))
            await self.job_repository.update_status(job.job_id, JobStatus.FAILED)
            await self.job_repository.update_error_message(job.job_id, str(e))
            raise
    
    async def mock_trellis_processing(self, job):
        """Mock TRELLIS processing that simulates 3D model generation"""
        
        job_id = job.job_id
        input_data = job.input_data
        
        # Simulate processing stages
        stages = [
            (0.1, "Loading models..."),
            (0.3, "Processing input..."),
            (0.5, "Generating 3D model..."),
            (0.7, "Converting to output formats..."),
            (0.9, "Uploading results..."),
            (1.0, "Processing complete")
        ]
        
        # Update progress through stages
        for progress, message in stages:
            await self.job_repository.update_progress(job_id, progress)
            self.logger.info("Processing stage", job_id=job_id, progress=progress, message=message)
            
            # Simulate processing time (2 seconds per stage = 10 seconds total)
            await asyncio.sleep(2)
        
        # Create mock output files
        output_files = await self.create_mock_output_files(job)
        
        # Update job with output files
        await self.job_repository.update_output_files(job_id, output_files)
        
        self.logger.info("Mock processing completed", job_id=job_id, output_files=len(output_files))
    
    async def create_mock_output_files(self, job):
        """Create mock output files for testing"""
        
        input_data = job.input_data
        output_formats = input_data.get('output_formats', ['glb'])
        
        output_files = []
        
        for fmt in output_formats:
            # Create mock file content
            if fmt == 'glb':
                content = b'GLB\x02\x00\x00\x00Mock GLB File - TRELLIS API Demo\x00\x00\x00\x00'
                size = len(content)
            elif fmt == 'obj':
                content = '''# Mock OBJ File - TRELLIS API Demo
# Generated from: {}
# Simple cube
v -1.0 -1.0  1.0
v  1.0 -1.0  1.0
v  1.0  1.0  1.0
v -1.0  1.0  1.0
v -1.0 -1.0 -1.0
v  1.0 -1.0 -1.0
v  1.0  1.0 -1.0
v -1.0  1.0 -1.0

f 1 2 3 4
f 8 7 6 5
f 4 3 7 8
f 5 1 4 8
f 5 6 2 1
f 2 6 7 3
'''.format(input_data.get('prompt', 'N/A')).encode()
                size = len(content)
            elif fmt == 'ply':
                content = '''ply
format ascii 1.0
comment Mock PLY File - TRELLIS API Demo
comment Generated from: {}
element vertex 8
property float x
property float y
property float z
end_header
-1.0 -1.0 1.0
1.0 -1.0 1.0
1.0 1.0 1.0
-1.0 1.0 1.0
-1.0 -1.0 -1.0
1.0 -1.0 -1.0
1.0 1.0 -1.0
-1.0 1.0 -1.0
'''.format(input_data.get('prompt', 'N/A')).encode()
                size = len(content)
            else:
                content = f'Mock {fmt.upper()} File - TRELLIS API Demo'.encode()
                size = len(content)
            
            # Create mock output file metadata
            output_file = {
                'format': fmt,
                'url': f'http://localhost:9000/trellis-output-dev/{job.user_id}/{job.job_id}/{fmt}_model.{fmt}',
                'size_bytes': size,
                'filename': f'{job.job_id}_model.{fmt}'
            }
            
            output_files.append(output_file)
            
            self.logger.info("Created mock output file", job_id=job.job_id, format=fmt, size=size)
        
        return output_files


async def main():
    """Main entry point"""
    
    # Setup logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    print("🤖 TRELLIS Mock Worker Starting...")
    print("📝 This worker processes jobs without GPU requirements")
    print("⏱️  Processing time: ~10 seconds per job")
    print("📁 Creates mock GLB/OBJ/PLY files for testing")
    print("🔄 Polling for pending jobs every 5 seconds...")
    
    worker = SimpleWorker()
    await worker.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Worker stopped by user")
    except Exception as e:
        print(f"❌ Worker failed: {e}")
        sys.exit(1)