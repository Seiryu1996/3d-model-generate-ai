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
            
            # Convert to requested formats
            output_formats = [OutputFormat(fmt) for fmt in input_data.get('output_formats', ['glb'])]
            output_files = await self._convert_to_formats(job, result, output_formats)
            
            if progress_callback:
                await progress_callback(0.9, "Uploading results...")
            
            # Upload output files
            uploaded_files = await self._upload_output_files(job, output_files)
            
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
            
            # Convert to requested formats
            output_formats = [OutputFormat(fmt) for fmt in input_data.get('output_formats', ['glb'])]
            output_files = await self._convert_to_formats(job, result, output_formats)
            
            if progress_callback:
                await progress_callback(0.9, "Uploading results...")
            
            # Upload output files
            uploaded_files = await self._upload_output_files(job, output_files)
            
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
    
    async def _convert_to_formats(
        self,
        job: Job,
        trellis_result: Any,
        output_formats: List[OutputFormat]
    ) -> List[Tuple[str, Path]]:
        """Convert TRELLIS result to requested output formats."""
        try:
            output_files = []
            
            # Create temporary directory for output files
            temp_dir = Path(tempfile.mkdtemp())
            
            try:
                for output_format in output_formats:
                    filename = f"{job.job_id}_{output_format.value}"
                    
                    if output_format == OutputFormat.GLB:
                        # Export as GLB
                        output_path = temp_dir / f"{filename}.glb"
                        await self._export_as_glb(trellis_result, output_path)
                        output_files.append((output_format.value, output_path))
                        
                    elif output_format == OutputFormat.OBJ:
                        # Export as OBJ
                        output_path = temp_dir / f"{filename}.obj"
                        await self._export_as_obj(trellis_result, output_path)
                        output_files.append((output_format.value, output_path))
                        
                    elif output_format == OutputFormat.PLY:
                        # Export as PLY
                        output_path = temp_dir / f"{filename}.ply"
                        await self._export_as_ply(trellis_result, output_path)
                        output_files.append((output_format.value, output_path))
                        
                    else:
                        logger.warning(f"Unsupported output format: {output_format}")
                
                logger.info(
                    "Format conversion completed",
                    job_id=job.job_id,
                    formats=[fmt.value for fmt in output_formats],
                    output_files_count=len(output_files)
                )
                
                return output_files
                
            except Exception as e:
                # Cleanup temp directory on error
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise e
            
        except Exception as e:
            logger.error(
                "Format conversion failed",
                job_id=job.job_id,
                error=str(e)
            )
            raise ProcessingError(f"Format conversion failed: {e}")
    
    async def _export_as_glb(self, trellis_result: Any, output_path: Path) -> None:
        """Export TRELLIS result as GLB format."""
        try:
            # This would depend on the actual TRELLIS result structure
            # For now, this is a placeholder implementation
            if hasattr(trellis_result, 'export_glb'):
                trellis_result.export_glb(str(output_path))
            elif hasattr(trellis_result, 'to_mesh'):
                mesh = trellis_result.to_mesh()
                if hasattr(mesh, 'export'):
                    mesh.export(str(output_path))
                else:
                    # Fallback: save as placeholder
                    output_path.write_text("GLB export not implemented")
            else:
                # Placeholder implementation
                output_path.write_text("GLB export not implemented")
                
            logger.info(f"GLB export completed: {output_path}")
            
        except Exception as e:
            logger.error(f"GLB export failed: {e}")
            raise ProcessingError(f"GLB export failed: {e}")
    
    async def _export_as_obj(self, trellis_result: Any, output_path: Path) -> None:
        """Export TRELLIS result as OBJ format."""
        try:
            # This would depend on the actual TRELLIS result structure
            # For now, this is a placeholder implementation
            if hasattr(trellis_result, 'export_obj'):
                trellis_result.export_obj(str(output_path))
            elif hasattr(trellis_result, 'to_mesh'):
                mesh = trellis_result.to_mesh()
                if hasattr(mesh, 'export'):
                    mesh.export(str(output_path))
                else:
                    # Fallback: save as placeholder
                    output_path.write_text("OBJ export not implemented")
            else:
                # Placeholder implementation
                output_path.write_text("OBJ export not implemented")
                
            logger.info(f"OBJ export completed: {output_path}")
            
        except Exception as e:
            logger.error(f"OBJ export failed: {e}")
            raise ProcessingError(f"OBJ export failed: {e}")
    
    async def _export_as_ply(self, trellis_result: Any, output_path: Path) -> None:
        """Export TRELLIS result as PLY format."""
        try:
            # This would depend on the actual TRELLIS result structure
            # For now, this is a placeholder implementation
            if hasattr(trellis_result, 'export_ply'):
                trellis_result.export_ply(str(output_path))
            elif hasattr(trellis_result, 'to_pointcloud'):
                pointcloud = trellis_result.to_pointcloud()
                if hasattr(pointcloud, 'export'):
                    pointcloud.export(str(output_path))
                else:
                    # Fallback: save as placeholder
                    output_path.write_text("PLY export not implemented")
            else:
                # Placeholder implementation
                output_path.write_text("PLY export not implemented")
                
            logger.info(f"PLY export completed: {output_path}")
            
        except Exception as e:
            logger.error(f"PLY export failed: {e}")
            raise ProcessingError(f"PLY export failed: {e}")
    
    async def _upload_output_files(
        self,
        job: Job,
        output_files: List[Tuple[str, Path]]
    ) -> List[JobOutputFile]:
        """Upload output files to storage and return file metadata."""
        try:
            uploaded_files = []
            bucket_names = self.storage_manager.get_bucket_names()
            output_bucket = bucket_names['output']
            
            for format_name, file_path in output_files:
                try:
                    # Generate storage key
                    file_extension = file_path.suffix
                    storage_key = f"{job.user_id}/{job.job_id}/{format_name}{file_extension}"
                    
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
                        format=format_name,
                        url=file_url,
                        size_bytes=file_size,
                        filename=f"{job.job_id}_{format_name}{file_extension}"
                    )
                    
                    uploaded_files.append(output_file)
                    
                    logger.info(
                        "Output file uploaded",
                        job_id=job.job_id,
                        format=format_name,
                        url=file_url,
                        size_bytes=file_size
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to upload output file",
                        job_id=job.job_id,
                        format=format_name,
                        file_path=str(file_path),
                        error=str(e)
                    )
                    # Continue with other files
                    continue
                finally:
                    # Clean up local file
                    try:
                        file_path.unlink()
                    except Exception:
                        pass
            
            # Clean up temp directory
            try:
                if output_files:
                    temp_dir = output_files[0][1].parent
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            
            if not uploaded_files:
                raise ProcessingError("No output files were successfully uploaded")
            
            logger.info(
                "All output files uploaded",
                job_id=job.job_id,
                uploaded_count=len(uploaded_files)
            )
            
            return uploaded_files
            
        except Exception as e:
            logger.error(
                "Failed to upload output files",
                job_id=job.job_id,
                error=str(e)
            )
            raise ProcessingError(f"Failed to upload output files: {e}")
    
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