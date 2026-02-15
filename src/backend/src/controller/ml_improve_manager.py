"""
ML Improve Manager

Business logic for feedback collection, gap analysis, and training data improvement.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.common.config import Settings
from src.db_models.training_data import (
    FeedbackItemDb,
    GapRecordDb,
    GapSeverity,
    GapStatus,
    QAPairDb,
    QAPairReviewStatus,
)
from src.models.ml_improve import (
    FeedbackItem,
    FeedbackItemCreate,
    FeedbackStats,
    Gap,
)

logger = logging.getLogger(__name__)


class MLImproveManager:
    """
    Manages feedback collection and improvement workflows.

    Handles:
    - Feedback CRUD
    - Feedback statistics
    - Gap identification
    - Converting feedback to training data
    """

    def __init__(
        self,
        db: Session,
        settings: Settings,
    ):
        self._db = db
        self._settings = settings

    # =========================================================================
    # FEEDBACK
    # =========================================================================

    def list_feedback(
        self,
        model_name: Optional[str] = None,
        feedback_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[FeedbackItem]:
        """List feedback items with optional filters"""
        query = self._db.query(FeedbackItemDb)
        if model_name:
            query = query.filter(FeedbackItemDb.model_name == model_name)
        if feedback_type:
            query = query.filter(FeedbackItemDb.feedback_type == feedback_type)
        db_objs = query.order_by(FeedbackItemDb.created_at.desc()).offset(skip).limit(limit).all()
        return [FeedbackItem.model_validate(obj) for obj in db_objs]

    def create_feedback(
        self,
        payload: FeedbackItemCreate,
        created_by: Optional[str] = None
    ) -> FeedbackItem:
        """Create a feedback item"""
        db_obj = FeedbackItemDb(
            model_name=payload.model_name,
            endpoint_name=payload.endpoint_name,
            query=payload.query,
            response=payload.response,
            rating=payload.rating,
            feedback_type=payload.feedback_type,
            category=payload.category,
            comment=payload.comment,
            created_by=created_by,
        )
        self._db.add(db_obj)
        self._db.flush()
        self._db.refresh(db_obj)
        logger.info(f"Created feedback for model '{payload.model_name}' with id {db_obj.id}")
        return FeedbackItem.model_validate(db_obj)

    def get_feedback_stats(
        self,
        model_name: Optional[str] = None
    ) -> FeedbackStats:
        """Get aggregated feedback statistics"""
        query = self._db.query(FeedbackItemDb)
        if model_name:
            query = query.filter(FeedbackItemDb.model_name == model_name)

        total = query.count()
        positive = query.filter(FeedbackItemDb.feedback_type == "positive").count()
        negative = query.filter(FeedbackItemDb.feedback_type == "negative").count()
        neutral = query.filter(FeedbackItemDb.feedback_type == "neutral").count()
        converted = query.filter(FeedbackItemDb.is_converted == True).count()

        avg_rating = self._db.query(func.avg(FeedbackItemDb.rating)).filter(
            FeedbackItemDb.rating.isnot(None)
        )
        if model_name:
            avg_rating = avg_rating.filter(FeedbackItemDb.model_name == model_name)
        avg_rating_val = avg_rating.scalar()

        # Get top categories
        category_counts = self._db.query(
            FeedbackItemDb.category,
            func.count(FeedbackItemDb.id).label('count')
        ).filter(
            FeedbackItemDb.category.isnot(None)
        )
        if model_name:
            category_counts = category_counts.filter(FeedbackItemDb.model_name == model_name)
        category_counts = category_counts.group_by(FeedbackItemDb.category).order_by(
            func.count(FeedbackItemDb.id).desc()
        ).limit(10).all()

        return FeedbackStats(
            total_feedback=total,
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            avg_rating=round(float(avg_rating_val), 2) if avg_rating_val else None,
            converted_count=converted,
            top_categories=[{"category": c, "count": n} for c, n in category_counts]
        )

    # =========================================================================
    # GAPS
    # =========================================================================

    def list_gaps(
        self,
        model_name: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Gap]:
        """List identified gaps"""
        query = self._db.query(GapRecordDb)
        if model_name:
            query = query.filter(GapRecordDb.model_name == model_name)
        if severity:
            query = query.filter(GapRecordDb.severity == severity)
        if status:
            query = query.filter(GapRecordDb.status == status)
        db_objs = query.order_by(
            GapRecordDb.priority.desc(),
            GapRecordDb.created_at.desc()
        ).offset(skip).limit(limit).all()
        return [Gap.model_validate(obj) for obj in db_objs]

    # =========================================================================
    # CONVERSION
    # =========================================================================

    def convert_feedback_to_training(
        self,
        feedback_id: UUID,
        collection_id: UUID,
        created_by: Optional[str] = None
    ) -> Optional[FeedbackItem]:
        """Convert a feedback item into a QA pair for training"""
        feedback = self._db.query(FeedbackItemDb).filter(
            FeedbackItemDb.id == feedback_id
        ).first()
        if not feedback:
            return None

        if feedback.is_converted:
            raise ValueError("Feedback already converted to training pair")

        # Create QA pair from feedback
        qa_pair = QAPairDb(
            collection_id=collection_id,
            source_item_ref=f"feedback:{feedback.id}",
            messages=[
                {"role": "user", "content": feedback.query},
                {"role": "assistant", "content": feedback.response}
            ],
            review_status=QAPairReviewStatus.PENDING,
            generation_metadata={
                "source": "feedback_conversion",
                "feedback_id": str(feedback.id),
                "original_rating": feedback.rating,
                "feedback_type": feedback.feedback_type,
            },
            created_by=created_by,
        )
        self._db.add(qa_pair)
        self._db.flush()
        self._db.refresh(qa_pair)

        # Mark feedback as converted
        feedback.is_converted = True
        feedback.converted_to_pair_id = qa_pair.id
        self._db.add(feedback)
        self._db.flush()
        self._db.refresh(feedback)

        logger.info(f"Converted feedback {feedback_id} to QA pair {qa_pair.id}")
        return FeedbackItem.model_validate(feedback)
