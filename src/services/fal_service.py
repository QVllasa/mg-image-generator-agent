"""
fal.ai Service

Verwendet fal.ai FLUX.2 [dev] Edit für Room Staging.
Natural Language Editing - beschreibe die gewünschten Änderungen im Prompt.
Kein Mask erforderlich, günstiger ($0.012/MP) und State-of-the-Art (Nov 2025).
"""

import base64
import time
from typing import Optional

import fal_client
from src.config import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2.0


class FalService:
    """
    Service für Bildgenerierung mit fal.ai.

    Verwendet FLUX.2 [dev] Edit für Room Staging.
    Natural Language Editing - beschreibe Änderungen im Prompt.
    """

    def __init__(self):
        """Initialisiert den fal.ai Service."""
        config = get_settings()
        self.api_key = config.fal.api_key
        self.model = config.fal.model
        self.timeout = config.fal.timeout

        # Setze API Key für fal_client
        fal_client.api_key = self.api_key

        logger.info(
            "FalService initialisiert",
            model=self.model,
        )

    def generate_staged_image(
        self,
        image_base64: str,
        prompt: str,
        guidance_scale: float = 2.5,
        num_inference_steps: int = 28,
    ) -> str:
        """
        Generiert ein Staging-Bild mit fal.ai FLUX.2 [dev] Edit.

        Args:
            image_base64: Base64-kodiertes Eingabebild
            prompt: Natural Language Beschreibung der gewünschten Änderungen
                   z.B. "Add a modern grey sofa and a wooden coffee table to this empty living room"
            guidance_scale: Wie stark der Prompt befolgt wird (default: 2.5)
            num_inference_steps: Anzahl der Inference Steps (default: 28)

        Returns:
            Base64-kodiertes Ergebnisbild
        """
        logger.info(
            "Starte Bildgenerierung mit FLUX.2",
            prompt_length=len(prompt),
            guidance_scale=guidance_scale,
        )

        # Erstelle Data URL für das Bild
        image_data_url = f"data:image/jpeg;base64,{image_base64}"

        # fal.ai Request für FLUX.2 [dev] Edit
        # Siehe: https://fal.ai/models/fal-ai/flux-2/edit/api
        request_data = {
            "image_urls": [image_data_url],  # FLUX.2 verwendet Array!
            "prompt": prompt,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "output_format": "jpeg",
            "enable_safety_checker": True,
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                start_time = time.time()

                # Rufe fal.ai API auf
                result = fal_client.subscribe(
                    self.model,
                    arguments=request_data,
                    with_logs=False,
                )

                duration = time.time() - start_time
                logger.info(
                    "Bildgenerierung erfolgreich",
                    duration_seconds=round(duration, 2),
                )

                # Extrahiere Bild aus Response
                if "images" in result and len(result["images"]) > 0:
                    image_data = result["images"][0]

                    # fal.ai gibt entweder URL oder Base64 zurück
                    if "url" in image_data:
                        # Lade Bild von URL und konvertiere zu Base64
                        import httpx
                        response = httpx.get(image_data["url"], timeout=30)
                        response.raise_for_status()
                        return base64.b64encode(response.content).decode("utf-8")

                    elif "base64" in image_data:
                        return image_data["base64"]

                    elif "content" in image_data:
                        return image_data["content"]

                raise ValueError("Keine Bilddaten in fal.ai Response gefunden")

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"fal.ai Fehler (Versuch {attempt + 1}/{MAX_RETRIES})",
                        error=str(e)[:200],
                    )
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(
                        f"fal.ai fehlgeschlagen nach {MAX_RETRIES} Versuchen",
                        error=str(e),
                    )

        raise last_error

    def generate_with_product_images(
        self,
        room_base64: str,
        product_images: list[dict],
        style: str = "modern",
        creative_prompt: Optional[str] = None,
        guidance_scale: float = 3.5,
        num_inference_steps: int = 28,
    ) -> str:
        """
        Generiert ein Staging-Bild mit echten Produktbildern (Multi-Reference).

        Args:
            room_base64: Base64-kodiertes Raumbild
            product_images: Liste von Produkten mit {"name": str, "base64": str}
            style: Einrichtungsstil
            creative_prompt: Optional kreativer Prompt von Qwen3-VL
            guidance_scale: Prompt-Stärke (default: 3.5)
            num_inference_steps: Inference Steps (default: 28)

        Returns:
            Base64-kodiertes Ergebnisbild mit platzierten Produkten
        """
        logger.info(
            "Starte Multi-Reference Staging",
            product_count=len(product_images),
            style=style,
            has_creative_prompt=creative_prompt is not None,
        )

        # Erstelle image_urls Array: [room, product1, product2, ...]
        image_urls = [f"data:image/jpeg;base64,{room_base64}"]
        for product in product_images:
            image_urls.append(f"data:image/jpeg;base64,{product['base64']}")

        # Verwende kreativen Prompt falls vorhanden, sonst Standard-Template
        if creative_prompt:
            # Erweitere den kreativen Prompt mit Bild-Referenzen
            prompt_parts = [
                creative_prompt,
                "",
                "Reference images:",
                "- Image 1: The empty room",
            ]
            for i, product in enumerate(product_images, start=2):
                name = product.get("name", f"furniture item {i-1}")
                prompt_parts.append(f"- Image {i}: {name}")
            prompt_parts.append("")
            prompt_parts.append("Place each furniture item from its reference image into the room. "
                               "Maintain photorealistic quality, correct perspective and natural lighting.")
            prompt = "\n".join(prompt_parts)
        else:
            # Fallback: Standard-Template
            prompt_parts = [
                f"Place the furniture from the reference images into the room from image 1.",
                f"Style: {style}, photorealistic interior design photography.",
            ]
            for i, product in enumerate(product_images, start=2):
                name = product.get("name", f"furniture item {i-1}")
                prompt_parts.append(f"- Add the {name} from image {i}")
            prompt_parts.append("Keep the original room lighting and perspective. Make it look realistic.")
            prompt = "\n".join(prompt_parts)

        logger.info("Multi-Reference Prompt", prompt=prompt[:500])

        # fal.ai Request
        request_data = {
            "image_urls": image_urls,
            "prompt": prompt,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "output_format": "jpeg",
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                start_time = time.time()

                result = fal_client.subscribe(
                    self.model,
                    arguments=request_data,
                    with_logs=False,
                )

                duration = time.time() - start_time
                logger.info(
                    "Multi-Reference Staging erfolgreich",
                    duration_seconds=round(duration, 2),
                    image_count=len(image_urls),
                )

                if "images" in result and len(result["images"]) > 0:
                    image_data = result["images"][0]

                    if "url" in image_data:
                        import httpx
                        response = httpx.get(image_data["url"], timeout=30)
                        response.raise_for_status()
                        return base64.b64encode(response.content).decode("utf-8")
                    elif "base64" in image_data:
                        return image_data["base64"]

                raise ValueError("Keine Bilddaten in Response")

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Multi-Reference Fehler (Versuch {attempt + 1}/{MAX_RETRIES})",
                        error=str(e)[:200],
                    )
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Multi-Reference fehlgeschlagen", error=str(e))

        raise last_error

    def create_staging_prompt(
        self,
        room_type: str,
        furniture_list: list[str],
        style: str,
        empty_areas: list[str],
    ) -> str:
        """
        Erstellt einen optimierten Prompt für Room Staging.

        Args:
            room_type: Art des Raums
            furniture_list: Liste der gewünschten Möbel
            style: Einrichtungsstil
            empty_areas: Beschreibung der leeren Bereiche

        Returns:
            Optimierter Prompt für FLUX Fill
        """
        furniture_str = ", ".join(furniture_list) if furniture_list else "furniture"
        areas_str = " and ".join(empty_areas[:2]) if empty_areas else "empty space"

        prompt = (
            f"Professional interior design photo of a {style} {room_type}. "
            f"Add {furniture_str} in the {areas_str}. "
            f"High-end {style} furniture with realistic shadows and lighting. "
            f"Magazine quality interior photography, natural lighting, "
            f"photorealistic rendering, 4K quality, professional staging."
        )

        return prompt


# Singleton
_fal_service: Optional[FalService] = None


def get_fal_service() -> FalService:
    """Holt oder erstellt den Singleton FalService."""
    global _fal_service
    if _fal_service is None:
        _fal_service = FalService()
    return _fal_service
