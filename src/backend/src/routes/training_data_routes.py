"""
ML Training Data API Routes

REST API endpoints for QA pairs, canonical labels, templates, and training collections.
Follows Ontos's route pattern with dependency injection, permissions, and audit logging.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.common.authorization import PermissionChecker
from src.common.config import Settings, get_settings
from src.common.dependencies import DBSessionDep, AuditCurrentUserDep, AuditManagerDep
from src.common.features import FeatureAccessLevel
from src.common.llm_service import LLMService
from src.common.workspace_client import get_obo_workspace_client, get_workspace_client
from src.controller.training_data_manager import TrainingDataManager
from src.db_models.training_data import (
    LabelType,
    QAPairReviewStatus,
    TemplateStatus,
    TrainingSheetStatus,
)
from src.models.training_data import (
    CanonicalLabel,
    CanonicalLabelCreate,
    CanonicalLabelUpdate,
    ChatMessage,
    DSPyExportRequest,
    DSPyExportResult,
    DSPyRun,
    DSPyRunCreate,
    Example,
    ExampleCreate,
    ExampleSearchQuery,
    ExampleUpdate,
    ExportFormat,
    ExportRequest,
    ExportResult,
    GenerationRequest,
    GenerationResult,
    ModelLineage,
    ModelLineageCreate,
    PromptTemplate,
    PromptTemplateCreate,
    PromptTemplateUpdate,
    QAPair,
    QAPairBulkReview,
    QAPairCreate,
    QAPairsByConceptQuery,
    QAPairUpdate,
    Sheet,
    SheetCreate,
    SheetUpdate,
    TrainingCollection,
    TrainingCollectionCreate,
    TrainingCollectionUpdate,
    TrainingDataGap,
    TrainingJob,
    TrainingJobCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/training-data", tags=["ML Training Data"])


# =============================================================================
# DEPENDENCIES
# =============================================================================

def get_manager(
    request: Request,
    db: DBSessionDep,
    settings: Settings = Depends(get_settings)
) -> TrainingDataManager:
    """Get TrainingDataManager with dependencies injected"""
    # Get workspace client - prefer OBO for user permissions, fallback to service principal
    workspace_client = None
    try:
        workspace_client = get_obo_workspace_client(request, settings)
    except Exception:
        try:
            workspace_client = get_workspace_client(settings)
        except Exception as e:
            logger.warning(f"Could not get workspace client: {e}")

    llm_service = getattr(request.app.state, 'llm_service', None) or LLMService(settings)
    semantic_models_manager = getattr(request.app.state, 'semantic_models_manager', None)

    return TrainingDataManager(
        db=db,
        settings=settings,
        workspace_client=workspace_client,
        llm_service=llm_service,
        semantic_models_manager=semantic_models_manager
    )


def get_user_token(request: Request) -> Optional[str]:
    """Extract user token from request for Databricks Apps context"""
    # In Databricks Apps, the user token is passed via header
    return request.headers.get("X-Databricks-Token")


# =============================================================================
# SHEETS
# =============================================================================

@router.post("/sheets", response_model=Sheet, status_code=201)
async def create_sheet(
    payload: SheetCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create a new sheet (data source pointer)"""
    success = False
    details = {"params": payload.model_dump(exclude_none=True)}

    try:
        result = manager.create_sheet(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create sheet: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-sheets",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/sheets", response_model=List[Sheet])
