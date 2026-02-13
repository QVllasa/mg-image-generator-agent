"""
LangGraph Graph Definition

Definiert den StateGraph für den Room Stager Agent.
"""

from typing import Optional, Dict, List

from langgraph.graph import StateGraph, END
from src.agent.nodes import (
    receive_images_node,
    analyze_room_node,
    generate_staged_node,
    validate_result_node,
    finalize_node,
    next_image_node,
    route_after_validate,
    route_after_next_image,
    # MeiliSearch Integration
    build_filter_node,
    fetch_products_node,
    select_products_node,
    should_use_meilisearch,
)
from src.agent.state import StagingState, create_initial_state
from src.utils.logging import get_logger, set_correlation_id

logger = get_logger(__name__)

# Singleton Graph Instance
_graph: Optional[StateGraph] = None


def route_after_analyze(state: StagingState) -> str:
    """
    Entscheidet nach Raumanalyse ob MeiliSearch-Flow oder direkt generieren.

    MeiliSearch-Flow: build_filter → fetch_products → select_products → generate
    Direct-Flow: generate_staged
    """
    if should_use_meilisearch(state):
        logger.info("MeiliSearch-Modus aktiviert")
        return "build_filter"
    else:
        logger.info("Direkt-Modus (product_images vorhanden oder keine Farbpräferenzen)")
        return "generate_staged"


def create_room_stager_graph() -> StateGraph:
    """
    Erstellt den LangGraph StateGraph für Room Staging.

    Flow (mit MeiliSearch):
    receive_images → analyze_room → build_filter → fetch_products → select_products
                                                                         ↓
                                                               generate_staged
                                                                         ↓
                                                               validate_result
                                                                    ↓    ↓
                                              ┌── retry ←──────────┘    └→ next_image
                                              ↓                              ↓
                                        generate_staged                  finalize

    Flow (ohne MeiliSearch):
    receive_images → analyze_room → generate_staged → validate_result → ...
    """
    logger.info("Erstelle Room Stager Graph")

    # Erstelle StateGraph
    graph = StateGraph(StagingState)

    # ═══ NODES ═══
    graph.add_node("receive_images", receive_images_node)
    graph.add_node("analyze_room", analyze_room_node)
    # MeiliSearch Integration Nodes
    graph.add_node("build_filter", build_filter_node)
    graph.add_node("fetch_products", fetch_products_node)
    graph.add_node("select_products", select_products_node)
    # Core Nodes
    graph.add_node("generate_staged", generate_staged_node)
    graph.add_node("validate_result", validate_result_node)
    graph.add_node("next_image", next_image_node)
    graph.add_node("finalize", finalize_node)

    # ═══ EDGES ═══

    # Start → receive_images
    graph.set_entry_point("receive_images")

    # receive_images → analyze_room
    graph.add_edge("receive_images", "analyze_room")

    # analyze_room → conditional (MeiliSearch oder direkt generieren)
    graph.add_conditional_edges(
        "analyze_room",
        route_after_analyze,
        {
            "build_filter": "build_filter",  # MeiliSearch-Flow
            "generate_staged": "generate_staged",  # Direkt-Flow
        }
    )

    # MeiliSearch-Flow: build_filter → fetch_products → select_products → generate
    graph.add_edge("build_filter", "fetch_products")
    graph.add_edge("fetch_products", "select_products")
    graph.add_edge("select_products", "generate_staged")

    # generate_staged → validate_result
    graph.add_edge("generate_staged", "validate_result")

    # validate_result → conditional (retry, next_image, oder finalize)
    graph.add_conditional_edges(
        "validate_result",
        route_after_validate,
        {
            "generate_staged": "generate_staged",  # Retry
            "next_image": "next_image",  # Nächstes Bild
            "finalize": "finalize",  # Fertig
        }
    )

    # next_image → conditional (analyze_room oder finalize)
    graph.add_conditional_edges(
        "next_image",
        route_after_next_image,
        {
            "analyze_room": "analyze_room",
            "finalize": "finalize",
        }
    )

    # finalize → END
    graph.add_edge("finalize", END)

    return graph.compile()


