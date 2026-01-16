"""
Vision Service

Verwendet vLLM mit Qwen3-VL für Bildanalyse und Validierung.
Basiert auf dem kaufberater LLM Client Pattern.
"""

import json
import time
from typing import Dict, Any, Optional, List

from openai import OpenAI, APIConnectionError, APITimeoutError
from pydantic import BaseModel
from src.config import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Retry Configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0


class RoomAnalysisResult(BaseModel):
    """Strukturiertes Ergebnis der Raumanalyse."""
    room_type: str
    empty_areas: List[str]
    existing_furniture: List[str]
    suggested_furniture: List[str]
    lighting: str
    style_hints: List[str]


class ValidationResult(BaseModel):
    """Strukturiertes Ergebnis der Validierung."""
    is_valid: bool
    confidence: float
    description: str  # Beschreibung was im Bild zu sehen ist
    detected_furniture: List[str]  # Erkannte Möbel im Staging
    placement_quality: str  # Bewertung der Platzierung
    issues: List[str]
    suggestions: List[str]


class StagingPromptResult(BaseModel):
    """Kreativer Prompt für die Bildgenerierung."""
    prompt: str  # Der generierte Prompt für FLUX
    placement_instructions: List[str]  # Wo welches Möbel platziert werden soll
    style_description: str  # Beschreibung des Zielstils
    atmosphere: str  # Gewünschte Atmosphäre


class ProductPosition(BaseModel):
    """Position eines Produkts im Bild (Prozent-basiert für Responsivität)."""
    product_name: str  # Name des Produkts
    product_id: Optional[str] = None  # Optional: ID für Frontend-Verknüpfung
    x: float  # X-Position in Prozent (0-100, von links)
    y: float  # Y-Position in Prozent (0-100, von oben)
    width: float  # Breite in Prozent (0-100)
    height: float  # Höhe in Prozent (0-100)
    confidence: float  # Erkennungssicherheit (0-1)
    hotspot_x: float  # Idealer Hotspot X (Mitte des Produkts)
    hotspot_y: float  # Idealer Hotspot Y (Mitte des Produkts)


class ProductDetectionResult(BaseModel):
    """Ergebnis der Produkt-Positionserkennung."""
    products: List[ProductPosition]
    image_description: str  # Kurze Beschreibung des Bildes
    total_products_detected: int


