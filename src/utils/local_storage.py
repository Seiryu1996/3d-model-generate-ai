"""
Local storage client for development environment (MinIO S3-compatible storage).
"""
import os
from typing import Optional, Dict, Any
from functools import lru_cache
import json
import sqlite3
from datetime import datetime, timedelta

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

import structlog
from .config import get_settings


logger = structlog.get_logger(__name__)


class LocalStorageError(Exception):
    """Base exception for local storage errors."""
    pass


class MinIOClient:
    """MinIO client wrapper for local development."""
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[Minio] = None
        
        if not MINIO_AVAILABLE:
            logger.warning("MinIO client not available - install minio package for local development")
    
    @property
    def client(self) -> Minio:
        """Get MinIO client instance."""
        if not MINIO_AVAILABLE:
            raise LocalStorageError("MinIO client not available - install minio package")
        
        if self._client is None:
            try:
                endpoint = self.settings.MINIO_ENDPOINT
                if not endpoint:
                    raise LocalStorageError("MINIO_ENDPOINT not configured")
                
                # Remove http:// or https:// prefix if present
                if endpoint.startswith('http://'):
                    endpoint = endpoint[7:]
                    secure = False
                elif endpoint.startswith('https://'):
                    endpoint = endpoint[8:]
                    secure = True
                else:
                    secure = False
                
                self._client = Minio(
                    endpoint,
                    access_key=self.settings.MINIO_ACCESS_KEY,
                    secret_key=self.settings.MINIO_SECRET_KEY,
                    secure=secure
                )
                
                logger.info("MinIO client initialized", endpoint=endpoint)
            except Exception as e:
                logger.error("Failed to initialize MinIO client", error=str(e))
                raise LocalStorageError(f"Failed to initialize MinIO client: {e}")
        
        return self._client
    
    def ensure_bucket(self, bucket_name: str) -> None:
        """Ensure bucket exists, create if it doesn't."""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info("Created MinIO bucket", bucket=bucket_name)
            else:
                logger.debug("MinIO bucket exists", bucket=bucket_name)
        except Exception as e:
            logger.error("Failed to ensure bucket", bucket=bucket_name, error=str(e))
            raise LocalStorageError(f"Failed to ensure bucket {bucket_name}: {e}")
    
    def upload_file(self, bucket_name: str, source_file: str, destination_name: str) -> str:
        """Upload a file to MinIO."""
        try:
            self.ensure_bucket(bucket_name)
            
            self.client.fput_object(bucket_name, destination_name, source_file)
            
            logger.info(
                "File uploaded to MinIO",
                bucket=bucket_name,
                destination=destination_name,
                source=source_file
            )
            
            return f"minio://{bucket_name}/{destination_name}"
        except Exception as e:
            logger.error(
                "Failed to upload file to MinIO",
                bucket=bucket_name,
                destination=destination_name,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to upload file: {e}")
    
    def upload_from_bytes(self, bucket_name: str, data: bytes, destination_name: str, content_type: str = None) -> str:
        """Upload data from bytes to MinIO."""
        try:
            from io import BytesIO
            
            self.ensure_bucket(bucket_name)
            
            data_stream = BytesIO(data)
            self.client.put_object(
                bucket_name,
                destination_name,
                data_stream,
                length=len(data),
                content_type=content_type or 'application/octet-stream'
            )
            
            logger.info(
                "Data uploaded to MinIO",
                bucket=bucket_name,
                destination=destination_name,
                size_bytes=len(data)
            )
            
            return f"minio://{bucket_name}/{destination_name}"
        except Exception as e:
            logger.error(
                "Failed to upload data to MinIO",
                bucket=bucket_name,
                destination=destination_name,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to upload data: {e}")
    
    def download_file(self, bucket_name: str, source_name: str, destination_file: str) -> None:
        """Download a file from MinIO."""
        try:
            self.client.fget_object(bucket_name, source_name, destination_file)
            
            logger.info(
                "File downloaded from MinIO",
                bucket=bucket_name,
                source=source_name,
                destination=destination_file
            )
        except Exception as e:
            logger.error(
                "Failed to download file from MinIO",
                bucket=bucket_name,
                source=source_name,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to download file: {e}")
    
    def delete_file(self, bucket_name: str, file_name: str) -> None:
        """Delete a file from MinIO."""
        try:
            self.client.remove_object(bucket_name, file_name)
            
            logger.info(
                "File deleted from MinIO",
                bucket=bucket_name,
                file=file_name
            )
        except Exception as e:
            logger.error(
                "Failed to delete file from MinIO",
                bucket=bucket_name,
                file=file_name,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to delete file: {e}")
    
    def generate_presigned_url(self, bucket_name: str, file_name: str, expiration_minutes: int = 60) -> str:
        """Generate a presigned URL for file access."""
        try:
            url = self.client.presigned_get_object(
                bucket_name,
                file_name,
                expires=timedelta(minutes=expiration_minutes)
            )
            
            logger.info(
                "Presigned URL generated",
                bucket=bucket_name,
                file=file_name,
                expiration_minutes=expiration_minutes
            )
            
            return url
        except Exception as e:
            logger.error(
                "Failed to generate presigned URL",
                bucket=bucket_name,
                file=file_name,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to generate presigned URL: {e}")


class SQLiteDocumentStore:
    """SQLite-based document store for local development (Firestore replacement)."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.settings = get_settings()
        self.db_path = db_path or self.settings.DATABASE_URL.replace('sqlite:///', '') if self.settings.DATABASE_URL else 'local_db.sqlite'
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS documents (
                        collection TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        data TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (collection, document_id)
                    )
                ''')
                conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_timestamp 
                    AFTER UPDATE ON documents
                    BEGIN
                        UPDATE documents SET updated_at = CURRENT_TIMESTAMP 
                        WHERE collection = NEW.collection AND document_id = NEW.document_id;
                    END
                ''')
                conn.commit()
                
            logger.info("SQLite document store initialized", db_path=self.db_path)
        except Exception as e:
            logger.error("Failed to initialize SQLite document store", error=str(e))
            raise LocalStorageError(f"Failed to initialize document store: {e}")
    
    def create_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        """Create a document in the SQLite store."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO documents (collection, document_id, data) VALUES (?, ?, ?)',
                    (collection, document_id, json.dumps(data))
                )
                conn.commit()
                
            logger.info(
                "Document created in SQLite store",
                collection=collection,
                document_id=document_id
            )
        except Exception as e:
            logger.error(
                "Failed to create document in SQLite store",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to create document: {e}")
    
    def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document from the SQLite store."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT data FROM documents WHERE collection = ? AND document_id = ?',
                    (collection, document_id)
                )
                row = cursor.fetchone()
                
                if row:
                    logger.info(
                        "Document retrieved from SQLite store",
                        collection=collection,
                        document_id=document_id
                    )
                    return json.loads(row[0])
                else:
                    logger.info(
                        "Document not found in SQLite store",
                        collection=collection,
                        document_id=document_id
                    )
                    return None
        except Exception as e:
            logger.error(
                "Failed to get document from SQLite store",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to get document: {e}")
    
    def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        """Update a document in the SQLite store."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'UPDATE documents SET data = ? WHERE collection = ? AND document_id = ?',
                    (json.dumps(data), collection, document_id)
                )
                
                if cursor.rowcount == 0:
                    raise LocalStorageError(f"Document {document_id} not found in collection {collection}")
                
                conn.commit()
                
            logger.info(
                "Document updated in SQLite store",
                collection=collection,
                document_id=document_id
            )
        except LocalStorageError:
            raise
        except Exception as e:
            logger.error(
                "Failed to update document in SQLite store",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to update document: {e}")
    
    def delete_document(self, collection: str, document_id: str) -> None:
        """Delete a document from the SQLite store."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'DELETE FROM documents WHERE collection = ? AND document_id = ?',
                    (collection, document_id)
                )
                
                if cursor.rowcount == 0:
                    raise LocalStorageError(f"Document {document_id} not found in collection {collection}")
                
                conn.commit()
                
            logger.info(
                "Document deleted from SQLite store",
                collection=collection,
                document_id=document_id
            )
        except LocalStorageError:
            raise
        except Exception as e:
            logger.error(
                "Failed to delete document from SQLite store",
                collection=collection,
                document_id=document_id,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to delete document: {e}")


class LocalTaskQueue:
    """Local task queue for development (Cloud Tasks replacement)."""
    
    def __init__(self):
        self.settings = get_settings()
        self._tasks = []  # Simple in-memory task queue for development
    
    def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        """Create a task in the local queue."""
        try:
            task_id = f"task_{len(self._tasks) + 1}_{datetime.utcnow().timestamp()}"
            
            task = {
                'id': task_id,
                'queue': queue_name,
                'payload': payload,
                'created_at': datetime.utcnow(),
                'schedule_at': datetime.utcnow() + timedelta(seconds=delay_seconds),
                'processed': False
            }
            
            self._tasks.append(task)
            
            logger.info(
                "Task created in local queue",
                queue=queue_name,
                task_id=task_id,
                delay_seconds=delay_seconds
            )
            
            return task_id
        except Exception as e:
            logger.error(
                "Failed to create task in local queue",
                queue=queue_name,
                error=str(e)
            )
            raise LocalStorageError(f"Failed to create task: {e}")
    
    def get_pending_tasks(self, queue_name: str) -> list:
        """Get pending tasks from the local queue."""
        now = datetime.utcnow()
        return [
            task for task in self._tasks
            if task['queue'] == queue_name and not task['processed'] and task['schedule_at'] <= now
        ]


@lru_cache()
def get_local_storage_client() -> MinIOClient:
    """Get cached MinIO client instance."""
    return MinIOClient()


@lru_cache()
def get_local_document_store() -> SQLiteDocumentStore:
    """Get cached SQLite document store instance."""
    return SQLiteDocumentStore()


@lru_cache()
def get_local_task_queue() -> LocalTaskQueue:
    """Get cached local task queue instance."""
    return LocalTaskQueue()


async def health_check_local_services() -> Dict[str, str]:
    """Health check for local development services."""
    health_status = {}
    
    # Check MinIO
    try:
        if MINIO_AVAILABLE:
            storage_client = get_local_storage_client()
            # Try to list buckets as a health check
            list(storage_client.client.list_buckets())
            health_status['minio'] = 'healthy'
        else:
            health_status['minio'] = 'unavailable'
    except Exception as e:
        logger.warning("MinIO health check failed", error=str(e))
        health_status['minio'] = 'unhealthy'
    
    # Check SQLite document store
    try:
        doc_store = get_local_document_store()
        # Try to perform a simple operation
        doc_store.get_document('health', 'check')
        health_status['document_store'] = 'healthy'
    except Exception as e:
        logger.warning("Document store health check failed", error=str(e))
        health_status['document_store'] = 'unhealthy'
    
    # Local task queue is always healthy in development
    health_status['task_queue'] = 'healthy'
    
    return health_status