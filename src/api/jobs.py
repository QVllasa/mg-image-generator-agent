"""
Jobs API Router

Async job management endpoints with real-time progress updates.
"""

import asyncio
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from src.agent.graph import run_staging
from src.models.job import (
    CreateJobRequest,
    CreateJobResponse,
    JobEvent,
    JobEventType,
    JobImage,
    JobListItem,
    JobListResponse,
    JobMode,
    JobResponse,
    JobStatistics,
    JobStatus,
    ProductHotspot,
    SelectedProduct,
)
from src.services.database_service import get_database_service
from src.services.storage_service import get_storage_service
from src.services.marker_service import draw_product_markers
from src.utils.logging import get_logger, get_correlation_id

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def determine_mode(request: CreateJobRequest) -> JobMode:
    """Determine job mode from request."""
    if request.product_images:
        return JobMode.MULTI_REFERENCE
    elif request.color_preferences:
        return JobMode.MEILISEARCH
    else:
        return JobMode.TEXT_PROMPT


# Mapping from node names to stages and event types
NODE_TO_STAGE = {
    "receive_images": ("receive", None),
    "analyze_room": ("analyze", JobEventType.ANALYZING),
    "build_filter": ("build_filter", JobEventType.BUILDING_FILTER),
    "fetch_products": ("fetch_products", JobEventType.FETCHING_PRODUCTS),
    "select_products": ("select_products", JobEventType.SELECTING_PRODUCTS),
    "generate_staged": ("generate", JobEventType.GENERATING),
    "validate_result": ("validate", JobEventType.VALIDATING),
    "next_image": ("validate", None),
    "finalize": ("finalize", None),
}

# Progress percentages for each stage
STAGE_PROGRESS = {
    "receive": 5,
    "analyze": 15,
    "build_filter": 25,
    "fetch_products": 35,
    "select_products": 45,
    "generate": 60,
    "validate": 85,
    "finalize": 95,
}


