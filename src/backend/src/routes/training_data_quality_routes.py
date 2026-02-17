"""
Training Data Quality Routes

API endpoints for DQX quality gate integration:
- Check CRUD (define quality checks per collection)
- Run quality checks (mock locally, DQX on Spark)
- Validate collection for training export
- Import DQX results from VITAL proxy
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.common.config import Settings, get_settings
from src.common.dependencies import AuditCurrentUserDep, DBSessionDep
from src.controller.training_data_quality_manager import TrainingDataQualityManager
from src.models.training_data_quality import (
    DQXResultImport,
    QualityCheck,
    QualityCheckCreate,
    QualityRun,
    QualityRunCreate,
    ValidationResult,
)

router = APIRouter(
    prefix="/api/training-data/quality",
    tags=["Training Data Quality"],
)


def get_quality_manager(
    db: DBSessionDep,
    settings: Settings = Depends(get_settings),
) -> TrainingDataQualityManager:
    return TrainingDataQualityManager(db=db, settings=settings)


# =============================================================================
# CHECKS — Define quality checks per collection
# =============================================================================


@router.post(
    "/collections/{collection_id}/checks",
    response_model=QualityCheck,
    status_code=status.HTTP_201_CREATED,
)
async def create_check(
    collection_id: UUID,
    payload: QualityCheckCreate,
    current_user: AuditCurrentUserDep,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """Create a quality check definition for a collection."""
    payload.collection_id = collection_id
    try:
        return manager.create_check(payload, created_by=current_user.username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/collections/{collection_id}/checks",
    response_model=List[QualityCheck],
)
async def list_checks(
    collection_id: UUID,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """List all quality checks for a collection."""
    return manager.list_checks(collection_id)


@router.delete(
    "/checks/{check_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_check(
    check_id: UUID,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """Delete a quality check definition."""
    if not manager.delete_check(check_id):
        raise HTTPException(status_code=404, detail="Check not found")


# =============================================================================
# RUNS — Execute quality checks
# =============================================================================


@router.post(
    "/collections/{collection_id}/runs",
    response_model=QualityRun,
    status_code=status.HTTP_201_CREATED,
)
async def run_quality_checks(
    collection_id: UUID,
    payload: QualityRunCreate = None,
    current_user: AuditCurrentUserDep = None,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """Execute quality checks against a collection's QA pairs."""
    source = payload.source if payload else "mock"
    try:
        return manager.run_quality_checks(
            collection_id,
            source=source,
            created_by=current_user.username if current_user else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quality check run failed: {e}")


@router.get(
    "/collections/{collection_id}/runs",
    response_model=List[QualityRun],
)
async def list_runs(
    collection_id: UUID,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """List all quality runs for a collection."""
    return manager.list_runs(collection_id)


# =============================================================================
# VALIDATION — Gate for training export
# =============================================================================


@router.get(
    "/collections/{collection_id}/validate",
    response_model=ValidationResult,
)
async def validate_for_training(
    collection_id: UUID,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """Check if a collection passes the quality gate for training export."""
    return manager.validate_for_training(collection_id)


# =============================================================================
# DQX IMPORT — Accept results from VITAL proxy
# =============================================================================


@router.post(
    "/collections/{collection_id}/import-dqx-results",
    response_model=QualityRun,
    status_code=status.HTTP_201_CREATED,
)
async def import_dqx_results(
    collection_id: UUID,
    payload: DQXResultImport,
    current_user: AuditCurrentUserDep = None,
    manager: TrainingDataQualityManager = Depends(get_quality_manager),
):
    """Import quality check results pushed from VITAL's DQX proxy."""
    try:
        return manager.import_dqx_results(
            collection_id,
            payload,
            created_by=current_user.username if current_user else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DQX import failed: {e}")


# =============================================================================
# ROUTE REGISTRATION
# =============================================================================


def register_routes(app):
    app.include_router(router)
