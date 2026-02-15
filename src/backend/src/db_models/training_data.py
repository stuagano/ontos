"""
ML Training Data Database Models

Adapts VITAL Workbench's Delta Lake schemas to Ontos's PostgreSQL patterns.
Provides the persistence layer for QA pairs, canonical labels, templates,
and training collections.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.common.database import Base


# =============================================================================
# ENUMS
# =============================================================================

class SheetSourceType(str, enum.Enum):
    """Type of data source for a sheet"""
    UNITY_CATALOG_TABLE = "unity_catalog_table"
    UNITY_CATALOG_VOLUME = "unity_catalog_volume"
    DELTA_TABLE = "delta_table"
    EXTERNAL_URL = "external_url"


class SheetSamplingStrategy(str, enum.Enum):
    """Sampling strategy for sheet data"""
    ALL = "all"
    RANDOM = "random"
    STRATIFIED = "stratified"
    FIRST_N = "first_n"


class TemplateStatus(str, enum.Enum):
    """Lifecycle status for templates"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class LabelType(str, enum.Enum):
    """Types of canonical labels"""
    ENTITY_EXTRACTION = "entity_extraction"
    CLASSIFICATION = "classification"
    SENTIMENT = "sentiment"
    SUMMARIZATION = "summarization"
    QA = "qa"
    CUSTOM = "custom"


class LabelConfidence(str, enum.Enum):
    """Confidence level for labels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class UsageType(str, enum.Enum):
    """Allowed/prohibited usage types for labels"""
    TRAINING = "training"
    VALIDATION = "validation"
    EVALUATION = "evaluation"
    FEW_SHOT = "few_shot"
    TESTING = "testing"


class DataClassification(str, enum.Enum):
    """Data sensitivity classification"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class QAPairReviewStatus(str, enum.Enum):
    """Review status for QA pairs"""
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class TrainingSheetStatus(str, enum.Enum):
    """Status for training sheets (materialized datasets)"""
    DRAFT = "draft"
    GENERATING = "generating"
    REVIEW = "review"
    APPROVED = "approved"
    EXPORTED = "exported"
    ARCHIVED = "archived"


class GenerationMethod(str, enum.Enum):
    """How QA pairs were generated"""
    LLM = "llm"
    MANUAL = "manual"
    HYBRID = "hybrid"
    IMPORTED = "imported"


# =============================================================================
# SHEETS - Lightweight pointers to data sources
# =============================================================================

