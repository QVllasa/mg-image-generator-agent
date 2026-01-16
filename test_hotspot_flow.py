#!/usr/bin/env python3
"""
Test-Script für den vollständigen Flow mit Hotspot-Erkennung.

Speichert:
- Sauberes Bild (ohne Marker)
- Bild mit Markern (für Debugging)
- JSON mit Hotspot-Koordinaten
"""

import base64
import json

import httpx

# Pfad zu Test-Bildern
TEST_DIR = "test_images"


def load_image(path):
    """Lädt Bild und konvertiert zu Base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def main():
    # Lade Testbilder
    print("📁 Lade Testbilder...")
    empty_room = load_image(f"{TEST_DIR}/empty_room.jpg")
    sofa = load_image(f"{TEST_DIR}/sofa.jpg")
    couchtisch = load_image(f"{TEST_DIR}/couchtisch.jpg")
    stehlampe = load_image(f"{TEST_DIR}/stehlampe.jpg")

    # Request bauen
    request = {
        "images": [
            {"data": empty_room, "filename": "wohnzimmer.jpg"}
        ],
        "style": "modern",
        "product_images": [
            {"name": "Rotes Sofa", "data": sofa, "ean": "sofa-001"},
            {"name": "Holz-Couchtisch", "data": couchtisch, "ean": "table-001"},
            {"name": "Designer Stehlampe", "data": stehlampe, "ean": "lamp-001"}
        ]
    }

    print(f"\n🚀 Starte API Request...")
    print(f"   Stil: {request['style']}")
    print(f"   Produkte: {[p['name'] for p in request['product_images']]}")

    # API Call
    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            "http://localhost:8000/api/v1/stage-room",
            json=request
        )

    result = response.json()

    print(f"\n{'='*60}")
    print(f"✅ RESPONSE ERHALTEN")
    print(f"{'='*60}")
    print(f"   Success: {result['success']}")
    print(f"   Total Time: {result['total_processing_time_ms']}ms")

    if result['success'] and result['results']:
        img = result['results'][0]

        print(f"\n📸 Bild: {img['original_filename']}")
        print(f"   Raumtyp: {img['room_type_detected']}")
        print(f"   Möbel hinzugefügt: {img['furniture_added']}")
        print(f"   Processing: {img['processing_time_ms']}ms")
        print(f"   Retries: {img['retries']}")

        # Speichere sauberes Bild
        clean_path = f"{TEST_DIR}/result_clean.jpg"
        with open(clean_path, "wb") as f:
            f.write(base64.b64decode(img['staged_image']))
        print(f"\n💾 Sauberes Bild: {clean_path}")

        # Speichere Marker-Bild (falls vorhanden)
        if img.get('staged_image_with_markers'):
            marker_path = f"{TEST_DIR}/result_with_markers.jpg"
            with open(marker_path, "wb") as f:
                f.write(base64.b64decode(img['staged_image_with_markers']))
            print(f"💾 Bild mit Markern: {marker_path}")
        else:
            print("⚠️ Kein Marker-Bild generiert")

        # Produktpositionen anzeigen und speichern
        if img.get('product_hotspots'):
            print(f"\n📍 PRODUKT-HOTSPOTS ({len(img['product_hotspots'])} gefunden):")
            print(f"{'─'*60}")

            for i, h in enumerate(img['product_hotspots'], 1):
                print(f"\n   [{i}] {h['product_name']}")
                print(f"       Bounding Box: x={h['x']:.1f}%, y={h['y']:.1f}%")
                print(f"                     Breite: {h['width']:.1f}%, Höhe: {h['height']:.1f}%")
                print(f"       Hotspot-Punkt: ({h['hotspot_x']:.1f}%, {h['hotspot_y']:.1f}%)")
                print(f"       Confidence: {h['confidence']:.0%}")
                if h.get('product_id'):
                    print(f"       Produkt-ID: {h['product_id']}")

            # Speichere Hotspot-Daten als JSON
            hotspot_data = {
                "filename": img['original_filename'],
                "image_dimensions": "Koordinaten in % (0-100)",
                "usage_example": {
                    "css": "position: absolute; left: {x}%; top: {y}%;",
                    "tooltip": "Platziere Tooltip bei hotspot_x/hotspot_y"
                },
                "product_hotspots": img['product_hotspots']
            }

            json_path = f"{TEST_DIR}/hotspot_data.json"
            with open(json_path, "w") as f:
                json.dump(hotspot_data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Hotspot-Daten: {json_path}")
        else:
            print("\n⚠️ Keine Produkt-Hotspots gefunden")

        print(f"\n{'='*60}")
        print("✅ TEST ABGESCHLOSSEN")
        print(f"{'='*60}")
        print(f"""
Dateien gespeichert:
  - {TEST_DIR}/result_clean.jpg (für User anzeigen)
  - {TEST_DIR}/result_with_markers.jpg (für Debugging)
  - {TEST_DIR}/hotspot_data.json (für programmatische Tags)
        """)
    else:
        print(f"\n❌ FEHLER: {result.get('error')}")


if __name__ == "__main__":
    main()
