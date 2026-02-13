/**
 * Training Data Curation Types
 *
 * TypeScript interfaces for ML training data management UI.
 * Maps to backend Pydantic models in src/backend/src/models/training_data.py
 */

// =============================================================================
// ENUMS
// =============================================================================

export enum SheetSourceType {
  UNITY_CATALOG_TABLE = "unity_catalog_table",
  UNITY_CATALOG_VOLUME = "unity_catalog_volume",
  DELTA_TABLE = "delta_table",
  EXTERNAL_URL = "external_url",
}

export enum SheetSamplingStrategy {
  ALL = "all",
  RANDOM = "random",
  STRATIFIED = "stratified",
  FIRST_N = "first_n",
}

export enum TemplateStatus {
  DRAFT = "draft",
  ACTIVE = "active",
  DEPRECATED = "deprecated",
  ARCHIVED = "archived",
}

export enum LabelType {
  ENTITY_EXTRACTION = "entity_extraction",
  CLASSIFICATION = "classification",
  SENTIMENT = "sentiment",
  SUMMARIZATION = "summarization",
  QA = "qa",
  CUSTOM = "custom",
}

export enum LabelConfidence {
  HIGH = "high",
  MEDIUM = "medium",
  LOW = "low",
}

export enum UsageType {
  TRAINING = "training",
  VALIDATION = "validation",
  EVALUATION = "evaluation",
  FEW_SHOT = "few_shot",
  TESTING = "testing",
}

export enum DataClassification {
  PUBLIC = "public",
  INTERNAL = "internal",
  CONFIDENTIAL = "confidential",
  RESTRICTED = "restricted",
}

export enum QAPairReviewStatus {
  PENDING = "pending",
  AUTO_APPROVED = "auto_approved",
  APPROVED = "approved",
  EDITED = "edited",
  REJECTED = "rejected",
  FLAGGED = "flagged",
}

export enum TrainingCollectionStatus {
  DRAFT = "draft",
  GENERATING = "generating",
  REVIEW = "review",
  APPROVED = "approved",
  EXPORTED = "exported",
  ARCHIVED = "archived",
}

export enum GenerationMethod {
  LLM = "llm",
  MANUAL = "manual",
  HYBRID = "hybrid",
  IMPORTED = "imported",
}

export enum ExportFormat {
  JSONL = "jsonl",
  ALPACA = "alpaca",
  SHAREGPT = "sharegpt",
  PARQUET = "parquet",
  CSV = "csv",
}

// =============================================================================
// CHAT MESSAGE
// =============================================================================

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  name?: string;
  tool_calls?: Record<string, unknown>[];
  tool_call_id?: string;
}

// =============================================================================
// SHEETS
// =============================================================================

export interface Sheet {
  id: string;
  name: string;
  description?: string;
  source_type: SheetSourceType;
  source_catalog?: string;
  source_schema?: string;
  source_table?: string;
  source_volume?: string;
  source_path?: string;
  text_columns: string[];
  image_columns: string[];
  metadata_columns: string[];
  id_column?: string;
  sampling_strategy: SheetSamplingStrategy;
  sample_size?: number;
  sample_filter?: string;
  stratify_column?: string;
  owner_id?: string;
  created_by?: string;
  updated_by?: string;
  created_at: string;
  updated_at: string;
}

export interface SheetCreate {
  name: string;
  description?: string;
  source_type: SheetSourceType;
  source_catalog?: string;
  source_schema?: string;
  source_table?: string;
  source_volume?: string;
  source_path?: string;
  text_columns?: string[];
  image_columns?: string[];
  metadata_columns?: string[];
  id_column?: string;
  sampling_strategy?: SheetSamplingStrategy;
  sample_size?: number;
  sample_filter?: string;
  stratify_column?: string;
  owner_id?: string;
}

export interface SheetValidationResult {
  valid: boolean;
  error?: string;
  source?: string;
  schema?: Array<{
    name: string;
    type: string;
    nullable: boolean;
    comment?: string;
  }>;
}

export interface SheetPreviewResult {
  items: Record<string, unknown>[];
  count: number;
  total_available?: number;
  source: string;
  columns: string[];
  warning?: string;
}

// =============================================================================
// PROMPT TEMPLATES
// =============================================================================

export interface PromptTemplate {
  id: string;
  name: string;
  description?: string;
  version: string;
  status: TemplateStatus;
  system_prompt?: string;
  user_prompt_template: string;
  few_shot_examples: Record<string, unknown>[];
  output_schema?: Record<string, unknown>;
  label_type?: LabelType;
  custom_label_type?: string;
  default_model?: string;
  default_temperature?: number;
  default_max_tokens?: number;
  sheet_id?: string;
  variable_mappings: Record<string, string>;
  tags: string[];
  owner_id?: string;
  created_by?: string;
  updated_by?: string;
  created_at: string;
  updated_at: string;
}

export interface PromptTemplateCreate {
  name: string;
  description?: string;
  version?: string;
  status?: TemplateStatus;
  system_prompt?: string;
  user_prompt_template: string;
  few_shot_examples?: Record<string, unknown>[];
  output_schema?: Record<string, unknown>;
  label_type?: LabelType;
  custom_label_type?: string;
  default_model?: string;
  default_temperature?: number;
  default_max_tokens?: number;
  sheet_id?: string;
  variable_mappings?: Record<string, string>;
  tags?: string[];
  owner_id?: string;
}

// =============================================================================
// CANONICAL LABELS
// =============================================================================

export interface CanonicalLabel {
  id: string;
  sheet_id: string;
  item_ref: string;
  label_type: LabelType;
  custom_label_type?: string;
  label_data: Record<string, unknown>;
  confidence: LabelConfidence;
  is_verified: boolean;
  verified_by?: string;
  verified_at?: string;
  allowed_uses: UsageType[];
  prohibited_uses: UsageType[];
  usage_reason?: string;
  data_classification: DataClassification;
  reuse_count: number;
  created_by?: string;
  updated_by?: string;
  created_at: string;
  updated_at: string;
}

export interface CanonicalLabelCreate {
  sheet_id: string;
  item_ref: string;
  label_type: LabelType;
  custom_label_type?: string;
  label_data: Record<string, unknown>;
  confidence?: LabelConfidence;
  is_verified?: boolean;
  allowed_uses?: UsageType[];
  prohibited_uses?: UsageType[];
  usage_reason?: string;
  data_classification?: DataClassification;
}

// =============================================================================
// TRAINING COLLECTIONS
// =============================================================================

export interface TrainingCollection {
  id: string;
  name: string;
  description?: string;
  version: string;
  status: TrainingCollectionStatus;
  sheet_id?: string;
  template_id?: string;
  generation_method: GenerationMethod;
  model_used?: string;
  generation_config?: Record<string, unknown>;
  total_pairs: number;
  approved_pairs: number;
  rejected_pairs: number;
  pending_pairs: number;
  default_train_ratio: number;
  default_val_ratio: number;
  default_test_ratio: number;
  last_exported_at?: string;
  export_format?: string;
  export_path?: string;
  tags: string[];
  owner_id?: string;
  created_by?: string;
  updated_by?: string;
  created_at: string;
  updated_at: string;
}

export interface TrainingCollectionCreate {
  name: string;
  description?: string;
  version?: string;
  status?: TrainingCollectionStatus;
  sheet_id?: string;
  template_id?: string;
  generation_method?: GenerationMethod;
  model_used?: string;
  generation_config?: Record<string, unknown>;
  default_train_ratio?: number;
  default_val_ratio?: number;
  default_test_ratio?: number;
  tags?: string[];
  owner_id?: string;
}

export interface TrainingCollectionStats {
  total_pairs: number;
  approved_pairs: number;
  rejected_pairs: number;
  pending_pairs: number;
  approval_rate: number;
}

// =============================================================================
// QA PAIRS
// =============================================================================

export interface QAPair {
  id: string;
  collection_id: string;
  source_item_ref?: string;
  messages: ChatMessage[];
  canonical_label_id?: string;
  review_status: QAPairReviewStatus;
  was_auto_approved: boolean;
  quality_score?: number;
  quality_flags: string[];
  generation_metadata?: Record<string, unknown>;
  reviewed_by?: string;
  reviewed_at?: string;
  review_notes?: string;
  original_messages?: ChatMessage[];
  edit_distance?: number;
  split?: string;
  sampling_weight: number;
  semantic_concept_iris: string[];
  created_by?: string;
  updated_by?: string;
  created_at: string;
  updated_at: string;
}

export interface QAPairCreate {
  collection_id: string;
  messages: ChatMessage[];
  source_item_ref?: string;
  canonical_label_id?: string;
  review_status?: QAPairReviewStatus;
  quality_score?: number;
  quality_flags?: string[];
  split?: string;
  sampling_weight?: number;
  semantic_concept_iris?: string[];
  generation_metadata?: Record<string, unknown>;
}

export interface QAPairBulkReview {
  pair_ids: string[];
  review_status: QAPairReviewStatus;
  review_notes?: string;
}

// =============================================================================
// GENERATION
// =============================================================================

export interface GenerationRequest {
  collection_id: string;
  sheet_id?: string;
  template_id?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  sample_size?: number;
  auto_approve_with_canonical?: boolean;
  link_to_canonical?: boolean;
}

export interface GenerationResult {
  collection_id: string;
  pairs_generated: number;
  pairs_auto_approved: number;
  pairs_pending_review: number;
  errors: Array<{ item_ref: string; error: string }>;
}

// =============================================================================
// EXPORT
// =============================================================================

export interface ExportRequest {
  collection_id: string;
  format: ExportFormat;
  include_splits?: string[];
  only_approved?: boolean;
  include_metadata?: boolean;
  output_path?: string;
}

export interface ExportResult {
  collection_id: string;
  format: ExportFormat;
  output_path: string;
  pairs_exported: number;
  splits: Record<string, number>;
}

// =============================================================================
// SEMANTIC LINKING
// =============================================================================

export interface QAPairsByConceptQuery {
  concept_iri: string;
  include_children?: boolean;
  only_approved?: boolean;
  limit?: number;
}

export interface TrainingDataGap {
  concept_iri: string;
  concept_label?: string;
  gap_type: string;
  severity: string;
  current_count: number;
  recommended_count: number;
  description: string;
}

// =============================================================================
// MODEL LINEAGE
// =============================================================================

export interface ModelLineage {
  id: string;
  model_name: string;
  model_version: string;
  model_registry_path?: string;
  collection_id?: string;
  training_job_id?: string;
  training_run_id?: string;
  base_model?: string;
  training_params?: Record<string, unknown>;
  final_loss?: number;
  final_accuracy?: number;
  training_metrics?: Record<string, unknown>;
  data_lineage?: Record<string, unknown>;
  training_started_at?: string;
  training_completed_at?: string;
  created_by?: string;
  created_at: string;
}

// =============================================================================
// UI HELPERS
// =============================================================================

export const REVIEW_STATUS_COLORS: Record<QAPairReviewStatus, string> = {
  [QAPairReviewStatus.PENDING]: "bg-yellow-100 text-yellow-800",
  [QAPairReviewStatus.AUTO_APPROVED]: "bg-blue-100 text-blue-800",
  [QAPairReviewStatus.APPROVED]: "bg-green-100 text-green-800",
  [QAPairReviewStatus.EDITED]: "bg-purple-100 text-purple-800",
  [QAPairReviewStatus.REJECTED]: "bg-red-100 text-red-800",
  [QAPairReviewStatus.FLAGGED]: "bg-orange-100 text-orange-800",
};

export const COLLECTION_STATUS_COLORS: Record<TrainingCollectionStatus, string> = {
  [TrainingCollectionStatus.DRAFT]: "bg-gray-100 text-gray-800",
  [TrainingCollectionStatus.GENERATING]: "bg-blue-100 text-blue-800",
  [TrainingCollectionStatus.REVIEW]: "bg-yellow-100 text-yellow-800",
  [TrainingCollectionStatus.APPROVED]: "bg-green-100 text-green-800",
  [TrainingCollectionStatus.EXPORTED]: "bg-purple-100 text-purple-800",
  [TrainingCollectionStatus.ARCHIVED]: "bg-gray-100 text-gray-600",
};

export const TEMPLATE_STATUS_COLORS: Record<TemplateStatus, string> = {
  [TemplateStatus.DRAFT]: "bg-gray-100 text-gray-800",
  [TemplateStatus.ACTIVE]: "bg-green-100 text-green-800",
  [TemplateStatus.DEPRECATED]: "bg-yellow-100 text-yellow-800",
  [TemplateStatus.ARCHIVED]: "bg-gray-100 text-gray-600",
};

export const CONFIDENCE_COLORS: Record<LabelConfidence, string> = {
  [LabelConfidence.HIGH]: "bg-green-100 text-green-800",
  [LabelConfidence.MEDIUM]: "bg-yellow-100 text-yellow-800",
  [LabelConfidence.LOW]: "bg-red-100 text-red-800",
};
