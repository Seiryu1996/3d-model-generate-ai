# TRELLIS Tech Stack

## Core Technologies
- **Python 3.8+**: Primary programming language
- **PyTorch 2.4.0**: Deep learning framework with CUDA 11.8 support
- **CUDA**: GPU acceleration (versions 11.8, 12.2 supported)
- **Conda**: Package and environment management

## Key Dependencies
- **Hugging Face Hub**: Model hosting and downloading
- **Gradio 4.44.1**: Web interface framework
- **PIL/Pillow**: Image processing
- **NumPy**: Numerical computations
- **ImageIO**: Video/image I/O operations
- **OpenCV**: Computer vision operations
- **Trimesh**: 3D mesh processing
- **Open3D**: 3D data processing
- **Transformers**: NLP model support

## Specialized Extensions
- **xformers/flash-attn**: Efficient attention mechanisms
- **spconv**: Sparse convolutions for 3D data
- **kaolin**: 3D deep learning operations (NVIDIA)
- **nvdiffrast**: Differentiable rendering
- **diffoctreerast**: Custom CUDA-based octree renderer
- **mip-splatting**: 3D Gaussian splatting
- **vox2seq**: Voxel processing

## Training Infrastructure
- **Distributed training**: Multi-node/multi-GPU support
- **TensorBoard**: Training monitoring
- **EasyDict**: Configuration management
- **LPIPS**: Perceptual loss metrics

## File Formats Supported
- **Input**: Images (PNG, JPG), Text prompts
- **Output**: PLY files, GLB files, MP4 videos
- **3D Representations**: Gaussian splats, Radiance fields, Meshes