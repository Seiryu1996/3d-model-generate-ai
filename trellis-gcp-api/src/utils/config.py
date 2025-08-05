"""
Configuration management for the TRELLIS API.
"""
import os
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings."""
    
    # API Configuration
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    RELOAD: bool = Field(default=False, env="RELOAD")
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    API_KEY_HEADER: str = Field(default="X-API-Key", env="API_KEY_HEADER")
    RATE_LIMIT_PER_MINUTE: int = Field(default=10, env="RATE_LIMIT_PER_MINUTE")
    
    # GCP Configuration
    GOOGLE_CLOUD_PROJECT: Optional[str] = Field(None, env="GOOGLE_CLOUD_PROJECT")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(None, env="GOOGLE_APPLICATION_CREDENTIALS")
    
    # Cloud Storage
    GCS_BUCKET_MODELS: str = Field(default="trellis-models-dev", env="GCS_BUCKET_MODELS")
    GCS_BUCKET_INPUT: str = Field(default="trellis-input-dev", env="GCS_BUCKET_INPUT")
    GCS_BUCKET_OUTPUT: str = Field(default="trellis-output-dev", env="GCS_BUCKET_OUTPUT")
    GCS_BUCKET_TEMP: str = Field(default="trellis-temp-dev", env="GCS_BUCKET_TEMP")
    
    # Cloud Tasks
    CLOUD_TASKS_QUEUE: str = Field(default="trellis-tasks-dev", env="CLOUD_TASKS_QUEUE")
    CLOUD_TASKS_LOCATION: str = Field(default="us-central1", env="CLOUD_TASKS_LOCATION")
    
    # Firestore
    FIRESTORE_COLLECTION_JOBS: str = Field(default="jobs", env="FIRESTORE_COLLECTION_JOBS")
    
    # TRELLIS Configuration
    TRELLIS_MODEL_PATH: str = Field(default="microsoft/TRELLIS-image-large", env="TRELLIS_MODEL_PATH")
    TRELLIS_TEXT_MODEL_PATH: str = Field(default="microsoft/TRELLIS-text-large", env="TRELLIS_TEXT_MODEL_PATH")
    TRELLIS_CACHE_DIR: str = Field(default="/tmp/trellis-cache", env="TRELLIS_CACHE_DIR")
    SPCONV_ALGO: str = Field(default="native", env="SPCONV_ALGO")
    ATTN_BACKEND: str = Field(default="flash-attn", env="ATTN_BACKEND")
    
    # Development/Local Configuration
    REDIS_URL: Optional[str] = Field(None, env="REDIS_URL")
    MINIO_ENDPOINT: Optional[str] = Field(None, env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: Optional[str] = Field(None, env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: Optional[str] = Field(None, env="MINIO_SECRET_KEY")
    DATABASE_URL: Optional[str] = Field(None, env="DATABASE_URL")
    
    # Processing Configuration
    MAX_CONCURRENT_JOBS: int = Field(default=1, env="MAX_CONCURRENT_JOBS")
    JOB_TIMEOUT_MINUTES: int = Field(default=30, env="JOB_TIMEOUT_MINUTES")
    MAX_FILE_SIZE_MB: int = Field(default=100, env="MAX_FILE_SIZE_MB")
    
    # Output Configuration
    SUPPORTED_IMAGE_FORMATS: List[str] = Field(
        default=["jpg", "jpeg", "png", "bmp", "tiff"],
        env="SUPPORTED_IMAGE_FORMATS"
    )
    OUTPUT_EXPIRY_DAYS: int = Field(default=7, env="OUTPUT_EXPIRY_DAYS")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return bool(self.DEBUG or self.REDIS_URL)
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.is_development()
    
    def get_storage_client_config(self) -> dict:
        """Get storage client configuration."""
        if self.is_development() and self.MINIO_ENDPOINT:
            return {
                "endpoint": self.MINIO_ENDPOINT,
                "access_key": self.MINIO_ACCESS_KEY,
                "secret_key": self.MINIO_SECRET_KEY,
                "secure": False,
                "region": "us-east-1"  # MinIO default
            }
        else:
            return {
                "project": self.GOOGLE_CLOUD_PROJECT,
                "credentials_path": self.GOOGLE_APPLICATION_CREDENTIALS
            }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()