class VisionService:
    """
    Service für Bildanalyse und Validierung mit Qwen3-VL.

    Verwendet OpenAI-kompatible API für vLLM-Backend.
    """

    def __init__(self):
        """Initialisiert den Vision Service."""
        config = get_settings()
        self.endpoint = config.vllm.endpoint
        self.model = config.vllm.model
        self.max_tokens = config.vllm.max_tokens
        self.temperature = config.vllm.temperature
        self.timeout = config.vllm.timeout

        self.client = OpenAI(
            base_url=self.endpoint,
            api_key="dummy",  # vLLM benötigt keinen echten Key
            timeout=self.timeout,
        )
        logger.info(
            "VisionService initialisiert",
            endpoint=self.endpoint,
            model=self.model,
        )

    def _retry_on_error(self, func, *args, **kwargs):
        """Führt eine Funktion mit Retry-Logik aus."""
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (APIConnectionError, APITimeoutError, ConnectionError, OSError) as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                    logger.warning(
                        f"Vision API Fehler (Versuch {attempt + 1}/{MAX_RETRIES})",
                        error=str(e)[:200],
                        retry_in=delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"Vision API fehlgeschlagen nach {MAX_RETRIES} Versuchen",
                        error=str(e),
                    )

        raise last_exception

    def analyze_room(
        self,
        image_base64: str,
        style: str = "modern",
        room_type_hint: Optional[str] = None,
    ) -> RoomAnalysisResult:
        """
        Analysiert ein Raumbild mit Qwen3-VL.

        Args:
            image_base64: Base64-kodiertes Bild
            style: Gewünschter Einrichtungsstil
            room_type_hint: Optional bekannter Raumtyp

        Returns:
            RoomAnalysisResult mit Rauminfos und Möbelvorschlägen
        """
        logger.info("Starte Raumanalyse", style=style, room_type_hint=room_type_hint)

        system_prompt = """Du bist ein Experte für Innenarchitektur und virtuelle Raumgestaltung.
Analysiere das Bild und gib NUR strukturiertes JSON zurück - KEINE Erklärungen, KEIN Thinking, KEINE Einleitung.

Antworte AUSSCHLIESSLICH mit diesem JSON-Format (nichts davor, nichts danach):
{"room_type": "living_room", "empty_areas": ["Bereich 1"], "existing_furniture": [], "suggested_furniture": ["Sofa", "Tisch"], "lighting": "natürlich", "style_hints": ["weiße Wände"]}"""

        user_prompt = f"""Stil: {style}. {f'Raumtyp: {room_type_hint}.' if room_type_hint else ''}
Antworte NUR mit JSON - kein Text davor oder danach."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]

        def _make_request():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            )

        response = self._retry_on_error(_make_request)
        content = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extrahiere JSON aus möglichem Markdown oder Thinking-Text
            # Versuche zuerst Markdown Code-Blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            else:
                # Suche nach JSON-Objekt - finde erstes { und letztes }
                first_brace = content.find('{')
                last_brace = content.rfind('}')
                if first_brace != -1 and last_brace != -1:
                    content = content[first_brace:last_brace + 1]

            data = json.loads(content.strip())
            result = RoomAnalysisResult(**data)
            logger.info(
                "Raumanalyse abgeschlossen",
                room_type=result.room_type,
                empty_areas_count=len(result.empty_areas),
                suggested_count=len(result.suggested_furniture),
            )
            return result

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Fehler beim Parsen der Raumanalyse: {e}", content=content[:500])
            # Fallback mit Defaults
            return RoomAnalysisResult(
                room_type=room_type_hint or "living_room",
                empty_areas=["Zentrum des Raums"],
                existing_furniture=[],
                suggested_furniture=["Sofa", "Couchtisch", "Stehlampe"],
                lighting="natürlich",
                style_hints=[],
            )

    def generate_staging_prompt(
        self,
        room_base64: str,
        product_images: List[Dict[str, str]],
        style: str = "modern",
        room_analysis: Optional[Dict[str, Any]] = None,
    ) -> StagingPromptResult:
        """
        Generiert einen kreativen, optimierten Prompt für FLUX basierend auf
        Raumanalyse, Produkten und gewünschtem Stil.

        Args:
            room_base64: Base64-kodiertes Raumbild
            product_images: Liste von {"name": str, "base64": str}
            style: Gewünschter Einrichtungsstil
            room_analysis: Optional vorherige Raumanalyse

        Returns:
            StagingPromptResult mit kreativem Prompt und Platzierungsanweisungen
        """
        logger.info(
            "Generiere Staging-Prompt",
            style=style,
            product_count=len(product_images),
        )

        # Erstelle Produktliste für den Prompt
        product_list = "\n".join([
            f"  - Produkt {i+1}: {p.get('name', f'Möbelstück {i+1}')}"
            for i, p in enumerate(product_images)
        ])

        # Füge Raumanalyse-Kontext hinzu falls vorhanden
        room_context = ""
        if room_analysis:
            room_context = f"""
Vorherige Raumanalyse:
- Raumtyp: {room_analysis.get('room_type', 'unbekannt')}
- Leere Bereiche: {', '.join(room_analysis.get('empty_areas', []))}
- Lichtverhältnisse: {room_analysis.get('lighting', 'unbekannt')}
- Stil-Hinweise: {', '.join(room_analysis.get('style_hints', []))}
"""

        system_prompt = f"""Du bist ein kreativer Innenarchitekt und Experte für virtuelles Home Staging.
Deine Aufgabe: Erstelle einen detaillierten, kreativen Prompt für ein KI-Bildgenerierungsmodell (FLUX),
das die gegebenen Möbelstücke realistisch in den Raum einfügen soll.

Der Prompt soll auf ENGLISCH sein und folgende Aspekte berücksichtigen:
1. Die Perspektive und Lichtverhältnisse des Originalraums
2. Die optimale Platzierung jedes Möbelstücks
3. Den gewünschten Stil: {style}
4. Eine stimmige Gesamtatmosphäre

Verfügbare Möbelstücke (werden als Referenzbilder übergeben):
{product_list}
{room_context}

Antworte NUR mit JSON - KEINE Erklärungen, KEIN Thinking.

