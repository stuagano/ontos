# ML Training Data Integration for Ontos

This document describes the ML training data generation capability added to Ontos, adapting patterns from the VITAL Workbench.

## Overview

The integration adds the following capabilities to Ontos:

1. **Sheets** - Lightweight pointers to Unity Catalog data sources
2. **Prompt Templates** - Reusable prompt IP with variable placeholders
3. **Canonical Labels** - Ground truth labels with "label once, reuse everywhere" pattern
4. **Training Collections** - Materialized QA datasets from Sheet + Template combinations
5. **QA Pairs** - Individual question-answer pairs with quality signals and review status
6. **Example Store** - Few-shot examples with embeddings for semantic search
7. **Model Lineage** - Complete traceability from trained models to source data
8. **Semantic Linking** - Integration with Ontos's ontology for concept-based organization

## Architecture

```
Unity Catalog (External Data)
        │
        ▼
    SHEETS (dataset pointers)
        │
        │ + variable mappings
        ▼
    TEMPLATES (prompt IP)
        │
        │ LLMService generation
        ▼
    TRAINING COLLECTIONS
        │
        │ contains
        ▼
    QA PAIRS ←──────→ CANONICAL LABELS
        │                    ↑
        │                    │ ground truth
        │                    │
        ▼                    │
    SEMANTIC LINKS ←───→ ONTOLOGY CONCEPTS
        │
        │ export
        ▼
    JSONL/Alpaca/ShareGPT → Model Training → MODEL LINEAGE
```

## What You Get "For Free" from Ontos

| Ontos Component | Used For |
|-----------------|----------|
| `LLMService` | QA pair generation with two-phase security |
| `LLMSearchManager` | Conversational interface for training data |
| `ToolRegistry` | Function-calling for structured extraction |
| `SemanticModelsManager` | Link QA pairs to business concepts |
| `Repository + Manager` | Consistent data access patterns |
| React Frontend | Curation UI components |
| RDF Knowledge Graph | Semantic queries across training data |

## Database Schema

### Tables Created

| Table | Purpose |
|-------|---------|
| `training_sheets_sources` | Sheet definitions (UC table pointers) |
| `prompt_templates` | Reusable prompt templates |
| `canonical_labels` | Ground truth with composite key |
| `training_collections` | Materialized QA datasets |
| `qa_pairs` | Individual Q&A pairs |
| `example_store` | Few-shot examples |
| `model_training_lineage` | Model traceability |

### Key Design Patterns

#### 1. Composite Key for Canonical Labels

```sql
UNIQUE (sheet_id, item_ref, label_type)
```

Enables:
- Same source item can have multiple independent label types
- "Label once, reuse everywhere" pattern
- Reuse count tracking

#### 2. OpenAI Chat Format for QA Pairs

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Direct compatibility with fine-tuning APIs.

#### 3. Semantic Concept Linking

```python
semantic_concept_iris = Column(ARRAY(String))
```

QA pairs can link to multiple ontology concepts, enabling:
- "Show me all training data about Customer entities"
- Gap analysis relative to ontology coverage
- Concept-based data organization

## API Endpoints

### Sheets
- `POST /api/training-data/sheets` - Create sheet
- `GET /api/training-data/sheets` - List sheets
- `GET /api/training-data/sheets/{id}` - Get sheet

### Templates
- `POST /api/training-data/templates` - Create template
- `GET /api/training-data/templates` - List templates
- `GET /api/training-data/templates/{id}` - Get template

### Canonical Labels
- `POST /api/training-data/canonical-labels` - Create/update label
- `GET /api/training-data/canonical-labels/{id}` - Get label
- `POST /api/training-data/canonical-labels/{id}/verify` - Verify label

### Collections
- `POST /api/training-data/collections` - Create collection
- `GET /api/training-data/collections` - List collections
- `GET /api/training-data/collections/{id}` - Get collection

### Generation
- `POST /api/training-data/collections/{id}/generate` - Generate QA pairs

### QA Pairs
- `GET /api/training-data/collections/{id}/pairs` - List pairs
- `GET /api/training-data/pairs/{id}` - Get pair
- `POST /api/training-data/pairs/{id}/review` - Review pair
- `POST /api/training-data/pairs/bulk-review` - Bulk review
- `POST /api/training-data/collections/{id}/assign-splits` - Assign train/val/test

### Semantic Linking
- `POST /api/training-data/pairs/{id}/link-concept` - Link to concept
- `DELETE /api/training-data/pairs/{id}/link-concept` - Unlink concept
- `POST /api/training-data/pairs/by-concept` - Query by concept
- `GET /api/training-data/gaps` - Analyze coverage gaps

### Export
- `POST /api/training-data/collections/{id}/export` - Export to JSONL/Alpaca/ShareGPT

### Model Lineage
- `POST /api/training-data/lineage` - Create lineage record
- `GET /api/training-data/lineage/{name}/{version}` - Get lineage
- `GET /api/training-data/collections/{id}/models` - List models for collection

## Usage Examples

### 1. Create a Sheet (Data Source)

```python
sheet = {
    "name": "customer_feedback",
    "source_type": "unity_catalog_table",
    "source_catalog": "main",
    "source_schema": "customer_data",
    "source_table": "feedback_2024",
    "text_columns": ["feedback_text", "summary"],
    "id_column": "feedback_id",
    "sampling_strategy": "random",
    "sample_size": 1000
}
```

