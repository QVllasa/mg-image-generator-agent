"""
Request Models

Pydantic models for API requests.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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


# ═══════════════════════════════════════════════════════════════════════════════
# NEW API ENDPOINTS - Request Models
# ═══════════════════════════════════════════════════════════════════════════════


class SuggestStageRoomRequest(BaseModel):
    """
    Request für AI-gesteuerte Raumgestaltung.

    Der Agent analysiert den Raum und wählt automatisch passende Produkte
    aus MeiliSearch basierend auf Stil, Farben und Budget.
    """

    images: List[ImageInput] = Field(
        ...,
        description="Liste der zu bearbeitenden Raumbilder",
        min_length=1,
        max_length=5,
    )
    style: str = Field(
        default="modern",
        description="Einrichtungsstil",
        examples=["modern", "skandinavisch", "industrial", "klassisch", "minimalist"],
    )
    color_preferences: List[str] = Field(
        ...,
        description="Bevorzugte Farben für die Produktauswahl",
        min_length=1,
        examples=[["weiss", "grau", "holz"], ["schwarz", "gold"], ["blau", "beige"]],
    )
    budget_range: Optional[BudgetRange] = Field(
        default=None,
        description="Optionaler Preisbereich für die Produktsuche",
    )
    products_per_type: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Anzahl Produktkandidaten pro Möbeltyp aus MeiliSearch",
    )
    room_type: Optional[str] = Field(
        default=None,
        description="Raumtyp (None = automatische Erkennung)",
        examples=["living_room", "bedroom", "office", "dining_room"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "images": [{"data": "base64...", "filename": "room.jpg"}],
                    "style": "skandinavisch",
                    "color_preferences": ["weiss", "grau", "holz"],
                    "budget_range": {"min": 100, "max": 2000},
                    "products_per_type": 5,
                }
            ]
        }
    }


class ProductReference(BaseModel):
    """
    Referenz auf ein Produkt - entweder per Bild ODER MeiliSearch-ID.

    Mindestens eines von product_id oder image_data muss angegeben werden.
    """

    product_id: Optional[str] = Field(
        default=None,
        description="MeiliSearch Produkt-ID (wenn bekannt)",
    )
    image_data: Optional[str] = Field(
        default=None,
        description="Base64-kodiertes Produktbild (Alternative zur product_id)",
    )
    name: str = Field(
        ...,
        description="Produktname (wird im Generierungsprompt verwendet)",
        examples=["Red Leather Sofa", "Oak Coffee Table", "Modern Floor Lamp"],
    )
    ean: Optional[str] = Field(
        default=None,
        description="EAN des Produkts (optional, für Tracking)",
    )

    @model_validator(mode="after")
    def validate_product_reference(self) -> "ProductReference":
        """Stellt sicher, dass entweder product_id oder image_data angegeben ist."""
        if not self.product_id and not self.image_data:
            raise ValueError(
                "Entweder product_id oder image_data muss angegeben werden"
            )
        return self


class CustomStageRoomRequest(BaseModel):
    """
    Request für benutzerdefinierte Raumgestaltung.

    Der Benutzer gibt explizit an, welche Produkte platziert werden sollen -
    entweder per Produktbild (Base64) oder per MeiliSearch-ID.
    """

    images: List[ImageInput] = Field(
        ...,
        description="Liste der zu bearbeitenden Raumbilder",
        min_length=1,
        max_length=5,
    )
    style: str = Field(
        default="modern",
        description="Einrichtungsstil",
        examples=["modern", "skandinavisch", "industrial", "klassisch", "minimalist"],
    )
    products: List[ProductReference] = Field(
        ...,
        description="Liste der zu platzierenden Produkte (per Bild oder MeiliSearch-ID)",
        min_length=1,
        max_length=9,  # FLUX.2 unterstützt max 9 Referenzbilder
    )
    room_type: Optional[str] = Field(
        default=None,
        description="Raumtyp (None = automatische Erkennung)",
        examples=["living_room", "bedroom", "office", "dining_room"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "images": [{"data": "base64...", "filename": "room.jpg"}],
                    "style": "modern",
                    "products": [
                        {"name": "Red Sofa", "image_data": "base64..."},
                        {"name": "Oak Table", "product_id": "3000173715"},
                    ],
                }
            ]
        }
    }
