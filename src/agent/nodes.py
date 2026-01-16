"""
LangGraph Nodes

Implementiert die einzelnen Verarbeitungsschritte des Room Stager Agents.
"""

import time
from typing import Dict, Any

from src.agent.state import StagingState, ImageData
from src.services.fal_service import get_fal_service
from src.services.vision_service import get_vision_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


def receive_images_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 1: Empfängt und validiert die Eingabebilder.

    - Prüft ob Bilder vorhanden sind
    - Validiert Base64-Format
    - Initialisiert den Workflow
    """
    logger.info(
        "receive_images_node",
        image_count=len(state["images"]),
    )

    # Validiere jedes Bild
    valid_count = 0
    for i, image in enumerate(state["images"]):
        try:
            # Prüfe ob Base64 gültig ist (einfacher Check)
            if len(image["original_base64"]) < 100:
                state["images"][i]["is_valid"] = False
                state["images"][i]["error"] = "Bild zu klein oder ungültig"
            else:
                valid_count += 1
        except Exception as e:
            state["images"][i]["is_valid"] = False
            state["images"][i]["error"] = str(e)

    logger.info(f"Bilder validiert: {valid_count}/{len(state['images'])} gültig")

    return {
        "workflow_stage": "analyze",
        "current_image_index": 0,
    }


def analyze_room_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 2: Analysiert den aktuellen Raum mit Qwen3-VL.

    - Erkennt Raumtyp
    - Identifiziert leere Bereiche
    - Schlägt passende Möbel vor
    """
    idx = state["current_image_index"]
    image = state["images"][idx]

    # Überspringe ungültige Bilder
    if not image["is_valid"]:
        logger.info(f"Überspringe ungültiges Bild: {image['filename']}")
        return {}

    logger.info(
        "analyze_room_node",
        filename=image["filename"],
        index=idx,
    )

    start_time = time.time()

    try:
        vision_service = get_vision_service()
        analysis = vision_service.analyze_room(
            image_base64=image["original_base64"],
            style=state["style"],
            room_type_hint=state["room_type_override"],
        )

        # Speichere Analyse im State
        room_analysis = {
            "room_type": analysis.room_type,
            "empty_areas": analysis.empty_areas,
            "existing_furniture": analysis.existing_furniture,
            "suggested_furniture": analysis.suggested_furniture,
            "lighting": analysis.lighting,
            "style_hints": analysis.style_hints,
        }

        # Update das Bild im State
        state["images"][idx]["room_analysis"] = room_analysis

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Raumanalyse abgeschlossen",
            room_type=analysis.room_type,
            suggested_furniture=analysis.suggested_furniture,
            duration_ms=duration_ms,
        )

        return {
            "workflow_stage": "generate",
        }

    except Exception as e:
        logger.error(f"Fehler bei Raumanalyse: {e}")
        state["images"][idx]["error"] = f"Analysefehler: {str(e)}"
        return {
            "workflow_stage": "generate",  # Versuche trotzdem zu generieren
        }


