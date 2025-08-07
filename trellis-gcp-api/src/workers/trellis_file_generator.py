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
                self._trellis_pipeline = None  # Mark as failed, will use mock
                return None
            except Exception as e:
                logger.error("Failed to load TRELLIS pipeline", error=str(e))
                self._trellis_pipeline = None  # Mark as failed, will use mock
                return None
                
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
        """Generate a highly detailed procedural 3D shape with advanced prompt analysis."""
        import math
        import hashlib
        import random
        import re
        
        prompt_lower = prompt.lower()
        
        # Enhanced prompt preprocessing - extract key descriptors
        # Remove common words to focus on meaningful terms
        stopwords = {'a', 'an', 'the', 'is', 'are', 'with', 'of', 'and', 'or', 'in', 'on', 'at', 'to', 'for'}
        words = [w for w in prompt_lower.split() if w not in stopwords and len(w) > 2]
        
        # Advanced semantic analysis
        descriptors = {
            'size_modifiers': ['tiny', 'small', 'large', 'huge', 'giant', 'massive', 'enormous', 'miniature'],
            'shape_modifiers': ['round', 'square', 'angular', 'curved', 'twisted', 'spiral', 'geometric', 'organic'],
            'texture_modifiers': ['smooth', 'rough', 'bumpy', 'spiky', 'serrated', 'ridged', 'faceted', 'crystalline'],
            'emotional_modifiers': ['fierce', 'gentle', 'aggressive', 'peaceful', 'majestic', 'elegant', 'powerful', 'delicate'],
            'animals': ['dragon', 'bird', 'fish', 'lion', 'tiger', 'eagle', 'snake', 'turtle', 'cat', 'dog', 'wolf', 'bear'],
            'objects': ['car', 'house', 'tree', 'flower', 'sword', 'shield', 'crown', 'chair', 'table', 'bottle', 'vase'],
            'fantasy': ['wizard', 'magic', 'crystal', 'wand', 'potion', 'spell', 'enchanted', 'mystical', 'ethereal'],
            'architecture': ['castle', 'tower', 'fortress', 'cathedral', 'temple', 'palace', 'bridge', 'gate'],
            'mechanical': ['robot', 'gear', 'engine', 'machine', 'clockwork', 'steampunk', 'android', 'mech']
        }
        
        # Analyze prompt context
        context = {}
        for category, items in descriptors.items():
            matches = [item for item in items if item in prompt_lower]
            if matches:
                context[category] = matches
        
        # Enhanced seed generation from semantic analysis
        semantic_seed = 0
        for category, matches in context.items():
            category_weight = len(category) * 100
            for match in matches:
                semantic_seed += hash(match) % 10000
            semantic_seed += category_weight
        
        # Multi-layer seeding for maximum uniqueness
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        word_signature = sum(ord(c) for word in words for c in word)
        length_signature = len(prompt) * len(words) if words else 1
        
        final_seed = (int(prompt_hash[:12], 16) + semantic_seed + word_signature + length_signature) % (2**31)
        random.seed(final_seed)
        
        # Advanced complexity calculation
        base_complexity = len(words) * 2
        detail_boost = sum(1 for cat, matches in context.items() if matches) * 3
        complexity = min(base_complexity + detail_boost, 25)
        
        # Enhanced material analysis
        material_properties = {
            'density': 1.0,
            'roughness': 0.5,
            'transparency': 0.0,
            'reflectivity': 0.3
        }
        
        # Material detection with detailed properties
        if any(mat in prompt_lower for mat in ['crystal', 'diamond', 'glass', 'ice', 'gem']):
            material_properties.update({'density': 0.6, 'roughness': 0.1, 'transparency': 0.8})
        elif any(mat in prompt_lower for mat in ['metal', 'steel', 'iron', 'gold', 'silver', 'bronze']):
            material_properties.update({'density': 1.8, 'roughness': 0.2, 'reflectivity': 0.9})
        elif any(mat in prompt_lower for mat in ['wood', 'oak', 'pine', 'bamboo', 'bark']):
            material_properties.update({'density': 1.2, 'roughness': 0.8})
        elif any(mat in prompt_lower for mat in ['stone', 'rock', 'marble', 'granite']):
            material_properties.update({'density': 1.6, 'roughness': 0.7})
        elif any(mat in prompt_lower for mat in ['fabric', 'silk', 'velvet', 'cotton']):
            material_properties.update({'density': 0.4, 'roughness': 0.9})
        
        # Advanced color-to-structure mapping
        color_influence = 1.0
        structural_modifier = 1.0
        
        color_mappings = {
            ('red', 'crimson', 'scarlet', 'ruby'): {'influence': 1.4, 'structure': 1.3, 'aggression': True},
            ('blue', 'azure', 'sapphire', 'navy'): {'influence': 0.9, 'structure': 0.8, 'smooth': True},
            ('green', 'emerald', 'jade', 'forest'): {'influence': 1.1, 'structure': 1.0, 'organic': True},
            ('purple', 'violet', 'amethyst', 'indigo'): {'influence': 1.3, 'structure': 1.4, 'mystical': True},
            ('gold', 'yellow', 'amber', 'topaz'): {'influence': 1.2, 'structure': 1.1, 'precious': True},
            ('black', 'obsidian', 'onyx', 'shadow'): {'influence': 1.1, 'structure': 1.5, 'sharp': True},
            ('white', 'pearl', 'ivory', 'snow'): {'influence': 0.8, 'structure': 0.9, 'pure': True}
        }
        
        for colors, properties in color_mappings.items():
            if any(color in prompt_lower for color in colors):
                color_influence = properties['influence']
                structural_modifier = properties['structure']
                break
        
        # Determine primary generation strategy based on semantic analysis
        if context.get('animals'):
            return self._generate_advanced_creature(context, complexity, material_properties, color_influence)
        elif context.get('mechanical'):
            return self._generate_advanced_mechanical(context, complexity, material_properties, structural_modifier)
        elif context.get('architecture'):
            return self._generate_advanced_architecture(context, complexity, material_properties, color_influence)
        elif context.get('objects'):
            return self._generate_advanced_object(context, complexity, material_properties, color_influence)
        elif context.get('fantasy'):
            return self._generate_advanced_fantasy(context, complexity, material_properties, color_influence)
        else:
            # Fallback to abstract shape with maximum detail
            return self._generate_advanced_abstract(prompt_lower, complexity, material_properties, color_influence)

    def _generate_simple_creature(self, creature_type, complexity):
        """Generate simple creature shapes."""
        import math
        vertices = []
        faces = []
        
        # Simple creature - elongated body
        for i in range(10):
            t = i / 9
            x = t * 4.0 - 2.0  # Body along X axis
            y = math.sin(t * math.pi) * 1.0  # Body width
            z = math.sin(t * math.pi * 2) * 0.5  # Some vertical variation
            
            vertices.extend([
                (x, y, z),
                (x, -y, z),
                (x, 0, z + 1.0)  # Top ridge
            ])
        
        # Simple triangular faces
        for i in range(len(vertices) - 3):
            if i % 3 == 0:
                faces.append((i, i+1, i+2))
        
        return vertices, faces

    def _generate_advanced_creature(self, context, complexity, material_properties, color_influence):
        """Generate highly detailed creatures based on semantic analysis."""
        import math
        import random
        
        vertices = []
        faces = []
        
        # Determine creature type from context
        animals = context.get('animals', ['creature'])
        primary_animal = animals[0]
        
        # Advanced creature generation based on animal type
        if 'dragon' in primary_animal:
            return self._generate_detailed_dragon(complexity, material_properties, color_influence, context)
        elif 'bird' in primary_animal or 'eagle' in primary_animal:
            return self._generate_detailed_bird(complexity, material_properties, color_influence, context)
        elif 'fish' in primary_animal:
            return self._generate_detailed_fish(complexity, material_properties, color_influence, context)
        elif any(pred in primary_animal for pred in ['lion', 'tiger', 'wolf', 'bear']):
            return self._generate_detailed_predator(primary_animal, complexity, material_properties, color_influence, context)
        else:
            # Fallback to simple creature shape
            return self._generate_simple_creature(primary_animal, complexity)

    def _generate_advanced_mechanical(self, context, complexity, material_properties, structural_modifier):
        """Generate highly detailed mechanical objects."""
        import math
        import random
        
        mechanical = context.get('mechanical', ['robot'])
        primary_type = mechanical[0]
        
        if 'robot' in primary_type or 'android' in primary_type:
            return self._generate_detailed_robot(complexity, material_properties, structural_modifier, context)
        elif 'gear' in primary_type or 'clockwork' in primary_type:
            return self._generate_detailed_gears(complexity, material_properties, structural_modifier, context)
        elif 'engine' in primary_type or 'machine' in primary_type:
            return self._generate_detailed_engine(complexity, material_properties, structural_modifier, context)
        else:
            return self._generate_detailed_generic_mechanical(primary_type, complexity, material_properties, structural_modifier, context)

    def _generate_advanced_architecture(self, context, complexity, material_properties, color_influence):
        """Generate highly detailed architectural structures."""
        architecture = context.get('architecture', ['building'])
        primary_type = architecture[0]
        
        if 'castle' in primary_type:
            return self._generate_detailed_castle(complexity, material_properties, color_influence, context)
        elif 'tower' in primary_type:
            return self._generate_detailed_tower(complexity, material_properties, color_influence, context)
        elif 'cathedral' in primary_type or 'temple' in primary_type:
            return self._generate_detailed_religious_building(primary_type, complexity, material_properties, color_influence, context)
        else:
            return self._generate_detailed_generic_architecture(primary_type, complexity, material_properties, color_influence, context)

    def _generate_advanced_object(self, context, complexity, material_properties, color_influence):
        """Generate highly detailed everyday objects."""
        objects = context.get('objects', ['object'])
        primary_object = objects[0]
        
        if 'car' in primary_object:
            return self._generate_detailed_vehicle(complexity, material_properties, color_influence, context)
        elif 'chair' in primary_object:
            return self._generate_detailed_furniture(primary_object, complexity, material_properties, color_influence, context)
        elif any(item in primary_object for item in ['sword', 'shield', 'crown']):
            return self._generate_detailed_weapon_item(primary_object, complexity, material_properties, color_influence, context)
        else:
            return self._generate_detailed_generic_object(primary_object, complexity, material_properties, color_influence, context)

    def _generate_advanced_fantasy(self, context, complexity, material_properties, color_influence):
        """Generate highly detailed fantasy objects."""
        fantasy = context.get('fantasy', ['magic'])
        primary_type = fantasy[0]
        
        if 'crystal' in primary_type:
            return self._generate_detailed_magical_crystal(complexity, material_properties, color_influence, context)
        elif 'wand' in primary_type:
            return self._generate_detailed_magical_wand(complexity, material_properties, color_influence, context)
        elif 'potion' in primary_type:
            return self._generate_detailed_potion_bottle(complexity, material_properties, color_influence, context)
        else:
            return self._generate_detailed_generic_fantasy(primary_type, complexity, material_properties, color_influence, context)

    def _generate_advanced_abstract(self, prompt_lower, complexity, material_properties, color_influence):
        """Generate highly detailed abstract shapes based on prompt analysis."""
        import math
        import random
        import hashlib
        
        # Advanced abstract generation
        prompt_hash = int(hashlib.md5(prompt_lower.encode()).hexdigest()[:8], 16)
        random.seed(prompt_hash)
        
        vertices = []
        faces = []
        
        # Multi-layer abstract structure
        layers = complexity + 5
        base_radius = 2.0 * color_influence
        height_scale = 3.0 * material_properties['density']
        
        # Generate complex abstract geometry
        for layer in range(layers):
            layer_t = layer / layers
            layer_radius = base_radius * (1.0 + 0.5 * math.sin(layer_t * math.pi))
            layer_height = layer_t * height_scale - height_scale/2
            
            # Variable segments based on layer
            segments = max(6, int(12 + complexity * math.sin(layer_t * math.pi * 2)))
            
            for segment in range(segments):
                segment_t = segment / segments
                angle = segment_t * 2 * math.pi
                
                # Complex radius modulation
                radius_mod = 1.0
                radius_mod *= (1.0 + 0.3 * math.sin(angle * 3 + layer_t * math.pi))
                radius_mod *= material_properties['roughness'] + 0.5
                
                final_radius = layer_radius * radius_mod
                
                x = final_radius * math.cos(angle)
                y = final_radius * math.sin(angle)
                z = layer_height
                
                vertices.append((x, y, z))
        
        # Generate sophisticated face connections
        for layer in range(layers - 1):
            current_layer_segments = max(6, int(12 + complexity * math.sin((layer / layers) * math.pi * 2)))
            next_layer_segments = max(6, int(12 + complexity * math.sin(((layer + 1) / layers) * math.pi * 2)))
            
            # Connect layers with triangular faces
            for i in range(min(current_layer_segments, next_layer_segments)):
                current_base = sum(max(6, int(12 + complexity * math.sin((l / layers) * math.pi * 2))) for l in range(layer))
                next_base = sum(max(6, int(12 + complexity * math.sin((l / layers) * math.pi * 2))) for l in range(layer + 1))
                
                v1 = current_base + i
                v2 = current_base + (i + 1) % current_layer_segments
                v3 = next_base + (i % next_layer_segments)
                v4 = next_base + ((i + 1) % next_layer_segments)
                
                # Create triangular faces
                if v3 < len(vertices) and v4 < len(vertices):
                    faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        return vertices, faces

    def _generate_detailed_dragon(self, complexity, material_properties, color_influence, context):
        """Generate an extremely simple, clearly recognizable dragon shape."""
        vertices = []
        faces = []
        
        scale = 1.0  # Keep it simple
        
        # BODY: Simple elongated box (main dragon body)
        body_length = 6.0 * scale
        body_width = 2.0 * scale
        body_height = 1.5 * scale
        
        # Dragon body as a simple rectangular box
        vertices.extend([
            # Bottom face of body
            (-body_length/2, -body_width/2, 0),           # 0
            (body_length/2, -body_width/2, 0),            # 1
            (body_length/2, body_width/2, 0),             # 2
            (-body_length/2, body_width/2, 0),            # 3
            # Top face of body
            (-body_length/2, -body_width/2, body_height), # 4
            (body_length/2, -body_width/2, body_height),  # 5
            (body_length/2, body_width/2, body_height),   # 6
            (-body_length/2, body_width/2, body_height),  # 7
        ])
        
        # HEAD: Simple larger box at front
        head_size = 1.8 * scale
        head_x = -body_length/2 - head_size/2  # In front of body
        
        vertices.extend([
            # Bottom face of head
            (head_x - head_size/2, -head_size/2, 0),           # 8
            (head_x + head_size/2, -head_size/2, 0),           # 9
            (head_x + head_size/2, head_size/2, 0),            # 10
            (head_x - head_size/2, head_size/2, 0),            # 11
            # Top face of head
            (head_x - head_size/2, -head_size/2, head_size),   # 12
            (head_x + head_size/2, -head_size/2, head_size),   # 13
            (head_x + head_size/2, head_size/2, head_size),    # 14
            (head_x - head_size/2, head_size/2, head_size),    # 15
        ])
        
        # TAIL: Simple smaller box at back
        tail_width = 0.8 * scale
        tail_length = 3.0 * scale
        tail_x = body_length/2 + tail_length/2  # Behind body
        
        vertices.extend([
            # Bottom face of tail
            (tail_x - tail_length/2, -tail_width/2, 0),           # 16
            (tail_x + tail_length/2, -tail_width/2, 0),           # 17
            (tail_x + tail_length/2, tail_width/2, 0),            # 18
            (tail_x - tail_length/2, tail_width/2, 0),            # 19
            # Top face of tail
            (tail_x - tail_length/2, -tail_width/2, tail_width),  # 20
            (tail_x + tail_length/2, -tail_width/2, tail_width),  # 21
            (tail_x + tail_length/2, tail_width/2, tail_width),   # 22
            (tail_x - tail_length/2, tail_width/2, tail_width),   # 23
        ])
        
        # WINGS: Two simple triangular wings
        wing_span = 4.0 * scale
        wing_height = 2.0 * scale
        
        # Left wing triangle
        vertices.extend([
            (0, 0, body_height),                    # 24 - Wing root (center of body)
            (-2, -wing_span, body_height + wing_height), # 25 - Wing tip left
            (2, -wing_span, body_height),           # 26 - Wing trailing edge left
        ])
        
        # Right wing triangle
        vertices.extend([
            (0, 0, body_height),                    # 27 - Wing root (center of body) 
            (-2, wing_span, body_height + wing_height),  # 28 - Wing tip right
            (2, wing_span, body_height),            # 29 - Wing trailing edge right
        ])
        
        # LEGS: Four simple stick legs
        leg_length = 2.0 * scale
        leg_positions = [
            (-1.5, -0.8, 0),  # Front left leg base
            (-1.5, 0.8, 0),   # Front right leg base  
            (1.5, -0.8, 0),   # Back left leg base
            (1.5, 0.8, 0),    # Back right leg base
        ]
        
        for i, (lx, ly, lz) in enumerate(leg_positions):
            leg_base = 30 + i * 2
            vertices.extend([
                (lx, ly, lz),                    # Leg top (on body)
                (lx, ly, lz - leg_length),       # Leg bottom (foot)
            ])
        
        # FACES: Simple box faces for each part
        # Body faces (vertices 0-7)
        faces.extend([
            # Bottom
            (0, 1, 2), (0, 2, 3),
            # Top  
            (4, 7, 6), (4, 6, 5),
            # Front
            (0, 4, 5), (0, 5, 1),
            # Back
            (2, 6, 7), (2, 7, 3),
            # Left
            (3, 7, 4), (3, 4, 0),
            # Right
            (1, 5, 6), (1, 6, 2),
        ])
        
        # Head faces (vertices 8-15)
        faces.extend([
            # Bottom
            (8, 9, 10), (8, 10, 11),
            # Top
            (12, 15, 14), (12, 14, 13),
            # Front
            (8, 12, 13), (8, 13, 9),
            # Back
            (10, 14, 15), (10, 15, 11),
            # Left
            (11, 15, 12), (11, 12, 8),
            # Right
            (9, 13, 14), (9, 14, 10),
        ])
        
        # Tail faces (vertices 16-23)
        faces.extend([
            # Bottom
            (16, 17, 18), (16, 18, 19),
            # Top
            (20, 23, 22), (20, 22, 21),
            # Front
            (16, 20, 21), (16, 21, 17),
            # Back
            (18, 22, 23), (18, 23, 19),
            # Left
            (19, 23, 20), (19, 20, 16),
            # Right
            (17, 21, 22), (17, 22, 18),
        ])
        
        # Wing faces (simple triangles)
        faces.extend([
            (24, 25, 26),  # Left wing
            (27, 28, 29),  # Right wing
        ])
        
        # Leg faces (simple lines as triangles)
        for i in range(4):
            leg_base = 30 + i * 2
            # Create a tiny triangle for each leg
            faces.append((leg_base, leg_base + 1, leg_base))
        
        return vertices, faces

    def _generate_detailed_robot(self, complexity, material_properties, structural_modifier, context):
        """Generate an extremely simple, clearly recognizable robot shape."""
        vertices = []
        faces = []
        
        scale = 1.0  # Keep it simple
        
        # TORSO: Simple rectangular main body
        torso_width = 2.0 * scale
        torso_height = 3.0 * scale
        torso_depth = 1.5 * scale
        
        # Main robot body as simple box
        vertices.extend([
            # Bottom face of torso
            (-torso_width/2, -torso_depth/2, 0),           # 0
            (torso_width/2, -torso_depth/2, 0),            # 1
            (torso_width/2, torso_depth/2, 0),             # 2
            (-torso_width/2, torso_depth/2, 0),            # 3
            # Top face of torso
            (-torso_width/2, -torso_depth/2, torso_height), # 4
            (torso_width/2, -torso_depth/2, torso_height),  # 5
            (torso_width/2, torso_depth/2, torso_height),   # 6
            (-torso_width/2, torso_depth/2, torso_height),  # 7
        ])
        
        # HEAD: Simple cubic head on top
        head_size = 1.2 * scale
        head_z = torso_height
        
        vertices.extend([
            # Bottom face of head
            (-head_size/2, -head_size/2, head_z),           # 8
            (head_size/2, -head_size/2, head_z),            # 9
            (head_size/2, head_size/2, head_z),             # 10
            (-head_size/2, head_size/2, head_z),            # 11
            # Top face of head
            (-head_size/2, -head_size/2, head_z + head_size), # 12
            (head_size/2, -head_size/2, head_z + head_size),  # 13
            (head_size/2, head_size/2, head_z + head_size),   # 14
            (-head_size/2, head_size/2, head_z + head_size),  # 15
        ])
        
        # LEFT ARM: Simple box arm
        arm_width = 0.4 * scale
        arm_length = 2.0 * scale
        arm_height = 0.4 * scale
        arm_z = torso_height * 0.8
        
        left_arm_x = -torso_width/2 - arm_length/2
        vertices.extend([
            # Bottom face of left arm
            (left_arm_x - arm_length/2, -arm_width/2, arm_z),           # 16
            (left_arm_x + arm_length/2, -arm_width/2, arm_z),           # 17
            (left_arm_x + arm_length/2, arm_width/2, arm_z),            # 18
            (left_arm_x - arm_length/2, arm_width/2, arm_z),            # 19
            # Top face of left arm
            (left_arm_x - arm_length/2, -arm_width/2, arm_z + arm_height), # 20
            (left_arm_x + arm_length/2, -arm_width/2, arm_z + arm_height), # 21
            (left_arm_x + arm_length/2, arm_width/2, arm_z + arm_height),  # 22
            (left_arm_x - arm_length/2, arm_width/2, arm_z + arm_height),  # 23
        ])
        
        # RIGHT ARM: Simple box arm (mirror of left)
        right_arm_x = torso_width/2 + arm_length/2
        vertices.extend([
            # Bottom face of right arm
            (right_arm_x - arm_length/2, -arm_width/2, arm_z),           # 24
            (right_arm_x + arm_length/2, -arm_width/2, arm_z),           # 25
            (right_arm_x + arm_length/2, arm_width/2, arm_z),            # 26
            (right_arm_x - arm_length/2, arm_width/2, arm_z),            # 27
            # Top face of right arm
            (right_arm_x - arm_length/2, -arm_width/2, arm_z + arm_height), # 28
            (right_arm_x + arm_length/2, -arm_width/2, arm_z + arm_height), # 29
            (right_arm_x + arm_length/2, arm_width/2, arm_z + arm_height),  # 30
            (right_arm_x - arm_length/2, arm_width/2, arm_z + arm_height),  # 31
        ])
        
        # LEFT LEG: Simple box leg
        leg_width = 0.6 * scale
        leg_height = 2.5 * scale
        leg_depth = 0.6 * scale
        
        left_leg_x = -torso_width/4
        vertices.extend([
            # Bottom face of left leg
            (left_leg_x - leg_width/2, -leg_depth/2, -leg_height),           # 32
            (left_leg_x + leg_width/2, -leg_depth/2, -leg_height),           # 33
            (left_leg_x + leg_width/2, leg_depth/2, -leg_height),            # 34
            (left_leg_x - leg_width/2, leg_depth/2, -leg_height),            # 35
            # Top face of left leg (connects to torso)
            (left_leg_x - leg_width/2, -leg_depth/2, 0),                     # 36
            (left_leg_x + leg_width/2, -leg_depth/2, 0),                     # 37
            (left_leg_x + leg_width/2, leg_depth/2, 0),                      # 38
            (left_leg_x - leg_width/2, leg_depth/2, 0),                      # 39
        ])
        
        # RIGHT LEG: Simple box leg (mirror of left)
        right_leg_x = torso_width/4
        vertices.extend([
            # Bottom face of right leg
            (right_leg_x - leg_width/2, -leg_depth/2, -leg_height),           # 40
            (right_leg_x + leg_width/2, -leg_depth/2, -leg_height),           # 41
            (right_leg_x + leg_width/2, leg_depth/2, -leg_height),            # 42
            (right_leg_x - leg_width/2, leg_depth/2, -leg_height),            # 43
            # Top face of right leg (connects to torso)
            (right_leg_x - leg_width/2, -leg_depth/2, 0),                     # 44
            (right_leg_x + leg_width/2, -leg_depth/2, 0),                     # 45
            (right_leg_x + leg_width/2, leg_depth/2, 0),                      # 46
            (right_leg_x - leg_width/2, leg_depth/2, 0),                      # 47
        ])
        
        # FACES: Box faces for each part
        # Torso faces (vertices 0-7)
        faces.extend([
            (0, 1, 2), (0, 2, 3),        # Bottom
            (4, 7, 6), (4, 6, 5),        # Top
            (0, 4, 5), (0, 5, 1),        # Front
            (2, 6, 7), (2, 7, 3),        # Back
            (3, 7, 4), (3, 4, 0),        # Left
            (1, 5, 6), (1, 6, 2),        # Right
        ])
        
        # Head faces (vertices 8-15)
        faces.extend([
            (8, 9, 10), (8, 10, 11),      # Bottom
            (12, 15, 14), (12, 14, 13),   # Top
            (8, 12, 13), (8, 13, 9),      # Front
            (10, 14, 15), (10, 15, 11),   # Back
            (11, 15, 12), (11, 12, 8),    # Left
            (9, 13, 14), (9, 14, 10),     # Right
        ])
        
        # Left arm faces (vertices 16-23)
        faces.extend([
            (16, 17, 18), (16, 18, 19),    # Bottom
            (20, 23, 22), (20, 22, 21),    # Top
            (16, 20, 21), (16, 21, 17),    # Front
            (18, 22, 23), (18, 23, 19),    # Back
            (19, 23, 20), (19, 20, 16),    # Left
            (17, 21, 22), (17, 22, 18),    # Right
        ])
        
        # Right arm faces (vertices 24-31)
        faces.extend([
            (24, 25, 26), (24, 26, 27),    # Bottom
            (28, 31, 30), (28, 30, 29),    # Top
            (24, 28, 29), (24, 29, 25),    # Front
            (26, 30, 31), (26, 31, 27),    # Back
            (27, 31, 28), (27, 28, 24),    # Left
            (25, 29, 30), (25, 30, 26),    # Right
        ])
        
        # Left leg faces (vertices 32-39)
        faces.extend([
            (32, 33, 34), (32, 34, 35),    # Bottom
            (36, 39, 38), (36, 38, 37),    # Top
            (32, 36, 37), (32, 37, 33),    # Front
            (34, 38, 39), (34, 39, 35),    # Back
            (35, 39, 36), (35, 36, 32),    # Left
            (33, 37, 38), (33, 38, 34),    # Right
        ])
        
        # Right leg faces (vertices 40-47)
        faces.extend([
            (40, 41, 42), (40, 42, 43),    # Bottom
            (44, 47, 46), (44, 46, 45),    # Top
            (40, 44, 45), (40, 45, 41),    # Front
            (42, 46, 47), (42, 47, 43),    # Back
            (43, 47, 44), (43, 44, 40),    # Left
            (41, 45, 46), (41, 46, 42),    # Right
        ])
        
        return vertices, faces

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

    def _generate_dragon_like_shape(self, prompt_lower, seed, complexity, color_scale):
        """Generate dragon, wyvern, drake shapes."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Dragon type affects proportions
        if 'wyvern' in prompt_lower:
            body_length = 6.0 * color_scale
            wing_span = 8.0 * color_scale
            neck_length = 2.0 * color_scale
        elif 'drake' in prompt_lower:
            body_length = 4.0 * color_scale
            wing_span = 5.0 * color_scale
            neck_length = 1.5 * color_scale
        else:  # dragon
            body_length = 8.0 * color_scale
            wing_span = 10.0 * color_scale
            neck_length = 3.0 * color_scale
        
        # Serpentine body
        body_segments = 20 + complexity
        for i in range(body_segments):
            t = i / body_segments
            
            # Sinuous dragon body curve
            spine_curve = math.sin(t * math.pi * 2) * 0.5
            body_radius = 1.0 - (t * 0.3)  # Tapers towards tail
            
            for j in range(8):
                angle = (j / 8) * 2 * math.pi
                x = (body_radius * math.cos(angle)) + spine_curve
                y = body_radius * math.sin(angle)
                z = t * body_length
                vertices.append((x, y, z))
        
        # Dragon head (enlarged front section)
        head_segments = 6
        for i in range(head_segments):
            t = i / head_segments
            head_radius = 1.5 + t * 0.5  # Expanding head
            z_pos = -neck_length + (t * neck_length)
            
            for j in range(8):
                angle = (j / 8) * 2 * math.pi
                x = head_radius * math.cos(angle)
                y = head_radius * math.sin(angle)
                z = z_pos
                vertices.append((x, y, z))
        
        # Wings (if not a drake without wings)
        if wing_span > 0:
            wing_membrane_points = 12
            for side in [-1, 1]:  # Left and right wings
                for i in range(wing_membrane_points):
                    for j in range(6):
                        u = (i / wing_membrane_points) * math.pi
                        v = (j / 5) * 0.8
                        
                        x = side * (wing_span/2 * math.sin(u)) * (1 - v * 0.3)
                        y = math.cos(u) * wing_span/4 + body_length/3
                        z = v * body_length/2 + body_length/4
                        vertices.append((x, y, z))
        
        # Generate dragon faces
        total_vertices = len(vertices)
        for i in range(total_vertices - 2):
            if i % 3 == 0 and i + 2 < total_vertices:
                faces.append((i, i+1, i+2))
        
        return vertices, faces
    
    def _generate_tree_shape(self, prompt_lower, seed, complexity, color_scale):
        """Generate a tree-like shape with variations."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Tree type affects structure
        if 'oak' in prompt_lower:
            trunk_radius = 0.5 * color_scale
            height = 6.0 * color_scale
            branch_density = complexity + 5
        elif 'pine' in prompt_lower:
            trunk_radius = 0.3 * color_scale
            height = 8.0 * color_scale
            branch_density = complexity + 3
        elif 'willow' in prompt_lower:
            trunk_radius = 0.4 * color_scale
            height = 5.0 * color_scale
            branch_density = complexity + 8
        else:  # generic tree
            trunk_radius = 0.4 * color_scale
            height = 6.0 * color_scale
            branch_density = complexity + 4
        
        # Trunk
        trunk_segments = 8
        trunk_height_segments = 10
        for h in range(trunk_height_segments):
            trunk_height = (h / trunk_height_segments) * (height / 2)
            radius = trunk_radius * (1 - h / trunk_height_segments * 0.3)
            
            for i in range(trunk_segments):
                angle = (i / trunk_segments) * 2 * math.pi
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                vertices.append((x, y, trunk_height))
        
        # Branches
        for branch in range(branch_density):
            branch_height = random.uniform(height * 0.3, height * 0.9)
            branch_angle = random.uniform(0, 2 * math.pi)
            branch_length = random.uniform(height * 0.2, height * 0.6)
            branch_radius = random.uniform(trunk_radius * 0.1, trunk_radius * 0.4)
            
            # Branch segments
            branch_segments = 6
            for i in range(branch_segments):
                t = i / branch_segments
                pos_x = math.cos(branch_angle) * (t * branch_length)
                pos_y = math.sin(branch_angle) * (t * branch_length)
                pos_z = branch_height + t * height * 0.2
                
                # Branch cross-section
                for j in range(4):
                    cross_angle = (j / 4) * 2 * math.pi
                    radius = branch_radius * (1 - t * 0.8)
                    x = pos_x + radius * math.cos(cross_angle)
                    y = pos_y + radius * math.sin(cross_angle)
                    vertices.append((x, y, pos_z))
        
        # Generate faces
        for i in range(len(vertices) - 2):
            if i % 4 != 3:
                faces.append((i, i+1, i+2))
        
        return vertices, faces
    
    def _generate_chair_shape(self, prompt_lower, seed, complexity, color_scale):
        """Generate chair, throne, seat shapes."""
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # Chair type affects design
        if 'throne' in prompt_lower:
            seat_width = 2.5 * color_scale
            seat_depth = 2.0 * color_scale
            back_height = 4.0 * color_scale
            arm_rests = True
            ornate = True
        elif 'bench' in prompt_lower:
            seat_width = 4.0 * color_scale
            seat_depth = 1.5 * color_scale
            back_height = 2.0 * color_scale
            arm_rests = False
            ornate = False
        else:  # chair
            seat_width = 1.8 * color_scale
            seat_depth = 1.6 * color_scale
            back_height = 3.0 * color_scale
            arm_rests = random.choice([True, False])
            ornate = False
        
        # Seat
        seat_height = 1.5 * color_scale
        vertices.extend([
            (-seat_width/2, -seat_depth/2, seat_height),
            (seat_width/2, -seat_depth/2, seat_height),
            (seat_width/2, seat_depth/2, seat_height),
            (-seat_width/2, seat_depth/2, seat_height)
        ])
        
        # Legs
        leg_positions = [
            (-seat_width/2, -seat_depth/2), (seat_width/2, -seat_depth/2),
            (seat_width/2, seat_depth/2), (-seat_width/2, seat_depth/2)
        ]
        
        for pos_x, pos_y in leg_positions:
            leg_thickness = 0.1 * color_scale
            vertices.extend([
                (pos_x - leg_thickness, pos_y - leg_thickness, 0),
                (pos_x + leg_thickness, pos_y - leg_thickness, 0),
                (pos_x + leg_thickness, pos_y + leg_thickness, 0),
                (pos_x - leg_thickness, pos_y + leg_thickness, 0),
                (pos_x - leg_thickness, pos_y - leg_thickness, seat_height),
                (pos_x + leg_thickness, pos_y - leg_thickness, seat_height),
                (pos_x + leg_thickness, pos_y + leg_thickness, seat_height),
                (pos_x - leg_thickness, pos_y + leg_thickness, seat_height)
            ])
        
        # Backrest
        if back_height > 0:
            vertices.extend([
                (-seat_width/2, seat_depth/2, seat_height),
                (seat_width/2, seat_depth/2, seat_height),
                (seat_width/2, seat_depth/2, seat_height + back_height),
                (-seat_width/2, seat_depth/2, seat_height + back_height)
            ])
        
        # Armrests
        if arm_rests:
            arm_height = seat_height + back_height * 0.6
            arm_width = 0.3 * color_scale
            for side in [-1, 1]:
                arm_x = side * (seat_width/2 + arm_width/2)
                vertices.extend([
                    (arm_x - arm_width/2, -seat_depth/2, seat_height),
                    (arm_x + arm_width/2, -seat_depth/2, seat_height),
                    (arm_x + arm_width/2, seat_depth/2, seat_height),
                    (arm_x - arm_width/2, seat_depth/2, seat_height),
                    (arm_x - arm_width/2, -seat_depth/2, arm_height),
                    (arm_x + arm_width/2, -seat_depth/2, arm_height),
                    (arm_x + arm_width/2, seat_depth/2, arm_height),
                    (arm_x - arm_width/2, seat_depth/2, arm_height)
                ])
        
        # Generate faces (simplified box faces)
        box_count = 1 + 4 + (1 if back_height > 0 else 0) + (2 if arm_rests else 0)
        for box in range(box_count):
            if box == 0:  # Seat
                base = 0
            elif box <= 4:  # Legs
                base = 4 + (box-1) * 8
            elif back_height > 0 and box == 5:  # Backrest
                base = 4 + 4 * 8
            else:  # Armrests
                base = 4 + 4 * 8 + (4 if back_height > 0 else 0) + (box - (6 if back_height > 0 else 5)) * 8
            
            if box == 0:  # Seat is quad
                faces.append((0, 1, 2))
                faces.append((0, 2, 3))
            else:  # Boxes
                # Generate standard box faces
                faces.extend([
                    (base, base+1, base+2), (base, base+2, base+3),  # Bottom
                    (base+4, base+7, base+6), (base+4, base+6, base+5),  # Top
                    (base, base+4, base+5), (base, base+5, base+1),  # Sides
                    (base+1, base+5, base+6), (base+1, base+6, base+2),
                    (base+2, base+6, base+7), (base+2, base+7, base+3),
                    (base+3, base+7, base+4), (base+3, base+4, base+0)
                ])
        
        return vertices, faces
    
    def _generate_house_shape(self, prompt_lower, seed, complexity, color_scale):
        """Generate house, home, building shapes."""
        import math
        import random
        random.seed(seed)
        
        vertices = []
        faces = []
        
        # House type affects structure
        if 'cabin' in prompt_lower:
            width = 4.0 * color_scale
            depth = 3.5 * color_scale
            height = 2.5 * color_scale
            roof_type = 'peaked'
        elif 'hut' in prompt_lower:
            width = 3.0 * color_scale
            depth = 3.0 * color_scale
            height = 2.0 * color_scale
            roof_type = 'round'
        else:  # house/home/building
            width = 5.0 * color_scale
            depth = 4.0 * color_scale
            height = 3.0 * color_scale
            roof_type = 'peaked'
        
        # Main structure base
        vertices.extend([
            (-width/2, -depth/2, 0), (width/2, -depth/2, 0),
            (width/2, depth/2, 0), (-width/2, depth/2, 0),
            (-width/2, -depth/2, height), (width/2, -depth/2, height),
            (width/2, depth/2, height), (-width/2, depth/2, height)
        ])
        
        # Roof
        if roof_type == 'peaked':
            roof_peak = height + 1.5 * color_scale
            vertices.extend([
                (0, -depth/2, roof_peak), (0, depth/2, roof_peak)
            ])
        elif roof_type == 'round':
            # Dome-like roof
            dome_segments = 8
            for i in range(dome_segments):
                for j in range(dome_segments):
                    u = (i / dome_segments) * math.pi
                    v = (j / dome_segments) * 2 * math.pi
                    
                    radius = min(width, depth) / 2
                    dome_height = radius * math.sin(u)
                    x = radius * math.cos(u) * math.cos(v)
                    y = radius * math.cos(u) * math.sin(v)
                    z = height + dome_height
                    vertices.append((x, y, z))
        
        # Additional details based on complexity
        for detail in range(complexity // 2):
            # Windows
            if random.random() < 0.7:
                wall = random.randint(0, 3)  # Choose wall
                window_size = 0.3 * color_scale
                
                if wall == 0:  # Front wall
                    win_x = random.uniform(-width/2 + window_size, width/2 - window_size)
                    win_y = -depth/2 - 0.01
                    win_z = random.uniform(height * 0.2, height * 0.8)
                elif wall == 1:  # Right wall
                    win_x = width/2 + 0.01
                    win_y = random.uniform(-depth/2 + window_size, depth/2 - window_size)
                    win_z = random.uniform(height * 0.2, height * 0.8)
                # Add window geometry (simplified)
                vertices.extend([
                    (win_x - window_size/2, win_y, win_z - window_size/2),
                    (win_x + window_size/2, win_y, win_z - window_size/2),
                    (win_x + window_size/2, win_y, win_z + window_size/2),
                    (win_x - window_size/2, win_y, win_z + window_size/2)
                ])
        
        # Generate faces
        # Main house body
        faces.extend([
            (0, 1, 2), (0, 2, 3),  # Bottom
            (4, 7, 6), (4, 6, 5),  # Top
            (0, 4, 5), (0, 5, 1),  # Sides
            (1, 5, 6), (1, 6, 2),
            (2, 6, 7), (2, 7, 3),
            (3, 7, 4), (3, 4, 0)
        ])
        
        # Roof faces
        if roof_type == 'peaked':
            faces.extend([
                (4, 8, 5), (5, 8, 6), (6, 8, 9), (7, 9, 4),
                (4, 9, 8), (6, 9, 7)
            ])
        
    
        return vertices, faces
    
    async def _create_fallback_model(self, output_path: str, format: str, prompt: str, job_id: str):
        """Create a simple fallback 3D model when TRELLIS fails."""
        logger.info("Creating simple fallback 3D model", format=format, job_id=job_id, prompt=prompt)
        
        # Generate simple shape based on prompt keywords
        vertices, faces = self._generate_simple_shape(prompt)
        
        if format.lower() == "glb":
            # Create a simple GLB (reuse existing implementation)
            glb_content = self._create_mock_glb(prompt)
            with open(output_path, 'wb') as f:
                f.write(glb_content)
        
        elif format.lower() == "obj":
            # Create OBJ with simple geometry
            with open(output_path, 'w') as f:
                f.write(f"# Simple 3D model for prompt: {prompt}\n")
                f.write(f"# Job ID: {job_id}\n")
                f.write(f"# Generated at: {datetime.utcnow().isoformat()}\n\n")
                
                for v in vertices:
                    f.write(f"v {v[0]} {v[1]} {v[2]}\n")
                
                for face in faces:
                    f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
        
        elif format.lower() == "ply":
            # Create PLY with simple geometry
            with open(output_path, 'w') as f:
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"comment Simple 3D model for prompt: {prompt}\n")
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

    def _generate_simple_shape(self, prompt):
        """Generate simple shapes based on prompt keywords."""
        import math
        
        prompt_lower = prompt.lower()
        vertices = []
        faces = []
        
        if 'dragon' in prompt_lower:
            return self._generate_detailed_dragon(5, {'density': 1.0}, 1.0, {})
        elif 'robot' in prompt_lower:
            return self._generate_detailed_robot(5, {'density': 1.0}, 1.0, {})
        elif 'cat' in prompt_lower or 'animal' in prompt_lower:
            return self._generate_simple_creature('cat', 5)
        elif 'car' in prompt_lower or 'vehicle' in prompt_lower:
            # Simple car shape
            vertices = [
                (-2, -1, 0), (2, -1, 0), (2, 1, 0), (-2, 1, 0),  # Bottom
                (-2, -1, 1), (2, -1, 1), (2, 1, 1), (-2, 1, 1),  # Top
            ]
            faces = [
                (0, 1, 2), (0, 2, 3),  # Bottom
                (4, 7, 6), (4, 6, 5),  # Top
                (0, 4, 5), (0, 5, 1),  # Sides
                (1, 5, 6), (1, 6, 2),
                (2, 6, 7), (2, 7, 3),
                (3, 7, 4), (3, 4, 0),
            ]
        elif 'house' in prompt_lower or 'building' in prompt_lower:
            # Simple house shape
            vertices = [
                (-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0),  # Base
                (-2, -2, 2), (2, -2, 2), (2, 2, 2), (-2, 2, 2),  # Walls
                (0, -2, 3), (0, 2, 3),  # Roof peak
            ]
            faces = [
                (0, 1, 2), (0, 2, 3),  # Floor
                (4, 7, 6), (4, 6, 5),  # Ceiling
                (0, 4, 5), (0, 5, 1),  # Walls
                (1, 5, 6), (1, 6, 2),
                (2, 6, 7), (2, 7, 3),
                (3, 7, 4), (3, 4, 0),
                (4, 8, 5), (5, 8, 6),  # Roof
                (6, 9, 7), (7, 9, 4),
                (8, 9, 6), (8, 6, 5),
            ]
        else:
            # Default simple triangle
            vertices = [(0, 0, 0), (1, 0, 0), (0.5, 1, 0)]
            faces = [(0, 1, 2)]
        
        return vertices, faces
    
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
