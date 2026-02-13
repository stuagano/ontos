# ML Training Data Generation Workflow Assessment

**Date:** 2026-02-12
**Scope:** Assess Ontos codebase for supporting an ML training data generation workflow encompassing raw data prompt templates, assembly into data/prompt instances, and reusable QA pairs across training set collections.

---

## Executive Summary

Ontos has **no existing ML training data generation capability**, but its architecture provides unusually strong foundations for building one. The codebase's entity lifecycle patterns (versioned CRUD with status workflows), template/serialization infrastructure, tool registry, and LLM integration layer can be directly extended. The gaps are entirely in domain-specific models and orchestration logic - not in architectural patterns.

**Verdict:** The project is well-positioned to support this workflow with moderate effort. The required primitives (templating, versioning, serialization, workflow orchestration, LLM calling) all exist. What's missing is the domain model layer connecting them for training data generation.

---

## 1. Current State: What Exists

### 1.1 LLM Infrastructure (Directly Reusable)

| Component | Location | Relevance |
|-----------|----------|-----------|
| `LLMSearchManager` | `controller/llm_search_manager.py` | Conversational LLM orchestration with tool-calling - could drive prompt-based data generation |
| `LLMService` | `common/llm_service.py` | Two-phase LLM calling (security check + content analysis) - reusable for QA generation with quality gates |
| `ToolRegistry` + `BaseTool` | `tools/registry.py`, `tools/base.py` | Pluggable tool system in OpenAI/MCP format - new data generation tools slot in cleanly |
| `ConversationSession` / `ChatMessage` | `models/llm_search.py`, `db_models/llm_sessions.py` | Persisted conversation storage - could capture raw QA generation sessions as provenance |

The `SYSTEM_PROMPT` in `llm_search_manager.py:35-118` demonstrates the existing pattern for structured prompting. This is a hard-coded string, not a template system - but it proves the integration works.

### 1.2 Template & Serialization Patterns

| Pattern | Location | Relevance |
|---------|----------|-----------|
| `FileModel` base class | `file_models/base.py` | Kubernetes-style YAML serialization with `apiVersion`, `kind`, `metadata`, `spec` - ideal format for prompt template definitions |
| `FileModelRegistry` | `file_models/base.py:159` | Decorator-based registry for entity types - new `PromptTemplate` file model registers automatically |
| Workflow notification templates | `models/process_workflows.py:175-187` | `NotificationStepConfig` with `template` field + `custom_message` - demonstrates template resolution pattern |
| `WebhookStepConfig.body_template` | `models/process_workflows.py:269` | `${variable}` substitution in JSON bodies - existing template variable syntax |
| YAML data files | `data/settings.yaml`, `data/default_workflows.yaml` | YAML-based configuration as data - natural format for prompt template libraries |

### 1.3 Entity Lifecycle Management

The codebase's strongest asset for this use case is its mature entity lifecycle pattern:

- **Versioned entities** with `parent_id` chains and `base_name` grouping (Data Products, Data Contracts)
- **Status workflows**: DRAFT → PROPOSED → UNDER_REVIEW → APPROVED → ACTIVE → DEPRECATED → RETIRED
- **Process workflows** (`process_workflows.py`) with triggers (`ON_CREATE`, `ON_STATUS_CHANGE`, `SCHEDULED`) and step types (`VALIDATION`, `APPROVAL`, `SCRIPT`, `CONDITIONAL`)
- **Repository pattern** (`CRUDBase`) with generic typed CRUD, relationship handling, eager loading
- **Tag system** with hierarchical namespaces - could tag training data by model, task type, domain
- **Subscription model** for tracking consumers of data products - maps to tracking which models consume which training sets

### 1.4 Data Contract / Schema Infrastructure

Data Contracts (`models/data_contracts_api.py`, `db_models/data_contracts.py`) are the closest existing analogy to what prompt templates + QA pair schemas need:

- Schema definitions with column types, constraints, validation rules
- ODCS v3.0.2 standard compliance with JSON Schema validation (`schemas/odcs-json-schema-v3.0.2.json`)
- Import/export in YAML, JSON formats
- Version lineage tracking

---

## 2. Gap Analysis: What's Missing

