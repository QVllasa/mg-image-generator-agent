"""
MeiliSearch Service

Provides product search and filter building for the Room Stager Agent.
Connects to MeiliSearch products index and loads filter values from metadata.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

import httpx
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# FURNITURE CATEGORY MAPPING
# Maps furniture type names to MeiliSearch category_identifier paths
# ═══════════════════════════════════════════════════════════════════════════════

FURNITURE_CATEGORY_MAPPING = {
    # Wohnzimmer - Korrekte MeiliSearch-Pfade
    "sofa": "/wohnen/sofas-couches/wohnlandschaften",
    "couch": "/wohnen/sofas-couches/wohnlandschaften",
    "wohnlandschaft": "/wohnen/sofas-couches/wohnlandschaften",
    "couchtisch": "/wohnen/tische/couchtische",
    "wohnzimmertisch": "/wohnen/tische/couchtische",
    "stehlampe": "/lampen",
    "deckenlampe": "/lampen",
    "lampe": "/lampen",
    "teppich": "/heimtextilien/teppiche",
    "regal": "/wohnen/regale-raumteiler",
    "sideboard": "/wohnen/kommoden-sideboards",
    "tv-möbel": "/wohnen/tv-hifi-moebel",
    "sessel": "/wohnen/sessel",
    "beistelltisch": "/wohnen/tische/beistelltische",

    # Schlafzimmer
    "bett": "/schlafen/betten",
    "nachttisch": "/schlafen/nachttische",
    "kleiderschrank": "/schlafen/kleiderschraenke",
    "kommode": "/wohnen/kommoden-sideboards",
    "nachttischlampe": "/lampen",

    # Esszimmer
    "esstisch": "/essen/tische",
    "stuhl": "/essen/stuehle-hocker",
    "esszimmerstuhl": "/essen/stuehle-hocker",
    "vitrine": "/wohnen/vitrinen",

    # Büro
    "schreibtisch": "/buero/schreibtische",
    "bürostuhl": "/buero/buerostuehle",
    "bücherregal": "/wohnen/regale-raumteiler",
}


# ═══════════════════════════════════════════════════════════════════════════════
# FILTER VALUES
# Loaded from MeiliSearch metadata 'filter' index - these are the allowed values
# ═══════════════════════════════════════════════════════════════════════════════

FILTER_VALUES = {
    "color": [
        "beige", "blau", "braun", "bronze", "bunt", "gelb", "gold", "grau",
        "gruen", "orange", "rosa", "rot", "schwarz", "silber", "transparent",
        "tuerkis", "violett", "weiss"
    ],

    "style": [
        "glamour", "industrial", "japandi", "klassisch", "kolonial", "landhaus",
        "maritim", "mid-century", "modern", "orientalisch", "retro",
        "skandinavisch", "urban", "vintage"
    ],

    "sofa_shape": ["gerade", "gerundet", "l-form", "u-form"],

    "sofa_design": [
        "einfarbig", "gemustert", "chesterfield-steppung", "mit-steppungen",
        "mit-2-armlehnen", "ohne-armlehnen"
    ],

    "lamp_features": [
        "dimmbar", "mit-bewegungsmelder", "mit-fernbedienung", "smart-home"
    ],

    "table_material": [
        "glas", "holz", "holzwerkstoff", "kunststoff", "massivholz", "metall"
    ],

    "material": [
        "holz", "metall", "stoff", "leder", "kunststoff", "glas", "rattan", "marmor"
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# QWEN FILTER SCHEMA PROMPT
# This prompt teaches Qwen how to build MeiliSearch filters
# ═══════════════════════════════════════════════════════════════════════════════

FILTER_SCHEMA_FOR_QWEN = """
Du baust MeiliSearch-Filter für Möbelsuche. Verwende NUR diese Werte:

═══ KATEGORIEN (category_identifier) ═══
{category_list}

═══ FILTER-ATTRIBUTE MIT ERLAUBTEN WERTEN ═══
- color: {color_values}
- style: {style_values}
- sofa_shape: {sofa_shape_values}
- table_material: {table_material_values}
- price: Zahl in EUR (z.B. price >= 100 AND price <= 2000)
- total_width, total_depth, total_height: cm (z.B. total_width <= 200)
- average_rating: Bewertung 0-5 (z.B. average_rating >= 4)

═══ MEILISEARCH FILTER-SYNTAX ═══
- Gleichheit: category_identifier = "/wohnen/sofas"
- IN-Liste: color IN ["weiss", "grau"]
- Vergleich: price >= 100 AND price <= 2000
- Kombination: filter1 AND filter2

