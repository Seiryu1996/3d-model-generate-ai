"""
GCP client utilities for Cloud Storage, Firestore, and Cloud Tasks.
"""
import os
from typing import Optional, Dict, Any
from functools import lru_cache

from google.cloud import storage
from google.cloud import firestore
from google.cloud import tasks_v2
from google.cloud import logging as cloud_logging
from google.cloud import monitoring_v3
from google.cloud import error_reporting
import structlog

from .config import get_settings


logger = structlog.get_logger(__name__)


class GCPClientError(Exception):
    """Base exception for GCP client errors."""
    pass


class CloudStorageClient:
    """Cloud Storage client wrapper."""
    
    def __init__(self, project_id: Optional[str] = None):
        self.settings = get_settings()
        self.project_id = project_id or self.settings.GOOGLE_CLOUD_PROJECT
        self._client: Optional[storage.Client] = None
    
    @property
    def client(self) -> storage.Client:
        """Get Cloud Storage client instance."""
        if self._client is None:
            try:
                if self.settings.GOOGLE_APPLICATION_CREDENTIALS:
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.settings.GOOGLE_APPLICATION_CREDENTIALS
                
                self._client = storage.Client(project=self.project_id)
                logger.info("Cloud Storage client initialized", project_id=self.project_id)
            except Exception as e:
                logger.error("Failed to initialize Cloud Storage client", error=str(e))
                raise GCPClientError(f"Failed to initialize Cloud Storage client: {e}")
        
        return self._client
    
    def get_bucket(self, bucket_name: str) -> storage.Bucket:
        """Get a storage bucket."""
        try:
            bucket = self.client.bucket(bucket_name)
            # Test bucket access
            bucket.exists()
            return bucket
        except Exception as e:
            logger.error("Failed to access bucket", bucket_name=bucket_name, error=str(e))
            raise GCPClientError(f"Failed to access bucket {bucket_name}: {e}")
    
    def upload_file(self, bucket_name: str, source_file: str, destination_name: str) -> str:
        """Upload a file to Cloud Storage."""
        try:
            bucket = self.get_bucket(bucket_name)
            blob = bucket.blob(destination_name)
            blob.upload_from_filename(source_file)
            
            logger.info(
                "File uploaded to Cloud Storage",
                bucket=bucket_name,
                destination=destination_name,
                source=source_file
            )
            
            return f"gs://{bucket_name}/{destination_name}"
        except Exception as e:
            logger.error(
                "Failed to upload file",
                bucket=bucket_name,
                destination=destination_name,
                error=str(e)
            )
            raise GCPClientError(f"Failed to upload file: {e}")
    
    def upload_from_bytes(self, bucket_name: str, data: bytes, destination_name: str, content_type: str = None) -> str:
        """Upload data from bytes to Cloud Storage."""
        try:
            bucket = self.get_bucket(bucket_name)
            blob = bucket.blob(destination_name)
            
            if content_type:
                blob.content_type = content_type
            
            blob.upload_from_string(data)
            
            logger.info(
                "Data uploaded to Cloud Storage",
                bucket=bucket_name,
                destination=destination_name,
                size_bytes=len(data)
            )
            
            return f"gs://{bucket_name}/{destination_name}"
        except Exception as e:
            logger.error(
                "Failed to upload data",
                bucket=bucket_name,
                destination=destination_name,
                error=str(e)
            )
            raise GCPClientError(f"Failed to upload data: {e}")
    
    def download_file(self, bucket_name: str, source_name: str, destination_file: str) -> None:
        """Download a file from Cloud Storage."""
        try:
            bucket = self.get_bucket(bucket_name)
            blob = bucket.blob(source_name)
            blob.download_to_filename(destination_file)
            
            logger.info(
                "File downloaded from Cloud Storage",
                bucket=bucket_name,
                source=source_name,
                destination=destination_file
            )
        except Exception as e:
            logger.error(
                "Failed to download file",
                bucket=bucket_name,
                source=source_name,
                error=str(e)
            )
            raise GCPClientError(f"Failed to download file: {e}")
    
    def delete_file(self, bucket_name: str, file_name: str) -> None:
        """Delete a file from Cloud Storage."""
        try:
            bucket = self.get_bucket(bucket_name)
            blob = bucket.blob(file_name)
            blob.delete()
            
            logger.info(
                "File deleted from Cloud Storage",
                bucket=bucket_name,
                file=file_name
            )
        except Exception as e:
            logger.error(
                "Failed to delete file",
                bucket=bucket_name,
                file=file_name,
                error=str(e)
            )
            raise GCPClientError(f"Failed to delete file: {e}")
    
    def generate_signed_url(self, bucket_name: str, file_name: str, expiration_minutes: int = 60) -> str:
        """Generate a signed URL for file access."""
        try:
            from datetime import timedelta
            
            bucket = self.get_bucket(bucket_name)
            blob = bucket.blob(file_name)
            
            url = blob.generate_signed_url(
                expiration=timedelta(minutes=expiration_minutes),
                method='GET'
            )
            
            logger.info(
                "Signed URL generated",
                bucket=bucket_name,
                file=file_name,
                expiration_minutes=expiration_minutes
            )
            
            return url
        except Exception as e:
            logger.error(
                "Failed to generate signed URL",
                bucket=bucket_name,
                file=file_name,
                error=str(e)
            )
            raise GCPClientError(f"Failed to generate signed URL: {e}")