### 2. Create a Prompt Template

```python
template = {
    "name": "sentiment_analysis",
    "version": "1.0.0",
    "system_prompt": "You are a sentiment analysis expert...",
    "user_prompt_template": "Analyze the sentiment of this customer feedback:\n\n{{feedback_text}}\n\nProvide a JSON response with sentiment and confidence.",
    "output_schema": {
        "type": "object",
        "properties": {
            "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
            "confidence": {"type": "number"}
        }
    },
    "label_type": "classification",
    "variable_mappings": {"feedback_text": "feedback_text"},
    "sheet_id": "<sheet_uuid>"
}
```

### 3. Generate QA Pairs

```python
POST /api/training-data/collections/{collection_id}/generate
{
    "sample_size": 100,
    "auto_approve_with_canonical": true,
    "link_to_canonical": true
}
```

### 4. Link QA Pair to Ontology Concept

```python
POST /api/training-data/pairs/{pair_id}/link-concept?concept_iri=http://example.org/ontology/CustomerFeedback
```

### 5. Export for Training

```python
POST /api/training-data/collections/{collection_id}/export
{
    "format": "jsonl",
    "include_splits": ["train", "val"],
    "only_approved": true
}
```

## Semantic Integration Features

### Query QA Pairs by Business Concept

```python
POST /api/training-data/pairs/by-concept
{
    "concept_iri": "http://example.org/ontology/Customer",
    "include_children": true,
    "only_approved": true,
    "limit": 100
}
```

### Analyze Training Data Gaps

```python
GET /api/training-data/gaps

# Returns:
[
    {
        "concept_iri": "http://example.org/ontology/FinancialProduct",
        "concept_label": "Financial Product",
        "gap_type": "coverage",
        "severity": "high",
        "current_count": 0,
        "recommended_count": 10,
        "description": "Concept 'Financial Product' has 0 training examples..."
    }
]
```

## Files Created

```
src/backend/src/
├── db_models/
│   └── training_data.py          # SQLAlchemy models
├── models/
│   └── training_data.py          # Pydantic API models
├── repositories/
│   └── training_data_repository.py  # Data access layer
├── controller/
│   └── training_data_manager.py  # Business logic + LLM integration
├── routes/
│   └── training_data_routes.py   # REST API endpoints
└── connectors/
    └── unity_catalog_data_connector.py  # UC data fetching

src/frontend/src/
├── types/
│   └── training-data.ts          # TypeScript interfaces
├── views/
│   ├── training-data-curation.tsx    # Main list view (Collections, Sheets, Templates)
│   └── training-collection-details.tsx  # Collection detail with QA pairs
└── components/training-data/
    ├── index.ts                  # Component exports
    ├── training-collection-form-dialog.tsx  # Create/edit collection
    ├── qa-pair-review-dialog.tsx # QA pair review with edit
    ├── generation-dialog.tsx     # QA generation settings
    └── export-dialog.tsx         # Export format selection

docs/
└── ml-training-data-integration.md  # This document
```

## Unity Catalog Connector

The integration includes a full Unity Catalog data connector (`src/backend/src/connectors/unity_catalog_data_connector.py`).

### Capabilities

| Feature | Description |
|---------|-------------|
| **UC Tables** | Query via Statement Execution API |
| **UC Volumes** | List and read files for multimodal data |
| **Random Sampling** | `TABLESAMPLE (N ROWS)` |
| **Stratified Sampling** | Window functions for balanced sampling |
| **Source Validation** | Check table/volume exists before generation |
| **Preview** | Quick data preview for template testing |

### Sampling Strategies

```python
# Random sampling - uses TABLESAMPLE
sampling_strategy = "random"
sample_size = 1000

# Stratified - balanced across a column
sampling_strategy = "stratified"
stratify_column = "category"
sample_size = 1000  # ~100 per category

# First N rows
sampling_strategy = "first_n"
sample_size = 100
```

### Security

- All UC identifiers sanitized via `sanitize_uc_identifier()`
- SQL filters validated for injection patterns
- OBO tokens used for user-level permissions
- Falls back to service principal when OBO unavailable

### Data Source Validation API

```bash
# Validate source exists
POST /api/training-data/sheets/{sheet_id}/validate
# Returns: {"valid": true, "source": "main.schema.table", "schema": [...]}

# Preview sample data
GET /api/training-data/sheets/{sheet_id}/preview?limit=5
# Returns: {"items": [...], "count": 5, "source": "..."}
```

---

## Next Steps

### To Activate

1. **Register routes** in `main.py`:
   ```python
   from src.backend.src.routes.training_data_routes import register_routes
   register_routes(app)
   ```

2. **Run migrations** to create tables:
   ```bash
   alembic revision --autogenerate -m "Add ML training data tables"
   alembic upgrade head
   ```

3. **Configure warehouse** in settings:
   ```python
   DATABRICKS_WAREHOUSE_ID = "your-warehouse-id"  # Required for UC table queries
   ```

### Optional Enhancements

- **Vector search for examples**: Integrate embedding model for semantic example retrieval
- **Curation UI**: React components for reviewing QA pairs
- **Streaming generation**: WebSocket support for real-time progress updates
- **Delta Lake export**: Direct export to Delta tables for large-scale training