def generate_staged_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 3: Generiert das Staging-Bild mit fal.ai FLUX Fill.

    - Erstellt optimierten Prompt
    - Ruft fal.ai API auf
    - Speichert Ergebnis
    """
    idx = state["current_image_index"]
    image = state["images"][idx]

    # Überspringe ungültige Bilder
    if not image["is_valid"]:
        return {}

    logger.info(
        "generate_staged_node",
        filename=image["filename"],
        index=idx,
        retry=image["retries"],
    )

    start_time = time.time()

    try:
        fal_service = get_fal_service()

        # Prüfe ob Multi-Reference (Produktbilder) vorhanden
        product_images = state.get("product_images")

        if product_images and len(product_images) > 0:
            # ═══ MULTI-REFERENCE MODE ═══
            # Verwende echte Produktbilder mit kreativem Prompt von Qwen3-VL
            logger.info(
                "Multi-Reference Staging",
                product_count=len(product_images),
            )

            # Generiere kreativen Prompt mit Qwen3-VL
            vision_service = get_vision_service()
            staging_prompt = vision_service.generate_staging_prompt(
                room_base64=image["original_base64"],
                product_images=product_images,
                style=state["style"],
                room_analysis=image["room_analysis"],
            )

            logger.info(
                "Kreativer Prompt generiert",
                prompt=staging_prompt.prompt[:200],
                style=staging_prompt.style_description,
                atmosphere=staging_prompt.atmosphere,
            )

            # Speichere Prompt-Details im State für Logging
            state["images"][idx]["staging_prompt"] = {
                "prompt": staging_prompt.prompt,
                "placement_instructions": staging_prompt.placement_instructions,
                "style_description": staging_prompt.style_description,
                "atmosphere": staging_prompt.atmosphere,
            }

            staged_base64 = fal_service.generate_with_product_images(
                room_base64=image["original_base64"],
                product_images=product_images,
                style=state["style"],
                creative_prompt=staging_prompt.prompt,
            )

            # Speichere welche Produkte hinzugefügt wurden
            furniture_types = [p.get("name", "furniture") for p in product_images]

        else:
            # ═══ TEXT-PROMPT MODE (Fallback) ═══
            # Generiere Möbel basierend auf Text-Beschreibung
            furniture_types = state["furniture_types"]
            if not furniture_types and image["room_analysis"]:
                furniture_types = image["room_analysis"].get("suggested_furniture", [])
            if not furniture_types:
                furniture_types = ["sofa", "coffee table", "floor lamp"]

            # Bestimme Raumtyp
            room_type = state["room_type_override"]
            if not room_type and image["room_analysis"]:
                room_type = image["room_analysis"].get("room_type", "living room")
            if not room_type:
                room_type = "living room"

            # Bestimme leere Bereiche
            empty_areas = []
            if image["room_analysis"]:
                empty_areas = image["room_analysis"].get("empty_areas", [])

            # Erstelle Prompt
            prompt = fal_service.create_staging_prompt(
                room_type=room_type,
                furniture_list=furniture_types[:5],
                style=state["style"],
                empty_areas=empty_areas,
            )

            logger.info("Text-Prompt Staging", prompt=prompt[:200])

            staged_base64 = fal_service.generate_staged_image(
                image_base64=image["original_base64"],
                prompt=prompt,
            )

        duration_ms = int((time.time() - start_time) * 1000)

        # Update State
        state["images"][idx]["staged_base64"] = staged_base64
        state["images"][idx]["furniture_added"] = furniture_types[:5]
        state["images"][idx]["processing_time_ms"] += duration_ms

        logger.info(
            "Bildgenerierung erfolgreich",
            duration_ms=duration_ms,
        )

        return {
            "workflow_stage": "validate",
        }

    except Exception as e:
        logger.error(f"Fehler bei Bildgenerierung: {e}")
        state["images"][idx]["error"] = f"Generierungsfehler: {str(e)}"

        # Erhöhe Retry-Counter
        state["images"][idx]["retries"] += 1

        return {
            "workflow_stage": "validate",
            "total_retries": state["total_retries"] + 1,
        }


def validate_result_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 4: Validiert das Staging-Ergebnis mit Qwen3-VL.

    - Vergleicht Original und Staging
    - Bewertet Qualität
    - Erkennt Produktpositionen für Frontend-Hotspots
    - Entscheidet über Retry
    """
    idx = state["current_image_index"]
    image = state["images"][idx]

    # Überspringe wenn kein Staging-Bild vorhanden
    if not image["staged_base64"]:
        logger.info("Kein Staging-Bild zum Validieren")
        return {
            "workflow_stage": "next_image",
        }

    logger.info(
        "validate_result_node",
        filename=image["filename"],
        retry=image["retries"],
    )

    try:
        vision_service = get_vision_service()
        validation = vision_service.validate_staging(
            original_base64=image["original_base64"],
            staged_base64=image["staged_base64"],
        )

        logger.info(
            "Validierung abgeschlossen",
            is_valid=validation.is_valid,
            confidence=validation.confidence,
            issues=validation.issues,
        )

        # Entscheide basierend auf Validierung
        if validation.is_valid or validation.confidence >= 0.7:
            # ═══ ERFOLG: Erkenne Produktpositionen ═══
            try:
                expected_products = image.get("furniture_added", [])
                if expected_products:
                    # Build product_id_mapping from selected_products or product_images
                    product_id_mapping = {}

                    # Check selected_products (MeiliSearch flow)
                    if state.get("selected_products"):
                        for p in state["selected_products"]:
                            name = p.get("name", "").lower().strip()
                            product_id = p.get("product_id", "")
                            if name and product_id:
                                product_id_mapping[name] = product_id

                    # Check product_images (custom flow) - may have product_id
                    if state.get("product_images"):
                        for p in state["product_images"]:
                            name = p.get("name", "").lower().strip()
                            product_id = p.get("product_id", "")
                            if name and product_id:
                                product_id_mapping[name] = product_id

                    logger.info(
                        "Starte Produkt-Positionserkennung",
                        products=expected_products,
                        id_mapping_count=len(product_id_mapping),
                    )
                    detection = vision_service.detect_product_positions(
                        staged_base64=image["staged_base64"],
                        expected_products=expected_products,
                        product_id_mapping=product_id_mapping if product_id_mapping else None,
                    )

                    # Speichere Positionen im State
                    state["images"][idx]["product_positions"] = [
                        {
                            "product_name": p.product_name,
                            "product_id": p.product_id,
                            "x": p.x,
                            "y": p.y,
                            "width": p.width,
                            "height": p.height,
                            "confidence": p.confidence,
                            "hotspot_x": p.hotspot_x,
                            "hotspot_y": p.hotspot_y,
                        }
                        for p in detection.products
                    ]

                    logger.info(
                        "Produktpositionen erkannt",
                        count=len(detection.products),
                        products=[(p.product_name, p.product_id) for p in detection.products],
                    )
            except Exception as pos_error:
                logger.warning(f"Positionserkennung fehlgeschlagen: {pos_error}")
                # Fortfahren ohne Positionen

            return {
                "workflow_stage": "next_image",
                "completed_count": state["completed_count"] + 1,
            }
        elif image["retries"] < state["max_retries"]:
            # Retry möglich
            logger.info(f"Retry {image['retries'] + 1}/{state['max_retries']}")
            state["images"][idx]["staged_base64"] = None  # Reset für Retry
            return {
                "workflow_stage": "generate",
            }
        else:
            # Max Retries erreicht - akzeptiere Ergebnis trotzdem
            logger.warning("Max Retries erreicht, akzeptiere Ergebnis")
            return {
                "workflow_stage": "next_image",
                "completed_count": state["completed_count"] + 1,
            }

    except Exception as e:
        logger.error(f"Fehler bei Validierung: {e}")
        # Bei Validierungsfehler: Akzeptiere Ergebnis
        return {
            "workflow_stage": "next_image",
            "completed_count": state["completed_count"] + 1,
        }