### 2.1 Prompt Template System (Not Present)

**Need:** A way to define, version, and parameterize raw data prompt templates that can be instantiated with variable data to produce concrete prompts.

**Current gap:**
- No `PromptTemplate` model or storage
- No template variable resolution engine beyond the simple `${variable}` substitution in webhook configs
- No template inheritance or composition (e.g., base system prompt + task-specific prompt + format instructions)
- The existing `SYSTEM_PROMPT` in `llm_search_manager.py` is a monolithic string, not a composable template

**What would be needed:**
- `PromptTemplate` Pydantic model with: `id`, `name`, `version`, `status`, `template_text` (with `{{variable}}` slots), `variables` schema (name/type/description/default), `category` (system/user/few-shot/qa), `output_format` spec
- `PromptTemplateDb` SQLAlchemy model
- `PromptTemplateRepository` extending `CRUDBase`
- Template rendering engine (Jinja2 is the natural choice - not currently a dependency)
- `PromptTemplateFileModel` for YAML serialization/Git sync

### 2.2 Data Assembly Pipeline (Not Present)

**Need:** An orchestration layer that combines raw data sources + prompt templates to produce concrete training instances (filled prompts, QA pairs, instruction/response tuples).

**Current gap:**
- No concept of "data source binding" to template variables
- No batch generation / assembly orchestration
- No sampling, filtering, or deduplication logic for source data
- The workflow system (`ProcessWorkflow`) handles governance events but not data transformation pipelines

**What would be needed:**
- `DataAssemblyPipeline` model: references prompt templates + data sources + output schema
- `DataSourceBinding`: maps template variables to data columns/fields (from Unity Catalog tables, Data Contracts, or uploaded files)
- `AssemblyRun` execution model: tracks batch generation runs with row counts, error rates, sample outputs
- Integration with Databricks SQL or Spark for scaled-out generation (existing `WorkspaceClient` SDK integration supports this)
- The existing `StepType.SCRIPT` workflow step could be extended to run assembly scripts

### 2.3 QA Pair Model (Not Present)

**Need:** A structured entity for question-answer pairs with metadata, quality signals, and reusability across multiple training set collections.

**Current gap:**
- No `QAPair` entity
- No concept of "training set collection" that aggregates QA pairs
- No quality scoring or human-review workflow specific to training data
- No deduplication or similarity detection

**What would be needed:**
- `QAPair` model: `question`, `answer`, `context` (optional), `source_template_id`, `source_data_ref`, `quality_score`, `human_reviewed`, `review_status`
- `TrainingCollection` model: named, versioned grouping of QA pairs with split ratios (train/val/test), export format config
- `CollectionMembership`: many-to-many between QA pairs and collections (enabling reuse)
- Quality metrics: automated scoring (LLM-as-judge via existing `LLMService`), human review workflow (could reuse `DataAssetReview` pattern from `controller/data_asset_reviews_manager.py`)

### 2.4 Export / Format Support (Partially Present)

**Current support:**
- YAML/JSON serialization via `FileModel`
- ODCS standard export for contracts

**Missing for training data:**
- JSONL export (standard for fine-tuning: OpenAI, Anthropic, HuggingFace)
- Alpaca format (`{"instruction": ..., "input": ..., "output": ...}`)
- ShareGPT format (`{"conversations": [{"from": "human", ...}, {"from": "gpt", ...}]}`)
- Parquet export for large datasets
- HuggingFace datasets integration
- Split-aware export (train/val/test)

---

## 3. Architecture Fit Assessment

### 3.1 Patterns That Map Cleanly

| Training Data Concept | Existing Ontos Pattern | Fit Quality |
|----------------------|----------------------|-------------|
| Prompt Template versioning | Data Contract versioning (parent_id chains) | Excellent |
| Template approval workflow | Process Workflows (VALIDATION → APPROVAL → NOTIFICATION) | Excellent |
| QA pair quality review | Data Asset Reviews (`data_asset_reviews_manager.py`) | Good |
| Training collection subscription | Data Product subscriptions (`DataProductSubscriptionDb`) | Good |
| Template tagging/discovery | Tag system with namespaces | Excellent |
| Search across templates/QA pairs | `SearchableAsset` + `@searchable_asset` decorator | Excellent |
| Batch generation jobs | Workflow Configurations + Databricks Jobs (`jobs_manager.py`) | Good |
| LLM-based QA generation | `LLMService` + `ToolRegistry` | Good |
| Template YAML storage/Git sync | `FileModel` + `FileModelRegistry` | Excellent |
| Access control for training data | Role-based permissions (`authorization.py`, `features.py`) | Excellent |