class FirestoreClient:
    """Firestore client wrapper."""
    
    def __init__(self, project_id: Optional[str] = None):
        self.settings = get_settings()
        self.project_id = project_id or self.settings.GOOGLE_CLOUD_PROJECT
        self._client: Optional[firestore.Client] = None
    
    @property
    def client(self) -> firestore.Client:
        """Get Firestore client instance."""
        if self._client is None:
            try:
                if self.settings.GOOGLE_APPLICATION_CREDENTIALS:
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.settings.GOOGLE_APPLICATION_CREDENTIALS
                
                self._client = firestore.Client(project=self.project_id)
                logger.info("Firestore client initialized", project_id=self.project_id)
            except Exception as e:
                logger.error("Failed to initialize Firestore client", error=str(e))
                raise GCPClientError(f"Failed to initialize Firestore client: {e}")
        
        return self._client
    
    def create_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        """Create a document in Firestore."""
        try:
            doc_ref = self.client.collection(collection).document(document_id)
            doc_ref.set(data)
            
            logger.info(
                "Document created in Firestore",
                collection=collection,
                document_id=document_id
            )
        except Exception as e:
            logger.error(
                "Failed to create document",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise GCPClientError(f"Failed to create document: {e}")
    
    def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document from Firestore."""
        try:
            doc_ref = self.client.collection(collection).document(document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                logger.info(
                    "Document retrieved from Firestore",
                    collection=collection,
                    document_id=document_id
                )
                return doc.to_dict()
            else:
                logger.info(
                    "Document not found in Firestore",
                    collection=collection,
                    document_id=document_id
                )
                return None
        except Exception as e:
            logger.error(
                "Failed to get document",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise GCPClientError(f"Failed to get document: {e}")
    
    def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        """Update a document in Firestore."""
        try:
            doc_ref = self.client.collection(collection).document(document_id)
            doc_ref.update(data)
            
            logger.info(
                "Document updated in Firestore",
                collection=collection,
                document_id=document_id
            )
        except Exception as e:
            logger.error(
                "Failed to update document",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise GCPClientError(f"Failed to update document: {e}")
    
    def delete_document(self, collection: str, document_id: str) -> None:
        """Delete a document from Firestore."""
        try:
            doc_ref = self.client.collection(collection).document(document_id)
            doc_ref.delete()
            
            logger.info(
                "Document deleted from Firestore",
                collection=collection,
                document_id=document_id
            )
        except Exception as e:
            logger.error(
                "Failed to delete document",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise GCPClientError(f"Failed to delete document: {e}")


class CloudTasksClient:
    """Cloud Tasks client wrapper."""
    
    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None):
        self.settings = get_settings()
        self.project_id = project_id or self.settings.GOOGLE_CLOUD_PROJECT
        self.location = location or self.settings.CLOUD_TASKS_LOCATION
        self._client: Optional[tasks_v2.CloudTasksClient] = None
    
    @property
    def client(self) -> tasks_v2.CloudTasksClient:
        """Get Cloud Tasks client instance."""
        if self._client is None:
            try:
                if self.settings.GOOGLE_APPLICATION_CREDENTIALS:
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.settings.GOOGLE_APPLICATION_CREDENTIALS
                
                self._client = tasks_v2.CloudTasksClient()
                logger.info("Cloud Tasks client initialized", project_id=self.project_id)
            except Exception as e:
                logger.error("Failed to initialize Cloud Tasks client", error=str(e))
                raise GCPClientError(f"Failed to initialize Cloud Tasks client: {e}")
        
        return self._client
    
    def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        """Create a task in Cloud Tasks queue."""
        try:
            import json
            from google.protobuf import timestamp_pb2
            from datetime import datetime, timedelta
            
            parent = self.client.queue_path(self.project_id, self.location, queue_name)
            
            task = {
                'http_request': {
                    'http_method': tasks_v2.HttpMethod.POST,
                    'url': f"https://your-worker-url/process",  # TODO: Configure worker URL
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps(payload).encode()
                }
            }
            
            if delay_seconds > 0:
                schedule_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
                timestamp = timestamp_pb2.Timestamp()
                timestamp.FromDatetime(schedule_time)
                task['schedule_time'] = timestamp
            
            response = self.client.create_task(request={'parent': parent, 'task': task})
            
            logger.info(
                "Task created in Cloud Tasks",
                queue=queue_name,
                task_name=response.name,
                delay_seconds=delay_seconds
            )
            
            return response.name
        except Exception as e:
            logger.error(
                "Failed to create task",
                queue=queue_name,
                error=str(e)
            )
            raise GCPClientError(f"Failed to create task: {e}")


@lru_cache()
def get_storage_client() -> CloudStorageClient:
    """Get cached Cloud Storage client instance."""
    return CloudStorageClient()


@lru_cache()
def get_firestore_client() -> FirestoreClient:
    """Get cached Firestore client instance."""
    return FirestoreClient()


@lru_cache()
def get_tasks_client() -> CloudTasksClient:
    """Get cached Cloud Tasks client instance."""
    return CloudTasksClient()


async def health_check_gcp_services() -> Dict[str, str]:
    """Health check for GCP services."""
    health_status = {}
    
    # Check Cloud Storage
    try:
        storage_client = get_storage_client()
        # Try to list buckets as a health check
        list(storage_client.client.list_buckets(max_results=1))
        health_status['cloud_storage'] = 'healthy'
    except Exception as e:
        logger.warning("Cloud Storage health check failed", error=str(e))
        health_status['cloud_storage'] = 'unhealthy'
    
    # Check Firestore
    try:
        firestore_client = get_firestore_client()
        # Try to get a non-existent document as a health check
        firestore_client.get_document('health', 'check')
        health_status['firestore'] = 'healthy'
    except GCPClientError:
        health_status['firestore'] = 'unhealthy'
    except Exception:
        # Connection successful, document not found is expected
        health_status['firestore'] = 'healthy'
    
    # Check Cloud Tasks
    try:
        tasks_client = get_tasks_client()
        # Try to list queues as a health check
        parent = f"projects/{tasks_client.project_id}/locations/{tasks_client.location}"
        list(tasks_client.client.list_queues(request={'parent': parent}, page_size=1))
        health_status['cloud_tasks'] = 'healthy'
    except Exception as e:
        logger.warning("Cloud Tasks health check failed", error=str(e))
        health_status['cloud_tasks'] = 'unhealthy'
    
    return health_status