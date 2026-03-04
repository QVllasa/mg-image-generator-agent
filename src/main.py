"""
Room Stager API

FastAPI Entry Point für den Room Staging Service.
"""

import base64
import time
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.agent.graph import run_staging
from src.config import get_settings
from src.models.request import StageRoomRequest, SuggestStageRoomRequest, CustomStageRoomRequest
from src.models.response import StageRoomResponse, StagedImage, ProductHotspot, SelectedProduct
from src.services.marker_service import draw_product_markers
from src.services.meilisearch_service import get_meilisearch_service
from src.services.database_service import get_database_service
from src.services.storage_service import get_storage_service
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

    # Initialize Database
    try:
        db = get_database_service()
        await db.connect()
        logger.info("Database verbunden")
    except Exception as e:
        logger.warning(f"Database nicht verfügbar: {e}")
        # Don't fail startup - database is optional for legacy sync endpoints

    # Initialize Storage
    try:
        storage = get_storage_service()
        storage.ensure_bucket()
        logger.info("Storage initialisiert")
    except Exception as e:
        logger.warning(f"Storage nicht verfügbar: {e}")
        # Don't fail startup - storage is optional for legacy sync endpoints

    yield

    # Shutdown
    logger.info("Room Stager API wird beendet...")

    # Disconnect database
    try:
        db = get_database_service()
        await db.disconnect()
        logger.info("Database getrennt")
    except Exception:
        pass


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

# Register Job API Router (async job processing)
from src.api.jobs import router as jobs_router
app.include_router(jobs_router)


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
                    images=p.get("images", []),
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


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def download_image_as_base64(url: str, timeout: float = 30.0) -> Optional[str]:
    """
    Downloads an image from a URL and returns it as base64.

    Args:
        url: The URL to download the image from
        timeout: Request timeout in seconds

    Returns:
        Base64-encoded image data, or None if download failed
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to download image from {url}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# NEW API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/api/v1/stage-room/suggest", response_model=StageRoomResponse)
async def stage_room_suggest(request: SuggestStageRoomRequest) -> StageRoomResponse:
    """
    AI-suggested room staging.

    Der Agent analysiert den Raum und wählt automatisch passende Produkte
    aus MeiliSearch basierend auf Stil, Farben und Budget aus.

    Returns:
        - staged images with furniture
        - selected_products (with full images array)
        - product_hotspots (with product_ids for linking)
    """
    start_time = time.time()

    logger.info(
        "Neuer Suggest-Staging-Request",
        image_count=len(request.images),
        style=request.style,
        color_preferences=request.color_preferences,
        budget_range=request.budget_range.model_dump() if request.budget_range else None,
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

        # Führe Staging aus mit MeiliSearch-Modus
        result = await run_staging(
            images=images,
            style=request.style,
            furniture_types=None,  # Agent bestimmt selbst
            product_images=None,   # Keine vorgegebenen Bilder
            room_type=request.room_type,
            # MeiliSearch Integration - AKTIV
            color_preferences=request.color_preferences,
            budget_range=budget_range,
            products_per_type=request.products_per_type,
        )

        # Build response using shared helper
        return _build_staging_response(result, start_time)

    except Exception as e:
        logger.error(f"Suggest-Staging-Fehler: {e}", exc_info=True)
        total_time_ms = int((time.time() - start_time) * 1000)
        return StageRoomResponse(
            success=False,
            results=[],
            total_processing_time_ms=total_time_ms,
            error=str(e),
            correlation_id=get_correlation_id(),
        )


@app.post("/api/v1/stage-room/custom", response_model=StageRoomResponse)
async def stage_room_custom(request: CustomStageRoomRequest) -> StageRoomResponse:
    """
    User-selected product staging.

    Der Benutzer gibt explizit an, welche Produkte platziert werden sollen -
    entweder per Produktbild (Base64) oder per MeiliSearch-ID.

    Produkte mit product_id werden aus MeiliSearch geholt, das Bild wird heruntergeladen.
    Produkte mit image_data werden direkt verwendet.

    Returns:
        - staged images with the specified furniture
        - product_hotspots (with product_ids for linking)
    """
    start_time = time.time()

    logger.info(
        "Neuer Custom-Staging-Request",
        image_count=len(request.images),
        style=request.style,
        products_count=len(request.products),
    )

    try:
        # Konvertiere Request zu internem Format
        images = [
            {"data": img.data, "filename": img.filename}
            for img in request.images
        ]

        # Verarbeite Produkte - entweder von MeiliSearch oder direkt
        product_images = []
        meilisearch = get_meilisearch_service()

        for product_ref in request.products:
            if product_ref.product_id:
                # Produkt aus MeiliSearch holen
                logger.info(f"Lade Produkt aus MeiliSearch: {product_ref.product_id}")
                meili_product = await meilisearch.get_product_by_id(product_ref.product_id)

                if meili_product:
                    # Download image
                    image_base64 = await download_image_as_base64(meili_product.image_url)

                    if image_base64:
                        product_images.append({
                            "name": product_ref.name or meili_product.name,
                            "base64": image_base64,
                            "ean": meili_product.ean,
                            "product_id": meili_product.product_id,
                        })
                        logger.info(
                            f"Produkt geladen: {meili_product.name}",
                            product_id=meili_product.product_id,
                        )
                    else:
                        logger.warning(f"Produktbild konnte nicht geladen werden: {meili_product.image_url}")
                else:
                    logger.warning(f"Produkt nicht in MeiliSearch gefunden: {product_ref.product_id}")

            elif product_ref.image_data:
                # Direktes Bild verwenden
                product_images.append({
                    "name": product_ref.name,
                    "base64": product_ref.image_data,
                    "ean": product_ref.ean or "",
                    "product_id": "",  # Keine ID bei direktem Upload
                })
                logger.info(f"Direktes Produktbild verwendet: {product_ref.name}")

        if not product_images:
            raise HTTPException(
                status_code=400,
                detail="Keine gültigen Produktbilder gefunden. Bitte Produkte mit image_data oder gültiger product_id angeben.",
            )

        logger.info(f"Verarbeite {len(product_images)} Produktbilder")

        # Führe Staging aus im Multi-Reference-Modus
        result = await run_staging(
            images=images,
            style=request.style,
            furniture_types=None,
            product_images=product_images,  # Explizite Produktbilder
            room_type=request.room_type,
            # Kein MeiliSearch - Produkte sind schon festgelegt
            color_preferences=None,
            budget_range=None,
            products_per_type=0,
        )

        # Build response using shared helper
        return _build_staging_response(result, start_time)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom-Staging-Fehler: {e}", exc_info=True)
        total_time_ms = int((time.time() - start_time) * 1000)
        return StageRoomResponse(
            success=False,
            results=[],
            total_processing_time_ms=total_time_ms,
            error=str(e),
            correlation_id=get_correlation_id(),
        )


def _build_staging_response(result: dict, start_time: float) -> StageRoomResponse:
    """
    Shared helper to build StageRoomResponse from agent result.

    Args:
        result: Result dict from run_staging()
        start_time: Request start time for calculating total_processing_time_ms

    Returns:
        StageRoomResponse
    """
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
                images=p.get("images", []),
                selection_reason=p.get("selection_reason", ""),
            )
            for p in result["selected_products"]
        ]

    return StageRoomResponse(
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
