"""Training Data Quality Models - Pydantic models for DQX quality gate integration"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================

class CheckCriticality(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class QualityRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


# =============================================================================
# QUALITY CHECK DEFINITIONS
# =============================================================================

class QualityCheckBase(BaseModel):
    check_name: str = Field(..., min_length=1, max_length=255, description="Human-readable check name")
    check_function: str = Field(..., min_length=1, description="DQX function name or heuristic ID (e.g. 'is_not_null', 'message_completeness')")
    column_name: Optional[str] = Field(None, description="Column/field the check applies to (e.g. 'messages', 'quality_score')")
    criticality: CheckCriticality = Field(default=CheckCriticality.WARNING)
    parameters: Optional[Dict[str, Any]] = Field(None, description="Function-specific parameters")


class QualityCheckCreate(QualityCheckBase):
    collection_id: UUID


class QualityCheck(QualityCheckBase):
    id: UUID
    collection_id: UUID
    created_at: datetime
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUALITY RUN RESULTS
# =============================================================================

class CheckResult(BaseModel):
    check_id: UUID
    check_name: str
    passed: bool
    criticality: CheckCriticality
    message: str
    details: Optional[Dict[str, Any]] = None


class QualityRunCreate(BaseModel):
    collection_id: UUID
    source: str = Field(default="mock", description="'mock' for local heuristics, 'dqx' for VITAL DQX proxy")


class QualityRun(BaseModel):
    id: UUID
    collection_id: UUID
    status: QualityRunStatus
    source: str
    pass_rate: Optional[float] = None
    quality_score: Optional[float] = None
    check_results: Optional[List[CheckResult]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# VALIDATION GATE
# =============================================================================

class ValidationIssue(BaseModel):
    check_name: str
    criticality: CheckCriticality
    message: str


class ValidationResult(BaseModel):
    collection_id: UUID
    is_valid: bool
    quality_score: Optional[float] = None
    blocking_issues: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    info: List[ValidationIssue] = []
    latest_run_id: Optional[UUID] = None


# =============================================================================
# DQX IMPORT
# =============================================================================

class DQXResultImport(BaseModel):
    """Results pushed from VITAL's DQX proxy"""
    check_results: List[CheckResult]
    source: str = "dqx"
    dqx_run_id: Optional[str] = None
