"""
ML Monitor Pydantic Models

API models for endpoint metrics, drift alerts, and monitoring data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EndpointMetrics(BaseModel):
    """Metrics for a serving endpoint"""
    model_config = {"protected_namespaces": ()}

    endpoint_name: str
    model_name: Optional[str] = None
    request_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    throughput_rps: float = 0.0
    time_window: str = "1h"
    last_updated: Optional[datetime] = None


class DriftAlert(BaseModel):
    """Data or model drift alert"""
    model_config = {"protected_namespaces": ()}

    id: str
    alert_type: str  # data_drift, concept_drift, prediction_drift
    severity: str  # low, medium, high
    model_name: str
    endpoint_name: Optional[str] = None
    description: str
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    created_at: Optional[datetime] = None
    is_acknowledged: bool = False