### 3.2 Patterns That Need Adaptation

| Concept | Challenge | Approach |
|---------|-----------|----------|
| Batch data assembly | Workflow system is event-driven, not batch-oriented | Add a `BATCH_GENERATE` step type or use Databricks Jobs directly |
| Template variable resolution | Only simple `${var}` exists; need Jinja2-level logic | Add Jinja2 dependency; create `TemplateRenderer` service |
| QA pair deduplication | No similarity/embedding infrastructure | Could use Databricks Vector Search or add a lightweight embedding service |
| Multi-collection membership | Entity relationships are 1:N, not N:M for most models | Add explicit junction table (`collection_qa_pair_membership`) |
| Export format variety | `FileModel` only outputs YAML | Create separate `ExportService` with format-specific serializers |

### 3.3 Technical Debt Risks

- **Manager complexity**: `data_contracts_manager.py` is 251KB. A `TrainingDataManager` that combines templates + assembly + QA + collections risks similar sprawl. Recommend splitting into: `PromptTemplateManager`, `DataAssemblyManager`, `QAPairManager`, `TrainingCollectionManager`.
- **LLM dependency**: QA generation via LLM requires careful rate limiting and cost tracking. The existing `CostsManager` could be extended.
- **Data volume**: Training sets can be orders of magnitude larger than governance metadata. The SQLite/Postgres storage pattern works for templates and collection metadata, but actual training data (generated QA pairs in bulk) should live in Unity Catalog tables/Delta Lake, not in the app database.

---

## 4. Proposed Domain Model

```
┌──────────────────┐     ┌──────────────────┐
│  PromptTemplate  │     │   DataSource     │
│                  │     │                  │
│  - id            │     │  - id            │
│  - name          │     │  - name          │
│  - version       │     │  - type (table/  │
│  - status        │     │    file/api)     │
│  - template_text │     │  - connection    │
│  - variables[]   │     │  - query/path    │
│  - category      │     │  - schema        │
│  - output_format │     └────────┬─────────┘
└────────┬─────────┘              │
         │                        │
         │    ┌───────────────────┘
         │    │
         ▼    ▼
┌──────────────────────┐
│  AssemblyPipeline    │
│                      │
│  - id                │
│  - name              │
│  - template_id  ─────┼──→ PromptTemplate
│  - data_bindings[]   │     (variable → column mapping)
│  - sampling_config   │
│  - generation_config │
│  - output_type       │     (qa_pair | instruction | chat)
└────────┬─────────────┘
         │
         │ runs
         ▼
┌──────────────────────┐
│  AssemblyRun         │
│                      │
│  - id                │
│  - pipeline_id       │
│  - status            │
│  - rows_generated    │
│  - error_count       │
│  - output_location   │     (Delta table path)
└────────┬─────────────┘
         │
         │ produces
         ▼
┌──────────────────────┐         ┌─────────────────────┐
│  QAPair              │◄───────►│ TrainingCollection   │
│                      │  N : M  │                      │
│  - id                │         │  - id                │
│  - question          │         │  - name              │
│  - answer            │         │  - version           │
│  - context           │         │  - status            │
│  - source_template   │         │  - split_config      │
│  - source_run        │         │  - export_format     │
│  - quality_score     │         │  - pair_count        │
│  - review_status     │         │  - collections can   │
│  - tags[]            │         │    share QA pairs    │
└──────────────────────┘         └─────────────────────┘
```

---

## 5. Reusability Strategy for QA Pairs

The key architectural requirement - QA pairs reusable across multiple training set collections - maps to a **many-to-many relationship** with collection-specific overrides:

```
CollectionMembership:
  - collection_id  (FK → TrainingCollection)
  - qa_pair_id     (FK → QAPair)
  - split_override (optional: force this pair into train/val/test)
  - weight         (optional: sampling weight within this collection)
  - added_at
  - added_by
```