async def process_job(job_id: UUID, session_id: str, request: CreateJobRequest):
    """
    Background task to process a staging job.

    This runs the full staging pipeline and updates the database with progress.
    """
    db = get_database_service()
    storage = get_storage_service()

    start_time = time.time()

    # Progress callback for live updates
    async def on_progress(node_name: str, state_update: dict):
        """Called after each graph node completes."""
        stage_info = NODE_TO_STAGE.get(node_name)
        if not stage_info:
            return

        stage, event_type = stage_info
        progress = STAGE_PROGRESS.get(stage, 0)

        # Update job status with current stage and progress
        await db.update_job_status(
            job_id,
            "processing",
            current_stage=stage,
            progress_percent=progress,
        )

        # Emit event if this stage has an event type
        if event_type:
            await db.add_job_event(
                job_id,
                event_type.value,
                {"node": node_name, "stage": stage},
            )

        logger.debug(f"Progress: {stage} ({progress}%)", job_id=str(job_id), node=node_name)

    try:
        # Update status to processing
        await db.update_job_status(job_id, "processing", current_stage="receive", progress_percent=0)
        await db.add_job_event(job_id, JobEventType.STARTED.value, {"session_id": session_id})

        logger.info(f"Job gestartet: {job_id}", session_id=session_id)

        # Prepare input data
        images = [{"data": img.data, "filename": img.filename} for img in request.images]

        product_images = None
        if request.product_images:
            product_images = [
                {"name": p.name, "base64": p.data, "ean": p.ean or ""}
                for p in request.product_images
            ]

        budget_range = None
        if request.budget_range:
            budget_range = {"min": request.budget_range.min, "max": request.budget_range.max}

        # Upload original images to storage
        for i, img in enumerate(request.images):
            original_url = storage.upload_original_image(
                session_id=session_id,
                filename=img.filename,
                image_base64=img.data,
            )
            # Create job image record
            await db.create_job_image(
                job_id=job_id,
                original_filename=img.filename,
                image_index=i,
                original_image_url=original_url,
            )

        # Run staging pipeline with progress callback
        result = await run_staging(
            images=images,
            style=request.style,
            furniture_types=request.furniture_types,
            product_images=product_images,
            room_type=request.room_type,
            color_preferences=request.color_preferences,
            budget_range=budget_range,
            products_per_type=request.products_per_type,
            # Pass job tracking info
            job_id=str(job_id),
            session_id=session_id,
            # Progress callback for live updates
            on_progress=on_progress,
        )

        # Process results
        job_images = await db.get_job_images(job_id)

        for i, img_result in enumerate(result.get("images", [])):
            if i < len(job_images):
                image_id = UUID(job_images[i]["id"])
                staged_url = None
                markers_url = None
                hotspots = []

                if img_result.get("staged_base64"):
                    # Upload staged image
                    staged_url = storage.upload_staged_image(
                        session_id=session_id,
                        filename=img_result["filename"],
                        image_base64=img_result["staged_base64"],
                    )

                    # Create markers image if hotspots exist
                    if img_result.get("product_positions"):
                        hotspots = img_result["product_positions"]
                        try:
                            markers_base64 = draw_product_markers(
                                image_base64=img_result["staged_base64"],
                                product_positions=hotspots,
                            )
                            if markers_base64:
                                markers_url = storage.upload_staged_image_with_markers(
                                    session_id=session_id,
                                    filename=img_result["filename"],
                                    image_base64=markers_base64,
                                )
                        except Exception as e:
                            logger.warning(f"Marker-Bild konnte nicht erstellt werden: {e}")

                # Update image record
                await db.update_job_image(
                    image_id=image_id,
                    status="completed" if staged_url else "failed",
                    staged_image_url=staged_url,
                    staged_image_with_markers_url=markers_url,
                    room_analysis=img_result.get("room_analysis"),
                    product_hotspots=hotspots,
                    furniture_added=img_result.get("furniture_added"),
                    processing_time_ms=img_result.get("processing_time_ms"),
                    error_message=img_result.get("error"),
                )

                # Emit image completed event
                await db.add_job_event(
                    job_id,
                    JobEventType.IMAGE_COMPLETED.value,
                    {
                        "image_index": i,
                        "filename": img_result["filename"],
                        "staged_url": staged_url,
                    },
                )

        # Save selected products (MeiliSearch mode)
        if result.get("selected_products"):
            for product in result["selected_products"]:
                await db.add_selected_product(
                    job_id=job_id,
                    product_id=product.get("product_id", ""),
                    name=product.get("name", ""),
                    furniture_type=product.get("furniture_type", ""),
                    ean=product.get("ean"),
                    price=product.get("price"),
                    image_url=product.get("image_url"),
                    images=product.get("images"),
                    selection_reason=product.get("selection_reason"),
                )

        # Calculate total processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Update job as completed
        await db.update_job_status(
            job_id,
            "completed",
            current_stage="done",
            processing_time_ms=processing_time_ms,
        )
        await db.add_job_event(
            job_id,
            JobEventType.COMPLETED.value,
            {"processing_time_ms": processing_time_ms},
        )

        logger.info(
            f"Job abgeschlossen: {job_id}",
            session_id=session_id,
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error(f"Job fehlgeschlagen: {job_id}", error=str(e), exc_info=True)

        processing_time_ms = int((time.time() - start_time) * 1000)

        await db.update_job_status(
            job_id,
            "failed",
            error_message=str(e),
            processing_time_ms=processing_time_ms,
        )
        await db.add_job_event(
            job_id,
            JobEventType.FAILED.value,
            {"error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS - Route order matters! Specific routes before parameterized routes.
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("", response_model=CreateJobResponse)
async def create_job(
    request: CreateJobRequest,
    background_tasks: BackgroundTasks,
) -> CreateJobResponse:
    """
    Create a new staging job.

    The job will be processed in the background. Poll GET /jobs/{id} or
    subscribe to GET /jobs/{id}/events for real-time progress.
    """
    db = get_database_service()

    # Determine mode
    mode = determine_mode(request)

    # Generate session ID
    import uuid
    session_id = f"stg-{uuid.uuid4().hex[:8]}"

    logger.info(
        "Neuer Job wird erstellt",
        mode=mode.value,
        style=request.style,
        image_count=len(request.images),
        session_id=session_id,
    )

    try:
        # Create job in database
        job_id = await db.create_job(
            session_id=session_id,
            mode=mode.value,
            style=request.style,
            total_images=len(request.images),
            room_type=request.room_type,
            color_preferences=request.color_preferences,
            budget_range=request.budget_range.model_dump() if request.budget_range else None,
            furniture_types=request.furniture_types,
            correlation_id=get_correlation_id(),
        )

        # Start background processing
        background_tasks.add_task(process_job, job_id, session_id, request)

        return CreateJobResponse(
            id=str(job_id),
            session_id=session_id,
            status=JobStatus.PENDING,
            message="Job created successfully. Processing will start shortly.",
        )

    except Exception as e:
        logger.error(f"Job-Erstellung fehlgeschlagen: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    mode: Optional[str] = Query(None, description="Filter by mode"),
    limit: int = Query(50, ge=1, le=100, description="Maximum jobs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> JobListResponse:
    """
    List jobs with optional filters and pagination.
    """
    db = get_database_service()

    jobs = await db.list_jobs(status=status, mode=mode, limit=limit, offset=offset)
    total = await db.count_jobs(status=status, mode=mode)

    return JobListResponse(
        jobs=[
            JobListItem(
                id=job["id"],
                session_id=job["session_id"],
                status=JobStatus(job["status"]),
                mode=JobMode(job["mode"]),
                style=job["style"],
                total_images=job["total_images"],
                completed_images=job["completed_images"],
                progress_percent=job["progress_percent"],
                created_at=job["created_at"],
                completed_at=job["completed_at"],
                processing_time_ms=job["processing_time_ms"],
                error_message=job["error_message"],
            )
            for job in jobs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats/overview", response_model=JobStatistics)
async def get_job_statistics() -> JobStatistics:
    """
    Get overall job statistics.
    """
    db = get_database_service()
    stats = await db.get_statistics()

    return JobStatistics(
        total_jobs=stats["total_jobs"],
        pending_jobs=stats["pending_jobs"],
        processing_jobs=stats["processing_jobs"],
        completed_jobs=stats["completed_jobs"],
        failed_jobs=stats["failed_jobs"],
        avg_processing_time_ms=stats["avg_processing_time_ms"],
        jobs_last_24h=stats["jobs_last_24h"],
        jobs_last_7d=stats["jobs_last_7d"],
        jobs_by_mode=stats["jobs_by_mode"],
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """
    Get job status and results.

    Returns full job details including images and selected products when completed.
    """
    db = get_database_service()

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await db.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get images and products
    images = None
    selected_products = None

    if job["status"] in ("completed", "processing"):
        job_images = await db.get_job_images(job_uuid)
        images = [
            JobImage(
                id=img["id"],
                original_filename=img["original_filename"],
                image_index=img["image_index"],
                original_image_url=img["original_image_url"],
                staged_image_url=img["staged_image_url"],
                staged_image_with_markers_url=img["staged_image_with_markers_url"],
                room_analysis=img["room_analysis"],
                product_hotspots=[ProductHotspot(**h) for h in img["product_hotspots"]] if img["product_hotspots"] else None,
                furniture_added=img["furniture_added"],
                status=img["status"],
                processing_time_ms=img["processing_time_ms"],
                error_message=img["error_message"],
            )
            for img in job_images
        ]

        db_products = await db.get_selected_products(job_uuid)
        if db_products:
            selected_products = [
                SelectedProduct(
                    id=p["id"],
                    product_id=p["product_id"],
                    ean=p["ean"],
                    name=p["name"],
                    furniture_type=p["furniture_type"],
                    price=float(p["price"]) if p["price"] else None,
                    image_url=p["image_url"],
                    images=p["images"],
                    selection_reason=p["selection_reason"],
                )
                for p in db_products
            ]

    return JobResponse(
        id=job["id"],
        session_id=job["session_id"],
        status=JobStatus(job["status"]),
        mode=JobMode(job["mode"]),
        style=job["style"],
        room_type=job["room_type"],
        color_preferences=job["color_preferences"],
        budget_range=job["budget_range"],
        furniture_types=job["furniture_types"],
        total_images=job["total_images"],
        completed_images=job["completed_images"],
        current_stage=job["current_stage"],
        progress_percent=job["progress_percent"],
        created_at=job["created_at"],
        started_at=job["started_at"],
        completed_at=job["completed_at"],
        processing_time_ms=job["processing_time_ms"],
        error_message=job["error_message"],
        images=images,
        selected_products=selected_products,
    )


@router.get("/{job_id}/events")
async def get_job_events(job_id: str):
    """
    Subscribe to real-time job events via Server-Sent Events (SSE).

    Events are streamed as they occur during job processing.
    Connection closes automatically when job completes or fails.
    """
    db = get_database_service()

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await db.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        """Generate SSE events."""
        last_event_id = 0

        while True:
            # Check job status
            job = await db.get_job(job_uuid)
            if not job:
                break

            # Get new events
            events = await db.get_job_events(job_uuid, after_id=last_event_id)

            for event in events:
                last_event_id = event["id"]
                yield {
                    "event": event["event_type"],
                    "id": str(event["id"]),
                    "data": {
                        "job_id": job_id,
                        "event_type": event["event_type"],
                        "event_data": event["event_data"],
                        "created_at": event["created_at"],
                    },
                }

            # Check if job is complete
            if job["status"] in ("completed", "failed"):
                # Send final status event
                yield {
                    "event": "close",
                    "data": {
                        "job_id": job_id,
                        "status": job["status"],
                        "message": "Job processing finished",
                    },
                }
                break

            # Wait before next poll
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