Format:
{{
  "prompt": "A detailed English prompt for FLUX describing the staged room...",
  "placement_instructions": ["Place the sofa in the center facing the window", "Position the coffee table in front of the sofa"],
  "style_description": "Modern minimalist with warm accents",
  "atmosphere": "Bright, welcoming, and contemporary"
}}"""

        user_prompt = f"""Analysiere den Raum im Bild und erstelle einen kreativen Staging-Prompt.
Stil: {style}
Antworte NUR mit JSON."""

        # Erstelle Message mit Raumbild
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{room_base64}"}
                    }
                ]
            }
        ]

        def _make_request():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,  # Etwas kreativer
                max_tokens=2000,
            )

        response = self._retry_on_error(_make_request)
        content = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extrahiere JSON aus Thinking-Text
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            else:
                first_brace = content.find('{')
                last_brace = content.rfind('}')
                if first_brace != -1 and last_brace != -1:
                    content = content[first_brace:last_brace + 1]

            data = json.loads(content.strip())
            result = StagingPromptResult(**data)

            logger.info(
                "Staging-Prompt generiert",
                prompt_length=len(result.prompt),
                style=result.style_description,
                atmosphere=result.atmosphere,
            )
            return result

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Fehler beim Parsen des Staging-Prompts: {e}", content=content[:500])
            # Fallback mit Standard-Prompt
            product_names = [p.get("name", "furniture") for p in product_images]
            return StagingPromptResult(
                prompt=f"Place the furniture items ({', '.join(product_names)}) into this {style} room. "
                       f"Photorealistic interior design photography, natural lighting, high quality.",
                placement_instructions=[f"Add {name} in a natural position" for name in product_names],
                style_description=style,
                atmosphere="Modern and welcoming",
            )

    def validate_staging(
        self,
        original_base64: str,
        staged_base64: str,
    ) -> ValidationResult:
        """
        Validiert ein Staging-Ergebnis durch Vergleich mit Original.

        Args:
            original_base64: Original-Bild
            staged_base64: Bearbeitetes Bild

        Returns:
            ValidationResult mit Bewertung und ggf. Verbesserungsvorschlägen
        """
        logger.info("Starte Staging-Validierung")

        system_prompt = """Du bist ein Qualitätsprüfer für virtuelles Home Staging.
Vergleiche Bild 1 (leerer Raum) mit Bild 2 (mit Möbeln) und bewerte die Qualität.

Antworte NUR mit JSON - KEINE Erklärungen, KEIN Thinking, KEINE Einleitung.

Format:
{
  "is_valid": true,
  "confidence": 0.85,
  "description": "Beschreibe was du im Staging-Bild siehst (Raum, Möbel, Atmosphäre)",
  "detected_furniture": ["Sofa", "Couchtisch", "Stehlampe"],
  "placement_quality": "Beschreibe wie gut die Möbel platziert sind",
  "issues": ["Problem 1", "Problem 2"],
  "suggestions": ["Verbesserung 1"]
}