async def list_sheets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    owner_id: Optional[str] = None,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List sheets"""
    return manager.list_sheets(skip=skip, limit=limit, owner_id=owner_id)


@router.get("/sheets/{sheet_id}", response_model=Sheet)
async def get_sheet(
    sheet_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get sheet by ID"""
    result = manager.get_sheet(sheet_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sheet not found")
    return result


@router.post("/sheets/{sheet_id}/validate")
async def validate_sheet_source(
    sheet_id: UUID,
    request: Request,
    manager: TrainingDataManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Validate that sheet's data source exists and is accessible"""
    from src.connectors.unity_catalog_data_connector import create_connector_from_sheet
    from src.repositories.training_data_repository import sheets_repository

    sheet = sheets_repository.get(manager._db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")

    # Get workspace client
    workspace_client = manager._workspace_client
    if not workspace_client:
        return {
            "valid": False,
            "error": "No workspace client available - cannot validate data source"
        }

    try:
        connector, config = create_connector_from_sheet(sheet, workspace_client, settings)
        is_valid, error = connector.validate_source(config)

        if is_valid:
            # Get schema info for tables
            schema_info = None
            if config.table:
                schema_info = connector.get_table_schema(
                    config.catalog, config.schema, config.table
                )

            return {
                "valid": True,
                "source": f"{config.catalog}.{config.schema}.{config.table or config.volume_path}",
                "schema": schema_info
            }
        else:
            return {"valid": False, "error": error}

    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.put("/sheets/{sheet_id}", response_model=Sheet)
async def update_sheet(
    sheet_id: UUID,
    payload: SheetUpdate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Update a sheet"""
    success = False
    details = {"sheet_id": str(sheet_id)}

    try:
        result = manager.update_sheet(
            sheet_id,
            payload,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="Sheet not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update sheet: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-sheets",
            action="UPDATE",
            success=success,
            details=details
        )


@router.delete("/sheets/{sheet_id}")
async def delete_sheet(
    sheet_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Delete a sheet"""
    success = False
    details = {"sheet_id": str(sheet_id)}

    try:
        deleted = manager.delete_sheet(sheet_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Sheet not found")
        db.commit()
        success = True
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete sheet: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-sheets",
            action="DELETE",
            success=success,
            details=details
        )


@router.get("/sheets/{sheet_id}/preview")
async def preview_sheet_data(
    sheet_id: UUID,
    request: Request,
    limit: int = Query(5, ge=1, le=20),
    manager: TrainingDataManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Preview a sample of data from the sheet's source"""
    from src.connectors.unity_catalog_data_connector import create_connector_from_sheet
    from src.repositories.training_data_repository import sheets_repository

    sheet = sheets_repository.get(manager._db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")

    # Get workspace client
    workspace_client = manager._workspace_client
    if not workspace_client:
        # Return mock preview
        mock_data = manager._get_mock_data(sheet, limit)
        return {
            "items": mock_data,
            "count": len(mock_data),
            "source": "mock",
            "warning": "No workspace client - showing mock data"
        }

    try:
        connector, config = create_connector_from_sheet(sheet, workspace_client, settings)
        result = connector.preview_data(config, limit=limit)

        return {
            "items": result.items,
            "count": result.sampled_count,
            "total_available": result.total_count,
            "source": result.source,
            "columns": result.columns
        }

    except Exception as e:
        logger.error(f"Failed to preview sheet data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

@router.post("/templates", response_model=PromptTemplate, status_code=201)
async def create_template(
    payload: PromptTemplateCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create a new prompt template"""
    success = False
    details = {"params": {"name": payload.name, "version": payload.version}}

    try:
        result = manager.create_template(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create template: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-templates",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/templates", response_model=List[PromptTemplate])
async def list_templates(
    status: Optional[TemplateStatus] = None,
    label_type: Optional[LabelType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List templates with optional filters"""
    return manager.list_templates(status=status, label_type=label_type, skip=skip, limit=limit)


@router.get("/templates/{template_id}", response_model=PromptTemplate)
async def get_template(
    template_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get template by ID"""
    result = manager.get_template(template_id)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.put("/templates/{template_id}", response_model=PromptTemplate)
async def update_template(
    template_id: UUID,
    payload: PromptTemplateUpdate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Update a prompt template"""
    success = False
    details = {"template_id": str(template_id)}

    try:
        result = manager.update_template(
            template_id,
            payload,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update template: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-templates",
            action="UPDATE",
            success=success,
            details=details
        )


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Delete a prompt template"""
    success = False
    details = {"template_id": str(template_id)}

    try:
        deleted = manager.delete_template(template_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Template not found")
        db.commit()
        success = True
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-templates",
            action="DELETE",
            success=success,
            details=details
        )


# =============================================================================
# CANONICAL LABELS
# =============================================================================

@router.post("/canonical-labels", response_model=CanonicalLabel, status_code=201)
async def create_canonical_label(
    payload: CanonicalLabelCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create or update a canonical label (ground truth)"""
    success = False
    details = {"params": {"sheet_id": str(payload.sheet_id), "item_ref": payload.item_ref, "label_type": payload.label_type.value}}

    try:
        result = manager.create_canonical_label(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create canonical label: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-labels",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/canonical-labels", response_model=List[CanonicalLabel])
async def list_canonical_labels(
    sheet_id: Optional[UUID] = None,
    label_type: Optional[LabelType] = None,
    only_verified: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List canonical labels with optional filters"""
    return manager.list_canonical_labels(
        sheet_id=sheet_id,
        label_type=label_type,
        only_verified=only_verified,
        skip=skip,
        limit=limit
    )


@router.get("/canonical-labels/{label_id}", response_model=CanonicalLabel)
async def get_canonical_label(
    label_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get canonical label by ID"""
    result = manager.get_canonical_label(label_id)
    if not result:
        raise HTTPException(status_code=404, detail="Canonical label not found")
    return result


@router.post("/canonical-labels/{label_id}/verify", response_model=CanonicalLabel)
async def verify_canonical_label(
    label_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Mark a canonical label as verified"""
    success = False
    details = {"label_id": str(label_id)}

    try:
        result = manager.verify_canonical_label(
            label_id,
            verified_by=current_user.username if current_user else "anonymous"
        )
        if not result:
            raise HTTPException(status_code=404, detail="Canonical label not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify canonical label: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-labels",
            action="VERIFY",
            success=success,
            details=details
        )


@router.put("/canonical-labels/{label_id}", response_model=CanonicalLabel)
async def update_canonical_label(
    label_id: UUID,
    payload: CanonicalLabelUpdate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Update a canonical label"""
    success = False
    details = {"label_id": str(label_id)}

    try:
        result = manager.update_canonical_label(
            label_id,
            payload,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="Canonical label not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update canonical label: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-labels",
            action="UPDATE",
            success=success,
            details=details
        )


@router.delete("/canonical-labels/{label_id}")
async def delete_canonical_label(
    label_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Delete a canonical label"""
    success = False
    details = {"label_id": str(label_id)}

    try:
        deleted = manager.delete_canonical_label(label_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Canonical label not found")
        db.commit()
        success = True
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete canonical label: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-labels",
            action="DELETE",
            success=success,
            details=details
        )


# =============================================================================
# TRAINING COLLECTIONS
# =============================================================================

@router.post("/collections", response_model=TrainingCollection, status_code=201)
async def create_collection(
    payload: TrainingCollectionCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create a new training collection"""
    success = False
    details = {"params": {"name": payload.name, "version": payload.version}}

    try:
        result = manager.create_collection(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create collection: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-collections",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/collections", response_model=List[TrainingCollection])
async def list_collections(
    status: Optional[TrainingSheetStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List training collections"""
    return manager.list_collections(status=status, skip=skip, limit=limit)


@router.get("/collections/{collection_id}", response_model=TrainingCollection)
async def get_collection(
    collection_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get collection by ID"""
    result = manager.get_collection(collection_id)
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


# =============================================================================
# QA PAIR GENERATION
# =============================================================================

@router.post("/collections/{collection_id}/generate", response_model=GenerationResult)
async def generate_qa_pairs(
    collection_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    sheet_id: Optional[UUID] = None,
    template_id: Optional[UUID] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    sample_size: Optional[int] = Query(None, ge=1, le=10000),
    auto_approve_with_canonical: bool = True,
    link_to_canonical: bool = True,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Generate QA pairs using LLM"""
    success = False
    details = {
        "collection_id": str(collection_id),
        "sample_size": sample_size,
        "model": model
    }

    try:
        gen_request = GenerationRequest(
            collection_id=collection_id,
            sheet_id=sheet_id,
            template_id=template_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            sample_size=sample_size,
            auto_approve_with_canonical=auto_approve_with_canonical,
            link_to_canonical=link_to_canonical
        )

        user_token = get_user_token(request)
        result = manager.generate_qa_pairs(
            gen_request,
            user_token=user_token,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["pairs_generated"] = result.pairs_generated
        details["pairs_auto_approved"] = result.pairs_auto_approved
        return result
    except Exception as e:
        logger.error(f"Failed to generate QA pairs: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-generation",
            action="GENERATE",
            success=success,
            details=details
        )


# =============================================================================
# QA PAIRS
# =============================================================================

@router.get("/collections/{collection_id}/pairs", response_model=List[QAPair])
async def list_qa_pairs(
    collection_id: UUID,
    review_status: Optional[QAPairReviewStatus] = None,
    split: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List QA pairs for a collection"""
    return manager.list_qa_pairs(
        collection_id=collection_id,
        review_status=review_status,
        split=split,
        skip=skip,
        limit=limit
    )


@router.get("/pairs/{pair_id}", response_model=QAPair)
async def get_qa_pair(
    pair_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get QA pair by ID"""
    result = manager.get_qa_pair(pair_id)
    if not result:
        raise HTTPException(status_code=404, detail="QA pair not found")
    return result


@router.put("/pairs/{pair_id}", response_model=QAPair)
async def update_qa_pair(
    pair_id: UUID,
    payload: QAPairUpdate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Update a QA pair"""
    success = False
    details = {"pair_id": str(pair_id)}

    try:
        result = manager.update_qa_pair(
            pair_id,
            payload,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="QA pair not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update QA pair: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-pairs",
            action="UPDATE",
            success=success,
            details=details
        )


@router.post("/pairs/{pair_id}/review", response_model=QAPair)
async def review_qa_pair(
    pair_id: UUID,
    status: QAPairReviewStatus,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    review_notes: Optional[str] = None,
    edited_messages: Optional[List[ChatMessage]] = None,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Review a QA pair"""
    success = False
    details = {"pair_id": str(pair_id), "status": status.value}

    try:
        result = manager.review_qa_pair(
            pair_id=pair_id,
            status=status,
            reviewed_by=current_user.username if current_user else "anonymous",
            review_notes=review_notes,
            edited_messages=edited_messages
        )
        if not result:
            raise HTTPException(status_code=404, detail="QA pair not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to review QA pair: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-pairs",
            action="REVIEW",
            success=success,
            details=details
        )


@router.post("/pairs/bulk-review")
async def bulk_review_qa_pairs(
    payload: QAPairBulkReview,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Bulk review multiple QA pairs"""
    success = False
    details = {"pair_count": len(payload.pair_ids), "status": payload.review_status.value}

    try:
        count = manager.bulk_review_qa_pairs(
            payload,
            reviewed_by=current_user.username if current_user else "anonymous"
        )
        db.commit()
        success = True
        details["updated_count"] = count
        return {"updated": count}
    except Exception as e:
        logger.error(f"Failed to bulk review QA pairs: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-pairs",
            action="BULK_REVIEW",
            success=success,
            details=details
        )


@router.post("/collections/{collection_id}/assign-splits")
async def assign_splits(
    collection_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    train_ratio: float = Query(0.8, ge=0, le=1),
    val_ratio: float = Query(0.1, ge=0, le=1),
    test_ratio: float = Query(0.1, ge=0, le=1),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Assign train/val/test splits to QA pairs"""
    success = False
    details = {"collection_id": str(collection_id), "ratios": {"train": train_ratio, "val": val_ratio, "test": test_ratio}}

    try:
        result = manager.assign_splits(
            collection_id=collection_id,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio
        )
        db.commit()
        success = True
        details["counts"] = result
        return result
    except Exception as e:
        logger.error(f"Failed to assign splits: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-collections",
            action="ASSIGN_SPLITS",
            success=success,
            details=details
        )


# =============================================================================
# SEMANTIC LINKING
# =============================================================================

@router.post("/pairs/{pair_id}/link-concept", response_model=QAPair)
async def link_qa_pair_to_concept(
    pair_id: UUID,
    concept_iri: str,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Link a QA pair to an ontology concept"""
    success = False
    details = {"pair_id": str(pair_id), "concept_iri": concept_iri}

    try:
        result = manager.link_qa_pair_to_concept(
            pair_id=pair_id,
            concept_iri=concept_iri,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="QA pair not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to link QA pair to concept: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-semantic",
            action="LINK_CONCEPT",
            success=success,
            details=details
        )


@router.delete("/pairs/{pair_id}/link-concept", response_model=QAPair)
async def unlink_qa_pair_from_concept(
    pair_id: UUID,
    concept_iri: str,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Remove link between QA pair and ontology concept"""
    success = False
    details = {"pair_id": str(pair_id), "concept_iri": concept_iri}

    try:
        result = manager.unlink_qa_pair_from_concept(
            pair_id=pair_id,
            concept_iri=concept_iri,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="QA pair not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unlink QA pair from concept: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-semantic",
            action="UNLINK_CONCEPT",
            success=success,
            details=details
        )


@router.post("/pairs/by-concept", response_model=List[QAPair])
async def list_qa_pairs_by_concept(
    query: QAPairsByConceptQuery,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List QA pairs linked to an ontology concept"""
    return manager.list_qa_pairs_by_concept(query)


@router.get("/gaps", response_model=List[TrainingDataGap])
async def analyze_training_gaps(
    collection_id: Optional[UUID] = None,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Analyze training data gaps relative to ontology coverage"""
    return manager.analyze_training_gaps(collection_id=collection_id)


# =============================================================================
# EXAMPLES
# =============================================================================

@router.get("/examples", response_model=List[Example])
async def list_examples(
    domain: Optional[str] = None,
    task_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    only_verified: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List examples with optional filters"""
    return manager.list_examples(
        domain=domain,
        task_type=task_type,
        difficulty=difficulty,
        only_verified=only_verified,
        skip=skip,
        limit=limit
    )


@router.get("/examples/top", response_model=List[Example])
async def get_top_examples(
    limit: int = Query(10, ge=1, le=100),
    domain: Optional[str] = None,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get top-performing examples by effectiveness score"""
    return manager.get_top_examples(limit=limit, domain=domain)


@router.post("/examples", response_model=Example, status_code=201)
async def create_example(
    payload: ExampleCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create a new example"""
    success = False
    details = {"params": {"domain": payload.domain, "task_type": payload.task_type}}

    try:
        result = manager.create_example(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create example: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-examples",
            action="CREATE",
            success=success,
            details=details
        )


@router.put("/examples/{example_id}", response_model=Example)
async def update_example(
    example_id: UUID,
    payload: ExampleUpdate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Update an example"""
    success = False
    details = {"example_id": str(example_id)}

    try:
        result = manager.update_example(
            example_id,
            payload,
            updated_by=current_user.username if current_user else None
        )
        if not result:
            raise HTTPException(status_code=404, detail="Example not found")
        db.commit()
        success = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update example: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-examples",
            action="UPDATE",
            success=success,
            details=details
        )


@router.delete("/examples/{example_id}")
async def delete_example(
    example_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Delete an example"""
    success = False
    details = {"example_id": str(example_id)}

    try:
        deleted = manager.delete_example(example_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Example not found")
        db.commit()
        success = True
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete example: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-examples",
            action="DELETE",
            success=success,
            details=details
        )


# =============================================================================
# EXPORT
# =============================================================================

@router.post("/collections/{collection_id}/export", response_model=ExportResult)
async def export_collection(
    collection_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    format: ExportFormat = ExportFormat.JSONL,
    include_splits: Optional[List[str]] = Query(None),
    only_approved: bool = True,
    include_metadata: bool = False,
    output_path: Optional[str] = None,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Export collection to training format"""
    success = False
    details = {"collection_id": str(collection_id), "format": format.value}

    try:
        export_request = ExportRequest(
            collection_id=collection_id,
            format=format,
            include_splits=include_splits or ["train", "val", "test"],
            only_approved=only_approved,
            include_metadata=include_metadata,
            output_path=output_path
        )

        result = manager.export_collection(
            export_request,
            exported_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["pairs_exported"] = result.pairs_exported
        details["output_path"] = result.output_path
        return result
    except Exception as e:
        logger.error(f"Failed to export collection: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-export",
            action="EXPORT",
            success=success,
            details=details
        )


# =============================================================================
# MODEL LINEAGE
# =============================================================================

@router.post("/lineage", response_model=ModelLineage, status_code=201)
async def create_model_lineage(
    payload: ModelLineageCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create model training lineage record"""
    success = False
    details = {"model_name": payload.model_name, "model_version": payload.model_version}

    try:
        result = manager.create_model_lineage(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create model lineage: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-lineage",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/lineage/{model_name}/{model_version}", response_model=ModelLineage)
async def get_model_lineage(
    model_name: str,
    model_version: str,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get model lineage by name and version"""
    result = manager.get_model_lineage(model_name, model_version)
    if not result:
        raise HTTPException(status_code=404, detail="Model lineage not found")
    return result


@router.get("/collections/{collection_id}/models", response_model=List[ModelLineage])
async def list_models_for_collection(
    collection_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List all models trained on a collection"""
    return manager.list_models_for_collection(collection_id)


# =============================================================================
# TRAINING JOBS
# =============================================================================

@router.get("/training-jobs", response_model=List[TrainingJob])
async def list_training_jobs(
    collection_id: Optional[UUID] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List training jobs"""
    return manager.list_training_jobs(collection_id=collection_id, skip=skip, limit=limit)


@router.post("/training-jobs", response_model=TrainingJob, status_code=201)
async def create_training_job(
    payload: TrainingJobCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create and submit a training job"""
    success = False
    details = {"model_name": payload.model_name, "collection_id": str(payload.collection_id)}

    try:
        result = manager.create_training_job(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create training job: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-jobs",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/training-jobs/{job_id}", response_model=TrainingJob)
async def get_training_job(
    job_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get training job by ID"""
    result = manager.get_training_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Training job not found")
    return result


# =============================================================================
# DSPY
# =============================================================================

@router.post("/dspy/export/{template_id}", response_model=DSPyExportResult)
async def export_template_as_dspy(
    template_id: UUID,
    payload: Optional[DSPyExportRequest] = None,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Export a prompt template as DSPy program code"""
    output_format = payload.output_format if payload else "module"
    result = manager.export_template_as_dspy(template_id, output_format=output_format)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.post("/dspy/runs", response_model=DSPyRun, status_code=201)
async def create_dspy_run(
    payload: DSPyRunCreate,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Create a DSPy optimization run"""
    success = False
    details = {"program_name": payload.program_name, "template_id": str(payload.template_id)}

    try:
        result = manager.create_dspy_run(
            payload,
            created_by=current_user.username if current_user else None
        )
        db.commit()
        success = True
        details["created_resource_id"] = str(result.id)
        return result
    except Exception as e:
        logger.error(f"Failed to create DSPy run: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-dspy",
            action="CREATE",
            success=success,
            details=details
        )


@router.get("/dspy/runs/{run_id}", response_model=DSPyRun)
async def get_dspy_run(
    run_id: UUID,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """Get DSPy run by ID"""
    result = manager.get_dspy_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="DSPy run not found")
    return result


@router.post("/dspy/runs/{run_id}/cancel")
async def cancel_dspy_run(
    run_id: UUID,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_WRITE))
):
    """Cancel a running DSPy optimization"""
    success = False
    details = {"run_id": str(run_id)}

    try:
        result = manager.cancel_dspy_run(run_id)
        if not result:
            raise HTTPException(status_code=404, detail="DSPy run not found")
        db.commit()
        success = True
        return {"cancelled": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel DSPy run: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="training-data-dspy",
            action="CANCEL",
            success=success,
            details=details
        )


@router.get("/dspy/runs", response_model=List[DSPyRun])
async def list_dspy_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    manager: TrainingDataManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('training-data', FeatureAccessLevel.READ_ONLY))
):
    """List all DSPy optimization runs"""
    return manager.list_dspy_runs(skip=skip, limit=limit)


# =============================================================================
# REGISTER ROUTES
# =============================================================================

def register_routes(app):
    """Register training data routes with the FastAPI app"""
    app.include_router(router)
