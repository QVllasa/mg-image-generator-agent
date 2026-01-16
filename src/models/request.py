"""
Request Models

Pydantic models for API requests.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ImageInput(BaseModel):
    """Ein einzelnes Eingabebild."""

    data: str = Field(
        ...,
        description="Base64-kodierte Bilddaten",
        min_length=100,  # Mindestens ein kleines Bild
    )
    filename: str = Field(
        ...,
        description="Dateiname des Bildes",
        examples=["room1.jpg", "living_room.png"],
    )

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validiert den Dateinamen."""
        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        ext = "." + v.rsplit(".", 1)[-1].lower() if "." in v else ""
        if ext not in allowed_extensions:
            raise ValueError(
                f"Ungültige Dateierweiterung. Erlaubt: {', '.join(allowed_extensions)}"
            )
        return v


class ProductImage(BaseModel):
    """Ein Produktbild für Multi-Reference Staging."""

    data: str = Field(
        ...,
        description="Base64-kodierte Produktbild-Daten",
        min_length=100,
    )
    name: str = Field(
        ...,
        description="Produktname (wird im Prompt verwendet)",
        examples=["red leather sofa", "wooden coffee table", "floor lamp"],
    )
    ean: Optional[str] = Field(
        default=None,
        description="EAN des Produkts (optional, für Tracking)",
    )


class BudgetRange(BaseModel):
    """Preisbereich für MeiliSearch-Produktsuche."""

    min: float = Field(
        default=0,
        ge=0,
        description="Minimaler Preis in EUR",
    )
    max: float = Field(
        default=10000,
        ge=0,
        description="Maximaler Preis in EUR",
    )


class StageRoomRequest(BaseModel):
    """Request für Room Staging API."""

    images: List[ImageInput] = Field(
        ...,
        description="Liste der zu bearbeitenden Bilder",
        min_length=1,
        max_length=5,
    )
    style: str = Field(
        default="modern",
        description="Einrichtungsstil",
        examples=["modern", "scandinavian", "industrial", "classic", "minimalist"],
    )
    furniture_types: Optional[List[str]] = Field(
        default=None,
        description="Gewünschte Möbeltypen (nur wenn keine product_images, None = auto)",
        examples=[["sofa", "table", "lamp"], ["bed", "nightstand", "wardrobe"]],
    )
    product_images: Optional[List[ProductImage]] = Field(
        default=None,
        description="Produktbilder für Multi-Reference Staging (überschreibt furniture_types)",
        max_length=9,  # FLUX.2 unterstützt max 9 Referenzbilder
    )
    room_type: Optional[str] = Field(
        default=None,
        description="Raumtyp (None = automatische Erkennung)",
        examples=["living_room", "bedroom", "office", "dining_room"],
    )

    # ═══ MEILISEARCH INTEGRATION ═══
    color_preferences: Optional[List[str]] = Field(
        default=None,
        description=(
            "Bevorzugte Farben für MeiliSearch-Produktsuche. "
            "Wenn gesetzt UND keine product_images: Agent wählt selbst passende Produkte."
        ),
        examples=[["weiss", "grau", "holz"], ["schwarz", "gold"], ["blau", "beige"]],
    )
    budget_range: Optional[BudgetRange] = Field(
        default=None,
        description="Preisbereich für MeiliSearch-Produktsuche",
    )
    products_per_type: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Anzahl Produktkandidaten pro Möbeltyp aus MeiliSearch",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "images": [
                        {
                            "data": "iVBORw0KGgoAAAANSUhEUg...",
                            "filename": "empty_room.jpg",
                        }
                    ],
                    "style": "modern",
                    "furniture_types": ["sofa", "coffee_table", "floor_lamp"],
                }
            ]
        }
    }