def finalize_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 5: Finalisiert die Verarbeitung.

    - Berechnet Statistiken
    - Setzt finalen Status
    - Speichert Ergebnisse in Output-Ordner (bei MeiliSearch-Modus)
    """
    logger.info(
        "finalize_node",
        completed=state["completed_count"],
        failed=state["failed_count"],
        total=len(state["images"]),
        session_id=state.get("session_id"),
    )

    # Zähle Ergebnisse
    successful = sum(1 for img in state["images"] if img["staged_base64"])
    failed = len(state["images"]) - successful

    # Speichere Ergebnisse in Output-Ordner (immer wenn session_id existiert)
    output_directory = None
    if state.get("session_id"):
        import os
        import json
        import base64
        import httpx

        session_id = state["session_id"]
        output_dir = f"test_images/{session_id}"
        os.makedirs(output_dir, exist_ok=True)

        # Speichere alle staged Bilder
        for img in state["images"]:
            if img["staged_base64"]:
                # Sauberes Bild
                filename_base = img['filename'].replace('.jpg', '').replace('.jpeg', '').replace('.png', '')
                clean_path = f"{output_dir}/{filename_base}_staged.jpg"
                with open(clean_path, "wb") as f:
                    f.write(base64.b64decode(img["staged_base64"]))
                logger.info(f"Staged image gespeichert: {clean_path}")

        # Speichere Produktbilder (wenn vorhanden) - ALLE Bilder pro Produkt
        selected_products = state.get("selected_products", [])
        if selected_products:
            products_dir = f"{output_dir}/products"
            os.makedirs(products_dir, exist_ok=True)

            for product in selected_products:
                furniture_type = product.get("furniture_type", "product")
                product_id = product.get("product_id", "unknown")

                # Erstelle Unterordner pro Produkt
                product_folder = f"{products_dir}/{furniture_type}_{product_id}"
                os.makedirs(product_folder, exist_ok=True)

                # Hole alle Bilder - bevorzuge 'images' Array, sonst 'image_url'
                all_images = product.get("images", [])
                if not all_images and product.get("image_url"):
                    all_images = [product.get("image_url")]

                logger.info(
                    f"Lade {len(all_images)} Bilder für {furniture_type}",
                    product_name=product.get("name", "?"),
                )

                for idx, image_url in enumerate(all_images):
                    if image_url:
                        try:
                            response = httpx.get(image_url, timeout=30)
                            if response.status_code == 200:
                                # Speichere mit Index
                                image_filename = f"{product_folder}/image_{idx + 1}.jpg"
                                with open(image_filename, "wb") as f:
                                    f.write(response.content)
                                logger.info(f"Produktbild gespeichert: {image_filename}")
                        except Exception as e:
                            logger.warning(f"Produktbild {idx + 1} konnte nicht geladen werden: {e}")

        # Speichere Metadaten
        metadata = {
            "session_id": session_id,
            "style": state["style"],
            "color_preferences": state.get("color_preferences", []),
            "selected_products": [
                {
                    "product_id": p.get("product_id"),
                    "ean": p.get("ean"),
                    "name": p.get("name"),
                    "furniture_type": p.get("furniture_type"),
                    "price": p.get("price"),
                    "image_url": p.get("image_url"),
                    "images": p.get("images", []),
                    "images_count": len(p.get("images", [])),
                    "selection_reason": p.get("selection_reason"),
                }
                for p in selected_products
            ],
            "hotspots_per_image": {
                img["filename"]: img.get("product_positions", [])
                for img in state["images"]
            },
            "room_analysis": state["images"][0].get("room_analysis") if state["images"] else None,
        }
        with open(f"{output_dir}/metadata.json", "w") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        output_directory = output_dir
        logger.info(f"Ergebnisse gespeichert in: {output_directory}")

    return {
        "workflow_stage": "done",
        "completed_count": successful,
        "failed_count": failed,
        "output_directory": output_directory,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MEILISEARCH INTEGRATION NODES
# ═══════════════════════════════════════════════════════════════════════════════

def build_filter_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 2b: Baut MeiliSearch-Filter basierend auf Raumanalyse.

    Qwen3-VL analysiert die Raumanalyse und Nutzer-Präferenzen
    und generiert passende MeiliSearch-Filter für jeden Möbeltyp.
    """
    logger.info(
        "build_filter_node",
        style=state["style"],
        colors=state.get("color_preferences"),
    )

    # Nutze Raumanalyse vom ersten Bild
    room_analysis = state["images"][0].get("room_analysis", {})
    if not room_analysis:
        # Fallback: Analysiere Raum erst
        logger.warning("Keine Raumanalyse vorhanden, verwende Defaults")
        room_analysis = {
            "room_type": "living_room",
            "suggested_furniture": ["sofa", "couchtisch", "stehlampe"],
            "empty_areas": ["Zentrum"],
            "lighting": "natürlich",
            "style_hints": [],
        }

    # Bestimme benötigte Möbeltypen
    furniture_types = room_analysis.get("suggested_furniture", [])
    if not furniture_types:
        furniture_types = ["sofa", "couchtisch", "stehlampe"]

    vision_service = get_vision_service()
    filters = vision_service.build_product_filters(
        room_analysis=room_analysis,
        style=state["style"],
        color_preferences=state.get("color_preferences", []),
        furniture_types=furniture_types,
    )

    logger.info(
        "Filter generiert",
        filter_count=len(filters),
        furniture_types=[f.get("furniture_type") for f in filters],
    )

    return {
        "product_filters": filters,
        "workflow_stage": "fetch_products",
    }


