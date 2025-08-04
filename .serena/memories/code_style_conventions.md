# TRELLIS Code Style and Conventions

## Python Code Style
Based on analysis of the codebase, TRELLIS follows these conventions:

### Import Organization
- Standard library imports first
- Third-party imports second  
- Local/relative imports last
- Example from `app.py`:
```python
import os
import shutil
from typing import *
import torch
import numpy as np
from trellis.pipelines import TrellisImageTo3DPipeline
```

### Function Documentation
- Uses Google-style docstrings with Args and Returns sections
- Example:
```python
def preprocess_image(image: Image.Image) -> Image.Image:
    """
    Preprocess the input image.

    Args:
        image (Image.Image): The input image.

    Returns:
        Image.Image: The preprocessed image.
    """
```

### Naming Conventions
- **Variables**: snake_case (e.g., `user_dir`, `processed_image`)
- **Functions**: snake_case (e.g., `preprocess_image`, `start_session`)
- **Classes**: PascalCase (e.g., `TrellisImageTo3DPipeline`, `EasyDict`)
- **Constants**: UPPER_CASE (e.g., `MAX_SEED`, `TMP_DIR`)

### Type Hints
- Extensive use of type hints throughout the codebase
- Uses `typing` module for complex types
- Example: `def preprocess_images(images: List[Tuple[Image.Image, str]]) -> List[Image.Image]:`

### Code Organization
- Configuration using EasyDict for easy access
- Environment variables for runtime configuration
- Modular structure with clear separation of concerns

### Error Handling
- Uses standard Python exception handling
- Graceful fallbacks for different hardware configurations

### Comments
- Inline comments for important configuration options
- Block comments for explaining complex logic
- Documentation strings for all public functions