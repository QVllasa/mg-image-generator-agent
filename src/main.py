"""
Room Stager API

FastAPI Entry Point für den Room Staging Service.
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.agent.graph import run_staging
from src.config import get_settings
from src.models.request import StageRoomRequest
from src.models.response import StageRoomResponse, StagedImage, ProductHotspot, SelectedProduct
from src.services.marker_service import draw_product_markers
from src.utils.logging import setup_logging, get_logger, get_correlation_id

# Setup Logging beim Import
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Room Stager API startet...")

    # Startup: Validiere Konfiguration
    try:
        config = get_settings()
        logger.info(
            "Konfiguration geladen",
            vllm_endpoint=config.vllm.endpoint,
            fal_model=config.fal.model,
        )
    except Exception as e:
        logger.error(f"Konfigurationsfehler: {e}")
        raise

    yield

    # Shutdown
    logger.info("Room Stager API wird beendet...")


# FastAPI App
app = FastAPI(
    title="Room Stager API",
    description="AI-powered virtual room staging with furniture",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health Check Endpoint."""
    return {
        "status": "healthy",
        "service": "room-stager",
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """Root Endpoint mit API Info."""
    return {
        "service": "Room Stager API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/api/v1/stage-room", response_model=StageRoomResponse)
async def stage_room(request: StageRoomRequest) -> StageRoomResponse:
    """
    Stage a room with virtual furniture.

    Empfängt Bilder von leeren Räumen und fügt virtuelle Möbel hinzu.
    """
    start_time = time.time()

    # Konvertiere Produktbilder zu internem Format
    product_images = None
    if request.product_images:
        product_images = [
            {"name": p.name, "base64": p.data, "ean": p.ean}
            for p in request.product_images
        ]

    # Bestimme Modus
    mode = "meilisearch" if (request.color_preferences and not product_images) else (
        "multi-reference" if product_images else "text-prompt"
    )

    logger.info(
        "Neuer Staging-Request",
        image_count=len(request.images),
        style=request.style,
        mode=mode,
        product_images_count=len(product_images) if product_images else 0,
        furniture_types=request.furniture_types if not product_images else None,
        color_preferences=request.color_preferences,
    )

    try:
        # Konvertiere Request zu internem Format
        images = [
            {"data": img.data, "filename": img.filename}
            for img in request.images
        ]

        # Konvertiere budget_range
        budget_range = None
        if request.budget_range:
            budget_range = {"min": request.budget_range.min, "max": request.budget_range.max}

        # Führe Staging aus
        result = await run_staging(
            images=images,
            style=request.style,
            furniture_types=request.furniture_types,
            product_images=product_images,
            room_type=request.room_type,
            # MeiliSearch Integration
            color_preferences=request.color_preferences,
            budget_range=budget_range,
            products_per_type=request.products_per_type,
        )

        # Erstelle Response
        staged_images = []
        for img in result["images"]:
            if img["staged_base64"]:
                # Konvertiere Produktpositionen zu ProductHotspot
                hotspots = []
                marker_image = None

                if img.get("product_positions"):
                    for pos in img["product_positions"]:
                        hotspots.append(
                            ProductHotspot(
                                product_name=pos["product_name"],
                                product_id=pos.get("product_id"),
                                x=pos["x"],
                                y=pos["y"],
                                width=pos["width"],
                                height=pos["height"],
                                confidence=pos["confidence"],
                                hotspot_x=pos["hotspot_x"],
                                hotspot_y=pos["hotspot_y"],
                            )
                        )

                    # Erstelle Marker-Bild für Debugging
                    try:
                        marker_image = draw_product_markers(
                            image_base64=img["staged_base64"],
                            product_positions=img["product_positions"],
                        )
                        logger.info("Marker-Bild erstellt", hotspot_count=len(hotspots))
                    except Exception as marker_error:
                        logger.warning(f"Marker-Bild konnte nicht erstellt werden: {marker_error}")

                staged_images.append(
                    StagedImage(
                        original_filename=img["filename"],
                        staged_image=img["staged_base64"],
                        staged_image_with_markers=marker_image,
                        furniture_added=img["furniture_added"],
                        product_hotspots=hotspots,
                        room_type_detected=img["room_analysis"]["room_type"] if img["room_analysis"] else None,
                        processing_time_ms=img["processing_time_ms"],
                        retries=img["retries"],
                    )
                )

        total_time_ms = int((time.time() - start_time) * 1000)

        # Konvertiere selected_products für Response
        selected_products_response = None
        if result.get("selected_products"):
            selected_products_response = [
                SelectedProduct(
                    product_id=p.get("product_id", ""),
                    ean=p.get("ean", ""),
                    name=p.get("name", ""),
                    furniture_type=p.get("furniture_type", ""),
                    price=p.get("price", 0),
                    image_url=p.get("image_url", ""),
                    selection_reason=p.get("selection_reason", ""),
                )
                for p in result["selected_products"]
            ]

        response = StageRoomResponse(
            success=len(staged_images) > 0,
            results=staged_images,
            total_processing_time_ms=total_time_ms,
            error=result.get("error"),
            correlation_id=get_correlation_id(),
            # MeiliSearch Integration
            session_id=result.get("session_id"),
            selected_products=selected_products_response,
            output_directory=result.get("output_directory"),
        )

        logger.info(
            "Staging-Request abgeschlossen",
            success=response.success,
            results_count=len(response.results),
            mode=mode,
            session_id=response.session_id,
            selected_products_count=len(selected_products_response) if selected_products_response else 0,
            total_time_ms=total_time_ms,
        )

        return response

    except Exception as e:
        logger.error(f"Staging-Fehler: {e}", exc_info=True)

        total_time_ms = int((time.time() - start_time) * 1000)

        return StageRoomResponse(
            success=False,
            results=[],
            total_processing_time_ms=total_time_ms,
            error=str(e),
            correlation_id=get_correlation_id(),
        )


# Entry Point für direkte Ausführung
if __name__ == "__main__":
    import uvicorn

    config = get_settings()
    uvicorn.run(
        "src.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
        log_level=config.server.log_level.lower(),
    )
