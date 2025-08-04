# TRELLIS Essential Commands

## Environment Setup
```bash
# Create and activate conda environment with dependencies
. ./setup.sh --new-env --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast

# For demo dependencies
. ./setup.sh --demo

# For training dependencies  
. ./setup.sh --train
```

## Running Examples
```bash
# Basic image-to-3D generation
python example.py

# Text-to-3D generation
python example_text.py

# Generate variants of existing 3D assets
python example_variant.py

# Multi-image conditioning
python example_multi_image.py
```

## Web Demos
```bash
# Launch image-to-3D web demo
python app.py

# Launch text-to-3D web demo  
python app_text.py
```

## Training
```bash
# Single-node training example (VAE decoder)
python train.py \
  --config configs/vae/slat_vae_dec_mesh_swin8_B_64l8_fp16.json \
  --output_dir outputs/my_training \
  --data_dir /path/to/dataset

# Multi-node training example (Flow model)
python train.py \
  --config configs/generation/slat_flow_img_dit_L_64l8p2_fp16.json \
  --output_dir outputs/my_training \
  --data_dir /path/to/dataset \
  --num_nodes 2 \
  --node_rank 0 \
  --master_addr $MASTER_ADDR \
  --master_port $MASTER_PORT

# Resume from checkpoint
python train.py \
  --config configs/generation/slat_flow_img_dit_L_64l8p2_fp16.json \
  --output_dir outputs/my_training \
  --data_dir /path/to/dataset \
  --load_dir /path/to/checkpoint \
  --ckpt [step_number]
```

## System Utilities
```bash
# Check GPU status
nvidia-smi

# List directory contents  
ls -la

# Search for files
find . -name "*.py" -type f

# Search for text in files
grep -r "pattern" .

# Git operations
git status
git add .
git commit -m "message"
```

## Environment Variables
```bash
# Set attention backend (default: flash-attn)
export ATTN_BACKEND=xformers  # or flash-attn

# Set spconv algorithm (default: auto)
export SPCONV_ALGO=native  # or auto
```