#!/usr/bin/env python3
"""
Test Client für Room Stager API

Lädt ein Testbild und sendet es an die API.
Speichert das Ergebnis lokal.
"""

import base64
import sys
from pathlib import Path

import requests


def load_image_as_base64(image_path: str) -> str:
    """Lädt ein Bild und konvertiert es zu Base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def save_base64_image(base64_data: str, output_path: str):
    """Speichert Base64-Daten als Bilddatei."""
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(base64_data))
    print(f"Bild gespeichert: {output_path}")


def test_staging(
    image_path: str,
    api_url: str = "http://localhost:8000/api/v1/stage-room",
    style: str = "modern",
):
    """
    Testet die Room Staging API.

    Args:
        image_path: Pfad zum Testbild
        api_url: URL der API
        style: Einrichtungsstil
    """
    print(f"\n{'='*60}")
    print("Room Stager Test Client")
    print(f"{'='*60}\n")

    # Lade Bild
    print(f"Lade Bild: {image_path}")
    if not Path(image_path).exists():
        print(f"FEHLER: Datei nicht gefunden: {image_path}")
        sys.exit(1)

    image_base64 = load_image_as_base64(image_path)
    filename = Path(image_path).name
    print(f"Bildgröße: {len(image_base64) / 1024:.1f} KB (Base64)")

    # Erstelle Request
    request_data = {
        "images": [
            {
                "data": image_base64,
                "filename": filename,
            }
        ],
        "style": style,
    }

    # Sende Request
    print(f"\nSende Request an: {api_url}")
    print(f"Stil: {style}")
    print("Bitte warten... (kann 30-60 Sekunden dauern)")

    try:
        response = requests.post(
            api_url,
            json=request_data,
            timeout=300,  # 5 Minuten Timeout
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("\nFEHLER: Konnte nicht mit API verbinden.")
        print("Ist der Server gestartet? (uvicorn src.main:app --reload)")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("\nFEHLER: Request Timeout.")
        sys.exit(1)

    # Verarbeite Response
    result = response.json()
    print(f"\n{'='*60}")
    print("ERGEBNIS")
    print(f"{'='*60}")
    print(f"Erfolg: {result['success']}")
    print(f"Verarbeitungszeit: {result['total_processing_time_ms']} ms")
    print(f"Correlation ID: {result.get('correlation_id', 'N/A')}")

    if result.get("error"):
        print(f"Fehler: {result['error']}")

    # Speichere Ergebnisse
    if result["results"]:
        output_dir = Path("test_outputs")
        output_dir.mkdir(exist_ok=True)

        for i, img_result in enumerate(result["results"]):
            output_filename = f"staged_{Path(img_result['original_filename']).stem}_{i}.jpg"
            output_path = output_dir / output_filename

            save_base64_image(img_result["staged_image"], str(output_path))

            print(f"\nBild {i+1}:")
            print(f"  - Original: {img_result['original_filename']}")
            print(f"  - Raumtyp: {img_result.get('room_type_detected', 'N/A')}")
            print(f"  - Möbel: {', '.join(img_result['furniture_added'])}")
            print(f"  - Zeit: {img_result['processing_time_ms']} ms")
            print(f"  - Retries: {img_result['retries']}")
    else:
        print("\nKeine Ergebnisse erhalten.")

    print(f"\n{'='*60}")
    print("Test abgeschlossen!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_client.py <image_path> [style]")
        print("")
        print("Example:")
        print("  python test_client.py empty_room.jpg modern")
        print("")
        print("Styles: modern, scandinavian, industrial, classic, minimalist")
        sys.exit(1)

    image_path = sys.argv[1]
    style = sys.argv[2] if len(sys.argv) > 2 else "modern"

    test_staging(image_path, style=style)
