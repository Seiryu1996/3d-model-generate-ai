# TRELLIS Codebase Structure

## Root Directory Structure
```
TRELLIS/
├── trellis/                    # Main package
│   ├── datasets/              # Dataset loading and preprocessing
│   ├── models/                # Model architectures and components
│   ├── modules/               # Custom modules for various models
│   ├── pipelines/             # Inference pipelines for different models
│   ├── renderers/             # Renderers for different 3D representations
│   ├── representations/       # Different 3D representations (Gaussian, Mesh, etc.)
│   ├── trainers/              # Training logic for different models
│   └── utils/                 # Utility functions for training and visualization
├── configs/                   # Configuration files for training/models
├── assets/                    # Example images and resources
├── extensions/                # Custom CUDA extensions
├── trellis_env/              # Environment-specific files
├── dataset_toolkits/         # Tools for dataset preparation
└── .github/                  # GitHub workflows and actions
```

## Key Entry Points
- **app.py**: Gradio web demo for image-to-3D generation
- **app_text.py**: Gradio web demo for text-to-3D generation  
- **example.py**: Basic usage example for image-to-3D
- **example_text.py**: Basic usage example for text-to-3D
- **example_variant.py**: Example for generating variants
- **example_multi_image.py**: Multi-image conditioning example
- **train.py**: Main training script
- **setup.sh**: Environment setup script

## Core Module Organization
- **Pipelines**: High-level interfaces (TrellisImageTo3DPipeline, etc.)
- **Models**: Neural network architectures (VAEs, Transformers)
- **Representations**: 3D data structures (Gaussian, Mesh, RadianceField)
- **Renderers**: Visualization and rendering utilities
- **Utils**: Helper functions for rendering, postprocessing, etc.

## Configuration Structure
- **VAE configs**: Encoder/decoder configurations for different representations
- **Generation configs**: Flow model configurations for text/image conditioning
- **Training configs**: Hyperparameters and training setup