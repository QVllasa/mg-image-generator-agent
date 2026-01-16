"""
Response Models

Pydantic models for API responses.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ProductHotspot(BaseModel):
    """
    Position eines Produkts im Bild für Frontend-Hotspots/Tooltips.

    Alle Koordinaten sind in PROZENT (0-100) für Responsivität.
    Das Frontend kann diese Werte direkt für CSS-Positionierung verwenden:
    - left: x%, top: y% für absolute Positionierung
    - hotspot_x/y für optimale Tooltip-Platzierung
    """

    product_name: str = Field(
        ...,
        description="Name des erkannten Produkts",
    )
    product_id: Optional[str] = Field(
        default=None,
        description="Produkt-ID für Frontend-Verknüpfung (z.B. MeiliSearch ID)",
    )
    x: float = Field(
        ...,
        ge=0,
        le=100,
        description="X-Position der Bounding Box in Prozent (von links)",
    )
    y: float = Field(
        ...,
        ge=0,
        le=100,
        description="Y-Position der Bounding Box in Prozent (von oben)",
    )
    width: float = Field(
        ...,
        ge=0,
        le=100,
        description="Breite der Bounding Box in Prozent",
    )
    height: float = Field(
        ...,
        ge=0,
        le=100,
        description="Höhe der Bounding Box in Prozent",
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Erkennungssicherheit (0-1)",
    )
    hotspot_x: float = Field(
        ...,
        ge=0,
        le=100,
        description="Optimaler Hotspot X für Tooltip (meist Mitte)",
    )
    hotspot_y: float = Field(
        ...,
        ge=0,
        le=100,
        description="Optimaler Hotspot Y für Tooltip (meist Mitte)",
    )


class SelectedProduct(BaseModel):
    """Ein vom Agent ausgewähltes Produkt aus MeiliSearch."""

    product_id: str = Field(
        ...,
        description="MeiliSearch Produkt-ID",
    )
    ean: str = Field(
        ...,
        description="EAN des Produkts",
    )
    name: str = Field(
        ...,
        description="Produktname",
    )
    furniture_type: str = Field(
        ...,
        description="Möbeltyp (sofa, couchtisch, stehlampe, etc.)",
    )
    price: float = Field(
        ...,
        ge=0,
        description="Preis in EUR",
    )
    image_url: str = Field(
        ...,
        description="URL zum Hauptproduktbild",
    )
    images: List[str] = Field(
        default_factory=list,
        description="Alle Produktbild-URLs aus MeiliSearch",
    )
    selection_reason: str = Field(
        ...,
        description="Begründung warum dieses Produkt ausgewählt wurde",
    )


class StagedImage(BaseModel):
    """Ein einzelnes bearbeitetes Bild."""

    original_filename: str = Field(
        ...,
        description="Ursprünglicher Dateiname",
    )
    staged_image: str = Field(
        ...,
        description="Base64-kodiertes Ergebnisbild (sauber, ohne Marker)",
    )
    staged_image_with_markers: Optional[str] = Field(
        default=None,
        description="Base64-kodiertes Bild MIT sichtbaren Produkt-Markern (für Debugging/Entwicklung)",
    )
    furniture_added: List[str] = Field(
        default_factory=list,
        description="Liste der hinzugefügten Möbel",
    )
    product_hotspots: List[ProductHotspot] = Field(
        default_factory=list,
        description="Positionen der Produkte im Bild für Frontend-Hotspots (Koordinaten in %)",
    )
    room_type_detected: Optional[str] = Field(
        default=None,
        description="Erkannter Raumtyp",
    )
    processing_time_ms: int = Field(
        ...,
        description="Verarbeitungszeit in Millisekunden",
    )
    retries: int = Field(
        default=0,
        description="Anzahl der Wiederholungsversuche",
    )


class StageRoomResponse(BaseModel):
    """Response der Room Staging API."""

    success: bool = Field(
        ...,
        description="Ob die Verarbeitung erfolgreich war",
    )
    results: List[StagedImage] = Field(
        default_factory=list,
        description="Liste der bearbeiteten Bilder",
    )
    total_processing_time_ms: int = Field(
        ...,
        description="Gesamte Verarbeitungszeit in Millisekunden",
    )
    error: Optional[str] = Field(
        default=None,
        description="Fehlermeldung bei Misserfolg",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Request-ID für Tracking",
    )

    # ═══ MEILISEARCH INTEGRATION ═══
    session_id: Optional[str] = Field(
        default=None,
        description="Session-ID für Output-Ordner (nur bei MeiliSearch-Modus)",
    )
    selected_products: Optional[List[SelectedProduct]] = Field(
        default=None,
        description="Vom Agent ausgewählte Produkte (nur bei MeiliSearch-Modus)",
    )
    output_directory: Optional[str] = Field(
        default=None,
        description="Pfad zum Output-Ordner mit gespeicherten Ergebnissen",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "results": [
                        {
                            "original_filename": "empty_room.jpg",
                            "staged_image": "iVBORw0KGgoAAAANSUhEUg...",
                            "furniture_added": ["sofa", "coffee_table", "floor_lamp"],
                            "room_type_detected": "living_room",
                            "processing_time_ms": 4500,
                            "retries": 0,
                        }
                    ],
                    "total_processing_time_ms": 4500,
                    "error": None,
                    "correlation_id": "rs-abc12345",
                }
            ]
        }
    }
