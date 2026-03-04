"""
Database Service

PostgreSQL operations for job tracking using asyncpg.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseService:
    """
    PostgreSQL Database Service for job tracking.

    Uses asyncpg connection pool for efficient async operations.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        min_connections: int = 2,
        max_connections: int = 10,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.min_connections = min_connections
        self.max_connections = max_connections
        self._pool: Optional[Pool] = None

    async def connect(self) -> None:
        """Initialize connection pool."""
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                min_size=self.min_connections,
                max_size=self.max_connections,
            )
            logger.info(
                "Database pool erstellt",
                host=self.host,
                database=self.database,
            )
        except Exception as e:
            logger.error(f"Database-Verbindungsfehler: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool geschlossen")

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if self._pool is None:
            await self.connect()
        async with self._pool.acquire() as conn:
            yield conn

    # ═══════════════════════════════════════════════════════════════════════════════
    # JOB CRUD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def create_job(
        self,
        session_id: str,
        mode: str,
        style: str,
        total_images: int,
        room_type: Optional[str] = None,
        color_preferences: Optional[List[str]] = None,
        budget_range: Optional[Dict[str, float]] = None,
        furniture_types: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> UUID:
        """
        Create a new staging job.

        Returns:
            UUID of the created job
        """
        async with self.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO staging_jobs (
                    session_id, mode, style, total_images, room_type,
                    color_preferences, budget_range, furniture_types,
                    correlation_id, status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
                RETURNING id
                """,
                session_id,
                mode,
                style,
                total_images,
                room_type,
                json.dumps(color_preferences) if color_preferences else None,
                json.dumps(budget_range) if budget_range else None,
                json.dumps(furniture_types) if furniture_types else None,
                correlation_id,
            )
            job_id = result["id"]
            logger.info(f"Job erstellt: {job_id}", session_id=session_id)
            return job_id

    async def get_job(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, session_id, status, mode, style, room_type,
                    color_preferences, budget_range, furniture_types,
                    total_images, completed_images, current_stage, progress_percent,
                    created_at, started_at, completed_at, processing_time_ms,
                    error_message, retry_count, correlation_id
                FROM staging_jobs
                WHERE id = $1
                """,
                job_id,
            )
            if row:
                return self._row_to_dict(row)
            return None

    async def get_job_by_session_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get job by session_id."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, session_id, status, mode, style, room_type,
                    color_preferences, budget_range, furniture_types,
                    total_images, completed_images, current_stage, progress_percent,
                    created_at, started_at, completed_at, processing_time_ms,
                    error_message, retry_count, correlation_id
                FROM staging_jobs
                WHERE session_id = $1
                """,
                session_id,
            )
            if row:
                return self._row_to_dict(row)
            return None

    async def update_job_status(
        self,
        job_id: UUID,
        status: str,
        current_stage: Optional[str] = None,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        progress_percent: Optional[int] = None,
    ) -> None:
        """Update job status."""
        async with self.acquire() as conn:
            # Build dynamic update query
            updates = ["status = $2"]
            params = [job_id, status]
            param_idx = 3

            if status == "processing" and current_stage:
                updates.append(f"started_at = COALESCE(started_at, NOW())")

            if current_stage:
                updates.append(f"current_stage = ${param_idx}")
                params.append(current_stage)
                param_idx += 1

            if error_message:
                updates.append(f"error_message = ${param_idx}")
                params.append(error_message)
                param_idx += 1

            if processing_time_ms is not None:
                updates.append(f"processing_time_ms = ${param_idx}")
                params.append(processing_time_ms)
                param_idx += 1

            if progress_percent is not None:
                updates.append(f"progress_percent = ${param_idx}")
                params.append(progress_percent)
                param_idx += 1

            if status in ("completed", "failed"):
                updates.append("completed_at = NOW()")
                # Set progress to 100% on completion
                if progress_percent is None:
                    updates.append("progress_percent = 100")

            query = f"UPDATE staging_jobs SET {', '.join(updates)} WHERE id = $1"
            await conn.execute(query, *params)

            logger.info(
                f"Job-Status aktualisiert",
                job_id=str(job_id),
                status=status,
                current_stage=current_stage,
            )

    async def update_job_progress(
        self,
        job_id: UUID,
        completed_images: int,
        progress_percent: int,
        current_stage: Optional[str] = None,
    ) -> None:
        """Update job progress."""
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE staging_jobs
                SET completed_images = $2,
                    progress_percent = $3,
                    current_stage = COALESCE($4, current_stage)
                WHERE id = $1
                """,
                job_id,
                completed_images,
                progress_percent,
                current_stage,
            )

    async def list_jobs(
        self,
        status: Optional[str] = None,
        mode: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List jobs with optional filters."""
        async with self.acquire() as conn:
            # Build query with filters
            conditions = []
            params = []
            param_idx = 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if mode:
                conditions.append(f"mode = ${param_idx}")
                params.append(mode)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            params.extend([limit, offset])
            limit_idx = param_idx
            offset_idx = param_idx + 1

            query = f"""
                SELECT
                    id, session_id, status, mode, style, room_type,
                    color_preferences, budget_range, furniture_types,
                    total_images, completed_images, current_stage, progress_percent,
                    created_at, started_at, completed_at, processing_time_ms,
                    error_message, retry_count, correlation_id
                FROM staging_jobs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${limit_idx} OFFSET ${offset_idx}
            """

            rows = await conn.fetch(query, *params)
            return [self._row_to_dict(row) for row in rows]

    async def count_jobs(
        self,
        status: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> int:
        """Count jobs with optional filters."""
        async with self.acquire() as conn:
            conditions = []
            params = []
            param_idx = 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if mode:
                conditions.append(f"mode = ${param_idx}")
                params.append(mode)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"SELECT COUNT(*) as count FROM staging_jobs {where_clause}"
            result = await conn.fetchrow(query, *params)
            return result["count"]

    # ═══════════════════════════════════════════════════════════════════════════════
    # JOB IMAGES OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def create_job_image(
        self,
        job_id: UUID,
        original_filename: str,
        image_index: int,
        original_image_url: Optional[str] = None,
    ) -> UUID:
        """Create a job image record."""
        async with self.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO staging_job_images (
                    job_id, original_filename, image_index, original_image_url, status
                )
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING id
                """,
                job_id,
                original_filename,
                image_index,
                original_image_url,
            )
            return result["id"]

    async def update_job_image(
        self,
        image_id: UUID,
        status: Optional[str] = None,
        staged_image_url: Optional[str] = None,
        staged_image_with_markers_url: Optional[str] = None,
        room_analysis: Optional[Dict[str, Any]] = None,
        product_hotspots: Optional[List[Dict[str, Any]]] = None,
        furniture_added: Optional[List[str]] = None,
        processing_time_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update a job image record."""
        async with self.acquire() as conn:
            updates = []
            params = [image_id]
            param_idx = 2

            if status:
                updates.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if staged_image_url:
                updates.append(f"staged_image_url = ${param_idx}")
                params.append(staged_image_url)
                param_idx += 1

            if staged_image_with_markers_url:
                updates.append(f"staged_image_with_markers_url = ${param_idx}")
                params.append(staged_image_with_markers_url)
                param_idx += 1

            if room_analysis is not None:
                updates.append(f"room_analysis = ${param_idx}")
                params.append(json.dumps(room_analysis))
                param_idx += 1

            if product_hotspots is not None:
                updates.append(f"product_hotspots = ${param_idx}")
                params.append(json.dumps(product_hotspots))
                param_idx += 1

            if furniture_added is not None:
                updates.append(f"furniture_added = ${param_idx}")
                params.append(furniture_added)
                param_idx += 1

            if processing_time_ms is not None:
                updates.append(f"processing_time_ms = ${param_idx}")
                params.append(processing_time_ms)
                param_idx += 1

            if error_message:
                updates.append(f"error_message = ${param_idx}")
                params.append(error_message)
                param_idx += 1

            if updates:
                query = f"UPDATE staging_job_images SET {', '.join(updates)} WHERE id = $1"
                await conn.execute(query, *params)

    async def get_job_images(self, job_id: UUID) -> List[Dict[str, Any]]:
        """Get all images for a job."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, job_id, original_filename, image_index,
                    original_image_url, staged_image_url, staged_image_with_markers_url,
                    room_analysis, product_hotspots, furniture_added,
                    status, processing_time_ms, error_message, created_at
                FROM staging_job_images
                WHERE job_id = $1
                ORDER BY image_index
                """,
                job_id,
            )
            return [self._row_to_dict(row) for row in rows]

    # ═══════════════════════════════════════════════════════════════════════════════
    # SELECTED PRODUCTS OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def add_selected_product(
        self,
        job_id: UUID,
        product_id: str,
        name: str,
        furniture_type: str,
        ean: Optional[str] = None,
        price: Optional[float] = None,
        image_url: Optional[str] = None,
        images: Optional[List[str]] = None,
        selection_reason: Optional[str] = None,
    ) -> UUID:
        """Add a selected product to a job."""
        async with self.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO staging_selected_products (
                    job_id, product_id, ean, name, furniture_type,
                    price, image_url, images, selection_reason
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                job_id,
                product_id,
                ean,
                name,
                furniture_type,
                price,
                image_url,
                json.dumps(images) if images else None,
                selection_reason,
            )
            return result["id"]

    async def get_selected_products(self, job_id: UUID) -> List[Dict[str, Any]]:
        """Get all selected products for a job."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, job_id, product_id, ean, name, furniture_type,
                    price, image_url, images, selection_reason, created_at
                FROM staging_selected_products
                WHERE job_id = $1
                ORDER BY created_at
                """,
                job_id,
            )
            return [self._row_to_dict(row) for row in rows]

    # ═══════════════════════════════════════════════════════════════════════════════
    # JOB EVENTS OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def add_job_event(
        self,
        job_id: UUID,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add an event to a job."""
        async with self.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO staging_job_events (job_id, event_type, event_data)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                job_id,
                event_type,
                json.dumps(event_data) if event_data else None,
            )
            return result["id"]

    async def get_job_events(
        self,
        job_id: UUID,
        after_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get events for a job.

        Args:
            job_id: Job ID
            after_id: Only return events with id > after_id (for SSE polling)
            limit: Maximum number of events to return
        """
        async with self.acquire() as conn:
            if after_id:
                rows = await conn.fetch(
                    """
                    SELECT id, job_id, event_type, event_data, created_at
                    FROM staging_job_events
                    WHERE job_id = $1 AND id > $2
                    ORDER BY id
                    LIMIT $3
                    """,
                    job_id,
                    after_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, job_id, event_type, event_data, created_at
                    FROM staging_job_events
                    WHERE job_id = $1
                    ORDER BY id
                    LIMIT $2
                    """,
                    job_id,
                    limit,
                )
            return [self._row_to_dict(row) for row in rows]

    # ═══════════════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics."""
        async with self.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_jobs,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_jobs,
                    COUNT(*) FILTER (WHERE status = 'processing') as processing_jobs,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_jobs,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_jobs,
                    AVG(processing_time_ms) FILTER (WHERE status = 'completed') as avg_processing_time_ms,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as jobs_last_24h,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as jobs_last_7d
                FROM staging_jobs
                """
            )

            mode_counts = await conn.fetch(
                """
                SELECT mode, COUNT(*) as count
                FROM staging_jobs
                GROUP BY mode
                """
            )

            return {
                "total_jobs": stats["total_jobs"],
                "pending_jobs": stats["pending_jobs"],
                "processing_jobs": stats["processing_jobs"],
                "completed_jobs": stats["completed_jobs"],
                "failed_jobs": stats["failed_jobs"],
                "avg_processing_time_ms": float(stats["avg_processing_time_ms"] or 0),
                "jobs_last_24h": stats["jobs_last_24h"],
                "jobs_last_7d": stats["jobs_last_7d"],
                "jobs_by_mode": {row["mode"]: row["count"] for row in mode_counts},
            }

    # ═══════════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════════════════

    def _row_to_dict(self, row: asyncpg.Record) -> Dict[str, Any]:
        """Convert asyncpg Record to dict, handling JSON fields."""
        result = dict(row)

        # Parse JSON fields
        json_fields = ["color_preferences", "budget_range", "furniture_types", "room_analysis", "product_hotspots", "images", "event_data"]
        for field in json_fields:
            if field in result and result[field] is not None:
                if isinstance(result[field], str):
                    try:
                        result[field] = json.loads(result[field])
                    except json.JSONDecodeError:
                        pass

        # Convert UUID to string
        if "id" in result and isinstance(result["id"], UUID):
            result["id"] = str(result["id"])
        if "job_id" in result and isinstance(result["job_id"], UUID):
            result["job_id"] = str(result["job_id"])

        # Convert datetime to ISO format
        datetime_fields = ["created_at", "started_at", "completed_at"]
        for field in datetime_fields:
            if field in result and result[field] is not None:
                if isinstance(result[field], datetime):
                    result[field] = result[field].isoformat()

        return result

    # ═══════════════════════════════════════════════════════════════════════════════
    # FEEDBACK OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def submit_feedback(self, job_id: UUID, feedback: str) -> UUID:
        """
        Save or update user feedback for a job.

        Uses UPSERT — one feedback per job, latest wins.
        """
        async with self.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO job_feedback (job_id, feedback)
                VALUES ($1, $2)
                ON CONFLICT (job_id)
                DO UPDATE SET feedback = $2, updated_at = NOW()
                RETURNING id
                """,
                job_id,
                feedback,
            )
            logger.info(
                "Feedback gespeichert",
                job_id=str(job_id),
                feedback=feedback,
            )
            return result["id"]


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_database_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Get or create the database service singleton."""
    global _database_service
    if _database_service is None:
        from src.config import get_settings
        config = get_settings()

        _database_service = DatabaseService(
            host=config.database.host,
            port=config.database.port,
            user=config.database.user,
            password=config.database.password,
            database=config.database.database,
            min_connections=config.database.min_connections,
            max_connections=config.database.max_connections,
        )
    return _database_service
