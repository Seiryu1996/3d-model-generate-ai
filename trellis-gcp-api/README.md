# TRELLIS GCP API

This project provides a scalable REST API for Microsoft's TRELLIS 3D model generation system deployed on Google Cloud Platform (GCP).

## Features

- **REST API**: FastAPI-based REST endpoints for image-to-3D and text-to-3D generation
- **Scalable Architecture**: Cloud Run + Vertex AI hybrid deployment
- **Asynchronous Processing**: Non-blocking job queue using Cloud Tasks
- **Multiple Output Formats**: GLB, OBJ, PLY file format support
- **Docker Development Environment**: Complete local development setup

## Architecture

- **API Layer**: Cloud Run with FastAPI for lightweight API services
- **ML Processing**: Vertex AI Custom Jobs for GPU-intensive TRELLIS processing
- **Job Management**: Cloud Tasks for queue management and Firestore for job status
- **Storage**: Cloud Storage for models, inputs, and outputs

## Quick Start (Local Development)

1. Clone the repository and navigate to the project directory:
```bash
git clone <repository-url>
cd trellis-gcp-api
```

2. Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Start the development environment:
```bash
docker-compose up --build
```

4. The API will be available at `http://localhost:8000`

## API Endpoints

### Generate 3D Models
- `POST /api/v1/generate/image-to-3d` - Generate 3D model from image
- `POST /api/v1/generate/text-to-3d` - Generate 3D model from text

### Job Management
- `GET /api/v1/jobs/{job_id}/status` - Get job status
- `GET /api/v1/jobs/{job_id}/result` - Get job results
- `DELETE /api/v1/jobs/{job_id}` - Cancel job

### System
- `GET /api/v1/health` - Health check endpoint

## Development

### Project Structure
```
src/
├── api/           # FastAPI routes and endpoints
├── models/        # Pydantic data models
├── services/      # Business logic and external integrations
├── repositories/  # Data access layer
└── utils/         # Utility functions

docker/            # Docker configurations
terraform/         # Infrastructure as Code
tests/            # Test suites
configs/          # Configuration files
```

### Running Tests
```bash
# Unit tests
docker-compose exec api pytest tests/unit/

# Integration tests
docker-compose exec api pytest tests/integration/
```

## GCP Deployment

### Prerequisites
- GCP Project with billing enabled
- Terraform installed
- Google Cloud CLI installed and authenticated

### Deploy Infrastructure
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### Deploy Services
```bash
# Deploy API service to Cloud Run
./scripts/deploy-api.sh

# Deploy TRELLIS worker to Vertex AI
./scripts/deploy-worker.sh
```

## Configuration

Key environment variables:
- `GOOGLE_CLOUD_PROJECT`: Your GCP project ID
- `TRELLIS_MODEL_PATH`: Hugging Face model path for image-to-3D
- `TRELLIS_TEXT_MODEL_PATH`: Hugging Face model path for text-to-3D
- `CLOUD_TASKS_QUEUE`: Cloud Tasks queue name
- `GCS_BUCKET_*`: Cloud Storage bucket names

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## Support

For issues and questions, please create an issue in the GitHub repository.