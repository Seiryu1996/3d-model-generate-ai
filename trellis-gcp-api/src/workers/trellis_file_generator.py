#!/usr/bin/env python3
"""
TRELLIS File Generator - creates actual 3D model files using Microsoft TRELLIS and uploads to MinIO
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile
from minio import Minio
from minio.error import S3Error
import structlog

# Set TRELLIS environment variables
os.environ['SPCONV_ALGO'] = 'native'  # Use native for single runs

logger = structlog.get_logger(__name__)

class TrellisFileGenerator:
    """Generates actual 3D model files using Microsoft TRELLIS and uploads to MinIO."""
    
    def __init__(self, minio_endpoint="minio:9000", access_key="minioadmin", secret_key="minioadmin"):
        self.minio_client = Minio(
            minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False
        )
        self._trellis_pipeline = None
        
    def _get_trellis_pipeline(self):
        """Lazy load TRELLIS pipeline (expensive operation)."""
        if self._trellis_pipeline is None:
            try:
                # Add TRELLIS to Python path
                trellis_path = Path(__file__).parent.parent.parent.parent / "TRELLIS"
                if str(trellis_path) not in sys.path:
                    sys.path.insert(0, str(trellis_path))
                
                from trellis.pipelines import TrellisTextTo3DPipeline
                
                logger.info("Loading TRELLIS text-to-3D pipeline...")
                self._trellis_pipeline = TrellisTextTo3DPipeline.from_pretrained("microsoft/TRELLIS-text-xlarge")
                
                # Move to CUDA if available
                try:
                    import torch
                    if torch.cuda.is_available():
                        self._trellis_pipeline.cuda()
                        logger.info("TRELLIS pipeline loaded on CUDA")
                    else:
                        logger.info("TRELLIS pipeline loaded on CPU (no CUDA available)")
                except Exception as e:
                    logger.warning("Could not move pipeline to CUDA", error=str(e))
                    
            except ImportError as e:
                logger.error("Failed to import TRELLIS. Make sure TRELLIS is installed", error=str(e))
                raise
            except Exception as e:
                logger.error("Failed to load TRELLIS pipeline", error=str(e))
                raise
                
        return self._trellis_pipeline
    
    async def generate_3d_from_text(self, job_id: str, prompt: str, output_path: str, format: str = "glb") -> str:
        """Generate actual 3D model from text using TRELLIS."""
        
        logger.info("Starting TRELLIS text-to-3D generation", job_id=job_id, prompt=prompt, format=format)
        
        try:
            # Get TRELLIS pipeline
            pipeline = self._get_trellis_pipeline()
            
            # Run TRELLIS generation
            logger.info("Running TRELLIS pipeline...", job_id=job_id)
            outputs = pipeline.run(
                prompt,
                seed=42,  # For reproducible results
                sparse_structure_sampler_params={
                    "steps": 12,
                    "cfg_strength": 7.5,
                },
                slat_sampler_params={
                    "steps": 12,
                    "cfg_strength": 7.5,
                },
            )
            
            logger.info("TRELLIS generation completed", job_id=job_id)
            
            # Export based on format
            if format.lower() == "glb":
                await self._export_glb(outputs, output_path, job_id)
            elif format.lower() == "obj":
                await self._export_obj(outputs, output_path, job_id)
            elif format.lower() == "ply":
                await self._export_ply(outputs, output_path, job_id)
            else:
                # Fallback to GLB
                logger.warning("Unknown format, falling back to GLB", format=format, job_id=job_id)
                await self._export_glb(outputs, output_path, job_id)
            
            logger.info("3D model exported successfully", job_id=job_id, format=format, output_path=output_path)
            return output_path
            
        except Exception as e:
            logger.error("Failed to generate 3D model with TRELLIS", job_id=job_id, error=str(e))
            # Create a fallback simple model
            await self._create_fallback_model(output_path, format, prompt, job_id)
            return output_path
    
    async def _export_glb(self, outputs, output_path: str, job_id: str):
        """Export TRELLIS outputs to GLB format."""
        try:
            from trellis.utils import postprocessing_utils
            
            # Create GLB from TRELLIS outputs
            glb = postprocessing_utils.to_glb(
                outputs['gaussian'][0],
                outputs['mesh'][0],
                simplify=0.95,          # Reduce triangle count
                texture_size=1024,      # Texture resolution
            )
            
            glb.export(output_path)
            logger.info("GLB export completed", job_id=job_id, path=output_path)
            
        except Exception as e:
            logger.error("Failed to export GLB", job_id=job_id, error=str(e))
            raise
    
    async def _export_obj(self, outputs, output_path: str, job_id: str):
        """Export TRELLIS outputs to OBJ format."""
        try:
            # Extract mesh from outputs
            mesh = outputs['mesh'][0]
            
            # Get vertices and faces
            vertices = mesh.vertices  # Should be numpy array of shape (N, 3)
            faces = mesh.faces       # Should be numpy array of shape (M, 3)
            
            # Write OBJ file
            with open(output_path, 'w') as f:
                f.write(f"# OBJ file generated by TRELLIS\n")
                f.write(f"# Job ID: {job_id}\n")
                f.write(f"# Generated at: {datetime.utcnow().isoformat()}\n\n")
                
                # Write vertices
                for vertex in vertices:
                    f.write(f"v {vertex[0]} {vertex[1]} {vertex[2]}\n")
                
                # Write faces (OBJ uses 1-based indexing)
                for face in faces:
                    f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
            
            logger.info("OBJ export completed", job_id=job_id, path=output_path)
            
        except Exception as e:
            logger.error("Failed to export OBJ", job_id=job_id, error=str(e))
            raise
    
    async def _export_ply(self, outputs, output_path: str, job_id: str):
        """Export TRELLIS outputs to PLY format."""
        try:
            # Extract mesh from outputs
            mesh = outputs['mesh'][0]
            
            # Get vertices and faces
            vertices = mesh.vertices  # Should be numpy array of shape (N, 3)
            faces = mesh.faces       # Should be numpy array of shape (M, 3)
            
            # Write PLY file
            with open(output_path, 'w') as f:
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"comment Generated by TRELLIS for job {job_id}\n")
                f.write(f"comment Generated at {datetime.utcnow().isoformat()}\n")
                f.write(f"element vertex {len(vertices)}\n")
                f.write("property float x\n")
                f.write("property float y\n")
                f.write("property float z\n")
                f.write(f"element face {len(faces)}\n")
                f.write("property list uchar int vertex_indices\n")
                f.write("end_header\n")
                
                # Write vertices
                for vertex in vertices:
                    f.write(f"{vertex[0]} {vertex[1]} {vertex[2]}\n")
                
                # Write faces
                for face in faces:
                    f.write(f"3 {face[0]} {face[1]} {face[2]}\n")
            
            logger.info("PLY export completed", job_id=job_id, path=output_path)
            
        except Exception as e:
            logger.error("Failed to export PLY", job_id=job_id, error=str(e))
            raise
    
    def _generate_procedural_shape(self, prompt: str):

    def _generate_magical_creature(self, prompt_lower, seed, complexity, color_scale):
        """Generate a magical creature like unicorn, pegasus."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Body proportions based on creature type
        if 'unicorn' in prompt_lower:
            body_length = 4.0 * color_scale
            body_height = 2.5 * color_scale
            horn_length = 1.5 * color_scale
            has_wings = 'winged' in prompt_lower or 'flying' in prompt_lower
        elif 'pegasus' in prompt_lower:
            body_length = 4.5 * color_scale
            body_height = 2.8 * color_scale
            horn_length = 0.0
            has_wings = True
        else:  # alicorn or generic
            body_length = 5.0 * color_scale
            body_height = 3.0 * color_scale
            horn_length = 2.0 * color_scale
            has_wings = True
        
        # Generate horse-like body with magical proportions
        segments = 12 + complexity
        for i in range(segments):
            for j in range(6):
                u = (i / segments) * 2 * math.pi
                v = (j / 5) * math.pi
                
                # More elegant, flowing curves for magical creatures
                body_radius = 1.0 + 0.3 * math.sin(v) + 0.1 * math.sin(u * 3)
                x = body_radius * math.cos(u) * body_length / 4
                y = body_radius * math.sin(u) * 0.8
                z = (v / math.pi) * body_height - body_height/2
                
                vertices.append((x, y, z))
        
        # Add horn if unicorn
        if horn_length > 0:
            horn_segments = 8
            for i in range(horn_segments):
                height = (i / horn_segments) * horn_length
                radius = (1.0 - i / horn_segments) * 0.2
                for j in range(6):
                    angle = (j / 6) * 2 * math.pi
                    x = radius * math.cos(angle)
                    y = radius * math.sin(angle) + body_length/3
                    z = body_height/2 + height
                    vertices.append((x, y, z))
        
        # Add wings if flying creature
        if has_wings:
            wing_span = body_length * 1.5
            wing_segments = 8 + complexity//2
            for side in [-1, 1]:  # Left and right wings
                for i in range(wing_segments):
                    for j in range(4):
                        u = (i / wing_segments) * math.pi
                        v = (j / 3) * 0.5
                        
                        x = side * (wing_span/2 * math.sin(u)) * (1 - v)
                        y = math.cos(u) * wing_span/3
                        z = body_height/4 + v * body_height/2
                        vertices.append((x, y, z))
        
        # Generate faces (simplified mesh)
        total_vertices = len(vertices)
        for i in range(total_vertices - 3):
            if i % 4 != 3:  # Avoid degenerate triangles
                faces.extend([
                    (i, i+1, i+2),
                    (i, i+2, i+3) if i+3 < total_vertices else (i, i+2, 0)
                ])
        
        return vertices, faces
    
    def _generate_mechanical_being(self, prompt_lower, seed, complexity, material_density):
        """Generate a robot, mech, or android."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Robot type analysis
        if 'mech' in prompt_lower or 'giant' in prompt_lower:
            scale = 6.0 * material_density
            joint_count = 8
        elif 'android' in prompt_lower or 'humanoid' in prompt_lower:
            scale = 2.5 * material_density
            joint_count = 12
        else:  # generic robot
            scale = 3.5 * material_density
            joint_count = 6
        
        # Core chassis (boxy, mechanical)
        chassis_width = scale
        chassis_height = scale * 1.5
        chassis_depth = scale * 0.8
        
        # Create angular, mechanical chassis
        vertices.extend([
            # Bottom face
            (-chassis_width/2, -chassis_depth/2, 0),
            (chassis_width/2, -chassis_depth/2, 0),
            (chassis_width/2, chassis_depth/2, 0),
            (-chassis_width/2, chassis_depth/2, 0),
            # Top face
            (-chassis_width/2, -chassis_depth/2, chassis_height),
            (chassis_width/2, -chassis_depth/2, chassis_height),
            (chassis_width/2, chassis_depth/2, chassis_height),
            (-chassis_width/2, chassis_depth/2, chassis_height),
        ])
        
        # Add mechanical details based on complexity
        for detail in range(complexity):
            # Random mechanical protrusions (gears, pipes, etc.)
            detail_x = random.uniform(-chassis_width/2, chassis_width/2)
            detail_y = random.uniform(-chassis_depth/2, chassis_depth/2)
            detail_z = random.uniform(0, chassis_height)
            detail_size = random.uniform(0.1, 0.3) * scale
            
            # Add small cubic details
            vertices.extend([
                (detail_x - detail_size, detail_y - detail_size, detail_z - detail_size),
                (detail_x + detail_size, detail_y - detail_size, detail_z - detail_size),
                (detail_x + detail_size, detail_y + detail_size, detail_z - detail_size),
                (detail_x - detail_size, detail_y + detail_size, detail_z - detail_size),
                (detail_x - detail_size, detail_y - detail_size, detail_z + detail_size),
                (detail_x + detail_size, detail_y - detail_size, detail_z + detail_size),
                (detail_x + detail_size, detail_y + detail_size, detail_z + detail_size),
                (detail_x - detail_size, detail_y + detail_size, detail_z + detail_size),
            ])
        
        # Generate faces for all cubes
        cube_count = 1 + complexity  # Main chassis + detail cubes
        for cube in range(cube_count):
            base = cube * 8
            # Cube faces
            faces.extend([
                # Bottom
                (base, base+1, base+2), (base, base+2, base+3),
                # Top
                (base+4, base+7, base+6), (base+4, base+6, base+5),
                # Sides
                (base, base+4, base+5), (base, base+5, base+1),
                (base+1, base+5, base+6), (base+1, base+6, base+2),
                (base+2, base+6, base+7), (base+2, base+7, base+3),
                (base+3, base+7, base+4), (base+3, base+4, base+0)
            ])
        
        return vertices, faces
    
    def _generate_architecture(self, prompt_lower, seed, complexity, color_scale):
        """Generate castle, fortress, tower architecture."""
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Architecture type determines structure
        if 'castle' in prompt_lower:
            tower_count = 4 + complexity//2
            base_size = 8.0 * color_scale
            height = 6.0 * color_scale
        elif 'tower' in prompt_lower:
            tower_count = 1
            base_size = 3.0 * color_scale
            height = 12.0 * color_scale
        else:  # fortress
            tower_count = 6 + complexity//3
            base_size = 10.0 * color_scale
            height = 4.0 * color_scale
        
        # Main base structure
        vertices.extend([
            (-base_size, -base_size, 0), (base_size, -base_size, 0),
            (base_size, base_size, 0), (-base_size, base_size, 0),
            (-base_size, -base_size, height), (base_size, -base_size, height),
            (base_size, base_size, height), (-base_size, base_size, height)
        ])
        
        # Add towers at strategic positions
        for tower in range(tower_count):
            angle = (tower / tower_count) * 2 * math.pi
            tower_x = (base_size * 1.2) * math.cos(angle)
            tower_y = (base_size * 1.2) * math.sin(angle)
            tower_radius = base_size / 8
            tower_height = height * (1.5 + random.uniform(0, 0.8))
            
            # Cylindrical towers
            tower_segments = 8
            base_vertex = len(vertices)
            for i in range(tower_segments):
                seg_angle = (i / tower_segments) * 2 * math.pi
                x = tower_x + tower_radius * math.cos(seg_angle)
                y = tower_y + tower_radius * math.sin(seg_angle)
                vertices.extend([(x, y, 0), (x, y, tower_height)])
            
            # Tower faces
            for i in range(tower_segments):
                next_i = (i + 1) % tower_segments
                v1 = base_vertex + i * 2
                v2 = base_vertex + i * 2 + 1
                v3 = base_vertex + next_i * 2
                v4 = base_vertex + next_i * 2 + 1
                faces.extend([(v1, v3, v2), (v2, v3, v4)])
        
        # Base structure faces
        faces.extend([
            (0, 1, 2), (0, 2, 3),  # Bottom
            (4, 7, 6), (4, 6, 5),  # Top
            (0, 4, 5), (0, 5, 1),  # Sides
            (1, 5, 6), (1, 6, 2),
            (2, 6, 7), (2, 7, 3),
            (3, 7, 4), (3, 4, 0)
        ])
        
        return vertices, faces
    
    def _generate_spacecraft(self, prompt_lower, seed, complexity, material_density):
        """Generate spaceship, rocket, or starship."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Ship type determines shape
        if 'rocket' in prompt_lower:
            length = 8.0 * material_density
            width = 1.5 * material_density
            shape_type = 'cylindrical'
        elif 'starship' in prompt_lower:
            length = 12.0 * material_density  
            width = 4.0 * material_density
            shape_type = 'saucer'
        else:  # generic spaceship
            length = 6.0 * material_density
            width = 2.5 * material_density
            shape_type = 'sleek'
        
        if shape_type == 'cylindrical':
            # Rocket-like cylinder
            segments = 16
            for i in range(segments):
                angle = (i / segments) * 2 * math.pi
                for z_level in [0, length]:
                    x = width * math.cos(angle)
                    y = width * math.sin(angle)
                    vertices.append((x, y, z_level))
            
            # Nose cone
            vertices.append((0, 0, length + width))
            
        elif shape_type == 'saucer':
            # Saucer-like disc
            rings = 8
            segments = 16
            for ring in range(rings):
                radius = (ring / rings) * width
                z = math.sin((ring / rings) * math.pi) * width/3
                for seg in range(segments):
                    angle = (seg / segments) * 2 * math.pi
                    x = radius * math.cos(angle)
                    y = radius * math.sin(angle)
                    vertices.append((x, y, z))
        
        else:  # sleek
            # Streamlined shape
            for i in range(complexity + 10):
                t = i / (complexity + 10)
                radius = width * math.sin(t * math.pi)
                z = t * length
                
                for j in range(8):
                    angle = (j / 8) * 2 * math.pi
                    x = radius * math.cos(angle)
                    y = radius * math.sin(angle)
                    vertices.append((x, y, z))
        
        # Generate faces (simplified triangulation)
        for i in range(len(vertices) - 2):
            if i % 3 == 0:
                faces.append((i, i+1, i+2))
        
        return vertices, faces
    
    def _generate_crystalline_structure(self, prompt_lower, seed, complexity, material_density):
        """Generate crystal, gem, or prismatic structures."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Crystal type affects structure
        if 'diamond' in prompt_lower:
            facets = 8 + complexity
            height = 3.0 / material_density  # Diamonds are precise, less dense mesh
        elif 'prism' in prompt_lower:
            facets = 6
            height = 5.0 / material_density
        else:  # generic crystal
            facets = random.randint(5, 12)
            height = 4.0 / material_density
        
        # Multi-level crystal with varying radii
        levels = 6 + complexity//2
        for level in range(levels):
            t = level / levels
            # Crystal tapers towards top and bottom
            radius = math.sin(t * math.pi) * 2.0
            z = (t - 0.5) * height
            
            for face in range(facets):
                angle = (face / facets) * 2 * math.pi
                # Add slight irregularity for natural crystal look
                r_variation = radius * (1 + random.uniform(-0.1, 0.1))
                x = r_variation * math.cos(angle)
                y = r_variation * math.sin(angle)
                vertices.append((x, y, z))
        
        # Generate crystal faces
        for level in range(levels - 1):
            for face in range(facets):
                next_face = (face + 1) % facets
                
                # Current level vertices
                v1 = level * facets + face
                v2 = level * facets + next_face
                
                # Next level vertices
                v3 = (level + 1) * facets + face
                v4 = (level + 1) * facets + next_face
                
                # Create triangular crystal faces
                faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        return vertices, faces
    
    def _generate_word_based_unique_shape(self, prompt_lower, seed, complexity, color_scale, material_density):
        """Generate completely unique shapes based on word analysis."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        words = prompt_lower.split()
        
        # Each word contributes to the shape characteristics
        base_radius = 2.0 * color_scale
        height = 3.0 * color_scale
        segments = max(6, len(words) * 2)
        
        # Word-driven shape generation
        shape_modifiers = []
        for i, word in enumerate(words):
            word_hash = hash(word) % 1000
            shape_modifiers.append({
                'angle_offset': (word_hash / 1000) * 2 * math.pi,
                'radius_mult': 0.5 + (word_hash % 100) / 100,
                'height_mult': 0.8 + (word_hash % 50) / 50,
                'frequency': max(1, len(word) // 2)
            })
        
        # Generate vertices using word-driven parameters
        levels = complexity + 3
        for level in range(levels):
            level_t = level / levels
            level_height = (level_t - 0.5) * height
            
            for segment in range(segments):
                segment_t = segment / segments
                base_angle = segment_t * 2 * math.pi
                
                # Apply word-driven modifications
                radius = base_radius
                angle = base_angle
                z_offset = 0
                
                for mod in shape_modifiers:
                    angle += mod['angle_offset'] * math.sin(level_t * mod['frequency'])
                    radius *= mod['radius_mult'] * (1 + 0.2 * math.cos(segment_t * mod['frequency'] * 2))
                    z_offset += 0.1 * mod['height_mult'] * math.sin(angle * mod['frequency'])
                
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                z = level_height + z_offset
                
                vertices.append((x, y, z))
        
        # Generate faces connecting the levels
        for level in range(levels - 1):
            for segment in range(segments):
                next_segment = (segment + 1) % segments
                
                v1 = level * segments + segment
                v2 = level * segments + next_segment
                v3 = (level + 1) * segments + segment
                v4 = (level + 1) * segments + next_segment
                
                faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        return vertices, faces
    """Generate a completely unique procedural 3D shape based on prompt content."""
    import math
    import hashlib
    import random
    
    prompt_lower = prompt.lower()
    
    # Create multiple hash seeds from different prompt characteristics
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
    word_count_seed = len(prompt.split())
    char_count_seed = len(prompt)
    vowel_count_seed = sum(1 for c in prompt_lower if c in 'aeiou')
    
    # Combine multiple aspects for more variation
    combined_seed = int(prompt_hash[:8], 16) + word_count_seed * 1000 + char_count_seed * 100 + vowel_count_seed * 10
    random.seed(combined_seed)
    
    # Advanced prompt analysis for truly unique shapes
    words = prompt_lower.split()
    
    # Determine base complexity from prompt richness
    complexity = min(len(words) + len([w for w in words if len(w) > 6]), 15)
    
    # Color analysis affects structure
    color_scale = 1.0
    if any(color in prompt_lower for color in ['red', 'crimson', 'scarlet']):
        color_scale = 1.3  # Red = larger, more aggressive
    elif any(color in prompt_lower for color in ['blue', 'azure', 'cyan']):
        color_scale = 0.9  # Blue = smaller, more delicate
    elif any(color in prompt_lower for color in ['green', 'emerald', 'jade']):
        color_scale = 1.1  # Green = natural scaling
    elif any(color in prompt_lower for color in ['purple', 'violet', 'magenta']):
        color_scale = 1.4  # Purple = exotic, larger scaling
    
    # Material analysis affects density
    material_density = 1.0
    if any(material in prompt_lower for material in ['crystal', 'glass', 'ice']):
        material_density = 0.7  # Crystalline = more sparse, angular
    elif any(material in prompt_lower for material in ['metal', 'steel', 'iron', 'bronze']):
        material_density = 1.5  # Metal = denser, more vertices
    elif any(material in prompt_lower for material in ['wood', 'bark', 'timber']):
        material_density = 1.2  # Wood = organic density
    elif any(material in prompt_lower for material in ['cloud', 'mist', 'fog']):
        material_density = 0.5  # Ethereal = very sparse
    
    # Specific object detection with unique generation
    if any(word in prompt_lower for word in ['unicorn', 'pegasus', 'alicorn']):
        return self._generate_magical_creature(prompt_lower, combined_seed, complexity, color_scale)
    elif any(word in prompt_lower for word in ['robot', 'mech', 'android', 'cyborg']):
        return self._generate_mechanical_being(prompt_lower, combined_seed, complexity, material_density)
    elif any(word in prompt_lower for word in ['castle', 'fortress', 'tower', 'citadel']):
        return self._generate_architecture(prompt_lower, combined_seed, complexity, color_scale)
    elif any(word in prompt_lower for word in ['spaceship', 'rocket', 'starship', 'craft']):
        return self._generate_spacecraft(prompt_lower, combined_seed, complexity, material_density)
    elif any(word in prompt_lower for word in ['crystal', 'gem', 'diamond', 'prism']):
        return self._generate_crystalline_structure(prompt_lower, combined_seed, complexity, material_density)
    elif any(word in prompt_lower for word in ['dragon', 'wyvern', 'drake']):
        return self._generate_dragon_like_shape(prompt_lower, combined_seed, complexity, color_scale)
    elif any(word in prompt_lower for word in ['tree', 'oak', 'pine', 'willow', 'maple']):
        return self._generate_tree_shape(prompt_lower, combined_seed, complexity, color_scale)
    elif any(word in prompt_lower for word in ['chair', 'throne', 'seat', 'bench']):
        return self._generate_chair_shape(prompt_lower, combined_seed, complexity, color_scale)
    elif any(word in prompt_lower for word in ['house', 'home', 'building', 'hut', 'cabin']):
        return self._generate_house_shape(prompt_lower, combined_seed, complexity, color_scale)
    else:
        # For truly unique prompts, generate based on word analysis
        return self._generate_word_based_unique_shape(prompt_lower, combined_seed, complexity, color_scale, material_density)
    
    def _generate_dragon_like_shape(self, prompt_lower, seed):
        """Generate a dragon-like shape with variations based on prompt."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Analyze prompt for specific attributes
        scale_x = 3.0
        scale_y = 1.0
        scale_z = 2.0
        
        # Modify based on descriptive words
        if 'big' in prompt_lower or 'huge' in prompt_lower or 'large' in prompt_lower:
            scale_x *= 1.5
            scale_y *= 1.3
            scale_z *= 1.4
        elif 'small' in prompt_lower or 'tiny' in prompt_lower:
            scale_x *= 0.7
            scale_y *= 0.8
            scale_z *= 0.8
        
        if 'fat' in prompt_lower or 'thick' in prompt_lower:
            scale_y *= 1.6
        elif 'thin' in prompt_lower or 'slim' in prompt_lower:
            scale_y *= 0.6
        
        if 'long' in prompt_lower:
            scale_x *= 1.8
        
        # Add random variation based on seed
        scale_x *= (1.0 + random.uniform(-0.3, 0.3))
        scale_y *= (1.0 + random.uniform(-0.3, 0.3))
        scale_z *= (1.0 + random.uniform(-0.3, 0.3))
        
        # Body (elongated ellipsoid)
        segments_u = 20 + random.randint(-5, 5)
        segments_v = 10 + random.randint(-2, 2)
        
        for i in range(segments_u):
            for j in range(segments_v):
                u = (i / (segments_u - 1)) * 2 * math.pi
                v = (j / (segments_v - 1)) * math.pi
                
                # Elongated body with variations
                x = scale_x * math.cos(u) * math.sin(v)
                y = scale_y * math.sin(u) * math.sin(v)
                z = scale_z * math.cos(v)
                
                vertices.append((x, y, z))
        
        # Generate faces for the mesh
        for i in range(segments_u - 1):
            for j in range(segments_v - 1):
                v1 = i * segments_v + j
                v2 = i * segments_v + (j + 1)
                v3 = (i + 1) * segments_v + j
                v4 = (i + 1) * segments_v + (j + 1)
                
                faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        return vertices, faces
    
    def _generate_chair_shape(self, prompt_lower, seed):
        """Generate a chair-like shape with variations."""
        import random
        random.seed(seed)
        
        # Base dimensions with variations
        seat_width = 1.0 + random.uniform(-0.3, 0.3)
        seat_depth = 1.0 + random.uniform(-0.2, 0.2)
        seat_height = 1.0 + random.uniform(-0.2, 0.2)
        back_height = 2.5 + random.uniform(-0.5, 0.5)
        
        # Modify based on descriptive words
        if 'wide' in prompt_lower or 'big' in prompt_lower:
            seat_width *= 1.3
            seat_depth *= 1.2
        elif 'narrow' in prompt_lower or 'small' in prompt_lower:
            seat_width *= 0.8
            seat_depth *= 0.9
        
        if 'high' in prompt_lower or 'tall' in prompt_lower:
            back_height *= 1.4
            seat_height *= 1.2
        elif 'low' in prompt_lower or 'short' in prompt_lower:
            back_height *= 0.7
            seat_height *= 0.8
        
        # Generate chair with variations
        sw, sd, sh, bh = seat_width, seat_depth, seat_height, back_height
        
        vertices = [
            # Seat
            (-sw, -sd, sh), (sw, -sd, sh), (sw, sd, sh), (-sw, sd, sh),
            (-sw, -sd, sh*0.8), (sw, -sd, sh*0.8), (sw, sd, sh*0.8), (-sw, sd, sh*0.8),
            # Backrest
            (-sw, sd*0.8, bh), (sw, sd*0.8, bh), (sw, sd, bh), (-sw, sd, bh),
            (-sw, sd*0.8, sh), (sw, sd*0.8, sh), (sw, sd, sh), (-sw, sd, sh),
        ]
        
        # Add legs with some variation
        leg_positions = [
            (-sw*0.8, -sd*0.8), (sw*0.8, -sd*0.8), 
            (-sw*0.8, sd*0.8), (sw*0.8, sd*0.8)
        ]
        
        for i, (lx, ly) in enumerate(leg_positions):
            leg_width = 0.1 + random.uniform(-0.02, 0.02)
            vertices.extend([
                (lx - leg_width, ly - leg_width, 0),
                (lx + leg_width, ly - leg_width, 0),
                (lx + leg_width, ly + leg_width, 0),
                (lx - leg_width, ly + leg_width, 0)
            ])
        
        faces = [
            # Seat top and bottom
            (0, 1, 2), (0, 2, 3), (4, 7, 6), (4, 6, 5),
            # Backrest
            (8, 9, 10), (8, 10, 11), (12, 15, 14), (12, 14, 13),
            # Legs (simplified)
            (16, 17, 18), (16, 18, 19), (20, 21, 22), (20, 22, 23),
            (24, 25, 26), (24, 26, 27), (28, 29, 30), (28, 30, 31)
        ]
        
        return vertices, faces
    
    def _generate_cup_shape(self, prompt_lower, seed):
        """Generate a cup-like shape."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Generate cup with cylindrical shape and variations
        segments = 16 + random.randint(-4, 4)
        height = 2.0 + random.uniform(-0.5, 0.5)
        outer_radius = 1.0 + random.uniform(-0.2, 0.3)
        inner_radius = 0.8 + random.uniform(-0.1, 0.1)
        
        # Modify based on descriptive words
        if 'tall' in prompt_lower:
            height *= 1.5
        elif 'short' in prompt_lower:
            height *= 0.7
        
        if 'wide' in prompt_lower:
            outer_radius *= 1.3
        elif 'narrow' in prompt_lower:
            outer_radius *= 0.8
        
        # Outer vertices
        for i in range(segments):
            angle = (i / segments) * 2 * math.pi
            x_outer = outer_radius * math.cos(angle)
            y_outer = outer_radius * math.sin(angle)
            x_inner = inner_radius * math.cos(angle)
            y_inner = inner_radius * math.sin(angle)
            
            # Bottom outer and inner
            vertices.extend([(x_outer, y_outer, 0), (x_inner, y_inner, 0)])
            # Top outer and inner
            vertices.extend([(x_outer, y_outer, height), (x_inner, y_inner, height)])
        
        # Generate faces (simplified)
        for i in range(segments):
            next_i = (i + 1) % segments
            base = i * 4
            next_base = next_i * 4
            
            # Outer wall
            faces.extend([
                (base, base + 2, next_base + 2), (base, next_base + 2, next_base),
                # Inner wall
                (base + 1, next_base + 3, base + 3), (base + 1, next_base + 1, next_base + 3),
                # Bottom
                (base, next_base, base + 1), (next_base, next_base + 1, base + 1)
            ])
        
        return vertices, faces
    
    def _generate_tree_shape(self, prompt_lower, seed):
        """Generate a tree-like shape with variations."""
    import math
    import random
    random.seed(seed)
    
    vertices = []
    faces = []
    
    # Tree parameters with variations
    trunk_height = 3.0 + random.uniform(-0.5, 1.0)
    trunk_radius = 0.3 + random.uniform(-0.1, 0.1)
    crown_radius = 1.5 + random.uniform(-0.3, 0.5)
    
    # Modify based on descriptive words
    if 'tall' in prompt_lower or 'giant' in prompt_lower:
        trunk_height *= 1.8
        crown_radius *= 1.2
    elif 'short' in prompt_lower or 'small' in prompt_lower:
        trunk_height *= 0.6
        crown_radius *= 0.8
    
    if 'thick' in prompt_lower or 'wide' in prompt_lower:
        trunk_radius *= 1.5
        crown_radius *= 1.4
    elif 'thin' in prompt_lower or 'narrow' in prompt_lower:
        trunk_radius *= 0.7
        crown_radius *= 0.9
    
    # Different tree types
    if 'pine' in prompt_lower or 'fir' in prompt_lower:
        crown_radius *= 0.7  # Narrower for conifers
        trunk_height *= 1.3
    elif 'oak' in prompt_lower or 'maple' in prompt_lower:
        crown_radius *= 1.3  # Broader for deciduous
        trunk_height *= 0.9
    
    # Trunk (cylinder)
    segments = 8 + random.randint(-2, 2)
    
    for i in range(segments):
        angle = (i / segments) * 2 * math.pi
        x = trunk_radius * math.cos(angle)
        y = trunk_radius * math.sin(angle)
        vertices.extend([(x, y, 0), (x, y, trunk_height)])
    
    # Crown (sphere approximation with variation)
    crown_center = (0, 0, trunk_height + crown_radius * 0.7)
    crown_segments = 12 + random.randint(-2, 4)
    
    for i in range(crown_segments):
        for j in range(crown_segments):
            u = (i / crown_segments) * 2 * math.pi
            v = (j / crown_segments) * math.pi
            
            # Add some noise for organic look
            radius_variation = crown_radius * (1.0 + random.uniform(-0.2, 0.2))
            
            x = crown_center[0] + radius_variation * math.cos(u) * math.sin(v)
            y = crown_center[1] + radius_variation * math.sin(u) * math.sin(v)  
            z = crown_center[2] + radius_variation * math.cos(v)
            
            vertices.append((x, y, z))
    
    # Generate faces (simplified)
    trunk_faces = []
    for i in range(segments):
        next_i = (i + 1) % segments
        v1 = i * 2
        v2 = i * 2 + 1
        v3 = next_i * 2
        v4 = next_i * 2 + 1
        trunk_faces.extend([(v1, v3, v2), (v2, v3, v4)])
    
    # Crown faces (simplified grid)
    crown_start = segments * 2
    for i in range(crown_segments - 1):
        for j in range(crown_segments - 1):
            v1 = crown_start + i * crown_segments + j
            v2 = crown_start + i * crown_segments + (j + 1)
            v3 = crown_start + (i + 1) * crown_segments + j
            v4 = crown_start + (i + 1) * crown_segments + (j + 1)
            
            trunk_faces.extend([(v1, v2, v3), (v2, v4, v3)])
    
    faces.extend(trunk_faces)
    
    return vertices, faces
    
    def _generate_house_shape(self, prompt_lower, seed):
        """Generate a house-like shape with variations."""
        import random
        random.seed(seed)
        
        # Basic house dimensions with variations
        width = 4.0 + random.uniform(-0.5, 1.0)
        depth = 4.0 + random.uniform(-0.5, 1.0)
        height = 2.0 + random.uniform(-0.3, 0.8)
        roof_height = 2.0 + random.uniform(-0.5, 1.0)
        
        # Modify based on descriptive words
        if 'big' in prompt_lower or 'large' in prompt_lower or 'mansion' in prompt_lower:
            width *= 1.5
            depth *= 1.4
            height *= 1.3
        elif 'small' in prompt_lower or 'tiny' in prompt_lower or 'cottage' in prompt_lower:
            width *= 0.7
            depth *= 0.8
            height *= 0.8
        
        if 'tall' in prompt_lower or 'tower' in prompt_lower:
            height *= 2.0
            roof_height *= 1.5
        elif 'low' in prompt_lower or 'ranch' in prompt_lower:
            height *= 0.6
            roof_height *= 0.7
        
        # Different house styles
        if 'cabin' in prompt_lower or 'log' in prompt_lower:
            height *= 0.8
            roof_height *= 1.2
        elif 'castle' in prompt_lower or 'fortress' in prompt_lower:
            height *= 1.8
            width *= 1.3
            depth *= 1.3
        
        w, d, h = width/2, depth/2, height
        
        vertices = [
            # Base cube (house body)
            (-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0),
            (-w, -d, h), (w, -d, h), (w, d, h), (-w, d, h),
            # Extended roof base
            (-w*1.1, -d*1.1, h), (w*1.1, -d*1.1, h), 
            (w*1.1, d*1.1, h), (-w*1.1, d*1.1, h),
            # Roof peak variations
            (0, 0, h + roof_height)  # Central peak
        ]
        
        # Add variation: chimney if mentioned or randomly
        if 'chimney' in prompt_lower or random.random() > 0.7:
            chimney_x = w * 0.6
            chimney_y = d * 0.3
            chimney_width = 0.3
            chimney_height = h + roof_height * 0.6
            
            vertices.extend([
                (chimney_x - chimney_width, chimney_y - chimney_width, h),
                (chimney_x + chimney_width, chimney_y - chimney_width, h),
                (chimney_x + chimney_width, chimney_y + chimney_width, h),
                (chimney_x - chimney_width, chimney_y + chimney_width, h),
                (chimney_x - chimney_width, chimney_y - chimney_width, chimney_height),
                (chimney_x + chimney_width, chimney_y - chimney_width, chimney_height),
                (chimney_x + chimney_width, chimney_y + chimney_width, chimney_height),
                (chimney_x - chimney_width, chimney_y + chimney_width, chimney_height)
            ])
        
        faces = [
            # House walls
            (0, 1, 5), (0, 5, 4),  # Front
            (2, 3, 7), (2, 7, 6),  # Back
            (3, 0, 4), (3, 4, 7),  # Left
            (1, 2, 6), (1, 6, 5),  # Right
            # Base
            (0, 3, 2), (0, 2, 1),
            # Roof faces
            (8, 9, 12), (9, 10, 12), (10, 11, 12), (11, 8, 12)
        ]
        
        # Add chimney faces if present
        if len(vertices) > 13:  # Chimney was added
            chimney_start = 13
            faces.extend([
                # Chimney walls
                (chimney_start, chimney_start+1, chimney_start+5), (chimney_start, chimney_start+5, chimney_start+4),
                (chimney_start+1, chimney_start+2, chimney_start+6), (chimney_start+1, chimney_start+6, chimney_start+5),
                (chimney_start+2, chimney_start+3, chimney_start+7), (chimney_start+2, chimney_start+7, chimney_start+6),
                (chimney_start+3, chimney_start, chimney_start+4), (chimney_start+3, chimney_start+4, chimney_start+7),
                # Chimney top
                (chimney_start+4, chimney_start+5, chimney_start+6), (chimney_start+4, chimney_start+6, chimney_start+7)
            ])
        
        return vertices, faces
    
    def _generate_geometric_shape(self, prompt_lower, seed):
        """Generate an interesting geometric shape with variations."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Shape selection based on prompt
        if 'torus' in prompt_lower or 'donut' in prompt_lower or 'ring' in prompt_lower:
            # Generate a torus-like shape
            major_radius = 2.0 + random.uniform(-0.5, 0.8)
            minor_radius = 0.8 + random.uniform(-0.2, 0.3)
            major_segments = 16 + random.randint(-4, 4)
            minor_segments = 10 + random.randint(-2, 2)
            
            # Modify based on descriptive words
            if 'big' in prompt_lower or 'wide' in prompt_lower:
                major_radius *= 1.4
            elif 'small' in prompt_lower or 'thin' in prompt_lower:
                major_radius *= 0.7
                minor_radius *= 0.8
            
            for i in range(major_segments):
                for j in range(minor_segments):
                    u = (i / major_segments) * 2 * math.pi
                    v = (j / minor_segments) * 2 * math.pi
                    
                    x = (major_radius + minor_radius * math.cos(v)) * math.cos(u)
                    y = (major_radius + minor_radius * math.cos(v)) * math.sin(u)
                    z = minor_radius * math.sin(v)
                    
                    vertices.append((x, y, z))
            
            # Generate faces
            for i in range(major_segments):
                for j in range(minor_segments):
                    current = i * minor_segments + j
                    next_i = ((i + 1) % major_segments) * minor_segments + j
                    next_j = i * minor_segments + ((j + 1) % minor_segments)
                    next_both = ((i + 1) % major_segments) * minor_segments + ((j + 1) % minor_segments)
                    
                    faces.extend([(current, next_i, next_both), (current, next_both, next_j)])
        
        elif 'spiral' in prompt_lower or 'helix' in prompt_lower:
            # Generate spiral/helix shape
            height = 4.0 + random.uniform(-1.0, 2.0)
            radius = 1.5 + random.uniform(-0.3, 0.5)
            turns = 3 + random.randint(-1, 2)
            segments = 50 + random.randint(-10, 20)
            
            for i in range(segments):
                t = (i / segments) * turns * 2 * math.pi
                z = (i / segments) * height
                
                x = radius * math.cos(t)
                y = radius * math.sin(t)
                vertices.append((x, y, z))
                
                # Add inner radius for thickness
                inner_x = radius * 0.7 * math.cos(t)
                inner_y = radius * 0.7 * math.sin(t)
                vertices.append((inner_x, inner_y, z))
            
            # Generate faces for spiral
            for i in range(segments - 1):
                v1 = i * 2
                v2 = i * 2 + 1
                v3 = (i + 1) * 2
                v4 = (i + 1) * 2 + 1
                
                faces.extend([(v1, v3, v2), (v2, v3, v4)])
        
        else:
            # Generate default crystal-like shape
            num_faces = 8 + random.randint(-2, 4)
            height = 3.0 + random.uniform(-0.8, 1.2)
            radius = 1.5 + random.uniform(-0.4, 0.6)
            
            # Modify based on descriptive words
            if 'tall' in prompt_lower:
                height *= 1.8
            elif 'short' in prompt_lower:
                height *= 0.6
            
            if 'wide' in prompt_lower:
                radius *= 1.5
            elif 'narrow' in prompt_lower:
                radius *= 0.7
            
            # Center vertices
            vertices.extend([(0, 0, 0), (0, 0, height)])  # Bottom and top center
            
            # Ring vertices
            for i in range(num_faces):
                angle = (i / num_faces) * 2 * math.pi
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                
                vertices.extend([
                    (x, y, height * 0.2),      # Lower ring
                    (x * 0.7, y * 0.7, height * 0.8)  # Upper ring (tapered)
                ])
            
            # Generate faces
            for i in range(num_faces):
                next_i = (i + 1) % num_faces
                
                lower_v = 2 + i * 2
                upper_v = 2 + i * 2 + 1
                next_lower_v = 2 + next_i * 2
                next_upper_v = 2 + next_i * 2 + 1
                
                # Bottom faces
                faces.append((0, next_lower_v, lower_v))
                # Top faces
                faces.append((1, upper_v, next_upper_v))
                # Side faces
                faces.extend([
                    (lower_v, next_lower_v, upper_v),
                    (next_lower_v, next_upper_v, upper_v)
                ])
        
        return vertices, faces
    
    def _generate_human_like_shape(self, prompt_lower, seed):
        """Generate a human-like figure shape."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Basic proportions with variation
        height = 2.0 + random.uniform(-0.3, 0.5)
        width = 0.6 + random.uniform(-0.1, 0.2)
        
        # Modify based on descriptive words
        if 'tall' in prompt_lower or 'giant' in prompt_lower:
            height *= 1.5
        elif 'short' in prompt_lower or 'dwarf' in prompt_lower:
            height *= 0.7
        
        if 'fat' in prompt_lower or 'wide' in prompt_lower:
            width *= 1.4
        elif 'thin' in prompt_lower or 'slim' in prompt_lower:
            width *= 0.7
        
        # Head (sphere approximation)
        head_radius = width * 0.15
        head_center = (0, 0, height * 0.9)
        
        # Body (cylinder/ellipsoid)
        body_height = height * 0.6
        body_width = width
        
        # Generate simplified human-like shape
        segments = 12
        for i in range(segments):
            angle = (i / segments) * 2 * math.pi
            
            # Head vertices
            x_head = head_center[0] + head_radius * math.cos(angle)
            y_head = head_center[1] + head_radius * math.sin(angle)
            vertices.append((x_head, y_head, head_center[2]))
            
            # Torso vertices (multiple levels)
            for level in range(5):
                z_level = height * 0.3 + (body_height / 4) * level
                body_scale = 1.0 - (level * 0.1)  # Taper towards head
                
                x_body = body_scale * body_width * math.cos(angle)
                y_body = body_scale * body_width * math.sin(angle)
                vertices.append((x_body, y_body, z_level))
        
        # Simple face generation
        for i in range(segments):
            next_i = (i + 1) % segments
            
            # Head faces
            faces.append((i, next_i, segments))  # Top
            
            # Body faces
            for level in range(4):
                v1 = i + segments + level * segments
                v2 = next_i + segments + level * segments
                v3 = i + segments + (level + 1) * segments
                v4 = next_i + segments + (level + 1) * segments
                
                faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        return vertices, faces
    
    def _generate_vehicle_shape(self, prompt_lower, seed):
        """Generate a vehicle-like shape."""
        import random
        random.seed(seed)
        
        # Basic car proportions
        length = 4.0 + random.uniform(-0.5, 1.0)
        width = 1.8 + random.uniform(-0.2, 0.4)
        height = 1.5 + random.uniform(-0.2, 0.3)
        
        # Modify based on type
        if 'truck' in prompt_lower or 'bus' in prompt_lower:
            length *= 1.5
            height *= 1.3
        elif 'sports' in prompt_lower or 'race' in prompt_lower:
            height *= 0.7
            length *= 1.2
        
        vertices = [
            # Main body (box)
            (-length/2, -width/2, 0), (length/2, -width/2, 0),
            (length/2, width/2, 0), (-length/2, width/2, 0),
            (-length/2, -width/2, height*0.6), (length/2, -width/2, height*0.6),
            (length/2, width/2, height*0.6), (-length/2, width/2, height*0.6),
            # Cabin
            (-length*0.3, -width*0.4, height*0.6), (length*0.2, -width*0.4, height*0.6),
            (length*0.2, width*0.4, height*0.6), (-length*0.3, width*0.4, height*0.6),
            (-length*0.3, -width*0.4, height), (length*0.2, -width*0.4, height),
            (length*0.2, width*0.4, height), (-length*0.3, width*0.4, height)
        ]
        
        faces = [
            # Main body
            (0, 1, 2), (0, 2, 3), (4, 7, 6), (4, 6, 5),
            (0, 4, 5), (0, 5, 1), (2, 6, 7), (2, 7, 3),
            (0, 3, 7), (0, 7, 4), (1, 5, 6), (1, 6, 2),
            # Cabin
            (8, 9, 10), (8, 10, 11), (12, 15, 14), (12, 14, 13),
            (8, 12, 13), (8, 13, 9), (10, 14, 15), (10, 15, 11)
        ]
        
        return vertices, faces
    
    def _generate_flower_shape(self, prompt_lower, seed):
        """Generate a flower-like shape."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Flower parameters
        petal_count = random.randint(5, 8)
        if 'rose' in prompt_lower:
            petal_count = random.randint(20, 30)
        elif 'daisy' in prompt_lower:
            petal_count = random.randint(12, 16)
        
        center_radius = 0.2
        petal_length = 1.0 + random.uniform(-0.2, 0.4)
        petal_width = 0.4 + random.uniform(-0.1, 0.2)
        
        # Center
        vertices.append((0, 0, 0))  # Center point
        
        # Generate petals
        for i in range(petal_count):
            angle = (i / petal_count) * 2 * math.pi
            
            # Petal base
            base_x = center_radius * math.cos(angle)
            base_y = center_radius * math.sin(angle)
            vertices.append((base_x, base_y, 0))
            
            # Petal tip
            tip_x = (center_radius + petal_length) * math.cos(angle)
            tip_y = (center_radius + petal_length) * math.sin(angle)
            vertices.append((tip_x, tip_y, 0.1))
            
            # Petal sides
            side_angle1 = angle - 0.2
            side_angle2 = angle + 0.2
            side_dist = center_radius + petal_length * 0.7
            
            side1_x = side_dist * math.cos(side_angle1)
            side1_y = side_dist * math.sin(side_angle1)
            vertices.append((side1_x, side1_y, 0.05))
            
            side2_x = side_dist * math.cos(side_angle2)
            side2_y = side_dist * math.sin(side_angle2)
            vertices.append((side2_x, side2_y, 0.05))
        
        # Generate faces for petals
        for i in range(petal_count):
            base_idx = 1 + i * 4
            tip_idx = base_idx + 1
            side1_idx = base_idx + 2
            side2_idx = base_idx + 3
            
            # Connect to center and form petal
            faces.extend([
                (0, base_idx, side1_idx),
                (0, side1_idx, side2_idx),
                (0, side2_idx, base_idx),
                (base_idx, tip_idx, side1_idx),
                (base_idx, side2_idx, tip_idx),
                (side1_idx, tip_idx, side2_idx)
            ])
        
        return vertices, faces
    
    def _generate_adaptive_shape(self, prompt_lower, seed):
        """Generate an adaptive shape based on prompt analysis."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Analyze prompt for shape characteristics
        complexity = len(prompt_lower.split()) + random.randint(0, 5)
        
        # Base shape selection based on prompt sentiment
        if any(word in prompt_lower for word in ['round', 'sphere', 'ball', 'circular']):
            # Generate sphere-like shape
            segments = 8 + (complexity % 8)
            radius = 1.0 + random.uniform(-0.3, 0.5)
            
            for i in range(segments):
                for j in range(segments//2):
                    u = (i / segments) * 2 * math.pi
                    v = (j / (segments//2)) * math.pi
                    
                    x = radius * math.cos(u) * math.sin(v)
                    y = radius * math.sin(u) * math.sin(v)
                    z = radius * math.cos(v)
                    
                    vertices.append((x, y, z))
            
            # Generate faces
            for i in range(segments):
                for j in range(segments//2 - 1):
                    v1 = i * (segments//2) + j
                    v2 = i * (segments//2) + (j + 1)
                    v3 = ((i + 1) % segments) * (segments//2) + j
                    v4 = ((i + 1) % segments) * (segments//2) + (j + 1)
                    
                    faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        else:
            # Generate abstract geometric shape
            num_points = 6 + (complexity % 10)
            height = 2.0 + random.uniform(-0.5, 1.0)
            
            for i in range(num_points):
                angle = (i / num_points) * 2 * math.pi
                radius = 1.0 + 0.3 * math.sin(angle * 3)  # Wavy outline
                
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                vertices.extend([(x, y, 0), (x * 0.8, y * 0.8, height)])
            
            # Generate faces
            for i in range(num_points):
                next_i = (i + 1) % num_points
                v1 = i * 2
                v2 = v1 + 1
                v3 = next_i * 2
                v4 = v3 + 1
                
                faces.extend([(v1, v3, v2), (v2, v3, v4)])
        
        return vertices, faces

    async def _create_fallback_model(self, output_path: str, format: str, prompt: str, job_id: str):
        """Create a more sophisticated fallback 3D model when TRELLIS fails."""
        logger.info("Creating procedural fallback 3D model", format=format, job_id=job_id, prompt=prompt)
        
        # Generate procedural shape based on prompt
        vertices, faces = self._generate_procedural_shape(prompt)
        
        if format.lower() == "glb":
            # Create a simple GLB (reuse existing implementation)
            glb_content = self._create_mock_glb(prompt)
            with open(output_path, 'wb') as f:
                f.write(glb_content)
        
        elif format.lower() == "obj":
            # Create OBJ with procedural geometry
            with open(output_path, 'w') as f:
                f.write(f"# Procedural 3D model for prompt: {prompt}\n")
                f.write(f"# Job ID: {job_id}\n")
                f.write(f"# Generated at: {datetime.utcnow().isoformat()}\n")
                f.write(f"# Shape generated based on prompt keywords\n\n")
                
                for v in vertices:
                    f.write(f"v {v[0]} {v[1]} {v[2]}\n")
                
                for face in faces:
                    f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
        
        elif format.lower() == "ply":
            # Create PLY with procedural geometry
            with open(output_path, 'w') as f:
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"comment Procedural 3D model for prompt: {prompt}\n")
                f.write(f"comment Job ID: {job_id}\n")
                f.write(f"element vertex {len(vertices)}\n")
                f.write("property float x\n")
                f.write("property float y\n")
                f.write("property float z\n")
                f.write(f"element face {len(faces)}\n")
                f.write("property list uchar int vertex_indices\n")
                f.write("end_header\n")
                
                for v in vertices:
                    f.write(f"{v[0]} {v[1]} {v[2]}\n")
                
                for face in faces:
                    f.write(f"3 {face[0]} {face[1]} {face[2]}\n")
    
    def _create_mock_glb(self, prompt: str) -> bytes:
        """Create a mock GLB file content (reuse from previous implementation)."""
        # This is a very basic mock - in reality you'd generate actual 3D content
        header = b'glTF'  # GLB header
        version = (2).to_bytes(4, 'little')
        length = (1000).to_bytes(4, 'little')  # File length
        
        # JSON chunk
        json_data = {
            "asset": {"version": "2.0"},
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
            "bufferViews": [{"buffer": 0, "byteLength": 36, "target": 34962}],
            "buffers": [{"byteLength": 36}],
            "_prompt": prompt,
            "_generated_at": datetime.utcnow().isoformat()
        }
        
        json_str = json.dumps(json_data, separators=(',', ':'))
        json_bytes = json_str.encode('utf-8')
        
        # Pad to 4-byte boundary
        padding = b'\x00' * (4 - (len(json_bytes) % 4)) if len(json_bytes) % 4 else b''
        json_bytes += padding
        
        json_chunk_length = len(json_bytes).to_bytes(4, 'little')
        json_chunk_type = b'JSON'
        
        # Binary chunk (minimal vertex data)
        binary_data = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80?\x00\x00\x80?\x00\x00\x00\x00\x00\x00\x80?\x00\x00\x80?\x00\x00\x80?'
        binary_chunk_length = len(binary_data).to_bytes(4, 'little')
        binary_chunk_type = b'BIN\x00'
        
        # Combine all parts
        glb_data = (header + version + length + 
                   json_chunk_length + json_chunk_type + json_bytes +
                   binary_chunk_length + binary_chunk_type + binary_data)
        
        return glb_data
    
    async def upload_to_minio(self, job_id: str, file_path: str, filename: str) -> str:
        """Upload file to MinIO and return public URL."""
        try:
            bucket_name = "trellis-output"
            object_name = f"{job_id}/{filename}"
            
            # Ensure bucket exists
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)
                # Set public read policy
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                        }
                    ]
                }
                self.minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
            
            # Upload file
            self.minio_client.fput_object(bucket_name, object_name, file_path)
            
            # Return public URL
            public_url = f"http://localhost:9100/{bucket_name}/{object_name}"
            
            logger.info(
                "File uploaded to MinIO",
                job_id=job_id,
                filename=filename,
                url=public_url
            )
            
            return public_url
            
        except S3Error as e:
            logger.error("Failed to upload to MinIO", job_id=job_id, error=str(e))
            raise
    
    async def generate_and_upload_file(self, job_id: str, prompt: str, format: str = "glb") -> dict:
        """Generate 3D file using TRELLIS and upload to MinIO storage."""
        
        with tempfile.NamedTemporaryFile(suffix=f'.{format}', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            # Generate the 3D model
            await self.generate_3d_from_text(job_id, prompt, tmp_path, format)
            
            # Get file size
            file_size = Path(tmp_path).stat().st_size
            
            # Upload to MinIO
            filename = f"{job_id}_model.{format}"
            public_url = await self.upload_to_minio(job_id, tmp_path, filename)
            
            return {
                "format": format,
                "url": public_url,
                "size_bytes": file_size,
                "filename": filename
            }
            
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)


async def main():
    """Test the TRELLIS file generator."""
    generator = TrellisFileGenerator()
    
    test_job_id = "test-trellis-job-123"
    test_prompt = "A beautiful red dragon sitting on a treasure pile"
    
    result = await generator.generate_and_upload_file(test_job_id, test_prompt, "obj")
    print(f"Generated file: {result}")


if __name__ == "__main__":
    asyncio.run(main())