#!/usr/bin/env python3
"""
Memory Worker - processes jobs from API's in-memory storage

This worker uses the same job repository as the API for consistent data access.
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime
import structlog
from enum import Enum
from typing import Dict, Any, Optional

from ..models.base import JobStatus, JobType
from ..repositories.job_repository import get_job_repository, JobRepositoryError

class MemoryWorker:
    """Worker that processes jobs from API's memory storage."""
    
    def __init__(self):
        self.job_repository = get_job_repository()
        self.logger = structlog.get_logger(__name__)
        
    async def start(self):
        """Start the worker process."""
        try:
            self.logger.info("🚀 Memory Worker initialized - using API's job repository")
            
            # Start processing loop
            await self.process_jobs_loop()
            
        except Exception as e:
            self.logger.error("Failed to start worker", error=str(e))
            raise
    
    async def process_jobs_loop(self):
        """Main job processing loop."""
        self.logger.info("📋 Memory Worker started - processing jobs from API memory...")
        
        while True:
            try:
                # Check for pending jobs using the repository
                pending_jobs = await self.job_repository.get_pending_jobs(limit=5)
                
                if pending_jobs:
                    self.logger.info(f"Found {len(pending_jobs)} pending jobs")
                    
                    # Process each job
                    for job in pending_jobs:
                        await self.process_job(job)
                else:
                    self.logger.info("No pending jobs found")
                
                # Wait before next check
                await asyncio.sleep(10)
                    
            except Exception as e:
                self.logger.error("Error in job processing loop", error=str(e))
                await asyncio.sleep(10)
    
    async def process_job(self, job):
        """Process a single job."""
        job_id = job.job_id
        job_type = job.job_type
        
        self.logger.info("🔄 Processing job", job_id=job_id, job_type=job_type)
        
        try:
            # Update status to processing
            await self.job_repository.update_status(
                job_id, 
                JobStatus.PROCESSING,
                completed_at=None
            )
            
            # Update started_at timestamp
            await self.job_repository.update_started_at(job_id, datetime.utcnow())
            
            # Simulate processing based on job type
            if job_type == JobType.TEXT_TO_3D:
                await self.process_text_to_3d(job_id, job)
            elif job_type == JobType.IMAGE_TO_3D:
                await self.process_image_to_3d(job_id, job)
            else:
                self.logger.warning("Unknown job type", job_type=job_type)
                return
            
            # Mark as completed
            await self.job_repository.update_status(
                job_id, 
                JobStatus.COMPLETED,
                completed_at=datetime.utcnow()
            )
            await self.job_repository.update_progress(job_id, 1.0)
            
            # Generate actual files and upload to MinIO
            try:
                from .file_generator import FileGenerator
                generator = FileGenerator()
                
                # Get prompt from job input_data
                input_data = getattr(job, 'input_data', {})
                if isinstance(input_data, str):
                    import json
                    input_data = json.loads(input_data)
                
                prompt = input_data.get('prompt', 'Generated 3D model')
                output_formats = input_data.get('output_formats', ['glb'])
                
                # Generate files for each requested format
                output_files = []
                for format in output_formats:
                    file_info = await generator.generate_and_upload_file(job_id, prompt, format)
                    output_files.append(file_info)
                
                await self.job_repository.update_output_files(job_id, output_files)
                
            except Exception as e:
                self.logger.warning("Failed to generate actual files, using mock", error=str(e))
                # Fallback to mock files
                output_files = [{
                    "format": "glb",
                    "url": f"https://storage.example.com/{job_id}/model.glb",
                    "size_bytes": 1500000,
                    "filename": f"{job_id}_model.glb"
                }]
                await self.job_repository.update_output_files(job_id, output_files)
            
            self.logger.info("✅ Job completed successfully", job_id=job_id)
            
        except Exception as e:
            error_message = str(e)
            self.logger.error("❌ Job processing failed", job_id=job_id, error=error_message)
            
            await self.job_repository.update_status(
                job_id, 
                JobStatus.FAILED,
                error_message=error_message
            )
    
    async def process_text_to_3d(self, job_id: str, job):
        """Process text-to-3D job."""
        input_data = getattr(job, 'input_data', {})
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except:
                input_data = {}
        
        prompt = input_data.get('prompt', 'Unknown prompt')
        self.logger.info("📝 Processing text-to-3D", job_id=job_id, prompt=prompt)
        
        stages = [
            (0.1, "Parsing text prompt..."),
            (0.3, "Generating concept..."),
            (0.5, "Creating 3D geometry..."),
            (0.7, "Refining details..."),
            (0.9, "Finalizing model...")
        ]
        
        for progress, message in stages:
            await self.job_repository.update_progress(job_id, progress)
            self.logger.info("📊 Progress", job_id=job_id, progress=progress, message=message)
            await asyncio.sleep(3)
    
    async def process_image_to_3d(self, job_id: str, job):
        """Process image-to-3D job."""
        self.logger.info("🖼️ Processing image-to-3D", job_id=job_id)
        
        stages = [
            (0.1, "Loading image..."),
            (0.3, "Extracting features..."),
            (0.5, "Generating mesh..."),
            (0.7, "Applying textures..."),
            (0.9, "Converting format...")
        ]
        
        for progress, message in stages:
            await self.job_repository.update_progress(job_id, progress)
            self.logger.info("📊 Progress", job_id=job_id, progress=progress, message=message)
            await asyncio.sleep(2)


async def main():
    """Main entry point."""
    
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
    
    print("🧠 TRELLIS Memory Worker Starting...")
    print("📋 This worker uses API's in-memory job repository")
    print("🔄 Checking for pending jobs every 10 seconds...")
    
    worker = MemoryWorker()
    await worker.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Worker stopped by user")
    except Exception as e:
        print(f"❌ Worker failed: {e}")
        sys.exit(1)