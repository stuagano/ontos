"""
ML Deploy Pydantic Models

API models for model deployment, serving endpoints, and inference.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UCModel(BaseModel):
    """Unity Catalog registered model"""
    name: str
    catalog_name: Optional[str] = None
    schema_name: Optional[str] = None
    full_name: Optional[str] = None
    comment: Optional[str] = None
    owner: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UCModelVersion(BaseModel):
    """Unity Catalog model version"""
    model_name: str
    version: int
    source: Optional[str] = None
    run_id: Optional[str] = None
    status: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class DeployRequest(BaseModel):
    """Request to deploy a model to a serving endpoint"""
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., description="Full model name in Unity Catalog")
    model_version: int = Field(..., description="Model version to deploy")
    endpoint_name: str = Field(..., description="Serving endpoint name")
    workload_size: str = Field("Small", description="Workload size: Small, Medium, Large")
    scale_to_zero: bool = Field(True, description="Whether to scale to zero when idle")


class ServingEndpoint(BaseModel):
    """Databricks serving endpoint"""
    name: str
    state: Optional[str] = None
    creator: Optional[str] = None
    creation_timestamp: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    served_models: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EndpointQueryRequest(BaseModel):
    """Request to query a serving endpoint"""
    inputs: Any = Field(..., description="Input data for the model")
    params: Optional[Dict[str, Any]] = Field(None, description="Optional inference parameters")


class EndpointQueryResult(BaseModel):
    """Result of querying a serving endpoint"""
    predictions: Any
    metadata: Optional[Dict[str, Any]] = None
