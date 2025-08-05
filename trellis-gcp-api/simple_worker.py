#!/usr/bin/env python3
"""
Simple Mock Worker for TRELLIS Job Processing

This is a simplified worker that demonstrates job processing without complex dependencies.
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime
import tempfile
import structlog
import redis
from enum import Enum

# Simple enum definitions
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobType(str, Enum):
    IMAGE_TO_3D = "image_to_3d"
    TEXT_TO_3D = "text_to_3d"

class SimpleWorker:
    """Simple worker that processes mock jobs"""
    
    def __init__(self):
        self.redis_client = None
        self.logger = structlog.get_logger(__name__)
        
    async def start(self):
        """Start the worker process"""
        try:
            # Connect to Redis
            self.redis_client = redis.Redis(
                host='redis',
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
        self.logger.info("Mock Worker started - simulating job processing...")
        
        job_counter = 0
        while True:
            try:
                # Simulate finding and processing a job every 30 seconds
                job_counter += 1
                job_id = f"mock_job_{job_counter}_{int(time.time())}"
                
                self.logger.info(f"Processing mock job {job_id}")
                
                # Simulate job processing stages
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
                    self.logger.info("Processing stage", job_id=job_id, progress=progress, message=message)
                    await asyncio.sleep(2)  # 2 seconds per stage
                
                self.logger.info("Mock job completed successfully", job_id=job_id)
                
                # Wait before processing next mock job
                await asyncio.sleep(20)
                    
            except Exception as e:
                self.logger.error("Error in processing loop", error=str(e))
                await asyncio.sleep(10)


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
    print("📝 This worker simulates job processing without dependencies")
    print("⏱️  Processing time: ~10 seconds per job")
    print("🔄 Simulates continuous job processing...")
    
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