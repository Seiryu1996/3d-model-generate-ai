# TRELLIS Task Completion Checklist

## When Completing Development Tasks

### Code Quality Checks
Since TRELLIS doesn't have explicit linting/formatting tools configured, follow these manual checks:

1. **Code Style Verification**
   - Ensure snake_case for variables and functions
   - Ensure PascalCase for classes
   - Add type hints to function signatures
   - Add docstrings for public functions using Google style

2. **Import Organization**
   - Standard library imports first
   - Third-party imports second
   - Local imports last
   - Remove unused imports

3. **Testing Approach**
   - Run basic examples to verify functionality:
     ```bash
     python example.py  # Test basic image-to-3D pipeline
     python example_text.py  # Test text-to-3D pipeline
     ```
   - For training code, use `--tryrun` flag to validate configuration:
     ```bash
     python train.py --config configs/... --tryrun
     ```

4. **Environment Verification**
   - Test with different attention backends if modified attention code:
     ```bash
     ATTN_BACKEND=xformers python example.py
     ATTN_BACKEND=flash-attn python example.py
     ```

### Hardware Considerations
- Verify GPU memory requirements (minimum 16GB)
- Test CUDA compatibility if modifying CUDA extensions
- Check that modifications work with both CUDA 11.8 and 12.2

### Before Committing Changes
1. **Functionality Test**: Run relevant examples
2. **Configuration Validation**: Use `--tryrun` for training configs
3. **Documentation Update**: Update docstrings and comments
4. **Memory Check**: Ensure GPU memory usage is reasonable
5. **Dependency Check**: Verify no new unlisted dependencies

### Training-Specific Tasks
- Validate configuration files in `configs/` directory
- Test distributed training setup if modifying training code
- Verify checkpoint loading/saving functionality
- Check that training curves look reasonable in TensorBoard

### Demo-Specific Tasks  
- Test Gradio interface functionality
- Verify file upload/download works
- Check that temporary files are cleaned up properly
- Test session management