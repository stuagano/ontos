"""
ML Monitor API Routes

REST API endpoints for model monitoring metrics and drift alerts.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Request

from src.common.authorization import PermissionChecker
from src.common.config import Settings, get_settings
from src.common.dependencies import DBSessionDep
from src.common.features import FeatureAccessLevel
from src.common.workspace_client import get_obo_workspace_client, get_workspace_client
from src.controller.ml_monitor_manager import MLMonitorManager
from src.models.ml_monitor import DriftAlert, EndpointMetrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml-monitor", tags=["ML Monitor"])


# =============================================================================
# DEPENDENCIES
# =============================================================================

def get_manager(
    request: Request,
    db: DBSessionDep,
    settings: Settings = Depends(get_settings)
) -> MLMonitorManager:
    """Get MLMonitorManager with dependencies injected"""
    workspace_client = None
    try:
        workspace_client = get_obo_workspace_client(request, settings)
    except Exception:
        try:
            workspace_client = get_workspace_client(settings)
        except Exception as e:
            logger.warning(f"Could not get workspace client: {e}")

    return MLMonitorManager(
        db=db,
        settings=settings,
        workspace_client=workspace_client
    )


# =============================================================================
# METRICS
# =============================================================================

@router.get("/metrics", response_model=List[EndpointMetrics])
async def get_endpoint_metrics(
    endpoint_name: Optional[str] = None,
    time_window: str = "1h",
    manager: MLMonitorManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-monitor', FeatureAccessLevel.READ_ONLY))
):
    """Get metrics for serving endpoints"""
    return manager.get_endpoint_metrics(endpoint_name=endpoint_name, time_window=time_window)


# =============================================================================
# ALERTS
# =============================================================================

@router.get("/alerts", response_model=List[DriftAlert])
async def list_alerts(
    model_name: Optional[str] = None,
    severity: Optional[str] = None,
    manager: MLMonitorManager = Depends(get_manager),
    _: bool = Depends(PermissionChecker('ml-monitor', FeatureAccessLevel.READ_ONLY))
):
    """List drift and quality alerts"""
    return manager.list_alerts(model_name=model_name, severity=severity)


# =============================================================================
# REGISTER ROUTES
# =============================================================================

def register_routes(app):
    """Register ML monitor routes with the FastAPI app"""
    app.include_router(router)
