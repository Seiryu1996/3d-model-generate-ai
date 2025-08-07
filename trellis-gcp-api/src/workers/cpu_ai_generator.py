#!/usr/bin/env python3
"""
CPU-based AI 3D Model Generator
Uses procedural generation, noise functions, and mathematical models
"""

import json
import asyncio
import tempfile
import numpy as np
import structlog
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from datetime import datetime
import trimesh
from scipy.spatial.distance import cdist
from scipy.spatial import SphericalVoronoi
from skimage import measure
import noise

logger = structlog.get_logger(__name__)

class CPUAIGenerator:
    """CPU-based AI 3D model generator using procedural techniques."""
    
    def __init__(self, minio_endpoint="minio:9000", access_key="minioadmin", secret_key="minioadmin"):
        self.minio_client = Minio(
            minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False
        )
    
    def analyze_text_prompt(self, prompt):
        """Analyze text prompt to extract semantic features."""
        prompt_lower = prompt.lower()
        
        # Extract semantic features
        features = {
            'complexity': len(prompt.split()) * 0.1,
            'smoothness': 0.5,
            'scale': 5.0,
            'density': 0.3,
            'organic': 0.5,
            'symmetry': 0.5
        }
        
        # Keyword-based feature adjustment
        if any(word in prompt_lower for word in ['complex', 'detailed', 'intricate']):
            features['complexity'] *= 2.0
        if any(word in prompt_lower for word in ['simple', 'basic', 'minimal']):
            features['complexity'] *= 0.5
        if any(word in prompt_lower for word in ['smooth', 'rounded', 'soft']):
            features['smoothness'] = 0.8
        if any(word in prompt_lower for word in ['rough', 'jagged', 'sharp']):
            features['smoothness'] = 0.2
        if any(word in prompt_lower for word in ['large', 'big', 'huge']):
            features['scale'] = 8.0
        if any(word in prompt_lower for word in ['small', 'tiny', 'mini']):
            features['scale'] = 3.0
        if any(word in prompt_lower for word in ['organic', 'natural', 'flowing']):
            features['organic'] = 0.8
        if any(word in prompt_lower for word in ['geometric', 'angular', 'mechanical']):
            features['organic'] = 0.2
        if any(word in prompt_lower for word in ['symmetric', 'balanced', 'regular']):
            features['symmetry'] = 0.9
        
        logger.info("Text analysis complete", features=features)
        return features
    
    def generate_voxel_field(self, features, resolution=64):
        """Generate 3D voxel field using noise functions."""
        
        # Create coordinate grids
        x = np.linspace(-features['scale'], features['scale'], resolution)
        y = np.linspace(-features['scale'], features['scale'], resolution)
        z = np.linspace(-features['scale'], features['scale'], resolution)
        X, Y, Z = np.meshgrid(x, y, z)
        
        # Generate base noise field
        noise_scale = features['complexity'] * 0.1
        voxels = np.zeros((resolution, resolution, resolution))
        
        for i in range(resolution):
            for j in range(resolution):
                for k in range(resolution):
                    # Combine multiple noise octaves
                    val = 0
                    freq = noise_scale
                    amp = 1.0
                    
                    for octave in range(4):
                        val += noise.pnoise3(
                            X[i,j,k] * freq,
                            Y[i,j,k] * freq,
                            Z[i,j,k] * freq,
                            octaves=1
                        ) * amp
                        freq *= 2
                        amp *= 0.5
                    
                    # Add distance-based falloff for organic shapes
                    if features['organic'] > 0.5:
                        dist = np.sqrt(X[i,j,k]**2 + Y[i,j,k]**2 + Z[i,j,k]**2)
                        falloff = np.exp(-dist / features['scale'])
                        val *= falloff
                    
                    voxels[i,j,k] = val
        
        # Apply threshold based on density
        threshold = np.percentile(voxels, 50)  # Use median as threshold
        return voxels, threshold
    
    def generate_parametric_mesh(self, features):
        """Generate mesh using parametric equations."""
        
        # Create base sphere/ellipsoid
        u = np.linspace(0, 2 * np.pi, 50)
        v = np.linspace(0, np.pi, 25)
        U, V = np.meshgrid(u, v)
        
        # Scale factors based on features
        a = features['scale'] * (1 + features['complexity'] * 0.5)
        b = features['scale'] * (1 + features['organic'] * 0.3)
        c = features['scale'] * (1 + features['symmetry'] * 0.2)
        
        # Generate vertices
        x = a * np.cos(U) * np.sin(V)
        y = b * np.sin(U) * np.sin(V)
        z = c * np.cos(V)
        
        # Add noise deformation
        if features['smoothness'] < 0.7:
            noise_factor = (1 - features['smoothness']) * 0.5
            for i in range(x.shape[0]):
                for j in range(x.shape[1]):
                    noise_val = noise.pnoise3(x[i,j] * 0.1, y[i,j] * 0.1, z[i,j] * 0.1)
                    x[i,j] += noise_val * noise_factor * features['scale']
                    y[i,j] += noise_val * noise_factor * features['scale']
                    z[i,j] += noise_val * noise_factor * features['scale']
        
        # Convert to trimesh format
        vertices = np.column_stack([x.flatten(), y.flatten(), z.flatten()])
        
        # Generate faces for quad mesh
        faces = []
        for i in range(x.shape[0] - 1):
            for j in range(x.shape[1] - 1):
                v1 = i * x.shape[1] + j
                v2 = i * x.shape[1] + (j + 1)
                v3 = (i + 1) * x.shape[1] + j
                v4 = (i + 1) * x.shape[1] + (j + 1)
                
                # Two triangles per quad
                faces.append([v1, v2, v3])
                faces.append([v2, v4, v3])
        
        return vertices, np.array(faces)
    
    async def generate_3d_from_text(self, job_id: str, prompt: str, output_path: str, format: str = "glb"):
        """Generate 3D model from text using CPU-based AI techniques."""
        
        logger.info("Starting CPU-based AI 3D generation", job_id=job_id, prompt=prompt, format=format)
        
        try:
            # Analyze text prompt
            features = self.analyze_text_prompt(prompt)
            
            # Choose generation method based on features
            if features['organic'] > 0.6:
                # Use voxel-based generation for organic shapes
                logger.info("Using voxel-based generation", job_id=job_id)
                voxels, threshold = self.generate_voxel_field(features, resolution=32)
                vertices, faces, _, _ = measure.marching_cubes(voxels, threshold)
                
                # Scale vertices to proper size
                vertices = vertices * (features['scale'] / 16.0) - features['scale']/2
                
            else:
                # Use parametric generation for geometric shapes
                logger.info("Using parametric generation", job_id=job_id)
                vertices, faces = self.generate_parametric_mesh(features)
            
            # Create trimesh object for processing
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            
            # Post-process mesh
            mesh.remove_duplicate_faces()
            mesh.remove_unreferenced_vertices()
            
            if features['smoothness'] > 0.7:
                # Apply smoothing
                mesh = mesh.smoothed()
            
            # Export to requested format
            if format.lower() == "obj":
                await self._export_obj(mesh, prompt, output_path)
            elif format.lower() == "ply":
                await self._export_ply(mesh, prompt, output_path)
            else:
                await self._export_glb(mesh, prompt, output_path)
            
            logger.info("CPU-based AI 3D generation completed", job_id=job_id, format=format)
            return output_path
            
        except Exception as e:
            logger.error("Failed to generate with CPU AI", job_id=job_id, error=str(e))
            raise
    
    async def _export_obj(self, mesh, prompt, output_path):
        """Export mesh to OBJ format."""
        with open(output_path, 'w') as f:
            f.write(f"# CPU AI-Generated 3D model for prompt: {prompt}\n")
            f.write(f"# Generated using procedural AI techniques\n")
            f.write(f"# Generated at: {datetime.utcnow().isoformat()}\n")
            f.write(f"# Vertices: {len(mesh.vertices)}, Faces: {len(mesh.faces)}\n\n")
            
            for v in mesh.vertices:
                f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            
            f.write("\n")
            for face in mesh.faces:
                f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
        
        logger.info("CPU AI OBJ export completed", path=output_path)
    
    async def _export_ply(self, mesh, prompt, output_path):
        """Export mesh to PLY format."""
        mesh.export(output_path)
        logger.info("CPU AI PLY export completed", path=output_path)
    
    async def _export_glb(self, mesh, prompt, output_path):
        """Export mesh to GLB format."""
        mesh.export(output_path)
        logger.info("CPU AI GLB export completed", path=output_path)
    
    async def upload_to_minio(self, job_id: str, file_path: str, filename: str) -> str:
        """Upload AI-generated file to MinIO."""
        try:
            bucket_name = "trellis-output"
            object_name = f"{job_id}/{filename}"
            
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                    }]
                }
                self.minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
            
            self.minio_client.fput_object(bucket_name, object_name, file_path,
                                        content_type="application/octet-stream")
            
            public_url = f"http://localhost:9100/{bucket_name}/{object_name}"
            
            logger.info("CPU AI-generated file uploaded to MinIO",
                       job_id=job_id, filename=filename, url=public_url)
            
            return public_url
            
        except S3Error as e:
            logger.error("Failed to upload CPU AI file to MinIO", job_id=job_id, error=str(e))
            raise
    
    async def generate_and_upload_file(self, job_id: str, prompt: str, format: str = "glb") -> dict:
        """Generate CPU AI-driven 3D file and upload to MinIO."""
        
        with tempfile.NamedTemporaryFile(suffix=f'.{format}', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            # Generate with CPU AI
            await self.generate_3d_from_text(job_id, prompt, tmp_path, format)
            
            file_size = Path(tmp_path).stat().st_size
            filename = f"{job_id}_model.{format}"
            public_url = await self.upload_to_minio(job_id, tmp_path, filename)
            
            return {
                "format": format,
                "url": public_url,
                "size_bytes": file_size,
                "filename": filename
            }
            
        finally:
            Path(tmp_path).unlink(missing_ok=True)


async def main():
    """Test CPU AI generator."""
    generator = CPUAIGenerator()
    
    test_job_id = "cpu-ai-test"
    test_prompt = "organic crystal sculpture"
    
    result = await generator.generate_and_upload_file(test_job_id, test_prompt, "obj")
    print(f"CPU AI generated file: {result}")


if __name__ == "__main__":
    asyncio.run(main())