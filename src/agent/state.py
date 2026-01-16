"""
Agent State Definitions

Defines the state for the LangGraph Room Stager Agent.
"""

from typing import TypedDict, List, Dict, Any, Optional


class ProductPosition(TypedDict):
    """Position eines Produkts im Bild für Frontend-Hotspots."""
    product_name: str
    product_id: Optional[str]
    x: float  # Prozent von links (0-100)
    y: float  # Prozent von oben (0-100)
    width: float  # Breite in Prozent
    height: float  # Höhe in Prozent
    confidence: float  # Erkennungssicherheit (0-1)
    hotspot_x: float  # Idealer Hotspot X
    hotspot_y: float  # Idealer Hotspot Y


class ProductCandidate(TypedDict):
    """Ein Produktkandidat aus MeiliSearch."""
    product_id: str
    ean: str
    name: str
    furniture_type: str
    category: str
    price: float
    image_url: str
    thumbnail: str
    images: List[str]  # All product image URLs from MeiliSearch
    style: List[str]
    color: List[str]
    dimensions: Dict[str, float]
    average_rating: Optional[float]
    brand_name: Optional[str]


class SelectedProduct(TypedDict):
    """Ein vom Agent ausgewähltes Produkt."""
    product_id: str
    ean: str
    name: str
    furniture_type: str
    price: float
    image_url: str
    images: List[str]  # All product image URLs from MeiliSearch
    image_base64: Optional[str]  # Heruntergeladen für FLUX
    selection_reason: str


class ProductFilter(TypedDict):
    """Ein generierter MeiliSearch-Filter für einen Möbeltyp."""
    furniture_type: str
    filter: str  # MeiliSearch filter expression


class BudgetRange(TypedDict):
    """Preisbereich für Produktsuche."""
    min: float
    max: float


class ImageData(TypedDict):
    """Daten für ein einzelnes Bild im State."""
    filename: str
    original_base64: str
    staged_base64: Optional[str]
    room_analysis: Optional[Dict[str, Any]]
    staging_prompt: Optional[Dict[str, Any]]  # Kreativer Prompt von Qwen3-VL
    product_positions: Optional[List[ProductPosition]]  # Erkannte Produktpositionen
    furniture_added: List[str]
    processing_time_ms: int
    retries: int
    is_valid: bool
    error: Optional[str]


class RoomAnalysis(TypedDict):
    """Ergebnis der Raumanalyse durch Qwen3-VL."""
    room_type: str  # living_room, bedroom, office, etc.
    empty_areas: List[str]  # Beschreibungen der leeren Bereiche
    existing_furniture: List[str]  # Bereits vorhandene Möbel
    suggested_furniture: List[str]  # Vorgeschlagene Möbel
    lighting: str  # Lichtverhältnisse
    style_hints: List[str]  # Erkannte Stilelemente


class ValidationResult(TypedDict):
    """Ergebnis der Staging-Validierung."""
    is_valid: bool
    confidence: float  # 0.0 - 1.0
    issues: List[str]
    suggestions: List[str]


class StagingState(TypedDict):
    """
    State für den Room Stager Agent.

    Enthält alle Daten für die Verarbeitung eines Staging-Requests.
    """

    # ═══ REQUEST DATA ═══
    style: str  # Gewünschter Einrichtungsstil
    furniture_types: Optional[List[str]]  # Gewünschte Möbeltypen (nur ohne product_images)
    product_images: Optional[List[Dict[str, str]]]  # Produktbilder für Multi-Reference
    room_type_override: Optional[str]  # Manueller Raumtyp

    # ═══ MEILISEARCH INTEGRATION (NEU) ═══
    color_preferences: Optional[List[str]]  # Bevorzugte Farben
    budget_range: Optional[BudgetRange]  # Preisbereich
    products_per_type: int  # Anzahl Kandidaten pro Möbeltyp
    product_filters: Optional[List[ProductFilter]]  # Generierte MeiliSearch-Filter
    product_candidates: Optional[Dict[str, List[ProductCandidate]]]  # Kandidaten pro Typ
    selected_products: Optional[List[SelectedProduct]]  # Finale Auswahl
    session_id: str  # Session-ID für Output-Ordner

    # ═══ IMAGE DATA ═══
    images: List[ImageData]  # Alle Bilder mit Status
    current_image_index: int  # Aktuell bearbeitetes Bild

    # ═══ WORKFLOW STATE ═══
    workflow_stage: str  # receive, analyze, build_filter, fetch, select, generate, validate, finalize
    max_retries: int  # Max Wiederholungen pro Bild
    total_retries: int  # Gesamte Wiederholungen

    # ═══ RESULTS ═══
    completed_count: int  # Erfolgreich bearbeitete Bilder
    failed_count: int  # Fehlgeschlagene Bilder
    output_directory: Optional[str]  # Pfad zum Output-Ordner

    # ═══ META ═══
    correlation_id: str
    start_time: float
    error: Optional[str]


def create_initial_state(
    images: List[Dict[str, str]],
    style: str = "modern",
    furniture_types: Optional[List[str]] = None,
    product_images: Optional[List[Dict[str, str]]] = None,
    room_type: Optional[str] = None,
    max_retries: int = 2,
    correlation_id: str = "",
    # Neue MeiliSearch-Parameter
    color_preferences: Optional[List[str]] = None,
    budget_range: Optional[Dict[str, float]] = None,
    products_per_type: int = 5,
) -> StagingState:
    """
    Erstellt den initialen State für einen Staging-Request.

    Args:
        images: Liste von {"data": base64, "filename": str}
        style: Einrichtungsstil
        furniture_types: Gewünschte Möbeltypen (nur ohne product_images)
        product_images: Produktbilder für Multi-Reference [{"name": str, "data": str}]
        room_type: Manueller Raumtyp
        max_retries: Max Wiederholungen
        correlation_id: Request-ID
        color_preferences: Bevorzugte Farben für MeiliSearch
        budget_range: Preisbereich {"min": float, "max": float}
        products_per_type: Anzahl Produktkandidaten pro Möbeltyp

    Returns:
        Initialer StagingState
    """
    import time
    import uuid

    # Konvertiere Eingabebilder zu ImageData
    image_data_list: List[ImageData] = []
    for img in images:
        image_data_list.append(
            ImageData(
                filename=img["filename"],
                original_base64=img["data"],
                staged_base64=None,
                room_analysis=None,
                staging_prompt=None,
                product_positions=None,
                furniture_added=[],
                processing_time_ms=0,
                retries=0,
                is_valid=True,
                error=None,
            )
        )

    # Generiere Session-ID für Output-Ordner
    session_id = f"stg-{uuid.uuid4().hex[:8]}"

    # Konvertiere budget_range zu BudgetRange TypedDict
    typed_budget_range: Optional[BudgetRange] = None
    if budget_range:
        typed_budget_range = BudgetRange(
            min=budget_range.get("min", 0),
            max=budget_range.get("max", 0),
        )

    return StagingState(
        # Request
        style=style,
        furniture_types=furniture_types,
        product_images=product_images,
        room_type_override=room_type,

        # MeiliSearch Integration
        color_preferences=color_preferences,
        budget_range=typed_budget_range,
        products_per_type=products_per_type,
        product_filters=None,
        product_candidates=None,
        selected_products=None,
        session_id=session_id,

        # Images
        images=image_data_list,
        current_image_index=0,

        # Workflow
        workflow_stage="receive",
        max_retries=max_retries,
        total_retries=0,

        # Results
        completed_count=0,
        failed_count=0,
        output_directory=None,

        # Meta
        correlation_id=correlation_id,
        start_time=time.time(),
        error=None,
    )
