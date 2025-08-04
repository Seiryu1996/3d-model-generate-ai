# TRELLIS - 3D Model Generation Project

## Project Purpose
TRELLIS is a large-scale 3D asset generation model developed by Microsoft. It takes text or image prompts and generates high-quality 3D assets in various formats including:
- Radiance Fields
- 3D Gaussians 
- Meshes

The model uses a unified Structured LATent (SLAT) representation that allows decoding to different output formats and Rectified Flow Transformers. It includes pre-trained models with up to 2 billion parameters trained on a dataset of 500K diverse 3D objects.

## Key Features
- High-quality 3D asset generation from text or image prompts
- Multiple output formats (Radiance Fields, 3D Gaussians, meshes)
- Flexible editing capabilities for generated 3D assets
- Large-scale pre-trained models
- Support for both image-to-3D and text-to-3D generation

## Available Models
- TRELLIS-image-large (1.2B parameters) - recommended for best quality
- TRELLIS-text-base (342M parameters)
- TRELLIS-text-large (1.1B parameters) 
- TRELLIS-text-xlarge (2.0B parameters)

## System Requirements
- Linux system (tested primarily on Linux)
- NVIDIA GPU with at least 16GB memory (tested on A100, A6000)
- CUDA Toolkit (11.8 or 12.2)
- Python 3.8+
- Conda (recommended for dependency management)