# MoebelGuru Image Generator Agent

AI-powered image generation services for German furniture e-commerce.

## Overview

This repository contains image generation agents for MoebelGuru, starting with the **Room Stager** service that creates virtual room staging with furniture.

## Services

### Room Stager

Virtual room staging service that takes empty room images and adds furniture using AI.

**Features:**
- Analyze room images to detect room type, dimensions, and suitable furniture placement
- Multiple input modes:
  - **Text Prompt**: Describe desired furniture style
  - **Multi-Reference**: Provide specific product images to place
  - **MeiliSearch Integration**: Auto-select products based on color/budget preferences
- Generate staged room images with realistic furniture placement
- Product hotspots with coordinates for interactive overlays
- FAL AI integration for high-quality image generation
- vLLM integration for room analysis and furniture positioning

**API Endpoints:**
- `POST /api/v1/stage-room` - Stage a room with virtual furniture
- `GET /health` - Health check
- `GET /` - API info

## Project Structure

```
mg-image-generator-agent/
├── src/
│   ├── agent/           # LangGraph agent orchestration
│   ├── models/          # Pydantic request/response models
│   ├── services/        # Business logic (marker service, etc.)
│   ├── utils/           # Logging and utilities
│   ├── config.py        # Configuration management
│   └── main.py          # FastAPI application
├── tests/               # Test suite
├── docker-compose.yaml  # Container orchestration
├── Dockerfile
├── requirements.txt
└── .env.example         # Environment template
```

## Setup

### Prerequisites

- Python 3.11+
- FAL AI API access
- vLLM endpoint
- MeiliSearch instance (optional, for product search)

### Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Environment Variables

```bash
# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# FAL AI
FAL_KEY=your-fal-api-key
FAL_MODEL=fal-ai/flux-pro/v1.1

# vLLM
VLLM_ENDPOINT=https://your-vllm-endpoint/v1
VLLM_MODEL=your-model-name

# MeiliSearch (optional)
MEILISEARCH_URL=https://your-meilisearch-url
MEILISEARCH_API_KEY=your-api-key
```

## Usage

### Running the API

```bash
# Development mode
python -m src.main

# Or with uvicorn directly
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Deployment

```bash
docker-compose up -d
```

### API Example

```bash
curl -X POST http://localhost:8000/api/v1/stage-room \
  -H "Content-Type: application/json" \
  -d '{
    "images": [{"data": "base64...", "filename": "room.jpg"}],
    "style": "modern",
    "furniture_types": ["sofa", "coffee_table"],
    "room_type": "living_room"
  }'
```

## Documentation

API documentation available at `/docs` (Swagger UI) when the server is running.
