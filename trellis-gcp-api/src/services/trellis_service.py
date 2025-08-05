"""
TRELLIS processing service for 3D model generation.

This service provides wrappers around the TRELLIS pipelines and handles
model management, GPU optimization, and processing orchestration.
"""
import os
import gc
import time
import torch
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
from functools import lru_cache
import tempfile
import shutil

import structlog
from PIL import Image

from ..models.base import JobType, QualityLevel, OutputFormat
from ..models.job import Job, JobOutputFile
from ..utils.config import get_settings
from ..utils.storage_adapter import get_storage_manager
from .model_converter import get_model_converter


logger = structlog.get_logger(__name__)


class TrellisServiceError(Exception):
    """Base exception for TRELLIS service errors."""
    pass


class ModelLoadError(TrellisServiceError):
    """Exception raised when model loading fails."""
    pass


class ProcessingError(TrellisServiceError):
    """Exception raised during 3D model processing."""
    pass


class TrellisService:
    """Service for TRELLIS 3D model generation."""
    
    def __init__(self):
        self.settings = get_settings()
        self.storage_manager = get_storage_manager()
        self.model_converter = get_model_converter()
        self._image_to_3d_pipeline = None
        self._text_to_3d_pipeline = None
        self._device = None
        self._models_loaded = False
        
        # Initialize device
        self._setup_device()
    
    def _setup_device(self) -> None:
        """Setup GPU device and check requirements."""
        try:
            if torch.cuda.is_available():
                # Check CUDA memory
                device_count = torch.cuda.device_count()
                for i in range(device_count):
                    mem_total = torch.cuda.get_device_properties(i).total_memory
                    mem_gb = mem_total / (1024**3)
                    
                    logger.info(
                        "CUDA device detected",
                        device_id=i,
                        name=torch.cuda.get_device_properties(i).name,
                        memory_gb=round(mem_gb, 1)
                    )
                    
                    if mem_gb < 12:
                        logger.warning(
                            "GPU memory may be insufficient for TRELLIS",
                            device_id=i,
                            memory_gb=round(mem_gb, 1),
                            recommended_gb=16
                        )
                
                self._device = torch.device("cuda:0")
                
                # Clear cache
                torch.cuda.empty_cache()
                
            else:
                logger.warning("CUDA not available, falling back to CPU (not recommended)")
                self._device = torch.device("cpu")
                
            logger.info(
                "TRELLIS device initialized",
                device=str(self._device),
                cuda_available=torch.cuda.is_available()
            )
            
        except Exception as e:
            logger.error("Failed to setup device", error=str(e))
            raise ModelLoadError(f"Device setup failed: {e}")
    
    def _load_image_to_3d_pipeline(self) -> None:
        """Load the image-to-3D pipeline."""
        try:
            if self._image_to_3d_pipeline is not None:
                return
            
            logger.info("Loading TRELLIS image-to-3D pipeline")
            start_time = time.time()
            
            # Import TRELLIS components
            try:
                from trellis.pipelines import TrellisImageTo3DPipeline
            except ImportError as e:
                logger.error("Failed to import TRELLIS pipelines", error=str(e))
                raise ModelLoadError("TRELLIS not installed or import failed")
            
            # Load the pipeline
            model_name = "JeffreyXiang/TRELLIS-image-large"
            
            self._image_to_3d_pipeline = TrellisImageTo3DPipeline.from_pretrained(
                model_name,
                device=self._device,
                torch_dtype=torch.float16 if self._device.type == "cuda" else torch.float32
            )
            
            # Enable memory efficient attention if available
            try:
                if hasattr(self._image_to_3d_pipeline, 'enable_model_cpu_offload'):
                    self._image_to_3d_pipeline.enable_model_cpu_offload()
                if hasattr(self._image_to_3d_pipeline, 'enable_sequential_cpu_offload'):
                    self._image_to_3d_pipeline.enable_sequential_cpu_offload()
            except Exception as e:
                logger.warning("Could not enable CPU offloading", error=str(e))
            
            load_time = time.time() - start_time
            
            logger.info(
                "TRELLIS image-to-3D pipeline loaded successfully",
                model_name=model_name,
                load_time_seconds=round(load_time, 2),
                device=str(self._device)
            )
            
        except Exception as e:
            logger.error("Failed to load image-to-3D pipeline", error=str(e))
            raise ModelLoadError(f"Image-to-3D pipeline loading failed: {e}")
    
    def _load_text_to_3d_pipeline(self) -> None:
        """Load the text-to-3D pipeline."""
        try:
            if self._text_to_3d_pipeline is not None:
                return
            
            logger.info("Loading TRELLIS text-to-3D pipeline")
            start_time = time.time()
            
            # Import TRELLIS components
            try:
                from trellis.pipelines import TrellisTextTo3DPipeline
            except ImportError as e:
                logger.error("Failed to import TRELLIS pipelines", error=str(e))
                raise ModelLoadError("TRELLIS not installed or import failed")
            
            # Load the pipeline
            model_name = "JeffreyXiang/TRELLIS-text-large"
            
            self._text_to_3d_pipeline = TrellisTextTo3DPipeline.from_pretrained(
                model_name,
                device=self._device,
                torch_dtype=torch.float16 if self._device.type == "cuda" else torch.float32
            )
            
            # Enable memory efficient attention if available
            try:
                if hasattr(self._text_to_3d_pipeline, 'enable_model_cpu_offload'):
                    self._text_to_3d_pipeline.enable_model_cpu_offload()
                if hasattr(self._text_to_3d_pipeline, 'enable_sequential_cpu_offload'):
                    self._text_to_3d_pipeline.enable_sequential_cpu_offload()
            except Exception as e:
                logger.warning("Could not enable CPU offloading", error=str(e))
            
            load_time = time.time() - start_time
            
            logger.info(
                "TRELLIS text-to-3D pipeline loaded successfully",
                model_name=model_name,
                load_time_seconds=round(load_time, 2),
                device=str(self._device)
            )
            
        except Exception as e:
            logger.error("Failed to load text-to-3D pipeline", error=str(e))
            raise ModelLoadError(f"Text-to-3D pipeline loading failed: {e}")
    
    def _get_quality_settings(self, quality: QualityLevel) -> Dict[str, Any]:
        """Get processing settings based on quality level."""
        if quality == QualityLevel.FAST:
            return {
                'num_inference_steps': 20,
                'guidance_scale': 7.0,
                'num_images_per_prompt': 1
            }
        elif quality == QualityLevel.BALANCED:
            return {
                'num_inference_steps': 50,
                'guidance_scale': 7.5,
                'num_images_per_prompt': 1
            }
        elif quality == QualityLevel.HIGH:
            return {
                'num_inference_steps': 100,
                'guidance_scale': 8.0,
                'num_images_per_prompt': 2
            }
        else:
            # Default to balanced
            return {
                'num_inference_steps': 50,
                'guidance_scale': 7.5,
                'num_images_per_prompt': 1
            }
    
    async def process_image_to_3d(
        self,
        job: Job,
        image_data: Optional[bytes] = None,
        image_url: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> List[JobOutputFile]:
        """
        Process image-to-3D generation.
        
        Args:
            job: Job instance with processing parameters
            image_data: Raw image bytes (optional)
            image_url: URL to image file (optional)
            progress_callback: Function to call with progress updates
            
        Returns:
            List of generated output files
        """
        try:
            if progress_callback:
                await progress_callback(0.1, "Loading models...")
            
            # Load pipeline if needed
            self._load_image_to_3d_pipeline()
            
            if progress_callback:
                await progress_callback(0.2, "Processing input image...")
            
            # Load input image
            input_image = await self._load_input_image(image_data, image_url)
            
            if progress_callback:
                await progress_callback(0.3, "Generating 3D model...")
            
            # Get quality settings
            input_data = job.input_data
            quality = QualityLevel(input_data.get('quality', 'balanced'))
            quality_settings = self._get_quality_settings(quality)
            
            # Generate 3D model
            with torch.inference_mode():
                result = self._image_to_3d_pipeline(
                    image=input_image,
                    **quality_settings
                )
            
            if progress_callback:
                await progress_callback(0.7, "Converting to output formats...")
            
            # Convert to requested formats using ModelConverter
            output_formats = [OutputFormat(fmt) for fmt in input_data.get('output_formats', ['glb'])]
            
            converted_files = await self.model_converter.convert_model(
                input_data=result,
                target_formats=output_formats,
                job_id=job.job_id,
                quality_settings=quality_settings
            )
            
            if progress_callback:
                await progress_callback(0.9, "Uploading results...")
            
            # Upload output files
            uploaded_files = await self._upload_converted_files(job, converted_files)
            
            if progress_callback:
                await progress_callback(1.0, "Processing complete")
            
            logger.info(
                "Image-to-3D processing completed",
                job_id=job.job_id,
                output_files_count=len(uploaded_files),
                quality=quality.value
            )
            
            return uploaded_files
            
        except Exception as e:
            logger.error(
                "Image-to-3D processing failed",
                job_id=job.job_id,
                error=str(e)
            )
            raise ProcessingError(f"Image-to-3D processing failed: {e}")
        finally:
            # Cleanup GPU memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
    
    async def process_text_to_3d(
        self,
        job: Job,
        progress_callback: Optional[callable] = None
    ) -> List[JobOutputFile]:
        """
        Process text-to-3D generation.
        
        Args:
            job: Job instance with processing parameters
            progress_callback: Function to call with progress updates
            
        Returns:
            List of generated output files
        """
        try:
            if progress_callback:
                await progress_callback(0.1, "Loading models...")
            
            # Load pipeline if needed
            self._load_text_to_3d_pipeline()
            
            if progress_callback:
                await progress_callback(0.2, "Processing text prompt...")
            
            # Get input parameters
            input_data = job.input_data
            prompt = input_data.get('prompt', '')
            negative_prompt = input_data.get('negative_prompt', '')
            
            if not prompt:
                raise ProcessingError("Text prompt is required")
            
            if progress_callback:
                await progress_callback(0.3, "Generating 3D model...")
            
            # Get quality settings
            quality = QualityLevel(input_data.get('quality', 'balanced'))
            quality_settings = self._get_quality_settings(quality)
            
            # Generate 3D model
            with torch.inference_mode():
                result = self._text_to_3d_pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    **quality_settings
                )
            
            if progress_callback:
                await progress_callback(0.7, "Converting to output formats...")
            
            # Convert to requested formats using ModelConverter
            output_formats = [OutputFormat(fmt) for fmt in input_data.get('output_formats', ['glb'])]
            
            converted_files = await self.model_converter.convert_model(
                input_data=result,
                target_formats=output_formats,
                job_id=job.job_id,
                quality_settings=quality_settings
            )
            
            if progress_callback:
                await progress_callback(0.9, "Uploading results...")
            
            # Upload output files
            uploaded_files = await self._upload_converted_files(job, converted_files)
            
            if progress_callback:
                await progress_callback(1.0, "Processing complete")
            
            logger.info(
                "Text-to-3D processing completed",
                job_id=job.job_id,
                output_files_count=len(uploaded_files),
                quality=quality.value,
                prompt_length=len(prompt)
            )
            
            return uploaded_files
            
        except Exception as e:
            logger.error(
                "Text-to-3D processing failed",
                job_id=job.job_id,
                error=str(e)
            )
            raise ProcessingError(f"Text-to-3D processing failed: {e}")
        finally:
            # Cleanup GPU memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
    
    async def _load_input_image(
        self,
        image_data: Optional[bytes] = None,
        image_url: Optional[str] = None
    ) -> Image.Image:
        """Load input image from data or URL."""
        try:
            if image_data:
                # Load from bytes
                import io
                image = Image.open(io.BytesIO(image_data))
            elif image_url:
                # Download from URL
                if image_url.startswith(('gs://', 'minio://')):
                    # Load from storage
                    url_parts = image_url.replace('gs://', '').replace('minio://', '').split('/', 1)
                    if len(url_parts) == 2:
                        bucket_name, file_name = url_parts
                        image_data = await self.storage_manager.storage.download_as_bytes(bucket_name, file_name)
                        import io
                        image = Image.open(io.BytesIO(image_data))
                    else:
                        raise ProcessingError(f"Invalid storage URL format: {image_url}")
                else:
                    # Load from HTTP URL
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as response:
                            if response.status != 200:
                                raise ProcessingError(f"Failed to download image: HTTP {response.status}")
                            image_data = await response.read()
                            import io
                            image = Image.open(io.BytesIO(image_data))
            else:
                raise ProcessingError("Either image_data or image_url must be provided")
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if too large (TRELLIS typically works well with 512x512)
            max_size = 512
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            logger.info(
                "Input image loaded",
                size=image.size,
                mode=image.mode
            )
            
            return image
            
        except Exception as e:
            logger.error("Failed to load input image", error=str(e))
            raise ProcessingError(f"Failed to load input image: {e}")
    
    async def _upload_converted_files(
        self,
        job: Job,
        converted_files: List[Tuple[OutputFormat, Path]]
    ) -> List[JobOutputFile]:
        """Upload converted files to storage and return file metadata."""
        try:
            uploaded_files = []
            bucket_names = self.storage_manager.get_bucket_names()
            output_bucket = bucket_names['output']
            
            for output_format, file_path in converted_files:
                try:
                    # Generate storage key
                    file_extension = file_path.suffix
                    storage_key = f"{job.user_id}/{job.job_id}/{output_format.value}{file_extension}"
                    
                    # Upload file
                    file_url = await self.storage_manager.storage.upload_file(
                        output_bucket,
                        str(file_path),
                        storage_key
                    )
                    
                    # Get file size
                    file_size = file_path.stat().st_size
                    
                    # Create output file metadata
                    output_file = JobOutputFile(
                        format=output_format.value,
                        url=file_url,
                        size_bytes=file_size,
                        filename=f"{job.job_id}_{output_format.value}{file_extension}"
                    )
                    
                    uploaded_files.append(output_file)
                    
                    logger.info(
                        "Converted file uploaded",
                        job_id=job.job_id,
                        format=output_format.value,
                        url=file_url,
                        size_bytes=file_size
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to upload converted file",
                        job_id=job.job_id,
                        format=output_format.value,
                        file_path=str(file_path),
                        error=str(e)
                    )
                    # Continue with other files
                    continue
            
            # Clean up temporary files
            try:
                self.model_converter.cleanup_temp_files(job.job_id)
            except Exception as e:
                logger.warning("Failed to cleanup temp files", job_id=job.job_id, error=str(e))
            
            if not uploaded_files:
                raise ProcessingError("No output files were successfully uploaded")
            
            logger.info(
                "All converted files uploaded",
                job_id=job.job_id,
                uploaded_count=len(uploaded_files)
            )
            
            return uploaded_files
            
        except Exception as e:
            logger.error(
                "Failed to upload converted files",
                job_id=job.job_id,
                error=str(e)
            )
            raise ProcessingError(f"Failed to upload converted files: {e}")
    
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models."""
        return {
            'device': str(self._device),
            'cuda_available': torch.cuda.is_available(),
            'image_to_3d_loaded': self._image_to_3d_pipeline is not None,
            'text_to_3d_loaded': self._text_to_3d_pipeline is not None,
            'gpu_memory_allocated': torch.cuda.memory_allocated() if torch.cuda.is_available() else 0,
            'gpu_memory_reserved': torch.cuda.memory_reserved() if torch.cuda.is_available() else 0
        }
    
    def cleanup_models(self) -> None:
        """Cleanup models to free memory."""
        try:
            if self._image_to_3d_pipeline is not None:
                del self._image_to_3d_pipeline
                self._image_to_3d_pipeline = None
                
            if self._text_to_3d_pipeline is not None:
                del self._text_to_3d_pipeline
                self._text_to_3d_pipeline = None
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            gc.collect()
            
            logger.info("TRELLIS models cleaned up")
            
        except Exception as e:
            logger.error("Failed to cleanup models", error=str(e))


@lru_cache()
def get_trellis_service() -> TrellisService:
    """Get cached TRELLIS service instance."""
    return TrellisService()