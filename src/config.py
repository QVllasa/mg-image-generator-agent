"""
Configuration

Lädt Environment-Variablen und stellt Konfiguration bereit.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Load .env file
load_dotenv()


@dataclass
class VLLMConfig:
    """Konfiguration für vLLM (Qwen3-VL)."""
    endpoint: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 300


@dataclass
class FalConfig:
    """Konfiguration für fal.ai."""
    api_key: str
    model: str = "fal-ai/flux-2/edit"  # FLUX.2 Dev Edit - newest, cheapest ($0.012/MP)
    timeout: int = 120


@dataclass
class ServerConfig:
    """Server-Konfiguration."""
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"


@dataclass
class LimitsConfig:
    """Limits für die API."""
    max_images_per_request: int = 5
    max_retries: int = 2
    max_image_size_mb: int = 10


@dataclass
class MeiliSearchConfig:
    """Konfiguration für MeiliSearch."""
    products_url: str
    products_api_key: str
    metadata_url: str
    metadata_api_key: str
    products_index: str = "products"
    metadata_filter_index: str = "filter"
    default_products_per_type: int = 5


@dataclass
class Config:
    """Haupt-Konfiguration."""
    vllm: VLLMConfig
    fal: FalConfig
    server: ServerConfig
    limits: LimitsConfig
    meilisearch: MeiliSearchConfig


def get_config() -> Config:
    """Lädt und validiert die Konfiguration aus Environment-Variablen."""

    # fal.ai API Key ist required
    fal_api_key = os.getenv("FAL_API_KEY")
    if not fal_api_key:
        raise ValueError("FAL_API_KEY environment variable is required")

    return Config(
        vllm=VLLMConfig(
            endpoint=os.getenv("VLLM_ENDPOINT", "http://localhost:8081/v1"),
            model=os.getenv("VLLM_MODEL", "qwen3-vl-thinking"),
            max_tokens=int(os.getenv("VLLM_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("VLLM_TEMPERATURE", "0.7")),
            timeout=int(os.getenv("VLLM_REQUEST_TIMEOUT", "300")),
        ),
        fal=FalConfig(
            api_key=fal_api_key,
            model=os.getenv("FAL_MODEL", "fal-ai/flux-2/edit"),
            timeout=int(os.getenv("FAL_TIMEOUT", "120")),
        ),
        server=ServerConfig(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        ),
        limits=LimitsConfig(
            max_images_per_request=int(os.getenv("MAX_IMAGES_PER_REQUEST", "5")),
            max_retries=int(os.getenv("MAX_RETRIES", "2")),
            max_image_size_mb=int(os.getenv("MAX_IMAGE_SIZE_MB", "10")),
        ),
        meilisearch=MeiliSearchConfig(
            products_url=os.getenv("MEILISEARCH_PRODUCTS_URL", "http://localhost:7700"),
            products_api_key=os.getenv("MEILISEARCH_PRODUCTS_API_KEY", ""),
            metadata_url=os.getenv("MEILISEARCH_METADATA_URL", "http://localhost:7701"),
            metadata_api_key=os.getenv("MEILISEARCH_METADATA_API_KEY", ""),
            products_index=os.getenv("MEILISEARCH_PRODUCTS_INDEX", "products"),
            metadata_filter_index=os.getenv("MEILISEARCH_FILTER_INDEX", "filter"),
            default_products_per_type=int(os.getenv("PRODUCTS_PER_TYPE", "5")),
        ),
    )


# Singleton instance
_config: Optional[Config] = None


def get_settings() -> Config:
    """Holt oder erstellt die Singleton-Konfiguration."""
    global _config
    if _config is None:
        _config = get_config()
    return _config
