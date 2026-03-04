"""
Feedback API Router

User feedback endpoint for rating generated staging images.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.services.database_service import get_database_service
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """Request body for submitting feedback."""
    job_id: str = Field(..., description="Job UUID")
    feedback: Literal["positive", "negative"] = Field(
        ..., description="User feedback: positive or negative"
    )


class FeedbackResponse(BaseModel):
    """Response for feedback submission."""
    success: bool


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Submit user feedback for a generated staging image."""
    db = get_database_service()

    try:
        job_uuid = UUID(request.job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    # Verify job exists
    job = await db.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.submit_feedback(job_uuid, request.feedback)

    logger.info(
        "Feedback submitted",
        job_id=request.job_id,
        feedback=request.feedback,
    )

    return FeedbackResponse(success=True)
