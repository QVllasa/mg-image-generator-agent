"""
Storage Service

MinIO/S3-compatible storage operations for image persistence.
"""

import base64
import io
from typing import Optional
from urllib.parse import urljoin

from minio import Minio
from minio.error import S3Error

from src.utils.logging import get_logger

logger = get_logger(__name__)


class StorageService:
    """
    MinIO/S3 Storage Service for image persistence.

    URL Structure:
    {bucket}/{session_id}/
      ├── original_{filename}.jpg
      ├── staged_{filename}.jpg
      ├── staged_{filename}_markers.jpg
      └── products/
          └── {furniture_type}_{product_id}.jpg
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        public_url: Optional[str] = None,
    ):
        self.endpoint = endpoint
        self.bucket = bucket
        self.secure = secure
        self.public_url = public_url or f"{'https' if secure else 'http'}://{endpoint}"

        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

        logger.info(
            "Storage Service initialisiert",
            endpoint=endpoint,
            bucket=bucket,
            public_url=self.public_url,
        )

    def ensure_bucket(self) -> None:
        """Ensure the bucket exists, create if not."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Bucket erstellt: {self.bucket}")
            else:
                logger.info(f"Bucket existiert bereits: {self.bucket}")
        except S3Error as e:
            logger.error(f"Bucket-Fehler: {e}")
            raise

    def _build_path(self, session_id: str, filename: str, prefix: str = "") -> str:
        """Build object path."""
        if prefix:
            return f"{session_id}/{prefix}/{filename}"
        return f"{session_id}/{filename}"

    def _build_public_url(self, object_name: str) -> str:
        """Build public URL for an object."""
        return f"{self.public_url}/{self.bucket}/{object_name}"

    # ═══════════════════════════════════════════════════════════════════════════════
    # UPLOAD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    def upload_image_base64(
        self,
        session_id: str,
        filename: str,
        image_base64: str,
        prefix: str = "",
        content_type: str = "image/jpeg",
    ) -> str:
        """
        Upload a base64-encoded image to storage.

        Args:
            session_id: Session ID for path
            filename: Filename for the image
            image_base64: Base64-encoded image data
            prefix: Optional path prefix (e.g., "products")
            content_type: MIME type

        Returns:
            Public URL of the uploaded image
        """
        try:
            # Decode base64
            image_data = base64.b64decode(image_base64)
            image_stream = io.BytesIO(image_data)
            image_size = len(image_data)

            # Build path
            object_name = self._build_path(session_id, filename, prefix)

            # Upload
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=image_stream,
                length=image_size,
                content_type=content_type,
            )

            url = self._build_public_url(object_name)
            logger.info(f"Bild hochgeladen: {object_name}")
            return url

        except S3Error as e:
            logger.error(f"Upload-Fehler: {e}")
            raise
        except Exception as e:
            logger.error(f"Upload-Fehler (base64): {e}")
            raise

    def upload_image_bytes(
        self,
        session_id: str,
        filename: str,
        image_bytes: bytes,
        prefix: str = "",
        content_type: str = "image/jpeg",
    ) -> str:
        """
        Upload image bytes to storage.

        Args:
            session_id: Session ID for path
            filename: Filename for the image
            image_bytes: Raw image bytes
            prefix: Optional path prefix
            content_type: MIME type

        Returns:
            Public URL of the uploaded image
        """
        try:
            image_stream = io.BytesIO(image_bytes)
            image_size = len(image_bytes)

            object_name = self._build_path(session_id, filename, prefix)

            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=image_stream,
                length=image_size,
                content_type=content_type,
            )

            url = self._build_public_url(object_name)
            logger.info(f"Bild hochgeladen: {object_name}")
            return url

        except S3Error as e:
            logger.error(f"Upload-Fehler: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════════════
    # SPECIALIZED UPLOAD METHODS
    # ═══════════════════════════════════════════════════════════════════════════════

    def upload_original_image(
        self,
        session_id: str,
        filename: str,
        image_base64: str,
    ) -> str:
        """Upload original room image."""
        # Clean filename
        clean_name = filename.replace(".jpg", "").replace(".jpeg", "").replace(".png", "")
        upload_filename = f"original_{clean_name}.jpg"
        return self.upload_image_base64(session_id, upload_filename, image_base64)

    def upload_staged_image(
        self,
        session_id: str,
        filename: str,
        image_base64: str,
    ) -> str:
        """Upload staged room image."""
        clean_name = filename.replace(".jpg", "").replace(".jpeg", "").replace(".png", "")
        upload_filename = f"staged_{clean_name}.jpg"
        return self.upload_image_base64(session_id, upload_filename, image_base64)

    def upload_staged_image_with_markers(
        self,
        session_id: str,
        filename: str,
        image_base64: str,
    ) -> str:
        """Upload staged room image with hotspot markers."""
        clean_name = filename.replace(".jpg", "").replace(".jpeg", "").replace(".png", "")
        upload_filename = f"staged_{clean_name}_markers.jpg"
        return self.upload_image_base64(session_id, upload_filename, image_base64)

    def upload_product_image(
        self,
        session_id: str,
        furniture_type: str,
        product_id: str,
        image_bytes: bytes,
        image_index: int = 1,
    ) -> str:
        """Upload a product reference image."""
        filename = f"{furniture_type}_{product_id}_img{image_index}.jpg"
        return self.upload_image_bytes(
            session_id=session_id,
            filename=filename,
            image_bytes=image_bytes,
            prefix="products",
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # DOWNLOAD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    def download_image_base64(self, session_id: str, filename: str, prefix: str = "") -> Optional[str]:
        """
        Download an image and return as base64.

        Returns:
            Base64-encoded image data, or None if not found
        """
        try:
            object_name = self._build_path(session_id, filename, prefix)
            response = self.client.get_object(self.bucket, object_name)
            image_data = response.read()
            response.close()
            response.release_conn()

            return base64.b64encode(image_data).decode("utf-8")

        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"Bild nicht gefunden: {object_name}")
                return None
            logger.error(f"Download-Fehler: {e}")
            raise

    def download_image_bytes(self, session_id: str, filename: str, prefix: str = "") -> Optional[bytes]:
        """
        Download an image as bytes.

        Returns:
            Raw image bytes, or None if not found
        """
        try:
            object_name = self._build_path(session_id, filename, prefix)
            response = self.client.get_object(self.bucket, object_name)
            image_data = response.read()
            response.close()
            response.release_conn()

            return image_data

        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"Bild nicht gefunden: {object_name}")
                return None
            logger.error(f"Download-Fehler: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════════════
    # LIST & DELETE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    def list_session_images(self, session_id: str) -> list[dict]:
        """List all images for a session."""
        try:
            objects = self.client.list_objects(
                bucket_name=self.bucket,
                prefix=f"{session_id}/",
                recursive=True,
            )

            images = []
            for obj in objects:
                images.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "url": self._build_public_url(obj.object_name),
                })

            return images

        except S3Error as e:
            logger.error(f"List-Fehler: {e}")
            raise

    def delete_session_images(self, session_id: str) -> int:
        """Delete all images for a session."""
        try:
            objects = self.client.list_objects(
                bucket_name=self.bucket,
                prefix=f"{session_id}/",
                recursive=True,
            )

            deleted_count = 0
            for obj in objects:
                self.client.remove_object(self.bucket, obj.object_name)
                deleted_count += 1

            logger.info(f"{deleted_count} Bilder gelöscht für Session: {session_id}")
            return deleted_count

        except S3Error as e:
            logger.error(f"Delete-Fehler: {e}")
            raise

    def get_image_url(self, session_id: str, filename: str, prefix: str = "") -> str:
        """Get public URL for an image."""
        object_name = self._build_path(session_id, filename, prefix)
        return self._build_public_url(object_name)

    # ═══════════════════════════════════════════════════════════════════════════════
    # HEALTH CHECK
    # ═══════════════════════════════════════════════════════════════════════════════

    def health_check(self) -> bool:
        """Check if storage is accessible."""
        try:
            self.client.bucket_exists(self.bucket)
            return True
        except Exception as e:
            logger.error(f"Storage health check fehlgeschlagen: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get or create the storage service singleton."""
    global _storage_service
    if _storage_service is None:
        from src.config import get_settings
        config = get_settings()

        _storage_service = StorageService(
            endpoint=config.storage.endpoint,
            access_key=config.storage.access_key,
            secret_key=config.storage.secret_key,
            bucket=config.storage.bucket,
            secure=config.storage.secure,
            public_url=config.storage.public_url,
        )
    return _storage_service
