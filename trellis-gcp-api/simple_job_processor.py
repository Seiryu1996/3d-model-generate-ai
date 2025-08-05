#!/usr/bin/env python3
"""
Simple Job Processor - processes pending jobs from database

This simple worker directly accesses the database to process jobs.
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime
import sqlite3
import structlog
from enum import Enum

# Simple enum definitions
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class SimpleJobProcessor:
    """Simple job processor that directly accesses SQLite database."""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.db_path = "/app/data/trellis.db"
        
    async def start(self):
        """Start the job processor."""
        self.logger.info("🚀 Simple Job Processor starting...")
        
        # Wait for API to create database
        await asyncio.sleep(10)
        
        # Start processing loop
        await self.process_jobs_loop()
    
    async def process_jobs_loop(self):
        """Main job processing loop."""
        self.logger.info("📋 Checking for pending jobs every 10 seconds...")
        
        while True:
            try:
                # Check for pending jobs
                pending_jobs = await self.get_pending_jobs()
                
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
    
    async def get_pending_jobs(self):
        """Get pending jobs from SQLite database."""
        try:
            if not os.path.exists(self.db_path):
                self.logger.info("Database file not found, waiting...")
                return []
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM jobs 
                WHERE status = ? 
                ORDER BY created_at ASC 
                LIMIT 5
            """, (JobStatus.PENDING.value,))
            
            jobs = cursor.fetchall()
            conn.close()
            
            return [dict(job) for job in jobs]
            
        except Exception as e:
            self.logger.error("Failed to get pending jobs", error=str(e))
            return []
    
    async def process_job(self, job):
        """Process a single job."""
        job_id = job['id']
        job_type = job['job_type']
        
        self.logger.info("🔄 Processing job", job_id=job_id, job_type=job_type)
        
        try:
            # Update status to processing
            await self.update_job_status(job_id, JobStatus.PROCESSING)
            await self.update_job_field(job_id, 'started_at', datetime.utcnow().isoformat())
            
            # Simulate processing
            if job_type == 'text_to_3d':
                await self.process_text_to_3d(job_id, job)
            elif job_type == 'image_to_3d':
                await self.process_image_to_3d(job_id, job)
            else:
                self.logger.warning("Unknown job type", job_type=job_type)
                return
            
            # Mark as completed
            await self.update_job_status(job_id, JobStatus.COMPLETED)
            await self.update_job_field(job_id, 'completed_at', datetime.utcnow().isoformat())
            await self.update_job_field(job_id, 'progress', 1.0)
            
            # Add mock output files
            output_files = json.dumps([{
                "format": "glb",
                "url": f"https://storage.example.com/{job_id}/model.glb",
                "size_bytes": 1500000,
                "filename": f"{job_id}_model.glb"
            }])
            await self.update_job_field(job_id, 'output_files', output_files)
            
            self.logger.info("✅ Job completed successfully", job_id=job_id)
            
        except Exception as e:
            error_message = str(e)
            self.logger.error("❌ Job processing failed", job_id=job_id, error=error_message)
            
            await self.update_job_status(job_id, JobStatus.FAILED)
            await self.update_job_field(job_id, 'error_message', error_message)
    
    async def process_text_to_3d(self, job_id: str, job):
        """Process text-to-3D job."""
        prompt = job.get('input_data', 'Unknown prompt')
        self.logger.info("📝 Processing text-to-3D", job_id=job_id)
        
        stages = [
            (0.1, "Parsing text prompt..."),
            (0.3, "Generating concept..."),
            (0.5, "Creating 3D geometry..."),
            (0.7, "Refining details..."),
            (0.9, "Finalizing model...")
        ]
        
        for progress, message in stages:
            await self.update_job_field(job_id, 'progress', progress)
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
            await self.update_job_field(job_id, 'progress', progress)
            self.logger.info("📊 Progress", job_id=job_id, progress=progress, message=message)
            await asyncio.sleep(2)
    
    async def update_job_status(self, job_id: str, status: JobStatus):
        """Update job status in database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE jobs 
                SET status = ?, updated_at = ? 
                WHERE id = ?
            """, (status.value, datetime.utcnow().isoformat(), job_id))
            
            conn.commit()
            conn.close()
            
            self.logger.info("Updated job status", job_id=job_id, status=status.value)
        except Exception as e:
            self.logger.error("Failed to update job status", job_id=job_id, error=str(e))
    
    async def update_job_field(self, job_id: str, field: str, value):
        """Update a job field in database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(f"""
                UPDATE jobs 
                SET {field} = ?, updated_at = ? 
                WHERE id = ?
            """, (value, datetime.utcnow().isoformat(), job_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error("Failed to update job field", job_id=job_id, field=field, error=str(e))


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
    
    print("🗃️ TRELLIS Simple Job Processor Starting...")
    print("📋 This processor directly accesses SQLite database")
    print("🔄 Checking for pending jobs every 10 seconds...")
    
    processor = SimpleJobProcessor()
    await processor.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Processor stopped by user")
    except Exception as e:
        print(f"❌ Processor failed: {e}")
        sys.exit(1)