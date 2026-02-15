"""
ML Improve Pydantic Models

API models for feedback collection, gap analysis, and improvement workflows.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackItemCreate(BaseModel):
    """Create feedback item"""
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., description="Model that produced the response")
    endpoint_name: Optional[str] = Field(None, description="Serving endpoint used")
    query: str = Field(..., description="User query")
    response: str = Field(..., description="Model response")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5")
    feedback_type: Optional[str] = Field(None, description="positive, negative, neutral")
    category: Optional[str] = Field(None, description="Issue category")
    comment: Optional[str] = Field(None, description="Free-text feedback")


class FeedbackItem(BaseModel):
    """Feedback item response"""
    id: UUID
    model_name: str
    endpoint_name: Optional[str] = None
    query: str
    response: str
    rating: Optional[int] = None
    feedback_type: Optional[str] = None
    category: Optional[str] = None
    comment: Optional[str] = None
    is_converted: bool = False
    converted_to_pair_id: Optional[UUID] = None
    created_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class FeedbackStats(BaseModel):
    """Aggregated feedback statistics"""
    total_feedback: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    avg_rating: Optional[float] = None
    converted_count: int = 0
    top_categories: List[Dict[str, Any]] = Field(default_factory=list)


class GapSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapStatus(str, Enum):
    IDENTIFIED = "identified"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class Gap(BaseModel):
    """Identified gap in model coverage"""
    id: UUID
    gap_type: str
    severity: GapSeverity
    description: str
    model_name: Optional[str] = None
    template_id: Optional[UUID] = None
    affected_queries_count: Optional[int] = None
    error_rate: Optional[float] = None
    suggested_action: Optional[str] = None
    estimated_records_needed: Optional[int] = None
    status: GapStatus = GapStatus.IDENTIFIED
    priority: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}
