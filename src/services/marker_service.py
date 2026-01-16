"""
Marker Service

Zeichnet visuelle Marker auf Staging-Bilder für Debugging/Entwicklung.
"""

import base64
import io
from typing import List, Dict, Any

from PIL import Image, ImageDraw, ImageFont
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Farben für verschiedene Produkte (RGB)
MARKER_COLORS = [
    (255, 87, 87),    # Rot
    (87, 255, 87),    # Grün
    (87, 87, 255),    # Blau
    (255, 215, 0),    # Gold
    (255, 87, 255),   # Magenta
    (87, 255, 255),   # Cyan
]


def draw_product_markers(
    image_base64: str,
    product_positions: List[Dict[str, Any]],
    line_width: int = 3,
    show_labels: bool = True,
    show_hotspots: bool = True,
) -> str:
    """
    Zeichnet Bounding Boxes und Hotspot-Marker auf ein Bild.

    Args:
        image_base64: Base64-kodiertes Eingabebild
        product_positions: Liste von Produktpositionen mit x, y, width, height (in %)
        line_width: Linienbreite für Bounding Boxes
        show_labels: Ob Produktnamen angezeigt werden sollen
        show_hotspots: Ob Hotspot-Kreise angezeigt werden sollen

    Returns:
        Base64-kodiertes Bild mit Markern
    """
    logger.info(
        "Zeichne Produktmarker",
        product_count=len(product_positions),
    )

    # Dekodiere Bild
    image_bytes = base64.b64decode(image_base64)
    image = Image.open(io.BytesIO(image_bytes))
    draw = ImageDraw.Draw(image)

    width, height = image.size

    # Versuche eine Schriftart zu laden
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        except:
            font = ImageFont.load_default()

    # Zeichne Marker für jedes Produkt
    for i, pos in enumerate(product_positions):
        color = MARKER_COLORS[i % len(MARKER_COLORS)]

        # Konvertiere Prozent zu Pixeln
        x1 = int(pos["x"] / 100 * width)
        y1 = int(pos["y"] / 100 * height)
        x2 = int((pos["x"] + pos["width"]) / 100 * width)
        y2 = int((pos["y"] + pos["height"]) / 100 * height)

        # Zeichne Bounding Box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)

        # Zeichne Label
        if show_labels:
            label = f"{pos['product_name']} ({pos['confidence']:.0%})"

            # Hintergrund für Label
            bbox = font.getbbox(label)
            label_width = bbox[2] - bbox[0]
            label_height = bbox[3] - bbox[1]

            # Label-Position (über der Box)
            label_x = x1
            label_y = max(0, y1 - label_height - 8)

            # Zeichne Label-Hintergrund
            draw.rectangle(
                [label_x, label_y, label_x + label_width + 8, label_y + label_height + 6],
                fill=color
            )

            # Zeichne Label-Text
            draw.text(
                (label_x + 4, label_y + 2),
                label,
                fill=(255, 255, 255),
                font=font
            )

        # Zeichne Hotspot
        if show_hotspots:
            hotspot_x = int(pos["hotspot_x"] / 100 * width)
            hotspot_y = int(pos["hotspot_y"] / 100 * height)

            # Äußerer Kreis
            draw.ellipse(
                [hotspot_x - 12, hotspot_y - 12, hotspot_x + 12, hotspot_y + 12],
                outline=color,
                width=3
            )

            # Innerer Punkt
            draw.ellipse(
                [hotspot_x - 4, hotspot_y - 4, hotspot_x + 4, hotspot_y + 4],
                fill=color
            )

    # Kodiere zurück zu Base64
    output_buffer = io.BytesIO()
    image.save(output_buffer, format="JPEG", quality=90)
    output_buffer.seek(0)

    result = base64.b64encode(output_buffer.read()).decode("utf-8")

    logger.info("Produktmarker gezeichnet", output_size=len(result))

    return result
