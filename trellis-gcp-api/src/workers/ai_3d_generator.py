#!/usr/bin/env python3
"""
AI-Powered 3D Model Generator
Uses Hugging Face Transformers and procedural generation for text-to-3D
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile
import numpy as np
import math
import hashlib
import structlog
from minio import Minio
from minio.error import S3Error

logger = structlog.get_logger(__name__)

class AI3DGenerator:
    """AI-powered 3D model generator using text analysis and procedural generation."""
    
    def __init__(self, minio_endpoint="minio:9000", access_key="minioadmin", secret_key="minioadmin"):
        self.minio_client = Minio(
            minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False
        )
        self._model = None
        self._tokenizer = None
        
    def _get_ai_model(self):
        """Load AI model for text analysis and embedding generation."""
        if self._model is None or self._tokenizer is None:
            try:
                from transformers import AutoTokenizer, AutoModel
                import torch
                
                # Use a lightweight sentence transformer model
                model_name = "sentence-transformers/all-MiniLM-L6-v2"
                logger.info("Loading AI text embedding model", model=model_name)
                
                self._tokenizer = AutoTokenizer.from_pretrained(model_name)
                self._model = AutoModel.from_pretrained(model_name)
                
                logger.info("AI model loaded successfully")
                return True
                
            except Exception as e:
                logger.warning("Failed to load AI model, using text analysis fallback", error=str(e))
                return False
        return True
    
    def _analyze_text_with_ai(self, prompt: str):
        """Analyze text using AI model to extract semantic features."""
        if not self._get_ai_model():
            return self._analyze_text_fallback(prompt)
        
        try:
            import torch
            
            # Tokenize and get embeddings
            inputs = self._tokenizer(prompt, return_tensors='pt', padding=True, truncation=True, max_length=128)
            
            with torch.no_grad():
                outputs = self._model(**inputs)
                embeddings = outputs.last_hidden_state.mean(dim=1).squeeze().numpy()
            
            # Convert embeddings to geometric parameters
            embedding_norm = np.linalg.norm(embeddings)
            
            # Use embedding features to influence generation
            complexity = min(int(embedding_norm * 2), 20)
            scale = 1.0 + (embeddings[0] % 1.0) * 2.0  # Use first embedding component
            roughness = abs(embeddings[1] % 1.0)  # Use second component
            
            # Extract semantic categories from embedding space
            semantic_features = {
                'complexity': complexity,
                'scale': scale,
                'roughness': roughness,
                'semantic_vector': embeddings[:10].tolist()  # First 10 dimensions
            }
            
            logger.info("AI text analysis completed", prompt=prompt, features=semantic_features)
            return semantic_features
            
        except Exception as e:
            logger.warning("AI text analysis failed, using fallback", error=str(e))
            return self._analyze_text_fallback(prompt)
    
    def _analyze_text_fallback(self, prompt: str):
        """Fallback text analysis using keyword detection."""
        prompt_lower = prompt.lower()
        
        # Keyword-based analysis
        complexity = len(prompt.split()) + 5
        scale = 1.0
        roughness = 0.5
        
        # Detect categories
        if any(word in prompt_lower for word in ['detailed', 'complex', 'intricate']):
            complexity += 5
        if any(word in prompt_lower for word in ['large', 'big', 'huge', 'massive']):
            scale *= 2.0
        if any(word in prompt_lower for word in ['rough', 'textured', 'bumpy']):
            roughness = 0.8
        if any(word in prompt_lower for word in ['smooth', 'polished', 'sleek']):
            roughness = 0.2
        
        return {
            'complexity': complexity,
            'scale': scale,
            'roughness': roughness,
            'semantic_vector': [hash(word) % 100 / 100.0 for word in prompt.split()[:10]]
        }
    
    def _generate_ai_driven_geometry(self, prompt: str, format: str):
        """Generate 3D geometry using AI-analyzed features."""
        
        # Get AI-powered semantic analysis
        features = self._analyze_text_with_ai(prompt)
        
        complexity = features['complexity']
        scale = features['scale']
        roughness = features['roughness']
        semantic_vector = features['semantic_vector']
        
        logger.info("Generating AI-driven 3D geometry", 
                   complexity=complexity, scale=scale, roughness=roughness)
        
        # Determine object type from semantic analysis and keywords
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ['dragon', 'creature', 'beast', 'animal']):
            return self._generate_creature_with_ai(semantic_vector, complexity, scale)
        elif any(word in prompt_lower for word in ['robot', 'mech', 'android', 'machine']):
            return self._generate_robot_with_ai(semantic_vector, complexity, scale)
        elif any(word in prompt_lower for word in ['building', 'house', 'castle', 'tower']):
            return self._generate_architecture_with_ai(semantic_vector, complexity, scale)
        elif any(word in prompt_lower for word in ['vehicle', 'car', 'ship', 'plane']):
            return self._generate_vehicle_with_ai(semantic_vector, complexity, scale)
        else:
            return self._generate_abstract_with_ai(semantic_vector, complexity, scale, roughness)
    
    def _generate_creature_with_ai(self, semantic_vector, complexity, scale):
        """Generate recognizable dragon creature using AI semantic features."""
        vertices = []
        faces = []
        
        # DRAGON BODY - elongated, serpentine
        body_segments = 12
        body_length = 8.0 * scale
        body_height = 2.0 * scale
        
        for i in range(body_segments):
            t = i / (body_segments - 1)
            
            # Dragon body curve (S-shaped)
            x = (t - 0.5) * body_length
            y = math.sin(t * math.pi * 2) * scale * 0.5  # Serpentine curve
            z = math.sin(t * math.pi) * body_height + body_height * 0.5  # Arched body
            
            # Body thickness (tapers toward tail)
            thickness = (1.0 - t * 0.7) * scale
            
            # Cross-section points for dragon body
            for j in range(6):
                angle = (j / 6) * 2 * math.pi
                r = thickness * (1.0 + 0.2 * math.cos(angle * 2))  # Slightly oval
                
                bx = x + r * math.cos(angle) * 0.8
                by = y + r * math.sin(angle)
                bz = z
                
                vertices.append((bx, by, bz))
        
        # DRAGON HEAD - larger front section
        head_x = -body_length/2 - 2.0 * scale
        head_size = 1.5 * scale
        
        # Head vertices (triangular snout)
        vertices.extend([
            # Head base
            (head_x - head_size, -head_size, body_height),      # Bottom left
            (head_x - head_size, head_size, body_height),       # Bottom right  
            (head_x - head_size, 0, body_height + head_size),   # Top center
            # Snout tip
            (head_x - head_size*2, 0, body_height + head_size*0.5),  # Nose
        ])
        
        # DRAGON WINGS - large triangular wings
        wing_base_idx = len(vertices)
        wing_span = body_length * 0.8
        wing_height = body_height * 1.5
        
        # Wing attachment point (mid-body)
        wing_attach_x = 0
        wing_attach_z = body_height * 1.2
        
        # Left wing
        vertices.extend([
            (wing_attach_x, 0, wing_attach_z),                    # Wing root
            (wing_attach_x - 2*scale, -wing_span, wing_attach_z + wing_height),  # Wing tip
            (wing_attach_x + 3*scale, -wing_span*0.7, wing_attach_z),  # Wing trailing edge
        ])
        
        # Right wing (mirror)
        vertices.extend([
            (wing_attach_x, 0, wing_attach_z),                    # Wing root
            (wing_attach_x - 2*scale, wing_span, wing_attach_z + wing_height),   # Wing tip
            (wing_attach_x + 3*scale, wing_span*0.7, wing_attach_z),   # Wing trailing edge
        ])
        
        # DRAGON LEGS - four legs
        leg_positions = [
            (-body_length*0.2, -scale*0.8),  # Front left
            (-body_length*0.2, scale*0.8),   # Front right
            (body_length*0.2, -scale*0.8),   # Back left  
            (body_length*0.2, scale*0.8),    # Back right
        ]
        
        for lx, ly in leg_positions:
            # Leg from body to ground
            vertices.extend([
                (lx, ly, body_height*0.5),    # Leg top (attached to body)
                (lx, ly, -body_height*0.5),   # Leg bottom (foot)
                (lx + scale*0.3, ly, -body_height*0.5),  # Foot spread
            ])
        
        # DRAGON TAIL - extending from back
        tail_segments = 6
        tail_start_x = body_length/2
        
        for i in range(tail_segments):
            t = i / (tail_segments - 1)
            tail_x = tail_start_x + t * body_length * 0.5
            tail_y = math.sin(t * math.pi * 3) * scale * 0.3  # Wavy tail
            tail_z = body_height * (1.0 - t * 0.5)
            tail_thickness = scale * (0.8 - t * 0.6)
            
            for j in range(4):  # Simpler tail cross-section
                angle = (j / 4) * 2 * math.pi
                tx = tail_x + tail_thickness * math.cos(angle) * 0.3
                ty = tail_y + tail_thickness * math.sin(angle)
                tz = tail_z
                vertices.append((tx, ty, tz))
        
        # GENERATE FACES
        # Body segments
        for i in range(body_segments - 1):
            for j in range(6):
                v1 = i * 6 + j
                v2 = i * 6 + (j + 1) % 6
                v3 = (i + 1) * 6 + j
                v4 = (i + 1) * 6 + (j + 1) % 6
                
                if v4 < body_segments * 6:  # Stay within body vertices
                    faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        # Head faces (simple triangular head)
        head_base_idx = body_segments * 6
        faces.extend([
            (head_base_idx, head_base_idx + 1, head_base_idx + 2),  # Head triangle
            (head_base_idx, head_base_idx + 2, head_base_idx + 3),  # Snout
            (head_base_idx + 1, head_base_idx + 3, head_base_idx + 2),  # Side
        ])
        
        # Wing faces  
        left_wing_idx = head_base_idx + 4
        right_wing_idx = left_wing_idx + 3
        
        faces.extend([
            (left_wing_idx, left_wing_idx + 1, left_wing_idx + 2),    # Left wing
            (right_wing_idx, right_wing_idx + 1, right_wing_idx + 2), # Right wing
        ])
        
        # Leg faces (simple triangles)
        leg_start_idx = right_wing_idx + 3
        for i in range(4):
            leg_base = leg_start_idx + i * 3
            faces.append((leg_base, leg_base + 1, leg_base + 2))
        
        # Tail faces
        tail_start_idx = leg_start_idx + 12  # After 4 legs * 3 vertices each
        for i in range(tail_segments - 1):
            for j in range(4):
                v1 = tail_start_idx + i * 4 + j
                v2 = tail_start_idx + i * 4 + (j + 1) % 4
                v3 = tail_start_idx + (i + 1) * 4 + j
                v4 = tail_start_idx + (i + 1) * 4 + (j + 1) % 4
                
                total_vertices = len(vertices)
                if v4 < total_vertices:
                    faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        logger.info("Generated recognizable AI dragon", vertices=len(vertices), faces=len(faces))
        return vertices, faces
    
    def _generate_robot_with_ai(self, semantic_vector, complexity, scale):
        """Generate recognizable robot using AI semantic features."""
        vertices = []
        faces = []
        
        # ROBOT TORSO - main body
        torso_width = 2.0 * scale
        torso_height = 3.0 * scale
        torso_depth = 1.5 * scale
        
        torso_vertices = [
            # Bottom face
            (-torso_width/2, -torso_depth/2, 0),
            (torso_width/2, -torso_depth/2, 0),
            (torso_width/2, torso_depth/2, 0),
            (-torso_width/2, torso_depth/2, 0),
            # Top face
            (-torso_width/2, -torso_depth/2, torso_height),
            (torso_width/2, -torso_depth/2, torso_height),
            (torso_width/2, torso_depth/2, torso_height),
            (-torso_width/2, torso_depth/2, torso_height),
        ]
        vertices.extend(torso_vertices)
        
        # ROBOT HEAD - cube on top
        head_size = 1.2 * scale
        head_z = torso_height
        
        head_vertices = [
            (-head_size/2, -head_size/2, head_z),
            (head_size/2, -head_size/2, head_z),
            (head_size/2, head_size/2, head_z),
            (-head_size/2, head_size/2, head_z),
            (-head_size/2, -head_size/2, head_z + head_size),
            (head_size/2, -head_size/2, head_z + head_size),
            (head_size/2, head_size/2, head_z + head_size),
            (-head_size/2, head_size/2, head_z + head_size),
        ]
        vertices.extend(head_vertices)
        
        # ROBOT ARMS - left and right
        arm_width = 0.4 * scale
        arm_length = 2.0 * scale
        arm_height = 0.4 * scale
        arm_z = torso_height * 0.8
        
        # Left arm
        left_arm_x = -torso_width/2 - arm_length/2
        vertices.extend([
            (left_arm_x - arm_length/2, -arm_width/2, arm_z),
            (left_arm_x + arm_length/2, -arm_width/2, arm_z),
            (left_arm_x + arm_length/2, arm_width/2, arm_z),
            (left_arm_x - arm_length/2, arm_width/2, arm_z),
            (left_arm_x - arm_length/2, -arm_width/2, arm_z + arm_height),
            (left_arm_x + arm_length/2, -arm_width/2, arm_z + arm_height),
            (left_arm_x + arm_length/2, arm_width/2, arm_z + arm_height),
            (left_arm_x - arm_length/2, arm_width/2, arm_z + arm_height),
        ])
        
        # Right arm
        right_arm_x = torso_width/2 + arm_length/2
        vertices.extend([
            (right_arm_x - arm_length/2, -arm_width/2, arm_z),
            (right_arm_x + arm_length/2, -arm_width/2, arm_z),
            (right_arm_x + arm_length/2, arm_width/2, arm_z),
            (right_arm_x - arm_length/2, arm_width/2, arm_z),
            (right_arm_x - arm_length/2, -arm_width/2, arm_z + arm_height),
            (right_arm_x + arm_length/2, -arm_width/2, arm_z + arm_height),
            (right_arm_x + arm_length/2, arm_width/2, arm_z + arm_height),
            (right_arm_x - arm_length/2, arm_width/2, arm_z + arm_height),
        ])
        
        # ROBOT LEGS - left and right
        leg_width = 0.6 * scale
        leg_height = 2.5 * scale
        leg_depth = 0.6 * scale
        
        # Left leg
        left_leg_x = -torso_width/4
        vertices.extend([
            (left_leg_x - leg_width/2, -leg_depth/2, -leg_height),
            (left_leg_x + leg_width/2, -leg_depth/2, -leg_height),
            (left_leg_x + leg_width/2, leg_depth/2, -leg_height),
            (left_leg_x - leg_width/2, leg_depth/2, -leg_height),
            (left_leg_x - leg_width/2, -leg_depth/2, 0),
            (left_leg_x + leg_width/2, -leg_depth/2, 0),
            (left_leg_x + leg_width/2, leg_depth/2, 0),
            (left_leg_x - leg_width/2, leg_depth/2, 0),
        ])
        
        # Right leg
        right_leg_x = torso_width/4
        vertices.extend([
            (right_leg_x - leg_width/2, -leg_depth/2, -leg_height),
            (right_leg_x + leg_width/2, -leg_depth/2, -leg_height),
            (right_leg_x + leg_width/2, leg_depth/2, -leg_height),
            (right_leg_x - leg_width/2, leg_depth/2, -leg_height),
            (right_leg_x - leg_width/2, -leg_depth/2, 0),
            (right_leg_x + leg_width/2, -leg_depth/2, 0),
            (right_leg_x + leg_width/2, leg_depth/2, 0),
            (right_leg_x - leg_width/2, leg_depth/2, 0),
        ])
        
        # ROBOT ANTENNA/SENSOR (AI-influenced)
        if len(semantic_vector) > 3 and semantic_vector[3] > 0.5:
            antenna_height = head_size * 1.5
            vertices.extend([
                (0, 0, head_z + head_size),
                (0, 0, head_z + head_size + antenna_height),
                (scale * 0.1, 0, head_z + head_size + antenna_height)  # Antenna tip
            ])
        
        # GENERATE FACES for all box components
        def add_box_faces(base_idx):
            return [
                (base_idx, base_idx+1, base_idx+2), (base_idx, base_idx+2, base_idx+3),  # Bottom
                (base_idx+4, base_idx+7, base_idx+6), (base_idx+4, base_idx+6, base_idx+5),  # Top
                (base_idx, base_idx+4, base_idx+5), (base_idx, base_idx+5, base_idx+1),  # Sides
                (base_idx+1, base_idx+5, base_idx+6), (base_idx+1, base_idx+6, base_idx+2),
                (base_idx+2, base_idx+6, base_idx+7), (base_idx+2, base_idx+7, base_idx+3),
                (base_idx+3, base_idx+7, base_idx+4), (base_idx+3, base_idx+4, base_idx+0)
            ]
        
        # Torso faces (vertices 0-7)
        faces.extend(add_box_faces(0))
        
        # Head faces (vertices 8-15)
        faces.extend(add_box_faces(8))
        
        # Left arm faces (vertices 16-23)
        faces.extend(add_box_faces(16))
        
        # Right arm faces (vertices 24-31)
        faces.extend(add_box_faces(24))
        
        # Left leg faces (vertices 32-39)
        faces.extend(add_box_faces(32))
        
        # Right leg faces (vertices 40-47)
        faces.extend(add_box_faces(40))
        
        # Antenna faces (if exists)
        if len(vertices) > 48:  # Antenna was added
            antenna_idx = 48
            faces.extend([
                (antenna_idx, antenna_idx+1, antenna_idx+2),  # Antenna triangle
            ])
        
        logger.info("Generated recognizable AI robot", vertices=len(vertices), faces=len(faces))
        return vertices, faces
    
    def _generate_architecture_with_ai(self, semantic_vector, complexity, scale):
        """Generate architecture using AI semantic features."""
        vertices = []
        faces = []
        
        # AI-influenced building dimensions
        width = scale * (2.0 + semantic_vector[0] * 3.0)
        depth = scale * (2.0 + semantic_vector[1] * 2.0)
        height = scale * (3.0 + semantic_vector[2] * 4.0)
        
        # Main building base
        base_vertices = [
            (-width/2, -depth/2, 0), (width/2, -depth/2, 0),
            (width/2, depth/2, 0), (-width/2, depth/2, 0),
            (-width/2, -depth/2, height), (width/2, -depth/2, height),
            (width/2, depth/2, height), (-width/2, depth/2, height)
        ]
        vertices.extend(base_vertices)
        
        # AI-influenced roof type
        if semantic_vector[3] > 0.6:
            # Peaked roof
            roof_height = height + scale * (1.0 + semantic_vector[4])
            vertices.extend([
                (0, -depth/2, roof_height),  # Front peak
                (0, depth/2, roof_height)   # Back peak
            ])
            
            # Roof faces
            faces.extend([
                (4, 8, 5), (5, 8, 6),  # Front roof slopes
                (6, 9, 7), (7, 9, 4),  # Back roof slopes
                (8, 9, 6), (8, 6, 5)   # Roof triangles
            ])
        
        # Building base faces
        faces.extend([
            (0, 1, 2), (0, 2, 3),  # Floor
            (4, 7, 6), (4, 6, 5),  # Ceiling
            (0, 4, 5), (0, 5, 1),  # Walls
            (1, 5, 6), (1, 6, 2),
            (2, 6, 7), (2, 7, 3),
            (3, 7, 4), (3, 4, 0)
        ])
        
        logger.info("Generated AI-driven architecture", vertices=len(vertices), faces=len(faces))
        return vertices, faces
    
    def _generate_vehicle_with_ai(self, semantic_vector, complexity, scale):
        """Generate vehicle using AI semantic features."""
        vertices = []
        faces = []
        
        # AI-influenced vehicle proportions
        length = scale * (3.0 + semantic_vector[0] * 2.0)
        width = scale * (1.5 + semantic_vector[1])
        height = scale * (1.0 + semantic_vector[2] * 0.5)
        
        # Main body
        body_vertices = [
            (-length/2, -width/2, 0), (length/2, -width/2, 0),
            (length/2, width/2, 0), (-length/2, width/2, 0),
            (-length/2, -width/2, height), (length/2, -width/2, height),
            (length/2, width/2, height), (-length/2, width/2, height)
        ]
        vertices.extend(body_vertices)
        
        # AI-influenced details (wings, wheels, etc.)
        if semantic_vector[3] > 0.7:
            # Add wings for flying vehicle
            wing_span = length * 1.5
            wing_y = semantic_vector[4] * height
            vertices.extend([
                (-length/4, -wing_span/2, wing_y), (-length/4, wing_span/2, wing_y),
                (length/4, -wing_span/2, wing_y), (length/4, wing_span/2, wing_y)
            ])
        
        # Body faces
        faces.extend([
            (0, 1, 2), (0, 2, 3),  # Bottom
            (4, 7, 6), (4, 6, 5),  # Top
            (0, 4, 5), (0, 5, 1),  # Sides
            (1, 5, 6), (1, 6, 2),
            (2, 6, 7), (2, 7, 3),
            (3, 7, 4), (3, 4, 0)
        ])
        
        logger.info("Generated AI-driven vehicle", vertices=len(vertices), faces=len(faces))
        return vertices, faces
    
    def _generate_abstract_with_ai(self, semantic_vector, complexity, scale, roughness):
        """Generate abstract shape using AI semantic features."""
        vertices = []
        faces = []
        
        # AI-driven abstract generation
        layers = max(5, complexity)
        radius_base = scale * 2.0
        height_scale = scale * 3.0
        
        for layer in range(layers):
            layer_t = layer / (layers - 1)
            layer_height = (layer_t - 0.5) * height_scale
            
            # AI-influenced layer properties
            segments = max(6, int(8 + semantic_vector[0] * 10))
            layer_radius = radius_base * (1.0 + semantic_vector[layer % len(semantic_vector)])
            
            for segment in range(segments):
                segment_t = segment / segments
                angle = segment_t * 2 * math.pi
                
                # AI-influenced radius modulation
                r_mod = layer_radius
                for i, sv in enumerate(semantic_vector[:3]):
                    r_mod *= (1.0 + sv * roughness * math.sin(angle * (i + 2)))
                
                x = r_mod * math.cos(angle)
                y = r_mod * math.sin(angle)
                z = layer_height
                
                vertices.append((x, y, z))
        
        # Generate faces
        segments = max(6, int(8 + semantic_vector[0] * 10))
        for layer in range(layers - 1):
            for segment in range(segments):
                next_segment = (segment + 1) % segments
                
                v1 = layer * segments + segment
                v2 = layer * segments + next_segment
                v3 = (layer + 1) * segments + segment
                v4 = (layer + 1) * segments + next_segment
                
                if v4 < len(vertices):
                    faces.extend([(v1, v2, v3), (v2, v4, v3)])
        
        logger.info("Generated AI-driven abstract shape", vertices=len(vertices), faces=len(faces))
        return vertices, faces
    
    async def generate_3d_from_text(self, job_id: str, prompt: str, output_path: str, format: str = "glb"):
        """Generate 3D model from text using AI analysis."""
        
        logger.info("Starting AI-powered 3D generation", job_id=job_id, prompt=prompt, format=format)
        
        try:
            # Generate AI-driven geometry
            vertices, faces = self._generate_ai_driven_geometry(prompt, format)
            
            # Export to requested format
            if format.lower() == "glb":
                await self._export_glb_with_ai(vertices, faces, prompt, output_path)
            elif format.lower() == "obj":
                await self._export_obj_with_ai(vertices, faces, prompt, output_path)
            elif format.lower() == "ply":
                await self._export_ply_with_ai(vertices, faces, prompt, output_path)
            else:
                logger.warning("Unknown format, falling back to GLB", format=format)
                await self._export_glb_with_ai(vertices, faces, prompt, output_path)
            
            logger.info("AI 3D generation completed successfully", job_id=job_id, format=format)
            return output_path
            
        except Exception as e:
            logger.error("Failed to generate 3D model with AI", job_id=job_id, error=str(e))
            raise
    
    async def _export_glb_with_ai(self, vertices, faces, prompt, output_path):
        """Export AI-generated geometry to GLB format."""
        # Create enhanced GLB with AI metadata
        glb_content = self._create_ai_glb(vertices, faces, prompt)
        with open(output_path, 'wb') as f:
            f.write(glb_content)
        logger.info("AI GLB export completed", path=output_path)
    
    async def _export_obj_with_ai(self, vertices, faces, prompt, output_path):
        """Export AI-generated geometry to OBJ format."""
        with open(output_path, 'w') as f:
            f.write(f"# AI-Generated 3D model for prompt: {prompt}\n")
            f.write(f"# Generated at: {datetime.utcnow().isoformat()}\n")
            f.write(f"# Vertices: {len(vertices)}, Faces: {len(faces)}\n\n")
            
            for v in vertices:
                f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            
            for face in faces:
                f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
        
        logger.info("AI OBJ export completed", path=output_path)
    
    async def _export_ply_with_ai(self, vertices, faces, prompt, output_path):
        """Export AI-generated geometry to PLY format."""
        with open(output_path, 'w') as f:
            f.write("ply\n")
            f.write("format ascii 1.0\n")
            f.write(f"comment AI-Generated 3D model for prompt: {prompt}\n")
            f.write(f"comment Generated at: {datetime.utcnow().isoformat()}\n")
            f.write(f"element vertex {len(vertices)}\n")
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write(f"element face {len(faces)}\n")
            f.write("property list uchar int vertex_indices\n")
            f.write("end_header\n")
            
            for v in vertices:
                f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            
            for face in faces:
                f.write(f"3 {face[0]} {face[1]} {face[2]}\n")
        
        logger.info("AI PLY export completed", path=output_path)
    
    def _create_ai_glb(self, vertices, faces, prompt):
        """Create GLB with AI-generated geometry."""
        # Enhanced GLB with actual geometry data
        header = b'glTF'
        version = (2).to_bytes(4, 'little')
        
        # Convert vertices to binary data
        vertex_data = np.array(vertices, dtype=np.float32).tobytes()
        face_data = np.array(faces, dtype=np.uint16).tobytes()
        
        # JSON chunk with actual geometry info
        json_data = {
            "asset": {"version": "2.0", "generator": "AI-3D-Generator"},
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{
                "primitives": [{
                    "attributes": {"POSITION": 0},
                    "indices": 1
                }]
            }],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,  # FLOAT
                    "count": len(vertices),
                    "type": "VEC3",
                    "min": [float(min(v[i] for v in vertices)) for i in range(3)],
                    "max": [float(max(v[i] for v in vertices)) for i in range(3)]
                },
                {
                    "bufferView": 1,
                    "componentType": 5123,  # UNSIGNED_SHORT
                    "count": len(faces) * 3,
                    "type": "SCALAR"
                }
            ],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": len(vertex_data)},
                {"buffer": 0, "byteOffset": len(vertex_data), "byteLength": len(face_data)}
            ],
            "buffers": [{"byteLength": len(vertex_data) + len(face_data)}],
            "_ai_prompt": prompt,
            "_generated_at": datetime.utcnow().isoformat()
        }
        
        json_str = json.dumps(json_data, separators=(',', ':'))
        json_bytes = json_str.encode('utf-8')
        
        # Pad to 4-byte boundary
        padding = b'\x20' * (4 - (len(json_bytes) % 4)) if len(json_bytes) % 4 else b''
        json_bytes += padding
        
        json_chunk_length = len(json_bytes).to_bytes(4, 'little')
        json_chunk_type = b'JSON'
        
        # Binary chunk
        binary_data = vertex_data + face_data
        binary_padding = b'\x00' * (4 - (len(binary_data) % 4)) if len(binary_data) % 4 else b''
        binary_data += binary_padding
        
        binary_chunk_length = len(binary_data).to_bytes(4, 'little')
        binary_chunk_type = b'BIN\x00'
        
        # Calculate total length
        total_length = 12 + 8 + len(json_bytes) + 8 + len(binary_data)
        length = total_length.to_bytes(4, 'little')
        
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
            
            # Upload file
            self.minio_client.fput_object(bucket_name, object_name, file_path,
                                        content_type="application/octet-stream")
            
            # Return public URL
            public_url = f"http://localhost:9100/{bucket_name}/{object_name}"
            
            logger.info("AI-generated file uploaded to MinIO",
                       job_id=job_id, filename=filename, url=public_url)
            
            return public_url
            
        except S3Error as e:
            logger.error("Failed to upload to MinIO", job_id=job_id, error=str(e))
            raise
    
    async def generate_and_upload_file(self, job_id: str, prompt: str, format: str = "glb") -> dict:
        """Generate AI-powered 3D file and upload to MinIO storage."""
        
        with tempfile.NamedTemporaryFile(suffix=f'.{format}', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
        try:
            # Generate AI-powered 3D model
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
    """Test the AI 3D generator."""
    generator = AI3DGenerator()
    
    test_job_id = "test-ai-job-123"
    test_prompt = "A majestic dragon with detailed scales and wings"
    
    result = await generator.generate_and_upload_file(test_job_id, test_prompt, "obj")
    print(f"Generated AI-powered file: {result}")


if __name__ == "__main__":
    asyncio.run(main())