═══ BEISPIEL-OUTPUT ═══
[
  {{
    "furniture_type": "sofa",
    "filter": "category_identifier = \\"/wohnen/sofas\\" AND style IN [\\"skandinavisch\\", \\"modern\\"] AND color IN [\\"weiss\\", \\"grau\\", \\"beige\\"]"
  }},
  {{
    "furniture_type": "couchtisch",
    "filter": "category_identifier = \\"/wohnen/couchtische\\" AND table_material IN [\\"holz\\", \\"massivholz\\"]"
  }},
  {{
    "furniture_type": "stehlampe",
    "filter": "category_identifier = \\"/wohnen/stehlampen\\" AND style IN [\\"skandinavisch\\", \\"modern\\"]"
  }}
]

WICHTIG:
- Verwende exakt die Werte aus den Listen oben (lowercase, mit Bindestrich)
- Jeder Filter MUSS category_identifier enthalten
- Kombiniere sinnvoll style und color basierend auf Nutzer-Präferenzen
"""


def get_filter_schema_prompt() -> str:
    """
    Generates the filter schema prompt for Qwen with all categories and allowed values.
    This prompt teaches Qwen how to construct valid MeiliSearch filters.
    """
    category_list = "\n".join(
        f"- {key}: {value}"
        for key, value in FURNITURE_CATEGORY_MAPPING.items()
    )

    return FILTER_SCHEMA_FOR_QWEN.format(
        category_list=category_list,
        color_values=FILTER_VALUES["color"],
        style_values=FILTER_VALUES["style"],
        sofa_shape_values=FILTER_VALUES["sofa_shape"],
        table_material_values=FILTER_VALUES["table_material"],
    )


def get_category_for_furniture(furniture_type: str) -> Optional[str]:
    """
    Maps a furniture type name to its MeiliSearch category_identifier.

    Args:
        furniture_type: Name of the furniture (e.g., "sofa", "couchtisch")

    Returns:
        Category path (e.g., "/wohnen/sofas") or None if not found
    """
    # Normalize: lowercase, strip whitespace
    normalized = furniture_type.lower().strip()

    # Direct match
    if normalized in FURNITURE_CATEGORY_MAPPING:
        return FURNITURE_CATEGORY_MAPPING[normalized]

    # Partial match (e.g., "großes sofa" -> "sofa")
    for key, value in FURNITURE_CATEGORY_MAPPING.items():
        if key in normalized:
            return value

    return None


@dataclass
class ProductCandidate:
    """A product candidate from MeiliSearch."""
    product_id: str
    ean: str
    name: str
    furniture_type: str
    category: str
    price: float
    image_url: str
    thumbnail: str
    images: List[str]  # All product images
    style: List[str]
    color: List[str]
    dimensions: Dict[str, float]
    average_rating: Optional[float] = None
    brand_name: Optional[str] = None


class MeiliSearchService:
    """
    Service for searching products in MeiliSearch.

    Provides:
    - Product search with dynamic filters
    - Filter expression building
    - Product candidate fetching
    """

    def __init__(
        self,
        products_url: Optional[str] = None,
        products_api_key: Optional[str] = None,
        metadata_url: Optional[str] = None,
        metadata_api_key: Optional[str] = None,
    ):
        """
        Initialize MeiliSearch service.

        Args:
            products_url: URL for products MeiliSearch instance
            products_api_key: API key for products instance
            metadata_url: URL for metadata MeiliSearch instance
            metadata_api_key: API key for metadata instance
        """
        self.products_url = products_url or os.getenv(
            "MEILISEARCH_PRODUCTS_URL", "http://meilisearch-products:7700"
        )
        self.products_api_key = products_api_key or os.getenv(
            "MEILISEARCH_PRODUCTS_KEY", ""
        )
        self.metadata_url = metadata_url or os.getenv(
            "MEILISEARCH_METADATA_URL", "http://meilisearch-metadata:7700"
        )
        self.metadata_api_key = metadata_api_key or os.getenv(
            "MEILISEARCH_METADATA_KEY", ""
        )

        self.products_index = "products"
        self._filter_values_cache: Optional[Dict[str, List[str]]] = None

        logger.info(
            "MeiliSearch Service initialized",
            products_url=self.products_url,
            metadata_url=self.metadata_url,
        )

    def _get_headers(self, api_key: str) -> Dict[str, str]:
        """Get headers for MeiliSearch API requests."""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def load_filter_values(self) -> Dict[str, List[str]]:
        """
        Load filter values from MeiliSearch metadata 'filter' index.
        Caches the result for subsequent calls.

        Returns:
            Dict mapping filter keys to lists of allowed values
        """
        if self._filter_values_cache is not None:
            return self._filter_values_cache

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.metadata_url}/indexes/filter/documents",
                    params={"limit": 200},
                    headers=self._get_headers(self.metadata_api_key),
                )
                response.raise_for_status()
                data = response.json()

                self._filter_values_cache = {}
                for f in data.get("results", []):
                    key = f.get("key")
                    filter_values = f.get("filter_values", [])
                    if key and filter_values:
                        self._filter_values_cache[key] = [
                            v["data"]["value"]
                            for v in filter_values
                            if v.get("data", {}).get("value")
                        ]

                logger.info(
                    "Loaded filter values from MeiliSearch",
                    filter_count=len(self._filter_values_cache),
                )
                return self._filter_values_cache

        except Exception as e:
            logger.warning(f"Failed to load filter values from MeiliSearch: {e}")
            # Fall back to hardcoded values
            return FILTER_VALUES

    def build_filter_expression(
        self,
        category: Optional[str] = None,
        style: Optional[List[str]] = None,
        colors: Optional[List[str]] = None,
        material: Optional[List[str]] = None,
        price_range: Optional[Tuple[float, float]] = None,
        max_dimensions: Optional[Dict[str, float]] = None,
        min_rating: Optional[float] = None,
    ) -> str:
        """
        Build a MeiliSearch filter expression from parameters.

        Args:
            category: Category identifier (e.g., "/wohnen/sofas")
            style: List of style values
            colors: List of color values
            material: List of material values
            price_range: Tuple of (min_price, max_price)
            max_dimensions: Dict with max values for total_width, total_depth, total_height
            min_rating: Minimum average rating

        Returns:
            MeiliSearch filter string
        """
        filters = []

        if category:
            filters.append(f'category_identifier = "{category}"')

        if style:
            style_str = ", ".join(f'"{s}"' for s in style)
            filters.append(f"style IN [{style_str}]")

        if colors:
            colors_str = ", ".join(f'"{c}"' for c in colors)
            filters.append(f"color IN [{colors_str}]")

        if material:
            material_str = ", ".join(f'"{m}"' for m in material)
            filters.append(f"material IN [{material_str}]")

        if price_range:
            min_price, max_price = price_range
            if min_price > 0:
                filters.append(f"price >= {min_price}")
            if max_price > 0:
                filters.append(f"price <= {max_price}")

        if max_dimensions:
            for dim, value in max_dimensions.items():
                if value > 0:
                    filters.append(f"{dim} <= {value}")

        if min_rating and min_rating > 0:
            filters.append(f"average_rating >= {min_rating}")

        return " AND ".join(filters)

    async def search_products(
        self,
        filter_expression: str,
        query: str = "",
        limit: int = 10,
        sort: Optional[List[str]] = None,
    ) -> List[ProductCandidate]:
        """
        Search products in MeiliSearch with a filter expression.

        Args:
            filter_expression: MeiliSearch filter string
            query: Optional search query
            limit: Maximum number of results
            sort: Optional sort fields (e.g., ["price:asc", "average_rating:desc"])

        Returns:
            List of ProductCandidate objects
        """
        try:
            search_body = {
                "q": query,
                "filter": filter_expression,
                "limit": limit,
                "attributesToRetrieve": [
                    "product_group_id", "ean", "title", "category_identifier",
                    "price", "image_url", "thumbnail", "images", "style", "color",
                    "total_width", "total_height", "total_depth",
                    "average_rating", "brand_name"
                ],
            }

            if sort:
                search_body["sort"] = sort

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.products_url}/indexes/{self.products_index}/search",
                    json=search_body,
                    headers=self._get_headers(self.products_api_key),
                )
                response.raise_for_status()
                data = response.json()

            candidates = []
            for hit in data.get("hits", []):
                candidates.append(
                    ProductCandidate(
                        product_id=str(hit.get("product_group_id", "")),
                        ean=hit.get("ean", ""),
                        name=hit.get("title", ""),
                        furniture_type="",  # Will be set by caller
                        category=hit.get("category_identifier", ""),
                        price=hit.get("price", 0.0),
                        image_url=hit.get("image_url", ""),
                        thumbnail=hit.get("thumbnail", ""),
                        images=hit.get("images", []) or [],
                        style=hit.get("style", []) or [],
                        color=hit.get("color", []) or [],
                        dimensions={
                            "width": hit.get("total_width", 0) or 0,
                            "height": hit.get("total_height", 0) or 0,
                            "depth": hit.get("total_depth", 0) or 0,
                        },
                        average_rating=hit.get("average_rating"),
                        brand_name=hit.get("brand_name"),
                    )
                )

            logger.info(
                "MeiliSearch search completed",
                filter=filter_expression[:100],
                results=len(candidates),
            )
            return candidates

        except Exception as e:
            logger.error(f"MeiliSearch search failed: {e}", filter=filter_expression)
            return []

    def _extract_category_from_filter(self, filter_expr: str) -> Optional[str]:
        """Extract category_identifier value from a filter expression."""
        import re
        match = re.search(r'category_identifier\s*=\s*"([^"]+)"', filter_expr)
        if match:
            return match.group(1)
        return None

    def _build_fallback_filters(self, filter_expr: str) -> List[str]:
        """
        Build a list of progressively less restrictive filters.

        Strategy:
        1. Full filter (original)
        2. Category + style only (remove color)
        3. Category + color only (remove style)
        4. Category only
        """
        import re

        fallbacks = [filter_expr]  # Start with original

        # Extract category
        category = self._extract_category_from_filter(filter_expr)
        if not category:
            return fallbacks

        # Extract style and color parts
        style_match = re.search(r'style\s+IN\s+\[[^\]]+\]', filter_expr)
        color_match = re.search(r'color\s+IN\s+\[[^\]]+\]', filter_expr)

        style_part = style_match.group(0) if style_match else None
        color_part = color_match.group(0) if color_match else None

        # Fallback 2: Category + style only
        if style_part and color_part:
            fallbacks.append(f'category_identifier = "{category}" AND {style_part}')

        # Fallback 3: Category + color only
        if color_part and style_part:
            fallbacks.append(f'category_identifier = "{category}" AND {color_part}')

        # Fallback 4: Category only
        fallbacks.append(f'category_identifier = "{category}"')

        return fallbacks

    async def fetch_products_for_furniture_types(
        self,
        filter_specs: List[Dict[str, Any]],
        products_per_type: int = 5,
        price_range: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, List[ProductCandidate]]:
        """
        Fetch product candidates for multiple furniture types.

        Uses fallback logic: if no products found with full filter,
        progressively loosens restrictions until products are found.

        Args:
            filter_specs: List of filter specifications from Qwen, each with:
                - furniture_type: str
                - filter: str (MeiliSearch filter expression)
            products_per_type: Number of products to fetch per type
            price_range: Optional global price range to apply

        Returns:
            Dict mapping furniture_type to list of ProductCandidate
        """
        candidates: Dict[str, List[ProductCandidate]] = {}

        for spec in filter_specs:
            furniture_type = spec.get("furniture_type", "unknown")
            original_filter = spec.get("filter", "")

            # Build fallback filters (progressively less restrictive)
            fallback_filters = self._build_fallback_filters(original_filter)

            products = []
            used_filter = ""

            for filter_expr in fallback_filters:
                # Add price range if provided and not already in filter
                if price_range and "price" not in filter_expr:
                    min_price, max_price = price_range
                    price_filter = f"price >= {min_price} AND price <= {max_price}"
                    if filter_expr:
                        filter_expr = f"{filter_expr} AND {price_filter}"
                    else:
                        filter_expr = price_filter

                products = await self.search_products(
                    filter_expression=filter_expr,
                    limit=products_per_type,
                    sort=["average_rating:desc", "price:asc"],
                )

                if products:
                    used_filter = filter_expr
                    logger.info(
                        f"Found products for {furniture_type}",
                        count=len(products),
                        filter=filter_expr[:100],
                        fallback_level=fallback_filters.index(filter_expr.split(" AND price")[0]) if " AND price" in filter_expr else fallback_filters.index(filter_expr),
                    )
                    break
                else:
                    logger.debug(
                        f"No products with filter: {filter_expr[:80]}, trying fallback..."
                    )

            # Final fallback: Query-based search without filter
            if not products:
                logger.info(f"Trying query-based fallback for {furniture_type}")
                products = await self.search_products(
                    filter_expression="",  # No filter
                    query=furniture_type,  # Use furniture type as search query
                    limit=products_per_type,
                    sort=["average_rating:desc", "price:asc"],
                )
                if products:
                    used_filter = f"query: {furniture_type}"
                    logger.info(
                        f"Found products via query fallback for {furniture_type}",
                        count=len(products),
                    )

            if not products:
                logger.warning(
                    f"No products found for {furniture_type} even with all fallbacks",
                    original_filter=original_filter[:100],
                )

            # Set furniture type on each candidate
            for p in products:
                p.furniture_type = furniture_type

            candidates[furniture_type] = products

            logger.info(
                f"Fetched products for {furniture_type}",
                count=len(products),
                filter=used_filter[:80] if used_filter else "none",
            )

        return candidates


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_meilisearch_service: Optional[MeiliSearchService] = None


def get_meilisearch_service() -> MeiliSearchService:
    """Get or create the singleton MeiliSearch service instance."""
    global _meilisearch_service
    if _meilisearch_service is None:
        _meilisearch_service = MeiliSearchService()
    return _meilisearch_service
