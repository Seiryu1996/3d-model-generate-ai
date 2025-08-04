.PHONY: help build up down logs test clean dev-tools

# Default target
help:
	@echo "Available commands:"
	@echo "  build      - Build all Docker images"
	@echo "  up         - Start all services"
	@echo "  down       - Stop all services"
	@echo "  logs       - View logs from all services"
	@echo "  test       - Run tests"
	@echo "  clean      - Clean up Docker resources"
	@echo "  dev-tools  - Start with development tools (adminer, redis-commander)"
	@echo "  api-shell  - Open shell in API container"
	@echo "  worker-shell - Open shell in worker container"

# Build all images
build:
	docker-compose build

# Start all services
up:
	docker-compose up -d

# Start all services with logs
up-logs:
	docker-compose up

# Stop all services
down:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# View logs for specific service
logs-api:
	docker-compose logs -f api

logs-worker:
	docker-compose logs -f worker

# Run tests
test:
	docker-compose exec api pytest tests/

# Clean up Docker resources
clean:
	docker-compose down -v
	docker system prune -f
	docker volume prune -f

# Start with development tools
dev-tools:
	docker-compose --profile dev-tools up -d

# Open shell in API container
api-shell:
	docker-compose exec api /bin/bash

# Open shell in worker container
worker-shell:
	docker-compose exec worker /bin/bash

# Restart specific services
restart-api:
	docker-compose restart api

restart-worker:
	docker-compose restart worker

# Check service status
status:
	docker-compose ps

# Pull latest images
pull:
	docker-compose pull

# Force rebuild and restart
rebuild:
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

# Development setup (first time)
setup-dev:
	cp .env.example .env
	@echo "Please edit .env file with your configuration"
	@echo "Then run: make build && make up"