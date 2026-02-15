"""
ML Monitor Manager

Business logic for model monitoring metrics and drift alerts.
Uses Databricks SDK when available, mock data in local dev.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from databricks.sdk import WorkspaceClient
from sqlalchemy.orm import Session

from src.common.config import Settings
from src.models.ml_monitor import DriftAlert, EndpointMetrics

logger = logging.getLogger(__name__)


class MLMonitorManager:
    """
    Manages model monitoring operations.

    Provides endpoint metrics and drift alerts.
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

    def get_endpoint_metrics(
        self,
        endpoint_name: Optional[str] = None,
        time_window: str = "1h"
    ) -> List[EndpointMetrics]:
        """Get metrics for serving endpoints"""
        if not self._workspace_client:
            return self._mock_metrics(endpoint_name)

        # SDK-based metrics retrieval would go here
        # For now, fall back to mock as metrics APIs are workspace-specific
        return self._mock_metrics(endpoint_name)

    def list_alerts(
        self,
        model_name: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[DriftAlert]:
        """List drift and quality alerts"""
        # In production, this would query monitoring tables or Lakehouse Monitoring
        # For now, return mock alerts
        return self._mock_alerts(model_name, severity)

    # =========================================================================
    # MOCK DATA
    # =========================================================================

    def _mock_metrics(self, endpoint_name: Optional[str] = None) -> List[EndpointMetrics]:
        now = datetime.now(timezone.utc)
        metrics = [
            EndpointMetrics(
                endpoint_name="mirion-radiation-classifier-endpoint",
                model_name="mirion-radiation-classifier",
                request_count=1247,
                error_count=3,
                avg_latency_ms=45.2,
                p99_latency_ms=120.5,
                throughput_rps=12.4,
                time_window="1h",
                last_updated=now,
            ),
            EndpointMetrics(
                endpoint_name="mirion-defect-detector-endpoint",
                model_name="mirion-defect-detector",
                request_count=834,
                error_count=1,
                avg_latency_ms=78.3,
                p99_latency_ms=210.0,
                throughput_rps=8.2,
                time_window="1h",
                last_updated=now,
            ),
        ]
        if endpoint_name:
            return [m for m in metrics if m.endpoint_name == endpoint_name]
        return metrics

    def _mock_alerts(
        self,
        model_name: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[DriftAlert]:
        now = datetime.now(timezone.utc)
        alerts = [
            DriftAlert(
                id=str(uuid.uuid4()),
                alert_type="data_drift",
                severity="medium",
                model_name="mirion-radiation-classifier",
                endpoint_name="mirion-radiation-classifier-endpoint",
                description="Input feature distribution shift detected in 'measurement_type' column",
                metric_name="psi_score",
                metric_value=0.25,
                threshold=0.2,
                created_at=now,
            ),
            DriftAlert(
                id=str(uuid.uuid4()),
                alert_type="prediction_drift",
                severity="low",
                model_name="mirion-defect-detector",
                endpoint_name="mirion-defect-detector-endpoint",
                description="Slight increase in 'unknown' class predictions over last 24h",
                metric_name="unknown_ratio",
                metric_value=0.08,
                threshold=0.05,
                created_at=now,
            ),
        ]
        if model_name:
            alerts = [a for a in alerts if a.model_name == model_name]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts
