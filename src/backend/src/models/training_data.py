"""
ML Training Data Pydantic Models

API models for QA pairs, canonical labels, templates, and training collections.
Follows Ontos's Base/Create/Update/Response pattern.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS (Mirrored from DB for API layer)
# =============================================================================

class SheetSourceType(str, Enum):
    UNITY_CATALOG_TABLE = "unity_catalog_table"
    UNITY_CATALOG_VOLUME = "unity_catalog_volume"
    DELTA_TABLE = "delta_table"
    EXTERNAL_URL = "external_url"


class SheetSamplingStrategy(str, Enum):
    ALL = "all"
    RANDOM = "random"
    STRATIFIED = "stratified"
    FIRST_N = "first_n"


class TemplateStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class LabelType(str, Enum):
    ENTITY_EXTRACTION = "entity_extraction"
    CLASSIFICATION = "classification"
    SENTIMENT = "sentiment"
    SUMMARIZATION = "summarization"
    QA = "qa"
    CUSTOM = "custom"


class LabelConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class UsageType(str, Enum):
    TRAINING = "training"
    VALIDATION = "validation"
    EVALUATION = "evaluation"
    FEW_SHOT = "few_shot"
    TESTING = "testing"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class QAPairReviewStatus(str, Enum):
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class TrainingSheetStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    REVIEW = "review"
    APPROVED = "approved"
    EXPORTED = "exported"
    ARCHIVED = "archived"


class GenerationMethod(str, Enum):
    LLM = "llm"
    MANUAL = "manual"
    HYBRID = "hybrid"
    IMPORTED = "imported"


# =============================================================================
# CHAT MESSAGE FORMAT
# =============================================================================

class ChatMessage(BaseModel):
    """OpenAI chat format message"""
    role: str = Field(..., description="Message role: system, user, assistant, or tool")
    content: str = Field(..., description="Message content")
    name: Optional[str] = Field(None, description="Optional name for the message author")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls (for assistant messages)")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID (for tool messages)")

    model_config = {"from_attributes": True}


# =============================================================================
# SHEETS
# =============================================================================

class SheetBase(BaseModel):
    """Base sheet fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Sheet name")
    description: Optional[str] = Field(None, description="Sheet description")
    source_type: SheetSourceType = Field(SheetSourceType.UNITY_CATALOG_TABLE, description="Type of data source")
    source_catalog: Optional[str] = Field(None, description="Unity Catalog catalog name")
    source_schema: Optional[str] = Field(None, description="Unity Catalog schema name")
    source_table: Optional[str] = Field(None, description="Table name")
    source_volume: Optional[str] = Field(None, description="Volume path for files")
    source_path: Optional[str] = Field(None, description="Path within volume or external URL")
    text_columns: List[str] = Field(default_factory=list, description="Columns containing text data")
    image_columns: List[str] = Field(default_factory=list, description="Columns containing image paths")
    metadata_columns: List[str] = Field(default_factory=list, description="Columns containing metadata")
    id_column: Optional[str] = Field(None, description="Primary key column in source")
    sampling_strategy: SheetSamplingStrategy = Field(SheetSamplingStrategy.ALL, description="Sampling strategy")
    sample_size: Optional[int] = Field(None, ge=1, description="Number of samples to take")
    sample_filter: Optional[str] = Field(None, description="SQL WHERE clause for filtering")
    stratify_column: Optional[str] = Field(None, description="Column for stratified sampling")


class SheetCreate(SheetBase):
    """Create sheet request"""
    owner_id: Optional[str] = Field(None, description="Owner user ID")

    @model_validator(mode='after')
    def validate_source_config(self):
        """Validate source configuration based on source_type"""
        if self.source_type == SheetSourceType.UNITY_CATALOG_TABLE:
            if not all([self.source_catalog, self.source_schema, self.source_table]):
                raise ValueError("Unity Catalog table source requires catalog, schema, and table")
        elif self.source_type == SheetSourceType.UNITY_CATALOG_VOLUME:
            if not self.source_volume:
                raise ValueError("Unity Catalog volume source requires source_volume")
        return self


class SheetUpdate(BaseModel):
    """Update sheet request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    text_columns: Optional[List[str]] = None
    image_columns: Optional[List[str]] = None
    metadata_columns: Optional[List[str]] = None
    id_column: Optional[str] = None
    sampling_strategy: Optional[SheetSamplingStrategy] = None
    sample_size: Optional[int] = None
    sample_filter: Optional[str] = None
    stratify_column: Optional[str] = None
    owner_id: Optional[str] = None


class Sheet(SheetBase):
    """Sheet response"""
    id: UUID
    owner_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

class PromptTemplateBase(BaseModel):
    """Base template fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    version: str = Field("1.0.0", description="Semantic version")
    status: TemplateStatus = Field(TemplateStatus.DRAFT, description="Template status")
    system_prompt: Optional[str] = Field(None, description="System prompt for the LLM")
    user_prompt_template: str = Field(..., description="User prompt template with {{variable}} placeholders")
    few_shot_examples: List[Dict[str, Any]] = Field(default_factory=list, description="Few-shot examples")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for structured output")
    label_type: Optional[LabelType] = Field(None, description="Type of label this template produces")
    custom_label_type: Optional[str] = Field(None, description="Custom label type name")
    default_model: Optional[str] = Field("databricks-meta-llama-3-1-70b-instruct", description="Default model")
    default_temperature: Optional[float] = Field(0.7, ge=0, le=2, description="Default temperature")
    default_max_tokens: Optional[int] = Field(1024, ge=1, description="Default max tokens")
    variable_mappings: Dict[str, str] = Field(default_factory=dict, description="Maps {{variables}} to sheet columns")
    tags: List[str] = Field(default_factory=list, description="Tags for organization")


class PromptTemplateCreate(PromptTemplateBase):
    """Create template request"""
    sheet_id: Optional[UUID] = Field(None, description="Associated sheet ID")
    owner_id: Optional[str] = Field(None, description="Owner user ID")

    @field_validator('user_prompt_template')
    @classmethod
    def validate_template_syntax(cls, v: str) -> str:
        """Validate template has proper {{variable}} syntax"""
        import re
        # Check for balanced braces
        if v.count('{{') != v.count('}}'):
            raise ValueError("Unbalanced {{ }} in template")
        return v


