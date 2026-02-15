"""
ML Deploy Manager

Business logic for model deployment using Databricks SDK.
Includes mock data fallback for local development.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient
from sqlalchemy.orm import Session

from src.common.config import Settings
from src.models.ml_deploy import (
    DeployRequest,
    EndpointQueryRequest,
    EndpointQueryResult,
    ServingEndpoint,
    UCModel,
    UCModelVersion,
)

logger = logging.getLogger(__name__)


class MLDeployManager:
    """
    Manages model deployment operations.

    Wraps Databricks SDK calls for serving endpoints and model registry.
    Falls back to mock data when workspace client is unavailable.
    """

    def __init__(
        self,
        db: Session,
        settings: Settings,
        workspace_client: Optional[WorkspaceClient] = None,
    ):
        self._db = db
        self._settings = settings
        self._workspace_client = workspace_client

    # =========================================================================
    # MODELS
    # =========================================================================

    def list_models(self, catalog: Optional[str] = None, schema: Optional[str] = None) -> List[UCModel]:
        """List registered models from Unity Catalog"""
        if not self._workspace_client:
            return self._mock_models()

        try:
            models = []
            for m in self._workspace_client.registered_models.list(
                catalog_name=catalog,
                schema_name=schema
            ):
                models.append(UCModel(
                    name=m.name,
                    catalog_name=getattr(m, 'catalog_name', None),
                    schema_name=getattr(m, 'schema_name', None),
                    full_name=getattr(m, 'full_name', None),
                    comment=getattr(m, 'comment', None),
                    owner=getattr(m, 'owner', None),
                ))
            return models
        except Exception as e:
            logger.warning(f"Failed to list models from SDK, using mock: {e}")
            return self._mock_models()

    def list_model_versions(self, model_name: str) -> List[UCModelVersion]:
        """List versions of a registered model"""
        if not self._workspace_client:
            return self._mock_model_versions(model_name)

        try:
            versions = []
            for v in self._workspace_client.model_versions.list(full_name=model_name):
                versions.append(UCModelVersion(
                    model_name=model_name,
                    version=v.version,
                    source=getattr(v, 'source', None),
                    run_id=getattr(v, 'run_id', None),
                    status=getattr(v, 'status', {}).get('status', None) if isinstance(getattr(v, 'status', None), dict) else str(getattr(v, 'status', '')),
                    comment=getattr(v, 'comment', None),
                ))
            return versions
        except Exception as e:
            logger.warning(f"Failed to list model versions from SDK, using mock: {e}")
            return self._mock_model_versions(model_name)

    # =========================================================================
    # SERVING ENDPOINTS
    # =========================================================================

    def deploy_model(self, request: DeployRequest) -> ServingEndpoint:
        """Deploy a model to a serving endpoint"""
        if not self._workspace_client:
            return self._mock_deploy(request)

        try:
            endpoint = self._workspace_client.serving_endpoints.create(
                name=request.endpoint_name,
                config={
                    "served_entities": [{
                        "entity_name": request.model_name,
                        "entity_version": str(request.model_version),
                        "workload_size": request.workload_size,
                        "scale_to_zero_enabled": request.scale_to_zero,
                    }]
                }
            )
            return ServingEndpoint(
                name=endpoint.name,
                state=str(getattr(endpoint, 'state', 'CREATING')),
                creator=getattr(endpoint, 'creator', None),
            )
        except Exception as e:
            logger.error(f"Failed to deploy model: {e}")
            raise

    def list_serving_endpoints(self) -> List[ServingEndpoint]:
        """List serving endpoints"""
        if not self._workspace_client:
            return self._mock_endpoints()

        try:
            endpoints = []
            for ep in self._workspace_client.serving_endpoints.list():
                served_models = []
                if hasattr(ep, 'config') and ep.config:
                    entities = getattr(ep.config, 'served_entities', []) or []
                    for entity in entities:
                        served_models.append({
                            "name": getattr(entity, 'entity_name', 'unknown'),
                            "version": getattr(entity, 'entity_version', '1'),
                        })
                endpoints.append(ServingEndpoint(
                    name=ep.name,
                    state=str(getattr(ep, 'state', 'UNKNOWN')),
                    creator=getattr(ep, 'creator', None),
                    creation_timestamp=getattr(ep, 'creation_timestamp', None),
                    served_models=served_models,
                ))
            return endpoints
        except Exception as e:
            logger.warning(f"Failed to list endpoints from SDK, using mock: {e}")
            return self._mock_endpoints()

    def query_endpoint(
        self,
        endpoint_name: str,
        request: EndpointQueryRequest
    ) -> EndpointQueryResult:
        """Query a serving endpoint"""
        if not self._workspace_client:
            return self._mock_query(endpoint_name, request)

        try:
            response = self._workspace_client.serving_endpoints.query(
                name=endpoint_name,
                inputs=request.inputs
            )
            return EndpointQueryResult(
                predictions=getattr(response, 'predictions', response),
                metadata={"endpoint": endpoint_name}
            )
        except Exception as e:
            logger.error(f"Failed to query endpoint: {e}")
            raise

    # =========================================================================
    # MOCK DATA (local dev)
    # =========================================================================

    def _mock_models(self) -> List[UCModel]:
        now = datetime.now(timezone.utc)
        return [
            UCModel(
                name="mirion-radiation-classifier",
                catalog_name="mirion_ml",
                schema_name="models",
                full_name="mirion_ml.models.mirion-radiation-classifier",
                comment="Radiation safety classification model",
                owner="ml-team@mirion.com",
                created_at=now,
                updated_at=now,
            ),
            UCModel(
                name="mirion-defect-detector",
                catalog_name="mirion_ml",
                schema_name="models",
                full_name="mirion_ml.models.mirion-defect-detector",
                comment="Equipment defect detection model",
                owner="ml-team@mirion.com",
                created_at=now,
                updated_at=now,
            ),
            UCModel(
                name="mirion-dosimetry-predictor",
                catalog_name="mirion_ml",
                schema_name="models",
                full_name="mirion_ml.models.mirion-dosimetry-predictor",
                comment="Dosimetry prediction model",
                owner="ml-team@mirion.com",
                created_at=now,
                updated_at=now,
            ),
        ]

    def _mock_model_versions(self, model_name: str) -> List[UCModelVersion]:
        now = datetime.now(timezone.utc)
        return [
            UCModelVersion(model_name=model_name, version=3, status="READY", comment="Production v3", created_at=now),
            UCModelVersion(model_name=model_name, version=2, status="READY", comment="Stable v2", created_at=now),
            UCModelVersion(model_name=model_name, version=1, status="READY", comment="Initial release", created_at=now),
        ]

    def _mock_deploy(self, request: DeployRequest) -> ServingEndpoint:
        return ServingEndpoint(
            name=request.endpoint_name,
            state="CREATING",
            served_models=[{
                "name": request.model_name,
                "version": str(request.model_version),
            }],
        )

    def _mock_endpoints(self) -> List[ServingEndpoint]:
        return [
            ServingEndpoint(
                name="mirion-radiation-classifier-endpoint",
                state="READY",
                creator="ml-team@mirion.com",
                served_models=[{"name": "mirion-radiation-classifier", "version": "3"}],
            ),
            ServingEndpoint(
                name="mirion-defect-detector-endpoint",
                state="READY",
                creator="ml-team@mirion.com",
                served_models=[{"name": "mirion-defect-detector", "version": "2"}],
            ),
        ]

    def _mock_query(self, endpoint_name: str, request: EndpointQueryRequest) -> EndpointQueryResult:
        return EndpointQueryResult(
            predictions=[{"label": "normal", "score": 0.95}],
            metadata={"endpoint": endpoint_name, "mock": True}
        )
