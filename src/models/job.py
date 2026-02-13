"""
Job Models

Pydantic models for async job tracking API.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job status enum."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobMode(str, Enum):
    """Job mode enum."""
    TEXT_PROMPT = "text-prompt"
    MULTI_REFERENCE = "multi-reference"
    MEILISEARCH = "meilisearch"


class JobStage(str, Enum):
    """Job processing stage enum."""
    RECEIVE = "receive"
    ANALYZE = "analyze"
    BUILD_FILTER = "build_filter"
    FETCH_PRODUCTS = "fetch_products"
    SELECT_PRODUCTS = "select_products"
    GENERATE = "generate"
    VALIDATE = "validate"
    FINALIZE = "finalize"


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class BudgetRange(BaseModel):
    """Budget range for product selection."""
    min: float = Field(0, ge=0, description="Minimum budget")
    max: float = Field(0, ge=0, description="Maximum budget")


class ImageInput(BaseModel):
    """Input image for staging."""
    data: str = Field(..., description="Base64-encoded image data")
    filename: str = Field(..., description="Original filename")


class ProductImageInput(BaseModel):
    """Product image input for multi-reference mode."""
    name: str = Field(..., description="Product name")
    data: str = Field(..., description="Base64-encoded product image")
    ean: Optional[str] = Field(None, description="Product EAN")


class CreateJobRequest(BaseModel):
    """Request model for creating a new staging job."""
    images: List[ImageInput] = Field(..., min_length=1, max_length=5)
    style: str = Field("modern", description="Desired furniture style")
    room_type: Optional[str] = Field(None, description="Manual room type override")
    furniture_types: Optional[List[str]] = Field(None, description="Desired furniture types (text-prompt mode)")
    product_images: Optional[List[ProductImageInput]] = Field(None, description="Product images (multi-reference mode)")
    color_preferences: Optional[List[str]] = Field(None, description="Color preferences (meilisearch mode)")
    budget_range: Optional[BudgetRange] = Field(None, description="Budget range (meilisearch mode)")
    products_per_type: int = Field(5, ge=1, le=10, description="Products per furniture type")


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ProductHotspot(BaseModel):
    """Product hotspot position for frontend overlays."""
    product_name: str
    product_id: Optional[str] = None
    x: float = Field(..., ge=0, le=100, description="X position in percent")
    y: float = Field(..., ge=0, le=100, description="Y position in percent")
    width: float = Field(..., ge=0, le=100, description="Width in percent")
    height: float = Field(..., ge=0, le=100, description="Height in percent")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence")
    hotspot_x: float = Field(..., ge=0, le=100, description="Ideal hotspot X")
    hotspot_y: float = Field(..., ge=0, le=100, description="Ideal hotspot Y")


class JobImage(BaseModel):
    """Job image result."""
    id: str
    original_filename: str
    image_index: int
    original_image_url: Optional[str] = None
    staged_image_url: Optional[str] = None
    staged_image_with_markers_url: Optional[str] = None
    room_analysis: Optional[Dict[str, Any]] = None
    product_hotspots: Optional[List[ProductHotspot]] = None
    furniture_added: Optional[List[str]] = None
    status: str
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None


class SelectedProduct(BaseModel):
    """Selected product from MeiliSearch."""
    id: str
    product_id: str
    ean: Optional[str] = None
    name: str
    furniture_type: str
    price: Optional[float] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    selection_reason: Optional[str] = None


class JobResponse(BaseModel):
    """Full job response with all details."""
    id: str
    session_id: str
    status: JobStatus
    mode: JobMode
    style: str
    room_type: Optional[str] = None

    # Request parameters
    color_preferences: Optional[List[str]] = None
    budget_range: Optional[BudgetRange] = None
    furniture_types: Optional[List[str]] = None

    # Progress
    total_images: int
    completed_images: int
    current_stage: Optional[str] = None
    progress_percent: int

    # Timing
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    processing_time_ms: Optional[int] = None

    # Error
    error_message: Optional[str] = None

    # Results (populated when status is completed)
    images: Optional[List[JobImage]] = None
    selected_products: Optional[List[SelectedProduct]] = None


class JobListItem(BaseModel):
    """Job list item (summary)."""
    id: str
    session_id: str
    status: JobStatus
    mode: JobMode
    style: str
    total_images: int
    completed_images: int
    progress_percent: int
    created_at: str
    completed_at: Optional[str] = None
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None


class JobListResponse(BaseModel):
    """Job list response with pagination."""
    jobs: List[JobListItem]
    total: int
    limit: int
    offset: int


class CreateJobResponse(BaseModel):
    """Response after creating a job."""
    id: str
    session_id: str
    status: JobStatus
    message: str = "Job created successfully"


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT MODELS (for SSE)
# ═══════════════════════════════════════════════════════════════════════════════

class JobEventType(str, Enum):
    """Job event types."""
    STARTED = "started"
    ANALYZING = "analyzing"
    BUILDING_FILTER = "building_filter"
    FETCHING_PRODUCTS = "fetching_products"
    SELECTING_PRODUCTS = "selecting_products"
    GENERATING = "generating"
    VALIDATING = "validating"
    IMAGE_COMPLETED = "image_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    PROGRESS = "progress"


class JobEvent(BaseModel):
    """Job event for SSE streaming."""
    id: int
    job_id: str
    event_type: JobEventType
    event_data: Optional[Dict[str, Any]] = None
    created_at: str


# ═══════════════════════════════════════════════════════════════════════════════
# STATISTICS MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class JobStatistics(BaseModel):
    """Job statistics response."""
    total_jobs: int
    pending_jobs: int
    processing_jobs: int
    completed_jobs: int
    failed_jobs: int
    avg_processing_time_ms: float
    jobs_last_24h: int
    jobs_last_7d: int
    jobs_by_mode: Dict[str, int]
