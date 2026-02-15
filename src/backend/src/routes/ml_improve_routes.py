"""
ML Improve API Routes

REST API endpoints for feedback collection, gap analysis, and improvement workflows.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.common.authorization import PermissionChecker
from src.common.config import Settings, get_settings
from src.common.dependencies import DBSessionDep, AuditCurrentUserDep, AuditManagerDep
from src.common.features import FeatureAccessLevel
from src.controller.ml_improve_manager import MLImproveManager
from src.models.ml_improve import (
    FeedbackItem,
    FeedbackItemCreate,
    FeedbackStats,
    Gap,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml-improve", tags=["ML Improve"])


# =============================================================================
# DEPENDENCIES
# =============================================================================

def get_manager(
    request: Request,
    db: DBSessionDep,
    settings: Settings = Depends(get_settings)
) -> MLImproveManager:
    """Get MLImproveManager with dependencies injected"""
    return MLImproveManager(
        db=db,
        settings=settings,
    )


# =============================================================================
# FEEDBACK
# =============================================================================

@router.get("/feedback", response_model=List[FeedbackItem])
async def list_feedback(
    model_name: Optional[str] = None,
    feedback_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: MLImproveManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-improve', FeatureAccessLevel.READ_ONLY))
):
    """List feedback items"""
    return manager.list_feedback(
        model_name=model_name,
        feedback_type=feedback_type,
        skip=skip,
        limit=limit
    )


@router.post("/feedback", response_model=FeedbackItem, status_code=201)
async def create_feedback(
    payload: FeedbackItemCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: MLImproveManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-improve', FeatureAccessLevel.READ_WRITE))
):
    """Submit feedback on a model prediction"""
    success = False
    details = {"model_name": payload.model_name, "feedback_type": payload.feedback_type}

    try:
        result = manager.create_feedback(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create feedback: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="ml-improve-feedback",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/feedback/stats", response_model=FeedbackStats)
async def get_feedback_stats(
    model_name: Optional[str] = None,
    manager: MLImproveManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-improve', FeatureAccessLevel.READ_ONLY))
):
    """Get aggregated feedback statistics"""
    return manager.get_feedback_stats(model_name=model_name)


# =============================================================================
# GAPS
# =============================================================================

@router.get("/gaps", response_model=List[Gap])
async def list_gaps(
    model_name: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: MLImproveManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-improve', FeatureAccessLevel.READ_ONLY))
):
    """List identified gaps"""
    return manager.list_gaps(
        model_name=model_name,
        severity=severity,
        status=status,
        skip=skip,
        limit=limit
    )


# =============================================================================
# CONVERSION
# =============================================================================

@router.post("/feedback/{feedback_id}/convert", response_model=FeedbackItem)
async def convert_feedback_to_training(
    feedback_id: UUID,
    collection_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: MLImproveManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-improve', FeatureAccessLevel.READ_WRITE))
):
    """Convert a feedback item into a QA pair for training"""
    success = False
    details = {"feedback_id": str(feedback_id), "collection_id": str(collection_id)}

    try:
        result = manager.convert_feedback_to_training(
            feedback_id,
            collection_id,
            created_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="Feedback item not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to convert feedback: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="ml-improve-conversion",
            action="CONVERT",
            success=success,
            details=details
        )


# =============================================================================
# REGISTER ROUTES
# =============================================================================

def register_routes(app):
    """Register ML improve routes with the FastAPI app"""
    app.include_router(router)