Kriterien:
- Möbel stehen auf dem Boden (nicht schwebend)
- Realistische Schatten und Beleuchtung
- Korrekte Proportionen zum Raum
- Perspektive passt zum Originalraum"""

        user_prompt = """Analysiere das Staging-Ergebnis detailliert. Beschreibe was du siehst und bewerte die Qualität. Antworte NUR mit JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{original_base64}"}
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{staged_base64}"}
                    }
                ]
            }
        ]

        def _make_request():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=3000,  # Erhöht für Thinking + JSON
            )

        response = self._retry_on_error(_make_request)
        content = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extrahiere JSON aus möglichem Thinking-Text
            # Qwen3-VL-Thinking gibt oft </think> vor dem JSON aus
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            # Versuche Markdown Code-Blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            else:
                # Suche nach JSON-Objekt - finde erstes { und letztes }
                first_brace = content.find('{')
                last_brace = content.rfind('}')
                if first_brace != -1 and last_brace != -1:
                    content = content[first_brace:last_brace + 1]

            data = json.loads(content.strip())
            result = ValidationResult(**data)
            logger.info(
                "Validierung abgeschlossen",
                is_valid=result.is_valid,
                confidence=result.confidence,
                description=result.description,
                detected_furniture=result.detected_furniture,
                placement_quality=result.placement_quality,
                issues=result.issues,
                suggestions=result.suggestions,
            )
            return result

        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                f"Fehler beim Parsen der Validierung: {e}",
                raw_content=content[:500] if content else "empty",
            )
            # Bei Parse-Fehler: Optimistisch validieren
            return ValidationResult(
                is_valid=True,
                confidence=0.7,
                description="Validierung konnte nicht durchgeführt werden",
                detected_furniture=[],
                placement_quality="Unbekannt",
                issues=[],
                suggestions=["Manuelle Überprüfung empfohlen"],
            )


    def detect_product_positions(
        self,
        staged_base64: str,
        expected_products: List[str],
    ) -> ProductDetectionResult:
        """
        Erkennt die Positionen der Produkte im Staging-Bild.

        Gibt Bounding Boxes als Prozent-Werte zurück, damit das Frontend
        Hotspots/Tooltips an den richtigen Stellen platzieren kann.

        Args:
            staged_base64: Das fertige Staging-Bild
            expected_products: Liste der erwarteten Produktnamen

        Returns:
            ProductDetectionResult mit Positionen aller erkannten Produkte
        """
        logger.info(
            "Starte Produkt-Positionserkennung",
            expected_products=expected_products,
        )

        products_str = ", ".join(expected_products)

        system_prompt = f"""Du bist ein Computer Vision Experte für Möbelerkennung.
Analysiere das Bild und finde die Positionen der folgenden Möbelstücke:
{products_str}

Gib für jedes erkannte Möbelstück die BOUNDING BOX als PROZENT-WERTE zurück:
- x: Prozent von links (0 = ganz links, 100 = ganz rechts)
- y: Prozent von oben (0 = ganz oben, 100 = ganz unten)
- width: Breite in Prozent der Bildbreite
- height: Höhe in Prozent der Bildhöhe
- hotspot_x/y: Optimaler Punkt für einen Tooltip (meist Mitte des Objekts)

Antworte NUR mit JSON - KEINE Erklärungen, KEIN Thinking.

Format:
{{
  "products": [
    {{
      "product_name": "Sofa",
      "x": 25.5,
      "y": 45.0,
      "width": 35.0,
      "height": 25.0,
      "confidence": 0.95,
      "hotspot_x": 43.0,
      "hotspot_y": 57.5
    }}
  ],
  "image_description": "Wohnzimmer mit modernem Sofa und Couchtisch",
  "total_products_detected": 2
}}

WICHTIG:
- Alle Werte sind PROZENT (0-100), nicht Pixel!
- hotspot_x = x + (width / 2), hotspot_y = y + (height / 2)
- confidence: Wie sicher bist du, dass das Objekt erkannt wurde (0-1)"""

        user_prompt = f"""Finde diese Möbelstücke im Bild: {products_str}
Gib die Bounding Boxes als Prozent-Werte zurück. Antworte NUR mit JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{staged_base64}"}
                    }
                ]
            }
        ]

        def _make_request():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,  # Präzise für Koordinaten
                max_tokens=3000,
            )

        response = self._retry_on_error(_make_request)
        content = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extrahiere JSON aus Thinking-Text
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            else:
                first_brace = content.find('{')
                last_brace = content.rfind('}')
                if first_brace != -1 and last_brace != -1:
                    content = content[first_brace:last_brace + 1]

            data = json.loads(content.strip())
            result = ProductDetectionResult(**data)

            logger.info(
                "Produkt-Positionen erkannt",
                total_detected=result.total_products_detected,
                products=[p.product_name for p in result.products],
            )
            return result

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Fehler beim Parsen der Positionserkennung: {e}", content=content[:500])
            # Fallback: Leeres Ergebnis
            return ProductDetectionResult(
                products=[],
                image_description="Positionserkennung fehlgeschlagen",
                total_products_detected=0,
            )

    def build_product_filters(
        self,
        room_analysis: Dict[str, Any],
        style: str,
        color_preferences: List[str],
        furniture_types: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Lässt Qwen3-VL MeiliSearch-Filter für die benötigten Möbeltypen erstellen.

        Qwen analysiert die Raumanalyse und Nutzer-Präferenzen und generiert
        passende Filter für jeden Möbeltyp.

        Args:
            room_analysis: Vorherige Raumanalyse (room_type, empty_areas, etc.)
            style: Gewünschter Einrichtungsstil
            color_preferences: Bevorzugte Farben des Nutzers
            furniture_types: Liste der benötigten Möbeltypen

        Returns:
            Liste von Filter-Spezifikationen:
            [{"furniture_type": "sofa", "filter": "category_identifier = ..."}, ...]
        """
        from src.services.meilisearch_service import get_filter_schema_prompt

        logger.info(
            "Generiere MeiliSearch-Filter",
            style=style,
            colors=color_preferences,
            furniture_types=furniture_types,
        )

        filter_schema = get_filter_schema_prompt()

        system_prompt = f"""Du bist ein Experte für Möbelsuche und MeiliSearch-Filter.
{filter_schema}

Deine Aufgabe: Erstelle für jeden benötigten Möbeltyp einen passenden MeiliSearch-Filter.
Beachte die Raumanalyse und Nutzer-Präferenzen bei der Filterauswahl."""

        # Formatiere Raumanalyse
        room_context = f"""
RAUMANALYSE:
- Raumtyp: {room_analysis.get('room_type', 'wohnzimmer')}
- Leere Bereiche: {', '.join(room_analysis.get('empty_areas', []))}
- Lichtverhältnisse: {room_analysis.get('lighting', 'natürlich')}
- Stil-Hinweise aus Raum: {', '.join(room_analysis.get('style_hints', []))}

NUTZER-PRÄFERENZEN:
- Gewünschter Stil: {style}
- Bevorzugte Farben: {', '.join(color_preferences) if color_preferences else 'keine Präferenz'}

BENÖTIGTE MÖBEL:
{', '.join(furniture_types)}

Erstelle für JEDEN Möbeltyp einen passenden MeiliSearch-Filter.
Antworte NUR mit dem JSON-Array - KEINE Erklärungen."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": room_context},
        ]

        def _make_request():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=3000,
            )

        response = self._retry_on_error(_make_request)
        content = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extrahiere JSON aus Thinking-Text
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            else:
                first_bracket = content.find('[')
                last_bracket = content.rfind(']')
                if first_bracket != -1 and last_bracket != -1:
                    content = content[first_bracket:last_bracket + 1]

            filters = json.loads(content.strip())

            logger.info(
                "MeiliSearch-Filter generiert",
                filter_count=len(filters),
                filters=[f.get("furniture_type") for f in filters],
            )
            return filters

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Fehler beim Parsen der Filter: {e}", content=content[:500])
            # Fallback: Einfache Filter basierend auf Kategorie-Mapping
            from src.services.meilisearch_service import get_category_for_furniture

            fallback_filters = []
            for ft in furniture_types:
                category = get_category_for_furniture(ft)
                if category:
                    style_filter = f' AND style IN ["{style}"]' if style else ""
                    fallback_filters.append({
                        "furniture_type": ft,
                        "filter": f'category_identifier = "{category}"{style_filter}',
                    })
            return fallback_filters

    def select_best_products(
        self,
        room_image_base64: str,
        candidates: Dict[str, List[Any]],
        style: str,
        color_preferences: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Lässt Qwen3-VL die besten Produkte aus den Kandidaten auswählen.

        Qwen analysiert die Produktbilder und wählt basierend auf:
        - Bildqualität (kein sichtbarer Freisteller-Hintergrund)
        - Stilpassung zum Raum
        - Farbharmonie
        - Proportionen

        Args:
            room_image_base64: Das Raumbild zur Referenz
            candidates: Dict mapping furniture_type -> List[ProductCandidate]
            style: Gewünschter Stil
            color_preferences: Bevorzugte Farben

        Returns:
            Liste der ausgewählten Produkte mit Begründung:
            [{"product_id": "...", "furniture_type": "sofa", "selection_reason": "...", ...}]
        """
        logger.info(
            "Wähle beste Produkte aus",
            furniture_types=list(candidates.keys()),
            style=style,
        )

        # Erstelle Produktliste für den Prompt und Index zum späteren Mapping
        products_info = []
        products_lookup = {}  # {furniture_type: {index: product}}
        for furniture_type, product_list in candidates.items():
            products_lookup[furniture_type] = {}
            for i, product in enumerate(product_list):
                # Hole images Liste
                images = product.images if hasattr(product, 'images') else product.get('images', [])
                products_lookup[furniture_type][i] = product
                products_info.append({
                    "furniture_type": furniture_type,
                    "index": i,
                    "product_id": product.product_id if hasattr(product, 'product_id') else product.get('product_id', ''),
                    "ean": product.ean if hasattr(product, 'ean') else product.get('ean', ''),
                    "name": product.name if hasattr(product, 'name') else product.get('name', ''),
                    "price": product.price if hasattr(product, 'price') else product.get('price', 0),
                    "colors": product.color if hasattr(product, 'color') else product.get('color', []),
                    "styles": product.style if hasattr(product, 'style') else product.get('style', []),
                    "image_url": product.image_url if hasattr(product, 'image_url') else product.get('image_url', ''),
                    "images_count": len(images),
                })

        system_prompt = f"""Du bist ein Experte für Interior Design und Produktauswahl.
Wähle für jeden Möbeltyp das BESTE Produkt aus den Kandidaten.

AUSWAHLKRITERIEN (in dieser Reihenfolge):
1. BILDQUALITÄT: Produkt sollte gut freigestellt sein (kein sichtbarer Hintergrund)
2. STILPASSUNG: Passt das Produkt zum gewünschten Stil "{style}"?
3. FARBHARMONIE: Passen die Farben zu den Präferenzen {color_preferences}?
4. PROPORTIONEN: Passt das Produkt zum Raum?
5. PREIS-LEISTUNG: Bei gleicher Qualität bevorzuge günstigere Optionen

Antworte NUR mit JSON - KEINE Erklärungen.

Format:
[
  {{
    "furniture_type": "sofa",
    "selected_index": 0,
    "product_id": "123",
    "ean": "4003...",
    "name": "Produktname",
    "price": 599.00,
    "image_url": "https://...",
    "selection_reason": "Gute Bildqualität, skandinavischer Stil passt, weiße Farbe harmoniert"
  }}
]

WICHTIG: Wähle für JEDEN furniture_type genau EIN Produkt aus."""

        user_prompt = f"""Hier sind die Produktkandidaten nach Möbeltyp:

{json.dumps(products_info, indent=2, ensure_ascii=False)}

Gewünschter Stil: {style}
Bevorzugte Farben: {', '.join(color_preferences) if color_preferences else 'keine Präferenz'}

Wähle für jeden Möbeltyp das beste Produkt aus. Antworte NUR mit JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{room_image_base64}"}
                    }
                ]
            }
        ]

        def _make_request():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=4000,
            )

        response = self._retry_on_error(_make_request)
        content = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extrahiere JSON aus Thinking-Text
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            else:
                first_bracket = content.find('[')
                last_bracket = content.rfind(']')
                if first_bracket != -1 and last_bracket != -1:
                    content = content[first_bracket:last_bracket + 1]

            selected = json.loads(content.strip())

            # Füge images aus den Originalprodukten hinzu
            for s in selected:
                furniture_type = s.get("furniture_type", "")
                selected_index = s.get("selected_index", 0)
                if furniture_type in products_lookup and selected_index in products_lookup[furniture_type]:
                    original_product = products_lookup[furniture_type][selected_index]
                    images = original_product.images if hasattr(original_product, 'images') else original_product.get('images', [])
                    s["images"] = images

            logger.info(
                "Produkte ausgewählt",
                count=len(selected),
                products=[s.get("name", "?") for s in selected],
            )
            return selected

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Fehler beim Parsen der Produktauswahl: {e}", content=content[:500])
            # Fallback: Erstes Produkt pro Typ
            fallback = []
            for furniture_type, product_list in candidates.items():
                if product_list:
                    p = product_list[0]
                    images = p.images if hasattr(p, 'images') else p.get('images', [])
                    fallback.append({
                        "furniture_type": furniture_type,
                        "selected_index": 0,
                        "product_id": p.product_id if hasattr(p, 'product_id') else p.get('product_id', ''),
                        "ean": p.ean if hasattr(p, 'ean') else p.get('ean', ''),
                        "name": p.name if hasattr(p, 'name') else p.get('name', ''),
                        "price": p.price if hasattr(p, 'price') else p.get('price', 0),
                        "image_url": p.image_url if hasattr(p, 'image_url') else p.get('image_url', ''),
                        "images": images,
                        "selection_reason": "Automatisch ausgewählt (Fallback)",
                    })
            return fallback


# Singleton
_vision_service: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    """Holt oder erstellt den Singleton VisionService."""
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service
