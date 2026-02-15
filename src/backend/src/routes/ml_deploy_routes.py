"""
ML Deploy API Routes

REST API endpoints for model deployment, serving endpoints, and inference.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.common.authorization import PermissionChecker
from src.common.config import Settings, get_settings
from src.common.dependencies import DBSessionDep, AuditCurrentUserDep, AuditManagerDep
from src.common.features import FeatureAccessLevel
from src.common.workspace_client import get_obo_workspace_client, get_workspace_client
from src.controller.ml_deploy_manager import MLDeployManager
from src.models.ml_deploy import (
    DeployRequest,
    EndpointQueryRequest,
    EndpointQueryResult,
    ServingEndpoint,
    UCModel,
    UCModelVersion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml-deploy", tags=["ML Deploy"])


# =============================================================================
# DEPENDENCIES
# =============================================================================

def get_manager(
    request: Request,
    db: DBSessionDep,
    settings: Settings = Depends(get_settings)
) -> MLDeployManager:
    """Get MLDeployManager with dependencies injected"""
    workspace_client = None
    try:
        workspace_client = get_obo_workspace_client(request, settings)
    except Exception:
        try:
            workspace_client = get_workspace_client(settings)
        except Exception as e:
            logger.warning(f"Could not get workspace client: {e}")

    return MLDeployManager(
        db=db,
        settings=settings,
        workspace_client=workspace_client
    )


# =============================================================================
# MODELS
# =============================================================================

@router.get("/models", response_model=List[UCModel])
async def list_models(
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    manager: MLDeployManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-deploy', FeatureAccessLevel.READ_ONLY))
):
    """List registered models from Unity Catalog"""
    return manager.list_models(catalog=catalog, schema=schema)


@router.get("/models/{model_name}/versions", response_model=List[UCModelVersion])
async def list_model_versions(
    model_name: str,
    manager: MLDeployManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-deploy', FeatureAccessLevel.READ_ONLY))
):
    """List versions of a registered model"""
    return manager.list_model_versions(model_name)


# =============================================================================
# DEPLOYMENT
# =============================================================================

@router.post("/deploy", response_model=ServingEndpoint)
async def deploy_model(
    payload: DeployRequest,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: MLDeployManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-deploy', FeatureAccessLevel.READ_WRITE))
):
    """Deploy a model to a serving endpoint"""
    success = False
    details = {"model_name": payload.model_name, "endpoint_name": payload.endpoint_name}

    try:
        result = manager.deploy_model(payload)
        db.commit()
        success = True
        return result
    except Exception as e:
        logger.error(f"Failed to deploy model: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="ml-deploy",
            action="DEPLOY",
            success=success,
            details=details
        )


# =============================================================================
# SERVING ENDPOINTS
# =============================================================================

@router.get("/endpoints", response_model=List[ServingEndpoint])
async def list_serving_endpoints(
    manager: MLDeployManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-deploy', FeatureAccessLevel.READ_ONLY))
):
    """List serving endpoints"""
    return manager.list_serving_endpoints()


@router.post("/endpoints/{endpoint_name}/query", response_model=EndpointQueryResult)
async def query_endpoint(
    endpoint_name: str,
    payload: EndpointQueryRequest,
    request: Request,
    current_user: AuditCurrentUserDep,
    audit_manager: AuditManagerDep,
    db: DBSessionDep,
    manager: MLDeployManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-deploy', FeatureAccessLevel.READ_WRITE))
):
    """Query a serving endpoint"""
    success = False
    details = {"endpoint_name": endpoint_name}

    try:
        result = manager.query_endpoint(endpoint_name, payload)
        success = True
        return result
    except Exception as e:
        logger.error(f"Failed to query endpoint: {e}", exc_info=True)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        audit_manager.log_action(
            db=db,
            username=current_user.username if current_user else "anonymous",
            ip_address=request.client.host if request.client else None,
            feature="ml-deploy",
            action="QUERY",
            success=success,
            details=details
        )


# =============================================================================
# REGISTER ROUTES
# =============================================================================

def register_routes(app):
    """Register ML deploy routes with the FastAPI app"""
    app.include_router(router)