class PromptTemplateUpdate(BaseModel):
    """Update template request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    version: Optional[str] = None
    status: Optional[TemplateStatus] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    few_shot_examples: Optional[List[Dict[str, Any]]] = None
    output_schema: Optional[Dict[str, Any]] = None
    label_type: Optional[LabelType] = None
    custom_label_type: Optional[str] = None
    default_model: Optional[str] = None
    default_temperature: Optional[float] = None
    default_max_tokens: Optional[int] = None
    sheet_id: Optional[UUID] = None
    variable_mappings: Optional[Dict[str, str]] = None
    tags: Optional[List[str]] = None
    owner_id: Optional[str] = None


class PromptTemplate(PromptTemplateBase):
    """Template response"""
    id: UUID
    sheet_id: Optional[UUID] = None
    owner_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# CANONICAL LABELS
# =============================================================================

class CanonicalLabelBase(BaseModel):
    """Base canonical label fields"""
    item_ref: str = Field(..., description="Reference to source item")
    label_type: LabelType = Field(..., description="Type of label")
    custom_label_type: Optional[str] = Field(None, description="Custom label type name")
    label_data: Dict[str, Any] = Field(..., description="The actual label data")
    confidence: LabelConfidence = Field(LabelConfidence.HIGH, description="Confidence level")
    is_verified: bool = Field(False, description="Whether label has been verified")
    allowed_uses: List[UsageType] = Field(
        default_factory=lambda: [UsageType.TRAINING, UsageType.VALIDATION, UsageType.EVALUATION, UsageType.FEW_SHOT, UsageType.TESTING],
        description="Allowed usage types"
    )
    prohibited_uses: List[UsageType] = Field(default_factory=list, description="Prohibited usage types")
    usage_reason: Optional[str] = Field(None, description="Reason for usage constraints")
    data_classification: DataClassification = Field(DataClassification.INTERNAL, description="Data sensitivity")


class CanonicalLabelCreate(CanonicalLabelBase):
    """Create canonical label request"""
    sheet_id: UUID = Field(..., description="Sheet this label belongs to")


class CanonicalLabelUpdate(BaseModel):
    """Update canonical label request"""
    label_data: Optional[Dict[str, Any]] = None
    confidence: Optional[LabelConfidence] = None
    is_verified: Optional[bool] = None
    allowed_uses: Optional[List[UsageType]] = None
    prohibited_uses: Optional[List[UsageType]] = None
    usage_reason: Optional[str] = None
    data_classification: Optional[DataClassification] = None


class CanonicalLabel(CanonicalLabelBase):
    """Canonical label response"""
    id: UUID
    sheet_id: UUID
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    reuse_count: int = 0
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CanonicalLabelBulkLookup(BaseModel):
    """Request for bulk label lookup"""
    sheet_id: UUID
    item_refs: List[str]
    label_type: Optional[LabelType] = None


class UsageConstraintCheck(BaseModel):
    """Check if label can be used for a specific purpose"""
    label_id: UUID
    intended_use: UsageType


class UsageConstraintResult(BaseModel):
    """Result of usage constraint check"""
    allowed: bool
    reason: Optional[str] = None


# =============================================================================
# TRAINING COLLECTIONS
# =============================================================================

class TrainingCollectionBase(BaseModel):
    """Base collection fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    version: str = Field("1.0.0", description="Semantic version")
    status: TrainingSheetStatus = Field(TrainingSheetStatus.DRAFT, description="Collection status")
    generation_method: GenerationMethod = Field(GenerationMethod.LLM, description="How pairs were generated")
    default_train_ratio: float = Field(0.8, ge=0, le=1, description="Default training split ratio")
    default_val_ratio: float = Field(0.1, ge=0, le=1, description="Default validation split ratio")
    default_test_ratio: float = Field(0.1, ge=0, le=1, description="Default test split ratio")
    tags: List[str] = Field(default_factory=list, description="Tags for organization")

    @model_validator(mode='after')
    def validate_split_ratios(self):
        """Ensure split ratios sum to 1.0"""
        total = self.default_train_ratio + self.default_val_ratio + self.default_test_ratio
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        return self


class TrainingCollectionCreate(TrainingCollectionBase):
    """Create collection request"""
    model_config = {"protected_namespaces": ()}

    sheet_id: Optional[UUID] = Field(None, description="Source sheet ID")
    template_id: Optional[UUID] = Field(None, description="Prompt template ID")
    model_used: Optional[str] = Field(None, description="Model used for generation")
    generation_config: Optional[Dict[str, Any]] = Field(None, description="Generation parameters")
    owner_id: Optional[str] = Field(None, description="Owner user ID")