This allows:
1. **Same QA pair in multiple collections** - e.g., a healthcare QA pair appears in both "Healthcare Domain Expert" and "General Medical" training sets
2. **Collection-specific split assignment** - pair is in training set for collection A but validation set for collection B
3. **Weighted sampling** - high-quality pairs get higher weight
4. **Provenance tracking** - who added which pair to which collection, when

The existing **subscription pattern** (`DataProductSubscriptionDb`) provides a direct analogue for this relationship.

---

## 6. Integration Points with Existing Ontos Features

| Existing Feature | Integration Opportunity |
|-----------------|----------------------|
| **Data Contracts** | Use contract schemas to define expected QA pair structure; validate generated pairs against contract |
| **Data Products** | Publish training collections as Data Products with output ports pointing to Delta tables |
| **Business Glossary** | Use glossary terms as seed data for domain-specific QA generation |
| **Tags** | Tag QA pairs with `domain/healthcare`, `task/summarization`, `difficulty/expert`, `model/gpt-4` |
| **Process Workflows** | Trigger quality checks on new QA pairs; approval workflows for collection releases |
| **Compliance** | Validate training data against PII/security policies before export |
| **Search** | Make templates, QA pairs, and collections discoverable via `SearchableAsset` |
| **Notifications** | Alert collection subscribers when new pairs are added or quality scores change |
| **Git Sync** | Version prompt templates as YAML in Git alongside governance configs |
| **LLM Service** | Use for automated QA generation and LLM-as-judge quality scoring |
| **Tool Registry** | Add `GenerateQAPairs`, `SearchTemplates`, `ExportCollection` tools for LLM-assisted workflows |

---

## 7. Recommended Implementation Phases

### Phase 1: Prompt Template Foundation
- `PromptTemplate` model/db_model/repository/manager
- CRUD API routes
- YAML serialization via `FileModel`
- Template variable schema definition
- Basic Jinja2 rendering engine
- Frontend view for template management

### Phase 2: Data Assembly
- `DataSource` + `AssemblyPipeline` models
- Variable-to-data binding configuration
- `AssemblyRun` execution tracking
- Databricks SQL/Spark job integration for batch generation
- Sampling and filtering configuration

### Phase 3: QA Pairs & Collections
- `QAPair` model with quality metadata
- `TrainingCollection` with N:M membership
- Split assignment (train/val/test)
- LLM-based quality scoring via `LLMService`
- Human review workflow (adapt `DataAssetReview` pattern)

### Phase 4: Export & Distribution
- JSONL, Alpaca, ShareGPT, Parquet exporters
- HuggingFace datasets push integration
- Collection versioning and diff
- Publish collections as Data Products
- Compliance validation before export

---

## 8. Key Technical Decisions

1. **Template engine**: Jinja2 (new dependency) - the `${variable}` pattern in webhooks is too limited for conditional/loop logic in prompts.

2. **QA pair storage**: Metadata in app database (Postgres/SQLite), actual generated content in Delta Lake tables via Unity Catalog. The app DB tracks lineage/quality/membership; bulk data lives in the lakehouse.

3. **Generation execution**: Databricks Workflows (already integrated via `jobs_manager.py`) for batch generation. The app orchestrates, Databricks executes.

4. **Quality scoring**: Two-tier approach:
   - Automated: LLM-as-judge via `LLMService` (already has two-phase verification pattern)
   - Human: Adapt `DataAssetReview` workflow for QA pair review

5. **Reuse model**: Junction table (`CollectionMembership`) rather than copying QA pairs. This preserves single-source-of-truth for quality scores and enables cross-collection analytics.

---

## 9. Conclusion

Ontos is architecturally well-suited for this workflow. The entity lifecycle, versioning, workflow orchestration, tool registry, and LLM integration patterns all transfer directly. The primary work is creating the domain model layer (templates, assemblies, QA pairs, collections) and wiring it into the existing infrastructure.

The biggest design decision is where bulk training data lives (app DB vs. Delta Lake). For anything beyond prototype scale, the answer is Delta Lake for generated content with the app DB handling metadata, lineage, and quality tracking.