class SheetDb(Base):
    """
    Sheet: A lightweight pointer to a Unity Catalog data source.

    Does NOT copy data - just references external tables/volumes.
    Supports multimodal data (text columns, image columns, metadata columns).
    """
    __tablename__ = "training_sheets_sources"  # Avoid conflict with existing "sheets"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Source configuration
    source_type = Column(
        Enum(SheetSourceType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SheetSourceType.UNITY_CATALOG_TABLE
    )
    source_catalog = Column(String(255), nullable=True)  # Unity Catalog catalog
    source_schema = Column(String(255), nullable=True)   # Unity Catalog schema
    source_table = Column(String(255), nullable=True)    # Table name
    source_volume = Column(String(512), nullable=True)   # Volume path for files
    source_path = Column(Text, nullable=True)            # Path within volume or external URL

    # Column mappings (which columns contain what)
    text_columns = Column(ARRAY(String), nullable=True, default=[])
    image_columns = Column(ARRAY(String), nullable=True, default=[])
    metadata_columns = Column(ARRAY(String), nullable=True, default=[])
    id_column = Column(String(255), nullable=True)  # Primary key column in source

    # Sampling configuration
    sampling_strategy = Column(
        Enum(SheetSamplingStrategy, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SheetSamplingStrategy.ALL
    )
    sample_size = Column(Integer, nullable=True)
    sample_filter = Column(Text, nullable=True)  # SQL WHERE clause
    stratify_column = Column(String(255), nullable=True)

    # Ownership & audit
    owner_id = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    templates = relationship("PromptTemplateDb", back_populates="sheet", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sheets_source", "source_catalog", "source_schema", "source_table"),
        Index("ix_sheets_name", "name"),
    )


# =============================================================================
# PROMPT TEMPLATES - Reusable prompt IP
# =============================================================================

class PromptTemplateDb(Base):
    """
    Prompt Template: Reusable prompt intellectual property.

    Contains system prompt, user prompt template (with {{variable}} placeholders),
    few-shot examples, and output schema for structured extraction.
    """
    __tablename__ = "prompt_templates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(50), nullable=False, default="1.0.0")

    # Status
    status = Column(
        Enum(TemplateStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TemplateStatus.DRAFT
    )

    # Prompt content
    system_prompt = Column(Text, nullable=True)
    user_prompt_template = Column(Text, nullable=False)  # Contains {{variable}} placeholders

    # Few-shot examples (JSON array of example objects)
    few_shot_examples = Column(JSON, nullable=True, default=[])

    # Output schema (JSON Schema for structured extraction)
    output_schema = Column(JSON, nullable=True)

    # Label type this template produces
    label_type = Column(
        Enum(LabelType, values_callable=lambda x: [e.value for e in x]),
        nullable=True
    )
    custom_label_type = Column(String(255), nullable=True)  # For LabelType.CUSTOM

    # Model configuration (defaults, can be overridden at runtime)
    default_model = Column(String(255), nullable=True, default="databricks-meta-llama-3-1-70b-instruct")
    default_temperature = Column(Float, nullable=True, default=0.7)
    default_max_tokens = Column(Integer, nullable=True, default=1024)

    # Source sheet binding (optional - template can be reused across sheets)
    sheet_id = Column(PG_UUID(as_uuid=True), ForeignKey("training_sheets_sources.id", ondelete="SET NULL"), nullable=True)

    # Variable mappings: maps template {{variables}} to sheet columns
    variable_mappings = Column(JSON, nullable=True, default={})

    # Tags for organization
    tags = Column(ARRAY(String), nullable=True, default=[])

    # Ownership & audit
    owner_id = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sheet = relationship("SheetDb", back_populates="templates")
    training_collections = relationship("TrainingCollectionDb", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_prompt_templates_status", "status"),
        Index("ix_prompt_templates_label_type", "label_type"),
        UniqueConstraint("name", "version", name="uq_template_name_version"),
    )


# =============================================================================
# CANONICAL LABELS - Ground truth, reusable labels
# =============================================================================

class CanonicalLabelDb(Base):
    """
    Canonical Label: Ground truth label that can be reused across QA pairs.

    Uses composite key (sheet_id, item_ref, label_type) to enable:
    - "Label once, reuse everywhere" pattern
    - Multiple labelsets per item (same item, different label types)
    """
    __tablename__ = "canonical_labels"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Composite key for reuse
    sheet_id = Column(PG_UUID(as_uuid=True), ForeignKey("training_sheets_sources.id", ondelete="CASCADE"), nullable=False)
    item_ref = Column(String(512), nullable=False)  # Reference to source item (row ID, file path, etc.)
    label_type = Column(
        Enum(LabelType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    custom_label_type = Column(String(255), nullable=True)  # For LabelType.CUSTOM

    # The actual label data (flexible JSON for different label structures)
    label_data = Column(JSON, nullable=False)

    # Quality metadata
    confidence = Column(
        Enum(LabelConfidence, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LabelConfidence.HIGH
    )
    is_verified = Column(Boolean, nullable=False, default=False)
    verified_by = Column(String(255), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Governance: usage constraints
    allowed_uses = Column(ARRAY(String), nullable=False, default=["training", "validation", "evaluation", "few_shot", "testing"])
    prohibited_uses = Column(ARRAY(String), nullable=False, default=[])
    usage_reason = Column(Text, nullable=True)  # Why certain uses are prohibited

    # Data classification
    data_classification = Column(
        Enum(DataClassification, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DataClassification.INTERNAL
    )

    # Reuse tracking
    reuse_count = Column(Integer, nullable=False, default=0)

    # Ownership & audit
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sheet = relationship("SheetDb")
    qa_pairs = relationship("QAPairDb", back_populates="canonical_label")

    __table_args__ = (
        UniqueConstraint("sheet_id", "item_ref", "label_type", name="uq_canonical_label_composite"),
        Index("ix_canonical_labels_sheet_item", "sheet_id", "item_ref"),
        Index("ix_canonical_labels_label_type", "label_type"),
        Index("ix_canonical_labels_verified", "is_verified"),
    )


# =============================================================================
# TRAINING COLLECTIONS - Materialized Q&A datasets
# =============================================================================

class TrainingCollectionDb(Base):
    """
    Training Collection: A materialized dataset of QA pairs.

    Created by combining a Sheet (data source) with a Template (prompt IP).
    Contains generation metadata and approval statistics.
    """
    __tablename__ = "training_collections"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(50), nullable=False, default="1.0.0")

    # Status
    status = Column(
        Enum(TrainingSheetStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TrainingSheetStatus.DRAFT
    )

    # Source bindings
    sheet_id = Column(PG_UUID(as_uuid=True), ForeignKey("training_sheets_sources.id", ondelete="SET NULL"), nullable=True)
    template_id = Column(PG_UUID(as_uuid=True), ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True)

    # Generation configuration
    generation_method = Column(
        Enum(GenerationMethod, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=GenerationMethod.LLM
    )
    model_used = Column(String(255), nullable=True)
    generation_config = Column(JSON, nullable=True)  # temperature, max_tokens, etc.

    # Statistics (updated as pairs are generated/reviewed)
    total_pairs = Column(Integer, nullable=False, default=0)
    approved_pairs = Column(Integer, nullable=False, default=0)
    rejected_pairs = Column(Integer, nullable=False, default=0)
    pending_pairs = Column(Integer, nullable=False, default=0)

    # Export tracking
    last_exported_at = Column(DateTime(timezone=True), nullable=True)
    export_format = Column(String(50), nullable=True)  # jsonl, alpaca, sharegpt, parquet
    export_path = Column(Text, nullable=True)

    # Split configuration (for train/val/test splits)
    default_train_ratio = Column(Float, nullable=False, default=0.8)
    default_val_ratio = Column(Float, nullable=False, default=0.1)
    default_test_ratio = Column(Float, nullable=False, default=0.1)

    # Tags for organization
    tags = Column(ARRAY(String), nullable=True, default=[])

    # Ownership & audit
    owner_id = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sheet = relationship("SheetDb")
    template = relationship("PromptTemplateDb", back_populates="training_collections")
    qa_pairs = relationship("QAPairDb", back_populates="collection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_training_collections_status", "status"),
        Index("ix_training_collections_sheet_template", "sheet_id", "template_id"),
        UniqueConstraint("name", "version", name="uq_collection_name_version"),
    )


# =============================================================================
# QA PAIRS - Individual question-answer pairs
# =============================================================================

class QAPairDb(Base):
    """
    QA Pair: Individual question-answer pair with full metadata.

    Stores messages in OpenAI chat format for direct use in training.
    Links to canonical labels for ground truth reuse.
    """
    __tablename__ = "qa_pairs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Parent collection
    collection_id = Column(PG_UUID(as_uuid=True), ForeignKey("training_collections.id", ondelete="CASCADE"), nullable=False)

    # Source reference
    source_item_ref = Column(String(512), nullable=True)  # Reference to original data item

    # The actual Q&A content (OpenAI chat format)
    messages = Column(JSON, nullable=False)  # [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    # Canonical label link (for ground truth reuse)
    canonical_label_id = Column(PG_UUID(as_uuid=True), ForeignKey("canonical_labels.id", ondelete="SET NULL"), nullable=True)

    # Review status
    review_status = Column(
        Enum(QAPairReviewStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=QAPairReviewStatus.PENDING
    )
    was_auto_approved = Column(Boolean, nullable=False, default=False)

    # Quality signals
    quality_score = Column(Float, nullable=True)  # 0.0 - 1.0
    quality_flags = Column(ARRAY(String), nullable=True, default=[])  # hallucination, incomplete, ambiguous, incorrect

    # Generation metadata
    generation_metadata = Column(JSON, nullable=True)  # model, latency, tokens_used, etc.

    # Human review
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)

    # Edit tracking (if human edited the generated content)
    original_messages = Column(JSON, nullable=True)  # Pre-edit content
    edit_distance = Column(Integer, nullable=True)  # Levenshtein distance from original

    # Split assignment (can be overridden per-pair)
    split = Column(String(20), nullable=True)  # train, val, test
    sampling_weight = Column(Float, nullable=True, default=1.0)

    # Semantic linking (to ontology concepts)
    semantic_concept_iris = Column(ARRAY(String), nullable=True, default=[])

    # Audit
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    collection = relationship("TrainingCollectionDb", back_populates="qa_pairs")
    canonical_label = relationship("CanonicalLabelDb", back_populates="qa_pairs")

    __table_args__ = (
        Index("ix_qa_pairs_collection", "collection_id"),
        Index("ix_qa_pairs_review_status", "review_status"),
        Index("ix_qa_pairs_canonical_label", "canonical_label_id"),
        Index("ix_qa_pairs_split", "split"),
    )


# =============================================================================
# TRAINING JOBS - Fine-tuning job tracking
# =============================================================================

class TrainingJobStatus(str, enum.Enum):
    """Status for training jobs"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingJobDb(Base):
    """
    Training Job: Tracks fine-tuning jobs submitted via Foundation Model APIs.

    Links to a training collection and records progress, metrics, and results.
    """
    __tablename__ = "training_jobs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source collection
    collection_id = Column(PG_UUID(as_uuid=True), ForeignKey("training_collections.id", ondelete="SET NULL"), nullable=True)

    # Model configuration
    model_name = Column(String(255), nullable=False)
    base_model = Column(String(255), nullable=True)

    # Status tracking
    status = Column(
        Enum(TrainingJobStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TrainingJobStatus.PENDING
    )

    # Training configuration
    training_config = Column(JSON, nullable=True)  # epochs, batch_size, learning_rate, etc.
    train_val_split = Column(Float, nullable=True, default=0.8)

    # Pair counts
    total_pairs = Column(Integer, nullable=True)
    train_pairs = Column(Integer, nullable=True)
    val_pairs = Column(Integer, nullable=True)

    # Progress tracking
    progress_percent = Column(Float, nullable=True, default=0.0)
    current_epoch = Column(Integer, nullable=True)
    total_epochs = Column(Integer, nullable=True)

    # Metrics
    best_metric = Column(Float, nullable=True)
    metric_name = Column(String(100), nullable=True)

    # External IDs
    fmapi_job_id = Column(String(255), nullable=True)  # Foundation Model API job ID
    mlflow_run_id = Column(String(255), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    collection = relationship("TrainingCollectionDb")

    __table_args__ = (
        Index("ix_training_jobs_status", "status"),
        Index("ix_training_jobs_collection", "collection_id"),
        Index("ix_training_jobs_fmapi", "fmapi_job_id"),
    )


# =============================================================================
# DSPY OPTIMIZATION RUNS
# =============================================================================

class DSPyRunStatus(str, enum.Enum):
    """Status for DSPy optimization runs"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DSPyOptimizationRunDb(Base):
    """
    DSPy Optimization Run: Tracks DSPy prompt optimization runs.

    Persisted to DB (unlike VITAL's in-memory approach) for restart resilience.
    """
    __tablename__ = "dspy_optimization_runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source template
    template_id = Column(PG_UUID(as_uuid=True), ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True)

    # Program configuration
    program_name = Column(String(255), nullable=False)
    signature_name = Column(String(255), nullable=True)

    # Status
    status = Column(
        Enum(DSPyRunStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DSPyRunStatus.PENDING
    )

    # Optimizer configuration
    optimizer_type = Column(String(100), nullable=True)  # BootstrapFewShot, MIPRO, etc.
    config = Column(JSON, nullable=True)  # optimizer-specific config

    # Progress
    trials_completed = Column(Integer, nullable=True, default=0)
    trials_total = Column(Integer, nullable=True)

    # Results
    best_score = Column(Float, nullable=True)
    results = Column(JSON, nullable=True)  # Full optimization results
    top_example_ids = Column(ARRAY(String), nullable=True, default=[])

    # Error handling
    error_message = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    template = relationship("PromptTemplateDb")

    __table_args__ = (
        Index("ix_dspy_runs_status", "status"),
        Index("ix_dspy_runs_template", "template_id"),
    )


# =============================================================================
# EXAMPLE STORE - Few-shot examples with embeddings
# =============================================================================

class ExampleStoreDb(Base):
    """
    Example Store: Repository of few-shot examples with vector embeddings.

    Supports semantic search for finding relevant examples.
    Tracks effectiveness metrics for continuous improvement.
    """
    __tablename__ = "example_store"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content
    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=False)
    system_context = Column(Text, nullable=True)  # Optional system prompt context

    # Categorization
    domain = Column(String(255), nullable=True, index=True)  # defect_detection, predictive_maintenance, etc.
    task_type = Column(String(255), nullable=True, index=True)  # entity_extraction, classification, etc.
    difficulty = Column(String(50), nullable=True)  # simple, moderate, complex, edge_case
    function_name = Column(String(255), nullable=True)  # For function-calling patterns

    # Tags for flexible categorization
    capability_tags = Column(ARRAY(String), nullable=True, default=[])

    # Vector embedding for semantic search (1536-dim for common embedding models)
    embedding = Column(ARRAY(Float), nullable=True)
    embedding_model = Column(String(255), nullable=True)

    # Effectiveness tracking
    usage_count = Column(Integer, nullable=False, default=0)
    effectiveness_score = Column(Float, nullable=True)  # Based on downstream task performance
    is_verified = Column(Boolean, nullable=False, default=False)

    # Source tracking
    source_qa_pair_id = Column(PG_UUID(as_uuid=True), ForeignKey("qa_pairs.id", ondelete="SET NULL"), nullable=True)
    source_description = Column(Text, nullable=True)

    # Audit
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_example_store_domain_task", "domain", "task_type"),
        Index("ix_example_store_function", "function_name"),
        Index("ix_example_store_verified", "is_verified"),
    )


# =============================================================================
# ML FEEDBACK ITEMS - User feedback on model predictions
# =============================================================================

class FeedbackItemDb(Base):
    """
    Feedback Item: User feedback on model predictions for improvement loop.

    Tracks queries, responses, ratings, and optional conversion to training pairs.
    """
    __tablename__ = "ml_feedback_items"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Model context
    model_name = Column(String(255), nullable=False, index=True)
    endpoint_name = Column(String(255), nullable=True)

    # The interaction
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)

    # Rating
    rating = Column(Integer, nullable=True)  # 1-5
    feedback_type = Column(String(100), nullable=True)  # positive, negative, neutral
    category = Column(String(255), nullable=True)  # hallucination, incomplete, wrong_format, etc.
    comment = Column(Text, nullable=True)

    # Conversion to training data
    is_converted = Column(Boolean, nullable=False, default=False)
    converted_to_pair_id = Column(PG_UUID(as_uuid=True), ForeignKey("qa_pairs.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_feedback_model", "model_name"),
        Index("ix_feedback_rating", "rating"),
        Index("ix_feedback_converted", "is_converted"),
    )


# =============================================================================
# ML IDENTIFIED GAPS - Systematic gaps in model coverage
# =============================================================================

class GapSeverity(str, enum.Enum):
    """Severity of identified gap"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapStatus(str, enum.Enum):
    """Status of gap remediation"""
    IDENTIFIED = "identified"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class GapRecordDb(Base):
    """
    Gap Record: Identified gap in model coverage or quality.

    Tracks systematic issues found through monitoring, feedback analysis,
    or manual review with suggested remediation actions.
    """
    __tablename__ = "ml_identified_gaps"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Gap details
    gap_type = Column(String(100), nullable=False)  # coverage, quality, distribution, drift
    severity = Column(
        Enum(GapSeverity, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=GapSeverity.MEDIUM
    )
    description = Column(Text, nullable=False)

    # Context
    model_name = Column(String(255), nullable=True)
    template_id = Column(PG_UUID(as_uuid=True), ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True)
    affected_queries_count = Column(Integer, nullable=True)
    error_rate = Column(Float, nullable=True)

    # Remediation
    suggested_action = Column(Text, nullable=True)
    estimated_records_needed = Column(Integer, nullable=True)
    status = Column(
        Enum(GapStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=GapStatus.IDENTIFIED
    )
    priority = Column(Integer, nullable=True, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_gaps_severity", "severity"),
        Index("ix_gaps_status", "status"),
        Index("ix_gaps_model", "model_name"),
    )


# =============================================================================
# MODEL TRAINING LINEAGE - Full traceability
# =============================================================================

class ModelTrainingLineageDb(Base):
    """
    Model Training Lineage: Complete traceability from model to source data.

    Records which collections, templates, and source data were used
    to train each model version.
    """
    __tablename__ = "model_training_lineage"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Model identification
    model_name = Column(String(255), nullable=False, index=True)
    model_version = Column(String(50), nullable=False)
    model_registry_path = Column(Text, nullable=True)  # Unity Catalog path

    # Training source
    collection_id = Column(PG_UUID(as_uuid=True), ForeignKey("training_collections.id", ondelete="SET NULL"), nullable=True)

    # Training job tracking
    training_job_id = Column(String(255), nullable=True)  # Databricks job ID
    training_run_id = Column(String(255), nullable=True)  # MLflow run ID

    # Base model
    base_model = Column(String(255), nullable=True)

    # Training configuration
    training_params = Column(JSON, nullable=True)  # epochs, batch_size, learning_rate, etc.

    # Metrics
    final_loss = Column(Float, nullable=True)
    final_accuracy = Column(Float, nullable=True)
    training_metrics = Column(JSON, nullable=True)  # Per-epoch metrics

    # Data lineage (denormalized for query efficiency)
    data_lineage = Column(JSON, nullable=True)  # {sheet_id, template_id, qa_pair_count, canonical_label_ids}

    # Timestamps
    training_started_at = Column(DateTime(timezone=True), nullable=True)
    training_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    collection = relationship("TrainingCollectionDb")

    __table_args__ = (
        UniqueConstraint("model_name", "model_version", name="uq_model_lineage_version"),
        Index("ix_lineage_model", "model_name"),
        Index("ix_lineage_collection", "collection_id"),
    )
