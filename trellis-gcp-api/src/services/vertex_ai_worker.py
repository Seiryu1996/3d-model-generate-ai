"""
Vertex AI Worker Service for TRELLIS Job Processing

This service receives jobs from Cloud Tasks and processes them using TRELLIS on Vertex AI.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import structlog
from google.cloud import tasks_v2, storage
from google.cloud.exceptions import GoogleCloudError

from ..models.base import JobStatus, JobType, OutputFormat
from ..models.job import Job
from ..repositories.job_repository import get_job_repository
from ..utils.config import get_settings
from ..utils.storage_adapter import get_storage_manager
from .trellis_service import get_trellis_service
from .model_converter import get_model_converter_service


logger = structlog.get_logger(__name__)


class VertexAIWorkerError(Exception):
    """Base exception for Vertex AI worker errors."""
    pass


class VertexAIWorkerService:
    """Service for processing TRELLIS jobs on Vertex AI."""
    
    def __init__(self):
        self.settings = get_settings()
        self.job_repository = get_job_repository()
        self.storage_manager = get_storage_manager()
        self.trellis_service = get_trellis_service()
        self.model_converter = get_model_converter_service()
        
        # Cloud Tasks client for receiving jobs
        self.tasks_client = tasks_v2.CloudTasksClient()
        self.queue_name = self.tasks_client.queue_path(
            self.settings.GOOGLE_CLOUD_PROJECT,
            self.settings.CLOUD_TASKS_LOCATION,
            self.settings.CLOUD_TASKS_QUEUE
        )
        
    async def start_worker(self) -> None:
        """Start the Vertex AI worker to process jobs."""
        logger.info("Starting Vertex AI worker", queue=self.queue_name)
        
        try:
            # Initialize connections
            await self._initialize_worker()
            
            # Start processing loop
            await self._process_jobs_loop()
            
        except Exception as e:
            logger.error("Failed to start Vertex AI worker", error=str(e))
            raise VertexAIWorkerError(f"Failed to start worker: {e}")
    
    async def _initialize_worker(self) -> None:
        """Initialize worker connections and resources."""
        try:
            # Verify Cloud Tasks queue exists
            queue = self.tasks_client.get_queue(name=self.queue_name)
            logger.info("Connected to Cloud Tasks queue", queue=queue.name)
            
            # Initialize storage connections
            await self.storage_manager.initialize()
            logger.info("Storage manager initialized")
            
            # Initialize TRELLIS service
            await self.trellis_service.initialize()
            logger.info("TRELLIS service initialized")
            
        except Exception as e:
            logger.error("Failed to initialize worker", error=str(e))
            raise
    
    async def _process_jobs_loop(self) -> None:
        """Main job processing loop."""
        logger.info("Worker started - listening for jobs...")
        
        while True:
            try:
                # Pull tasks from Cloud Tasks
                request = tasks_v2.PullTasksRequest(
                    parent=self.queue_name,
                    max_tasks=10,
                    response_view=tasks_v2.Task.View.FULL
                )
                
                response = self.tasks_client.pull_tasks(request=request)
                
                if response.tasks:
                    logger.info(f"Received {len(response.tasks)} tasks")
                    
                    # Process tasks concurrently
                    tasks = [
                        self._process_task(task) 
                        for task in response.tasks
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # No tasks available, wait before next pull
                    await asyncio.sleep(5)
                    
            except Exception as e:
                logger.error("Error in job processing loop", error=str(e))
                await asyncio.sleep(10)
    
    async def _process_task(self, task: tasks_v2.Task) -> None:
        """Process a single Cloud Task."""
        task_name = task.name
        
        try:
            # Parse task payload
            payload = json.loads(task.http_request.body.decode('utf-8'))
            job_id = payload.get('job_id')
            
            if not job_id:
                logger.error("Task missing job_id", task_name=task_name)
                self._acknowledge_task(task_name)
                return
            
            logger.info("Processing task", task_name=task_name, job_id=job_id)
            
            # Process the job
            await self._process_job(payload)
            
            # Acknowledge successful processing
            self._acknowledge_task(task_name)
            logger.info("Task completed", task_name=task_name, job_id=job_id)
            
        except Exception as e:
            logger.error("Task processing failed", task_name=task_name, error=str(e))
            
            # Handle task failure
            job_id = None
            try:
                payload = json.loads(task.http_request.body.decode('utf-8'))
                job_id = payload.get('job_id')
            except:
                pass
            
            if job_id:
                await self._handle_job_failure(job_id, str(e))
            
            # Acknowledge task to prevent redelivery
            self._acknowledge_task(task_name)
    
    def _acknowledge_task(self, task_name: str) -> None:
        """Acknowledge a task to remove it from the queue."""
        try:
            self.tasks_client.acknowledge_task(
                request=tasks_v2.AcknowledgeTaskRequest(name=task_name)
            )
        except Exception as e:
            logger.error("Failed to acknowledge task", task_name=task_name, error=str(e))
    
    async def _process_job(self, payload: Dict[str, Any]) -> None:
        """Process a TRELLIS job."""
        job_id = payload['job_id']
        user_id = payload['user_id']
        job_type = payload['job_type']
        input_data = payload['input_data']
        
        logger.info("Starting job processing", job_id=job_id, job_type=job_type)
        
        try:
            # Update job status to processing
            await self.job_repository.update_status(job_id, JobStatus.PROCESSING)
            await self.job_repository.update_started_at(job_id, datetime.utcnow())
            
            # Process based on job type
            if job_type == JobType.IMAGE_TO_3D.value:
                result = await self._process_image_to_3d(job_id, input_data)
            elif job_type == JobType.TEXT_TO_3D.value:
                result = await self._process_text_to_3d(job_id, input_data)
            else:
                raise VertexAIWorkerError(f"Unknown job type: {job_type}")
            
            # Convert and upload results
            output_files = await self._process_results(
                job_id, user_id, result, input_data
            )
            
            # Update job with results
            await self.job_repository.update_status(job_id, JobStatus.COMPLETED)
            await self.job_repository.update_completed_at(job_id, datetime.utcnow())
            await self.job_repository.update_output_files(job_id, output_files)
            await self.job_repository.update_progress(job_id, 1.0)
            
            logger.info("Job completed successfully", job_id=job_id)
            
        except Exception as e:
            logger.error("Job processing failed", job_id=job_id, error=str(e))
            await self._handle_job_failure(job_id, str(e))
            raise
    
    async def _process_image_to_3d(self, job_id: str, input_data: Dict[str, Any]) -> Any:
        """Process image-to-3D job using TRELLIS."""
        logger.info("Processing image-to-3D job", job_id=job_id)
        
        # Update progress
        await self.job_repository.update_progress(job_id, 0.1)
        
        try:
            # Download input image from storage
            image_url = input_data.get('image_url')
            if not image_url:
                raise VertexAIWorkerError("Missing image_url in input data")
            
            # Process with TRELLIS
            await self.job_repository.update_progress(job_id, 0.3)
            
            result = await self.trellis_service.process_image_to_3d(
                image_url=image_url,
                quality=input_data.get('quality', 'balanced'),
                progress_callback=lambda p: self.job_repository.update_progress(job_id, 0.3 + p * 0.4)
            )
            
            await self.job_repository.update_progress(job_id, 0.7)
            
            return result
            
        except Exception as e:
            logger.error("Image-to-3D processing failed", job_id=job_id, error=str(e))
            raise
    
    async def _process_text_to_3d(self, job_id: str, input_data: Dict[str, Any]) -> Any:
        """Process text-to-3D job using TRELLIS."""
        logger.info("Processing text-to-3D job", job_id=job_id)
        
        # Update progress
        await self.job_repository.update_progress(job_id, 0.1)
        
        try:
            prompt = input_data.get('prompt')
            negative_prompt = input_data.get('negative_prompt', '')
            
            if not prompt:
                raise VertexAIWorkerError("Missing prompt in input data")
            
            # Process with TRELLIS
            await self.job_repository.update_progress(job_id, 0.3)
            
            result = await self.trellis_service.process_text_to_3d(
                prompt=prompt,
                negative_prompt=negative_prompt,
                quality=input_data.get('quality', 'balanced'),
                progress_callback=lambda p: self.job_repository.update_progress(job_id, 0.3 + p * 0.4)
            )
            
            await self.job_repository.update_progress(job_id, 0.7)
            
            return result
            
        except Exception as e:
            logger.error("Text-to-3D processing failed", job_id=job_id, error=str(e))
            raise
    
    async def _process_results(
        self, 
        job_id: str, 
        user_id: str, 
        trellis_result: Any, 
        input_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Process TRELLIS results and upload to storage."""
        logger.info("Processing results", job_id=job_id)
        
        try:
            # Get requested output formats
            output_formats = input_data.get('output_formats', ['glb'])
            quality_settings = input_data.get('quality_settings', {})
            
            # Convert to requested formats
            await self.job_repository.update_progress(job_id, 0.8)
            
            converted_files = await self.model_converter.convert_model(
                input_data=trellis_result,
                target_formats=[OutputFormat(fmt) for fmt in output_formats],
                job_id=job_id,
                quality_settings=quality_settings
            )
            
            # Upload files to storage
            await self.job_repository.update_progress(job_id, 0.9)
            
            output_files = []
            bucket_names = self.storage_manager.get_bucket_names()
            
            for fmt, file_path in converted_files:
                # Upload to output bucket
                object_name = f"{user_id}/{job_id}/{fmt.value}_model.{fmt.value}"
                
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                url = await self.storage_manager.storage.upload_from_bytes(
                    bucket_names['output'],
                    file_data,
                    object_name,
                    f'model/{fmt.value}'
                )
                
                output_files.append({
                    'format': fmt.value,
                    'url': url,
                    'size_bytes': len(file_data),
                    'filename': f'{job_id}_model.{fmt.value}'
                })
                
                # Clean up temporary file
                file_path.unlink(missing_ok=True)
            
            logger.info("Results processed successfully", job_id=job_id, files=len(output_files))
            return output_files
            
        except Exception as e:
            logger.error("Result processing failed", job_id=job_id, error=str(e))
            raise
    
    async def _handle_job_failure(self, job_id: str, error_message: str) -> None:
        """Handle job failure."""
        try:
            await self.job_repository.update_status(job_id, JobStatus.FAILED)
            await self.job_repository.update_error_message(job_id, error_message)
            logger.info("Job marked as failed", job_id=job_id)
        except Exception as e:
            logger.error("Failed to update job failure status", job_id=job_id, error=str(e))


# Global service instance
_vertex_ai_worker_service = None


def get_vertex_ai_worker_service() -> VertexAIWorkerService:
    """Get cached Vertex AI worker service instance."""
    global _vertex_ai_worker_service
    if _vertex_ai_worker_service is None:
        _vertex_ai_worker_service = VertexAIWorkerService()
    return _vertex_ai_worker_service


async def main():
    """Main entry point for Vertex AI worker."""
    import sys
    
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
    
    logger.info("🚀 Starting Vertex AI TRELLIS Worker")
    
    try:
        worker = get_vertex_ai_worker_service()
        await worker.start_worker()
    except KeyboardInterrupt:
        logger.info("👋 Worker stopped by user")
    except Exception as e:
        logger.error("❌ Worker failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())