def get_room_stager_graph() -> StateGraph:
    """
    Holt oder erstellt den Singleton Room Stager Graph.

    Returns:
        Kompilierter StateGraph
    """
    global _graph
    if _graph is None:
        _graph = create_room_stager_graph()
    return _graph


async def run_staging(
    images: List[Dict[str, str]],
    style: str = "modern",
    furniture_types: Optional[List[str]] = None,
    product_images: Optional[List[Dict[str, str]]] = None,
    room_type: Optional[str] = None,
    max_retries: int = 2,
    # MeiliSearch Integration
    color_preferences: Optional[List[str]] = None,
    budget_range: Optional[Dict[str, float]] = None,
    products_per_type: int = 5,
    # Job Tracking
    job_id: Optional[str] = None,
    session_id: Optional[str] = None,
    # Progress callback
    on_progress: Optional[callable] = None,
) -> StagingState:
    """
    Führt den Room Staging Workflow aus.

    Args:
        images: Liste von {"data": base64, "filename": str}
        style: Einrichtungsstil
        furniture_types: Gewünschte Möbeltypen (nur ohne product_images)
        product_images: Produktbilder für Multi-Reference [{"name": str, "base64": str}]
        room_type: Raumtyp (optional, sonst auto-detect)
        max_retries: Max Wiederholungen pro Bild
        color_preferences: Farbpräferenzen für MeiliSearch (aktiviert MeiliSearch-Modus)
        budget_range: Preisbereich {"min": float, "max": float}
        products_per_type: Anzahl Produktkandidaten pro Möbeltyp
        job_id: UUID des Jobs für DB-Tracking (optional)
        session_id: Session-ID für Output-Ordner (optional)
        on_progress: Optional async callback(node_name, state) called after each node

    Returns:
        Finaler StagingState mit Ergebnissen
    """
    # Generiere Correlation ID
    correlation_id = set_correlation_id()

    # Bestimme Modus
    mode = "meilisearch" if (color_preferences and not product_images) else (
        "multi-reference" if product_images else "text-prompt"
    )

    logger.info(
        "Starte Room Staging",
        correlation_id=correlation_id,
        image_count=len(images),
        style=style,
        mode=mode,
        product_count=len(product_images) if product_images else 0,
        color_preferences=color_preferences,
        job_id=job_id,
    )

    # Erstelle initialen State
    initial_state = create_initial_state(
        images=images,
        style=style,
        furniture_types=furniture_types,
        product_images=product_images,
        room_type=room_type,
        max_retries=max_retries,
        correlation_id=correlation_id,
        # MeiliSearch Integration
        color_preferences=color_preferences,
        budget_range=budget_range,
        products_per_type=products_per_type,
        # Job Tracking
        job_id=job_id,
        session_id=session_id,
    )

    # Hole Graph
    graph = get_room_stager_graph()

    # Führe Graph mit Streaming aus für Live-Updates
    final_state = None
    async for chunk in graph.astream(initial_state, stream_mode="updates"):
        # chunk ist dict mit {node_name: state_update}
        for node_name, state_update in chunk.items():
            logger.debug(f"Node abgeschlossen: {node_name}")

            # Rufe Progress-Callback auf falls vorhanden
            if on_progress:
                try:
                    await on_progress(node_name, state_update)
                except Exception as e:
                    logger.warning(f"Progress callback Fehler: {e}")

            # Speichere letzten State
            if state_update:
                if final_state is None:
                    final_state = dict(initial_state)
                final_state.update(state_update)

    # Falls kein State-Update kam, verwende initial_state
    if final_state is None:
        final_state = dict(initial_state)

    logger.info(
        "Room Staging abgeschlossen",
        correlation_id=correlation_id,
        completed=final_state.get("completed_count", 0),
        failed=final_state.get("failed_count", 0),
        mode=mode,
        session_id=final_state.get("session_id"),
        output_directory=final_state.get("output_directory"),
    )

    return final_state
