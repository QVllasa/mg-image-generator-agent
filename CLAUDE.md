# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python -m src.main
# Or with uvicorn directly
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest
pytest tests/test_specific.py -v  # Single test file
pytest -k "test_function_name"    # Single test

# Docker deployment
docker-compose up -d
```

## Environment Setup

Copy `.env.example` to `.env` and configure:
- `FAL_API_KEY` (required) - fal.ai API key for FLUX.2 image generation
- `VLLM_ENDPOINT` - vLLM endpoint for Qwen3-VL vision model
- `MEILISEARCH_PRODUCTS_URL` / `MEILISEARCH_METADATA_URL` - MeiliSearch instances

## Architecture Overview

### LangGraph Agent Flow

The core of this service is a LangGraph StateGraph that orchestrates room staging:

```
receive_images → analyze_room → [MeiliSearch Flow OR Direct Flow] → generate_staged → validate_result → finalize
```

**MeiliSearch Flow** (when `color_preferences` provided, no `product_images`):
```
analyze_room → build_filter → fetch_products → select_products → generate_staged
```

**Direct Flow** (when `product_images` provided or text-prompt mode):
```
analyze_room → generate_staged
```

### Key Components

- **`src/agent/graph.py`** - LangGraph StateGraph definition, routing logic, `run_staging()` entry point
- **`src/agent/nodes.py`** - Individual graph nodes: receive_images, analyze_room, generate_staged, validate_result, finalize, plus MeiliSearch nodes (build_filter, fetch_products, select_products)
- **`src/agent/state.py`** - `StagingState` TypedDict defining the complete workflow state

### Services

- **`src/services/vision_service.py`** - Qwen3-VL integration for room analysis, staging prompt generation, validation, and product position detection. Uses OpenAI-compatible API for vLLM.
- **`src/services/fal_service.py`** - fal.ai FLUX.2 [dev] Edit integration for image generation. Supports text-prompt and multi-reference (product images) modes.
- **`src/services/meilisearch_service.py`** - Product search with dynamic filter building. Contains `FURNITURE_CATEGORY_MAPPING` for German furniture categories and `FILTER_VALUES` for allowed filter values.

### Three Staging Modes

1. **Text-Prompt Mode**: Generate furniture based on text description and room analysis
2. **Multi-Reference Mode**: Place specific product images into the room using FLUX.2 multi-image input
3. **MeiliSearch Mode**: Agent automatically selects products from MeiliSearch based on color/style preferences

### State Management

`StagingState` in `src/agent/state.py` contains all workflow data:
- Request data (style, furniture_types, product_images)
- MeiliSearch integration (color_preferences, budget_range, selected_products)
- Image processing state (current_image_index, room_analysis, staged_base64)
- Results (product_positions/hotspots for frontend overlays)

## Code Conventions

- German comments/logging in most files (originally developed for German furniture e-commerce)
- Singleton pattern for services (`get_fal_service()`, `get_vision_service()`, `get_meilisearch_service()`)
- Pydantic models for API request/response validation in `src/models/`
- Structured logging via structlog in `src/utils/logging.py`
- All vision service methods return Pydantic models and expect/return JSON responses from Qwen3-VL