async def fetch_products_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 3: Holt Produktkandidaten aus MeiliSearch.

    Führt Suchanfragen für jeden generierten Filter durch
    und sammelt Produktkandidaten.
    """
    from src.services.meilisearch_service import get_meilisearch_service

    logger.info(
        "fetch_products_node",
        filter_count=len(state.get("product_filters", [])),
    )

    meilisearch = get_meilisearch_service()

    # Extrahiere Preisbereich
    price_range = None
    if state.get("budget_range"):
        price_range = (
            state["budget_range"].get("min", 0),
            state["budget_range"].get("max", 0),
        )

    candidates = await meilisearch.fetch_products_for_furniture_types(
        filter_specs=state.get("product_filters", []),
        products_per_type=state.get("products_per_type", 5),
        price_range=price_range,
    )

    # Konvertiere zu Dict für State
    candidates_dict = {}
    for furniture_type, product_list in candidates.items():
        candidates_dict[furniture_type] = [
            {
                "product_id": p.product_id,
                "ean": p.ean,
                "name": p.name,
                "furniture_type": p.furniture_type,
                "category": p.category,
                "price": p.price,
                "image_url": p.image_url,
                "thumbnail": p.thumbnail,
                "images": p.images,  # All product image URLs from MeiliSearch
                "style": p.style,
                "color": p.color,
                "dimensions": p.dimensions,
                "average_rating": p.average_rating,
                "brand_name": p.brand_name,
            }
            for p in product_list
        ]

    total_candidates = sum(len(v) for v in candidates_dict.values())
    logger.info(
        "Produktkandidaten geholt",
        total=total_candidates,
        by_type={k: len(v) for k, v in candidates_dict.items()},
    )

    return {
        "product_candidates": candidates_dict,
        "workflow_stage": "select_products",
    }


def select_products_node(state: StagingState) -> Dict[str, Any]:
    """
    Node 4: Qwen3-VL wählt die besten Produkte aus den Kandidaten.

    Analysiert Produktbilder und wählt basierend auf:
    - Bildqualität
    - Stilpassung
    - Farbharmonie
    - Proportionen
    """
    import httpx
    import base64

    logger.info(
        "select_products_node",
        candidate_types=list((state.get("product_candidates") or {}).keys()),
    )

    vision_service = get_vision_service()

    # Wähle beste Produkte
    selected = vision_service.select_best_products(
        room_image_base64=state["images"][0]["original_base64"],
        candidates=state.get("product_candidates", {}),
        style=state["style"],
        color_preferences=state.get("color_preferences", []),
    )

    # Lade Produktbilder herunter für FLUX
    for product in selected:
        image_url = product.get("image_url", "")
        if image_url:
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(image_url)
                    response.raise_for_status()
                    product["image_base64"] = base64.b64encode(response.content).decode("utf-8")
                    logger.info(f"Produktbild geladen: {product.get('name', '?')}")
            except Exception as e:
                logger.warning(f"Produktbild konnte nicht geladen werden: {e}")
                product["image_base64"] = None

    # Konvertiere selected_products zu product_images Format für generate_staged_node
    # WICHTIG: product_id muss hier mitgegeben werden für Hotspot-Linking
    product_images = [
        {
            "name": p.get("name", "Möbelstück"),
            "base64": p.get("image_base64", ""),
            "ean": p.get("ean", ""),
            "product_id": p.get("product_id", ""),  # Für Hotspot-Verknüpfung
        }
        for p in selected
        if p.get("image_base64")
    ]

    logger.info(
        "Produkte ausgewählt",
        count=len(selected),
        products=[p.get("name", "?") for p in selected],
    )

    return {
        "selected_products": selected,
        "product_images": product_images,  # Für generate_staged_node
        "workflow_stage": "generate",
    }


def should_use_meilisearch(state: StagingState) -> bool:
    """
    Prüft ob der MeiliSearch-Modus verwendet werden soll.

    MeiliSearch-Modus wird aktiviert wenn:
    - Keine product_images vorhanden sind
    - color_preferences angegeben sind
    ODER
    - furniture_types leer sind (Agent soll selbst entscheiden)
    """
    has_product_images = bool(state.get("product_images"))
    has_color_preferences = bool(state.get("color_preferences"))

    return not has_product_images and has_color_preferences


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def route_after_validate(state: StagingState) -> str:
    """
    Entscheidet nach Validierung ob retry, nächstes Bild oder finalize.
    """
    workflow_stage = state["workflow_stage"]

    if workflow_stage == "generate":
        # Retry
        return "generate_staged"

    idx = state["current_image_index"]
    if idx + 1 < len(state["images"]):
        # Nächstes Bild
        return "next_image"
    else:
        # Alle Bilder verarbeitet
        return "finalize"


def route_after_next_image(state: StagingState) -> str:
    """
    Prüft ob noch Bilder zu verarbeiten sind.
    """
    idx = state["current_image_index"]
    if idx < len(state["images"]):
        return "analyze_room"
    else:
        return "finalize"


def next_image_node(state: StagingState) -> Dict[str, Any]:
    """
    Hilfnode zum Weitergehen zum nächsten Bild.
    """
    return {
        "current_image_index": state["current_image_index"] + 1,
        "workflow_stage": "analyze",
    }
