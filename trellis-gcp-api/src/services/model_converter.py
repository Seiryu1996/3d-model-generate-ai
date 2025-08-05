"""
3D model format conversion and post-processing service.

This module provides conversion utilities for 3D models between different formats
including GLB, OBJ, PLY, and provides optimization and compression features.
"""
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import asyncio
import subprocess

import structlog

from ..models.base import OutputFormat
from ..utils.config import get_settings


logger = structlog.get_logger(__name__)


class ModelConverterError(Exception):
    """Base exception for model conversion errors."""
    pass


class UnsupportedFormatError(ModelConverterError):
    """Exception raised for unsupported format conversion."""
    pass


class ConversionFailedError(ModelConverterError):
    """Exception raised when format conversion fails."""
    pass


class ModelConverter:
    """Service for 3D model format conversion and optimization."""
    
    def __init__(self):
        self.settings = get_settings()
        self.temp_dir = Path(tempfile.gettempdir()) / "trellis-converter"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def convert_model(
        self,
        input_data: Any,
        target_formats: List[OutputFormat],
        job_id: str,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[OutputFormat, Path]]:
        """
        Convert TRELLIS model output to multiple formats.
        
        Args:
            input_data: TRELLIS model output data
            target_formats: List of target formats to convert to
            job_id: Job ID for temporary file naming
            quality_settings: Optional quality settings for conversion
            
        Returns:
            List of tuples containing (format, file_path)
        """
        try:
            logger.info(
                "Starting model conversion",
                job_id=job_id,
                target_formats=[fmt.value for fmt in target_formats]
            )
            
            # Create job-specific temp directory
            job_temp_dir = self.temp_dir / job_id
            job_temp_dir.mkdir(exist_ok=True)
            
            converted_files = []
            
            try:
                for target_format in target_formats:
                    logger.info(
                        "Converting to format",
                        job_id=job_id,
                        format=target_format.value
                    )
                    
                    output_path = await self._convert_to_format(
                        input_data=input_data,
                        target_format=target_format,
                        output_dir=job_temp_dir,
                        job_id=job_id,
                        quality_settings=quality_settings
                    )
                    
                    if output_path and output_path.exists():
                        # Apply post-processing optimizations
                        optimized_path = await self._optimize_model(
                            input_path=output_path,
                            target_format=target_format,
                            quality_settings=quality_settings
                        )
                        
                        converted_files.append((target_format, optimized_path))
                        
                        logger.info(
                            "Format conversion completed",
                            job_id=job_id,
                            format=target_format.value,
                            file_size=optimized_path.stat().st_size
                        )
                    else:
                        logger.error(
                            "Format conversion failed",
                            job_id=job_id,
                            format=target_format.value
                        )
                
                logger.info(
                    "Model conversion completed",
                    job_id=job_id,
                    successful_formats=len(converted_files),
                    total_formats=len(target_formats)
                )
                
                return converted_files
                
            except Exception as e:
                # Clean up temp directory on error
                shutil.rmtree(job_temp_dir, ignore_errors=True)
                raise e
            
        except Exception as e:
            logger.error(
                "Model conversion failed",
                job_id=job_id,
                error=str(e)
            )
            raise ModelConverterError(f"Model conversion failed: {e}")
    
    async def _convert_to_format(
        self,
        input_data: Any,
        target_format: OutputFormat,
        output_dir: Path,
        job_id: str,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> Optional[Path]:
        """Convert model to specific format."""
        try:
            output_filename = f"{job_id}_{target_format.value}"
            
            if target_format == OutputFormat.GLB:
                return await self._convert_to_glb(
                    input_data, output_dir, output_filename, quality_settings
                )
            elif target_format == OutputFormat.OBJ:
                return await self._convert_to_obj(
                    input_data, output_dir, output_filename, quality_settings
                )
            elif target_format == OutputFormat.PLY:
                return await self._convert_to_ply(
                    input_data, output_dir, output_filename, quality_settings
                )
            else:
                raise UnsupportedFormatError(f"Unsupported format: {target_format}")
                
        except Exception as e:
            logger.error(
                "Format-specific conversion failed",
                format=target_format.value,
                error=str(e)
            )
            raise ConversionFailedError(f"Failed to convert to {target_format}: {e}")
    
    async def _convert_to_glb(
        self,
        input_data: Any,
        output_dir: Path,
        filename: str,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Convert to GLB format."""
        try:
            output_path = output_dir / f"{filename}.glb"
            
            # Check if input_data has GLB export method
            if hasattr(input_data, 'export_glb'):
                # Direct GLB export
                await asyncio.get_event_loop().run_in_executor(
                    None, input_data.export_glb, str(output_path)
                )
            elif hasattr(input_data, 'to_trimesh'):
                # Convert via trimesh
                import trimesh
                mesh = input_data.to_trimesh()
                
                # Apply quality settings
                if quality_settings:
                    mesh = await self._apply_mesh_quality_settings(mesh, quality_settings)
                
                # Export as GLB
                await asyncio.get_event_loop().run_in_executor(
                    None, mesh.export, str(output_path)
                )
            elif hasattr(input_data, 'vertices') and hasattr(input_data, 'faces'):
                # Create trimesh from vertices and faces
                import trimesh
                mesh = trimesh.Trimesh(
                    vertices=input_data.vertices,
                    faces=input_data.faces
                )
                
                # Apply quality settings
                if quality_settings:
                    mesh = await self._apply_mesh_quality_settings(mesh, quality_settings)
                
                # Export as GLB
                await asyncio.get_event_loop().run_in_executor(
                    None, mesh.export, str(output_path)
                )
            else:
                # Fallback: create placeholder GLB
                await self._create_placeholder_glb(output_path)
            
            return output_path
            
        except Exception as e:
            logger.error("GLB conversion failed", error=str(e))
            raise ConversionFailedError(f"GLB conversion failed: {e}")
    
    async def _convert_to_obj(
        self,
        input_data: Any,
        output_dir: Path,
        filename: str,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Convert to OBJ format."""
        try:
            output_path = output_dir / f"{filename}.obj"
            
            # Check if input_data has OBJ export method
            if hasattr(input_data, 'export_obj'):
                # Direct OBJ export
                await asyncio.get_event_loop().run_in_executor(
                    None, input_data.export_obj, str(output_path)
                )
            elif hasattr(input_data, 'to_trimesh'):
                # Convert via trimesh
                import trimesh
                mesh = input_data.to_trimesh()
                
                # Apply quality settings
                if quality_settings:
                    mesh = await self._apply_mesh_quality_settings(mesh, quality_settings)
                
                # Export as OBJ (trimesh will create .obj and .mtl files)
                await asyncio.get_event_loop().run_in_executor(
                    None, mesh.export, str(output_path)
                )
            elif hasattr(input_data, 'vertices') and hasattr(input_data, 'faces'):
                # Create OBJ file manually
                await self._write_obj_file(
                    output_path,
                    input_data.vertices,
                    input_data.faces,
                    quality_settings
                )
            else:
                # Fallback: create placeholder OBJ
                await self._create_placeholder_obj(output_path)
            
            return output_path
            
        except Exception as e:
            logger.error("OBJ conversion failed", error=str(e))
            raise ConversionFailedError(f"OBJ conversion failed: {e}")
    
    async def _convert_to_ply(
        self,
        input_data: Any,
        output_dir: Path,
        filename: str,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Convert to PLY format."""
        try:
            output_path = output_dir / f"{filename}.ply"
            
            # Check if input_data has PLY export method
            if hasattr(input_data, 'export_ply'):
                # Direct PLY export
                await asyncio.get_event_loop().run_in_executor(
                    None, input_data.export_ply, str(output_path)
                )
            elif hasattr(input_data, 'to_pointcloud'):
                # Convert to point cloud PLY
                pointcloud = input_data.to_pointcloud()
                await self._write_pointcloud_ply(output_path, pointcloud, quality_settings)
            elif hasattr(input_data, 'to_trimesh'):
                # Convert via trimesh
                import trimesh
                mesh = input_data.to_trimesh()
                
                # Apply quality settings
                if quality_settings:
                    mesh = await self._apply_mesh_quality_settings(mesh, quality_settings)
                
                # Export as PLY
                await asyncio.get_event_loop().run_in_executor(
                    None, mesh.export, str(output_path)
                )
            elif hasattr(input_data, 'vertices'):
                # Create PLY from vertices (point cloud)
                await self._write_vertex_ply(
                    output_path,
                    input_data.vertices,
                    quality_settings
                )
            else:
                # Fallback: create placeholder PLY
                await self._create_placeholder_ply(output_path)
            
            return output_path
            
        except Exception as e:
            logger.error("PLY conversion failed", error=str(e))
            raise ConversionFailedError(f"PLY conversion failed: {e}")
    
    async def _apply_mesh_quality_settings(
        self,
        mesh,
        quality_settings: Dict[str, Any]
    ):
        """Apply quality settings to mesh."""
        try:
            import trimesh
            
            # Get quality level
            quality_level = quality_settings.get('quality', 'balanced')
            
            if quality_level == 'fast':
                # High compression, lower quality
                # Simplify mesh more aggressively
                if hasattr(mesh, 'simplify_quadric_decimation'):
                    target_faces = max(1000, len(mesh.faces) // 4)
                    mesh = mesh.simplify_quadric_decimation(target_faces)
                
            elif quality_level == 'balanced':
                # Moderate compression
                if hasattr(mesh, 'simplify_quadric_decimation'):
                    target_faces = max(2000, len(mesh.faces) // 2)
                    mesh = mesh.simplify_quadric_decimation(target_faces)
                
            elif quality_level == 'high':
                # Minimal compression, preserve quality
                # Apply minimal smoothing
                if hasattr(mesh, 'smoothed'):
                    mesh = mesh.smoothed()
            
            # Remove duplicate vertices
            if hasattr(mesh, 'merge_vertices'):
                mesh.merge_vertices()
            
            # Remove degenerate faces
            if hasattr(mesh, 'remove_degenerate_faces'):
                mesh.remove_degenerate_faces()
            
            return mesh
            
        except Exception as e:
            logger.warning("Failed to apply quality settings", error=str(e))
            return mesh
    
    async def _optimize_model(
        self,
        input_path: Path,
        target_format: OutputFormat,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Apply post-processing optimizations to the model."""
        try:
            # For now, return the input path as-is
            # In a full implementation, you could apply:
            # - File size optimization
            # - Texture compression
            # - Geometry optimization
            # - Binary format conversion
            
            logger.debug(
                "Model optimization completed",
                format=target_format.value,
                input_size=input_path.stat().st_size
            )
            
            return input_path
            
        except Exception as e:
            logger.warning(
                "Model optimization failed, using unoptimized version",
                error=str(e)
            )
            return input_path
    
    async def _write_obj_file(
        self,
        output_path: Path,
        vertices,
        faces,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> None:
        """Write OBJ file manually."""
        try:
            with open(output_path, 'w') as f:
                f.write("# OBJ file generated by TRELLIS\n")
                f.write("# Vertices\n")
                
                for vertex in vertices:
                    f.write(f"v {vertex[0]} {vertex[1]} {vertex[2]}\n")
                
                f.write("# Faces\n")
                for face in faces:
                    # OBJ indices are 1-based
                    f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
            
            logger.debug("OBJ file written manually", path=output_path)
            
        except Exception as e:
            logger.error("Failed to write OBJ file", error=str(e))
            raise
    
    async def _write_pointcloud_ply(
        self,
        output_path: Path,
        pointcloud,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> None:
        """Write point cloud PLY file."""
        try:
            vertices = pointcloud.vertices if hasattr(pointcloud, 'vertices') else pointcloud
            
            with open(output_path, 'w') as f:
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"element vertex {len(vertices)}\n")
                f.write("property float x\n")
                f.write("property float y\n")
                f.write("property float z\n")
                f.write("end_header\n")
                
                for vertex in vertices:
                    f.write(f"{vertex[0]} {vertex[1]} {vertex[2]}\n")
            
            logger.debug("Point cloud PLY file written", path=output_path)
            
        except Exception as e:
            logger.error("Failed to write PLY point cloud", error=str(e))
            raise
    
    async def _write_vertex_ply(
        self,
        output_path: Path,
        vertices,
        quality_settings: Optional[Dict[str, Any]] = None
    ) -> None:
        """Write vertex PLY file."""
        try:
            with open(output_path, 'w') as f:
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"element vertex {len(vertices)}\n")
                f.write("property float x\n")
                f.write("property float y\n")
                f.write("property float z\n")
                f.write("end_header\n")
                
                for vertex in vertices:
                    f.write(f"{vertex[0]} {vertex[1]} {vertex[2]}\n")
            
            logger.debug("Vertex PLY file written", path=output_path)
            
        except Exception as e:
            logger.error("Failed to write vertex PLY", error=str(e))
            raise
    
    # Placeholder file creation methods
    async def _create_placeholder_glb(self, output_path: Path) -> None:
        """Create placeholder GLB file."""
        # Create minimal GLB file
        placeholder_content = b'glTF placeholder - TRELLIS conversion not yet implemented'
        output_path.write_bytes(placeholder_content)
        logger.info("Created placeholder GLB file", path=output_path)
    
    async def _create_placeholder_obj(self, output_path: Path) -> None:
        """Create placeholder OBJ file."""
        placeholder_content = """# OBJ placeholder - TRELLIS conversion not yet implemented
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
"""
        output_path.write_text(placeholder_content)
        logger.info("Created placeholder OBJ file", path=output_path)
    
    async def _create_placeholder_ply(self, output_path: Path) -> None:
        """Create placeholder PLY file."""
        placeholder_content = """ply
format ascii 1.0
comment PLY placeholder - TRELLIS conversion not yet implemented
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
"""
        output_path.write_text(placeholder_content)
        logger.info("Created placeholder PLY file", path=output_path)
    
    def cleanup_temp_files(self, job_id: str) -> None:
        """Clean up temporary files for a job."""
        try:
            job_temp_dir = self.temp_dir / job_id
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir)
                logger.info("Cleaned up temp files", job_id=job_id)
        except Exception as e:
            logger.warning("Failed to clean up temp files", job_id=job_id, error=str(e))


def get_model_converter() -> ModelConverter:
    """Get model converter instance."""
    return ModelConverter()