class TrainingCollectionUpdate(BaseModel):
    """Update collection request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    version: Optional[str] = None
    status: Optional[TrainingSheetStatus] = None
    default_train_ratio: Optional[float] = None
    default_val_ratio: Optional[float] = None
    default_test_ratio: Optional[float] = None
    tags: Optional[List[str]] = None
    owner_id: Optional[str] = None


class TrainingCollectionStats(BaseModel):
    """Collection statistics"""
    total_pairs: int = 0
    approved_pairs: int = 0
    rejected_pairs: int = 0
    pending_pairs: int = 0
    approval_rate: float = 0.0


class TrainingCollection(TrainingCollectionBase):
    """Collection response"""
    id: UUID
    sheet_id: Optional[UUID] = None
    template_id: Optional[UUID] = None
    model_used: Optional[str] = None
    generation_config: Optional[Dict[str, Any]] = None
    total_pairs: int = 0
    approved_pairs: int = 0
    rejected_pairs: int = 0
    pending_pairs: int = 0
    last_exported_at: Optional[datetime] = None
    export_format: Optional[str] = None
    export_path: Optional[str] = None
    owner_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}

    @property
    def stats(self) -> TrainingCollectionStats:
        """Compute statistics"""
        approval_rate = self.approved_pairs / self.total_pairs if self.total_pairs > 0 else 0.0
        return TrainingCollectionStats(
            total_pairs=self.total_pairs,
            approved_pairs=self.approved_pairs,
            rejected_pairs=self.rejected_pairs,
            pending_pairs=self.pending_pairs,
            approval_rate=approval_rate
        )


# =============================================================================
# QA PAIRS
# =============================================================================

class QAPairBase(BaseModel):
    """Base QA pair fields"""
    messages: List[ChatMessage] = Field(..., description="Chat messages in OpenAI format")
    source_item_ref: Optional[str] = Field(None, description="Reference to source data item")
    review_status: QAPairReviewStatus = Field(QAPairReviewStatus.PENDING, description="Review status")
    quality_score: Optional[float] = Field(None, ge=0, le=1, description="Quality score 0-1")
    quality_flags: List[str] = Field(default_factory=list, description="Quality issue flags")
    split: Optional[str] = Field(None, description="Dataset split: train, val, test")
    sampling_weight: float = Field(1.0, ge=0, description="Sampling weight for this pair")
    semantic_concept_iris: List[str] = Field(default_factory=list, description="Linked ontology concept IRIs")


class QAPairCreate(QAPairBase):
    """Create QA pair request"""
    collection_id: UUID = Field(..., description="Parent collection ID")
    canonical_label_id: Optional[UUID] = Field(None, description="Linked canonical label")
    generation_metadata: Optional[Dict[str, Any]] = Field(None, description="Generation metadata")


class QAPairUpdate(BaseModel):
    """Update QA pair request"""
    messages: Optional[List[ChatMessage]] = None
    review_status: Optional[QAPairReviewStatus] = None
    quality_score: Optional[float] = None
    quality_flags: Optional[List[str]] = None
    split: Optional[str] = None
    sampling_weight: Optional[float] = None
    review_notes: Optional[str] = None
    semantic_concept_iris: Optional[List[str]] = None


class QAPair(QAPairBase):
    """QA pair response"""
    id: UUID
    collection_id: UUID
    canonical_label_id: Optional[UUID] = None
    was_auto_approved: bool = False
    generation_metadata: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    original_messages: Optional[List[ChatMessage]] = None
    edit_distance: Optional[int] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QAPairBulkReview(BaseModel):
    """Bulk review request"""
    pair_ids: List[UUID]
    review_status: QAPairReviewStatus
    review_notes: Optional[str] = None


# =============================================================================
# GENERATION REQUESTS
# =============================================================================

class GenerationRequest(BaseModel):
    """Request to generate QA pairs"""
    collection_id: UUID = Field(..., description="Collection to generate into")
    sheet_id: Optional[UUID] = Field(None, description="Override sheet (defaults to collection's sheet)")
    template_id: Optional[UUID] = Field(None, description="Override template (defaults to collection's template)")
    model: Optional[str] = Field(None, description="Override model")
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1)
    sample_size: Optional[int] = Field(None, ge=1, description="Number of items to process")
    auto_approve_with_canonical: bool = Field(True, description="Auto-approve if canonical label matches")
    link_to_canonical: bool = Field(True, description="Link generated pairs to canonical labels")


class GenerationProgress(BaseModel):
    """Generation progress update"""
    collection_id: UUID
    total_items: int
    processed_items: int
    successful_items: int
    failed_items: int
    status: str  # running, completed, failed
    error_message: Optional[str] = None


class GenerationResult(BaseModel):
    """Generation result"""
    collection_id: UUID
    pairs_generated: int
    pairs_auto_approved: int
    pairs_pending_review: int
    errors: List[Dict[str, Any]] = []


# =============================================================================
# EXPORT REQUESTS
# =============================================================================

class ExportFormat(str, Enum):
    JSONL = "jsonl"
    ALPACA = "alpaca"
    SHAREGPT = "sharegpt"
    PARQUET = "parquet"
    CSV = "csv"


class ExportRequest(BaseModel):
    """Request to export collection"""
    collection_id: UUID
    format: ExportFormat = Field(ExportFormat.JSONL, description="Export format")
    include_splits: List[str] = Field(default_factory=lambda: ["train", "val", "test"], description="Splits to include")
    only_approved: bool = Field(True, description="Only export approved pairs")
    include_metadata: bool = Field(False, description="Include generation metadata")
    output_path: Optional[str] = Field(None, description="Output path (defaults to generated)")
    enforce_quality_gate: bool = Field(False, description="Require quality gate pass before export")


class ExportResult(BaseModel):
    """Export result"""
    collection_id: UUID
    format: ExportFormat
    output_path: str
    pairs_exported: int
    splits: Dict[str, int]  # {train: 800, val: 100, test: 100}


# =============================================================================
# TRAINING JOBS
# =============================================================================

class TrainingJobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingJobCreate(BaseModel):
    """Create training job request"""
    model_config = {"protected_namespaces": ()}

    collection_id: UUID = Field(..., description="Training collection to use")
    model_name: str = Field(..., description="Name for the fine-tuned model")
    base_model: Optional[str] = Field(None, description="Base model to fine-tune")
    training_config: Optional[Dict[str, Any]] = Field(None, description="Training hyperparameters")
    train_val_split: float = Field(0.8, ge=0.1, le=0.99, description="Train/val split ratio")


class TrainingJob(BaseModel):
    """Training job response"""
    id: UUID
    collection_id: Optional[UUID] = None
    model_name: str
    base_model: Optional[str] = None
    status: TrainingJobStatus = TrainingJobStatus.PENDING
    training_config: Optional[Dict[str, Any]] = None
    train_val_split: Optional[float] = None
    total_pairs: Optional[int] = None
    train_pairs: Optional[int] = None
    val_pairs: Optional[int] = None
    progress_percent: Optional[float] = None
    current_epoch: Optional[int] = None
    total_epochs: Optional[int] = None
    best_metric: Optional[float] = None
    metric_name: Optional[str] = None
    fmapi_job_id: Optional[str] = None
    mlflow_run_id: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# =============================================================================
# DSPY
# =============================================================================

class DSPyRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DSPyExportRequest(BaseModel):
    """Request to export template as DSPy program"""
    output_format: str = Field("module", description="Export format: module or signature")


class DSPyExportResult(BaseModel):
    """Result of DSPy export"""
    template_id: UUID
    program_code: str
    signature_code: Optional[str] = None
    format: str


class DSPyRunCreate(BaseModel):
    """Create DSPy optimization run"""
    template_id: UUID = Field(..., description="Template to optimize")
    program_name: str = Field(..., description="DSPy program name")
    signature_name: Optional[str] = Field(None, description="DSPy signature name")
    optimizer_type: Optional[str] = Field("BootstrapFewShot", description="Optimizer type")
    config: Optional[Dict[str, Any]] = Field(None, description="Optimizer config")
    trials_total: Optional[int] = Field(None, description="Total optimization trials")


class DSPyRun(BaseModel):
    """DSPy optimization run response"""
    id: UUID
    template_id: Optional[UUID] = None
    program_name: str
    signature_name: Optional[str] = None
    status: DSPyRunStatus = DSPyRunStatus.PENDING
    optimizer_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    trials_completed: Optional[int] = None
    trials_total: Optional[int] = None
    best_score: Optional[float] = None
    results: Optional[Dict[str, Any]] = None
    top_example_ids: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# EXAMPLE STORE
# =============================================================================

class ExampleBase(BaseModel):
    """Base example fields"""
    input_text: str = Field(..., description="Example input")
    output_text: str = Field(..., description="Example output")
    system_context: Optional[str] = Field(None, description="System prompt context")
    domain: Optional[str] = Field(None, description="Domain category")
    task_type: Optional[str] = Field(None, description="Task type")
    difficulty: Optional[str] = Field(None, description="Difficulty level")
    function_name: Optional[str] = Field(None, description="Function name for function-calling")
    capability_tags: List[str] = Field(default_factory=list, description="Capability tags")
    is_verified: bool = Field(False, description="Whether verified by expert")


class ExampleCreate(ExampleBase):
    """Create example request"""
    source_qa_pair_id: Optional[UUID] = Field(None, description="Source QA pair")
    source_description: Optional[str] = Field(None, description="Source description")


class ExampleUpdate(BaseModel):
    """Update example request"""
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    system_context: Optional[str] = None
    domain: Optional[str] = None
    task_type: Optional[str] = None
    difficulty: Optional[str] = None
    function_name: Optional[str] = None
    capability_tags: Optional[List[str]] = None
    is_verified: Optional[bool] = None


class Example(ExampleBase):
    """Example response"""
    id: UUID
    embedding_model: Optional[str] = None
    usage_count: int = 0
    effectiveness_score: Optional[float] = None
    source_qa_pair_id: Optional[UUID] = None
    source_description: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExampleSearchQuery(BaseModel):
    """Search for examples"""
    query_text: Optional[str] = Field(None, description="Text to search for")
    domain: Optional[str] = Field(None, description="Filter by domain")
    task_type: Optional[str] = Field(None, description="Filter by task type")
    difficulty: Optional[str] = Field(None, description="Filter by difficulty")
    function_name: Optional[str] = Field(None, description="Filter by function name")
    capability_tags: Optional[List[str]] = Field(None, description="Filter by tags")
    only_verified: bool = Field(False, description="Only return verified examples")
    limit: int = Field(10, ge=1, le=100, description="Max results")


class ExampleSearchResult(BaseModel):
    """Example search result"""
    example: Example
    similarity_score: Optional[float] = None
    match_type: str = "metadata"  # vector, metadata, hybrid


# =============================================================================
# MODEL TRAINING LINEAGE
# =============================================================================

class ModelLineageCreate(BaseModel):
    """Create lineage record"""
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., description="Model name")
    model_version: str = Field(..., description="Model version")
    model_registry_path: Optional[str] = Field(None, description="Unity Catalog path")
    collection_id: UUID = Field(..., description="Training collection ID")
    training_job_id: Optional[str] = Field(None, description="Databricks job ID")
    training_run_id: Optional[str] = Field(None, description="MLflow run ID")
    base_model: Optional[str] = Field(None, description="Base/foundation model")
    training_params: Optional[Dict[str, Any]] = Field(None, description="Training parameters")


class ModelLineageUpdate(BaseModel):
    """Update lineage record"""
    model_config = {"protected_namespaces": ()}

    model_registry_path: Optional[str] = None
    training_run_id: Optional[str] = None
    final_loss: Optional[float] = None
    final_accuracy: Optional[float] = None
    training_metrics: Optional[Dict[str, Any]] = None
    training_completed_at: Optional[datetime] = None


class ModelLineage(BaseModel):
    """Model lineage response"""
    id: UUID
    model_name: str
    model_version: str
    model_registry_path: Optional[str] = None
    collection_id: Optional[UUID] = None
    training_job_id: Optional[str] = None
    training_run_id: Optional[str] = None
    base_model: Optional[str] = None
    training_params: Optional[Dict[str, Any]] = None
    final_loss: Optional[float] = None
    final_accuracy: Optional[float] = None
    training_metrics: Optional[Dict[str, Any]] = None
    data_lineage: Optional[Dict[str, Any]] = None
    training_started_at: Optional[datetime] = None
    training_completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# =============================================================================
# SEMANTIC LINKING FOR TRAINING DATA
# =============================================================================

class QAPairSemanticLink(BaseModel):
    """Link QA pair to ontology concept"""
    qa_pair_id: UUID
    concept_iri: str
    label: Optional[str] = None


class QAPairsByConceptQuery(BaseModel):
    """Query QA pairs by concept IRI"""
    concept_iri: str
    include_children: bool = Field(False, description="Include pairs linked to child concepts")
    only_approved: bool = Field(True, description="Only return approved pairs")
    limit: int = Field(100, ge=1, le=1000)


class TrainingDataGap(BaseModel):
    """Identified gap in training data coverage"""
    concept_iri: str
    concept_label: Optional[str] = None
    gap_type: str  # coverage, quality, distribution
    severity: str  # low, medium, high
    current_count: int
    recommended_count: int
    description: str
