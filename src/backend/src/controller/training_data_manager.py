"""
ML Training Data Manager

Business logic for QA pair generation, curation, and semantic linking.
Wires LLMService for generation and SemanticLinksManager for ontology integration.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from databricks.sdk import WorkspaceClient
from sqlalchemy.orm import Session

from src.common.llm_service import LLMService
from src.common.config import Settings
from src.connectors.unity_catalog_data_connector import (
    UnityCatalogDataConnector,
    DataFetchConfig,
    SamplingStrategy,
    create_connector_from_sheet,
)
from src.db_models.training_data import (
    CanonicalLabelDb,
    ExampleStoreDb,
    ModelTrainingLineageDb,
    PromptTemplateDb,
    QAPairDb,
    QAPairReviewStatus,
    SheetDb,
    TemplateStatus,
    TrainingCollectionDb,
    TrainingSheetStatus,
    GenerationMethod,
    LabelType,
)
from src.models.training_data import (
    CanonicalLabel,
    CanonicalLabelCreate,
    ChatMessage,
    Example,
    ExampleCreate,
    ExampleSearchQuery,
    ExampleSearchResult,
    ExportFormat,
    ExportRequest,
    ExportResult,
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    ModelLineage,
    ModelLineageCreate,
    PromptTemplate,
    PromptTemplateCreate,
    QAPair,
    QAPairCreate,
    QAPairBulkReview,
    QAPairsByConceptQuery,
    Sheet,
    SheetCreate,
    TrainingCollection,
    TrainingCollectionCreate,
    TrainingDataGap,
)
from src.repositories.training_data_repository import (
    canonical_labels_repository,
    example_store_repository,
    model_training_lineage_repository,
    prompt_templates_repository,
    qa_pairs_repository,
    sheets_repository,
    training_collections_repository,
)

logger = logging.getLogger(__name__)


class TrainingDataManager:
    """
    Orchestrates ML training data workflows.

    Handles:
    - Sheet, Template, Collection CRUD
    - QA pair generation using LLMService
    - Canonical label management
    - Semantic linking to ontology concepts
    - Export to training formats
    """

    def __init__(
        self,
        db: Session,
        settings: Settings,
        workspace_client: Optional[WorkspaceClient] = None,
        llm_service: Optional[LLMService] = None,
        semantic_models_manager: Optional[Any] = None  # SemanticModelsManager
    ):
        self._db = db
        self._settings = settings
        self._workspace_client = workspace_client
        self._llm_service = llm_service or LLMService(settings)
        self._semantic_models_manager = semantic_models_manager
        self._uc_connector: Optional[UnityCatalogDataConnector] = None

    # =========================================================================
    # SHEETS
    # =========================================================================

    def create_sheet(self, payload: SheetCreate, created_by: Optional[str] = None) -> Sheet:
        """Create a new sheet (data source pointer)"""
        db_obj = sheets_repository.create(self._db, obj_in=payload)
        if created_by:
            db_obj.created_by = created_by
        self._db.flush()
        self._db.refresh(db_obj)
        logger.info(f"Created sheet '{payload.name}' with id {db_obj.id}")
        return self._sheet_to_api(db_obj)

    def get_sheet(self, sheet_id: UUID) -> Optional[Sheet]:
        """Get sheet by ID"""
        db_obj = sheets_repository.get(self._db, sheet_id)
        return self._sheet_to_api(db_obj) if db_obj else None

    def list_sheets(
        self,
        skip: int = 0,
        limit: int = 100,
        owner_id: Optional[str] = None
    ) -> List[Sheet]:
        """List sheets"""
        db_objs = sheets_repository.list_all(self._db, skip=skip, limit=limit, owner_id=owner_id)
        return [self._sheet_to_api(obj) for obj in db_objs]

    def _sheet_to_api(self, db_obj: SheetDb) -> Sheet:
        """Convert DB sheet to API model"""
        return Sheet.model_validate(db_obj)

    # =========================================================================
    # PROMPT TEMPLATES
    # =========================================================================

    def create_template(self, payload: PromptTemplateCreate, created_by: Optional[str] = None) -> PromptTemplate:
        """Create a new prompt template"""
        db_obj = prompt_templates_repository.create(self._db, obj_in=payload)
        if created_by:
            db_obj.created_by = created_by
        self._db.flush()
        self._db.refresh(db_obj)
        logger.info(f"Created template '{payload.name}' v{payload.version} with id {db_obj.id}")
        return self._template_to_api(db_obj)

    def get_template(self, template_id: UUID) -> Optional[PromptTemplate]:
        """Get template by ID"""
        db_obj = prompt_templates_repository.get(self._db, template_id)
        return self._template_to_api(db_obj) if db_obj else None

    def list_templates(
        self,
        status: Optional[TemplateStatus] = None,
        label_type: Optional[LabelType] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[PromptTemplate]:
        """List templates with filters"""
        if status:
            db_objs = prompt_templates_repository.list_by_status(self._db, status, skip, limit)
        elif label_type:
            db_objs = prompt_templates_repository.list_by_label_type(self._db, label_type)
        else:
            db_objs = self._db.query(PromptTemplateDb).offset(skip).limit(limit).all()
        return [self._template_to_api(obj) for obj in db_objs]

    def render_template(
        self,
        template: PromptTemplate,
        variables: Dict[str, Any]
    ) -> Tuple[Optional[str], str]:
        """
        Render template with variables.

        Returns (system_prompt, user_prompt).
        """
        user_prompt = template.user_prompt_template

        # Replace {{variable}} placeholders
        for var_name, value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            user_prompt = user_prompt.replace(placeholder, str(value))

        # Check for unreplaced variables
        remaining = re.findall(r'\{\{(\w+)\}\}', user_prompt)
        if remaining:
            logger.warning(f"Template has unreplaced variables: {remaining}")

        return template.system_prompt, user_prompt

    def _template_to_api(self, db_obj: PromptTemplateDb) -> PromptTemplate:
        """Convert DB template to API model"""
        return PromptTemplate.model_validate(db_obj)

    # =========================================================================
    # CANONICAL LABELS
    # =========================================================================

    def create_canonical_label(
        self,
        payload: CanonicalLabelCreate,
        created_by: Optional[str] = None
    ) -> CanonicalLabel:
        """Create a canonical label (ground truth)"""
        # Check for existing (upsert pattern)
        existing = canonical_labels_repository.get_by_composite_key(
            self._db,
            payload.sheet_id,
            payload.item_ref,
            payload.label_type
        )
        if existing:
            # Update existing label
            for field, value in payload.model_dump(exclude={'sheet_id', 'item_ref', 'label_type'}).items():
                if value is not None:
                    setattr(existing, field, value)
            existing.updated_by = created_by
            self._db.add(existing)
            self._db.flush()
            self._db.refresh(existing)
            return self._canonical_label_to_api(existing)

        # Create new
        db_obj = canonical_labels_repository.create(self._db, obj_in=payload)
        if created_by:
            db_obj.created_by = created_by
        self._db.flush()
        self._db.refresh(db_obj)
        logger.info(f"Created canonical label for item '{payload.item_ref}' type '{payload.label_type}'")
        return self._canonical_label_to_api(db_obj)

    def get_canonical_label(self, label_id: UUID) -> Optional[CanonicalLabel]:
        """Get canonical label by ID"""
        db_obj = canonical_labels_repository.get(self._db, label_id)
        return self._canonical_label_to_api(db_obj) if db_obj else None

    def lookup_canonical_labels(
        self,
        sheet_id: UUID,
        item_refs: List[str],
        label_type: Optional[LabelType] = None
    ) -> Dict[str, List[CanonicalLabel]]:
        """Bulk lookup canonical labels"""
        results = canonical_labels_repository.bulk_lookup(self._db, sheet_id, item_refs, label_type)
        return {
            ref: [self._canonical_label_to_api(lbl) for lbl in labels]
            for ref, labels in results.items()
        }

    def verify_canonical_label(
        self,
        label_id: UUID,
        verified_by: str
    ) -> Optional[CanonicalLabel]:
        """Mark a canonical label as verified"""
        db_obj = canonical_labels_repository.get(self._db, label_id)
        if not db_obj:
            return None
        db_obj.is_verified = True
        db_obj.verified_by = verified_by
        db_obj.verified_at = datetime.now(timezone.utc)
        self._db.add(db_obj)
        self._db.flush()
        self._db.refresh(db_obj)
        return self._canonical_label_to_api(db_obj)

    def _canonical_label_to_api(self, db_obj: CanonicalLabelDb) -> CanonicalLabel:
        """Convert DB canonical label to API model"""
        return CanonicalLabel.model_validate(db_obj)

    # =========================================================================
    # TRAINING COLLECTIONS
    # =========================================================================

    def create_collection(
        self,
        payload: TrainingCollectionCreate,
        created_by: Optional[str] = None
    ) -> TrainingCollection:
        """Create a training collection"""
        db_obj = training_collections_repository.create(self._db, obj_in=payload)
        if created_by:
            db_obj.created_by = created_by
        self._db.flush()
        self._db.refresh(db_obj)
        logger.info(f"Created collection '{payload.name}' v{payload.version} with id {db_obj.id}")
        return self._collection_to_api(db_obj)

    def get_collection(self, collection_id: UUID) -> Optional[TrainingCollection]:
        """Get collection by ID"""
        db_obj = training_collections_repository.get_with_stats(self._db, collection_id)
        return self._collection_to_api(db_obj) if db_obj else None

    def list_collections(
        self,
        status: Optional[TrainingSheetStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[TrainingCollection]:
        """List collections"""
        if status:
            db_objs = training_collections_repository.list_by_status(self._db, status, skip, limit)
        else:
            db_objs = self._db.query(TrainingCollectionDb).offset(skip).limit(limit).all()
        return [self._collection_to_api(obj) for obj in db_objs]

    def _collection_to_api(self, db_obj: TrainingCollectionDb) -> TrainingCollection:
        """Convert DB collection to API model"""
        return TrainingCollection.model_validate(db_obj)

    # =========================================================================
    # QA PAIR GENERATION (Core LLM Integration)
    # =========================================================================

    def generate_qa_pairs(
        self,
        request: GenerationRequest,
        user_token: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> GenerationResult:
        """
        Generate QA pairs using LLM.

        This is the core generation pipeline that:
        1. Fetches source data from sheet
        2. Renders prompt template with data
        3. Calls LLM to generate responses
        4. Creates QA pairs with metadata
        5. Links to canonical labels if available
        6. Auto-approves if canonical label matches
        """
        collection = training_collections_repository.get_with_stats(self._db, request.collection_id)
        if not collection:
            raise ValueError(f"Collection {request.collection_id} not found")

        # Get sheet and template (from request or collection defaults)
        sheet_id = request.sheet_id or collection.sheet_id
        template_id = request.template_id or collection.template_id

        if not sheet_id:
            raise ValueError("No sheet specified")
        if not template_id:
            raise ValueError("No template specified")

        sheet = sheets_repository.get(self._db, sheet_id)
        template = prompt_templates_repository.get(self._db, template_id)

        if not sheet or not template:
            raise ValueError("Sheet or template not found")

        # Update collection status
        collection.status = TrainingSheetStatus.GENERATING
        self._db.add(collection)
        self._db.flush()

        # Fetch source data (placeholder - actual implementation depends on data connector)
        source_items = self._fetch_source_data(sheet, request.sample_size)

        # Lookup canonical labels if linking enabled
        canonical_labels_map = {}
        if request.link_to_canonical and template.label_type:
            item_refs = [item.get(sheet.id_column or 'id', str(i)) for i, item in enumerate(source_items)]
            canonical_labels_map = canonical_labels_repository.bulk_lookup(
                self._db,
                sheet.id,
                item_refs,
                template.label_type
            )

        # Generate QA pairs
        pairs_generated = 0
        pairs_auto_approved = 0
        pairs_pending = 0
        errors = []

        model = request.model or template.default_model or self._settings.LLM_ENDPOINT
        temperature = request.temperature or template.default_temperature or 0.7
        max_tokens = request.max_tokens or template.default_max_tokens or 1024

        for i, item in enumerate(source_items):
            try:
                item_ref = item.get(sheet.id_column or 'id', str(i))

                # Build variable mappings
                variables = {}
                for var_name, col_name in (template.variable_mappings or {}).items():
                    variables[var_name] = item.get(col_name, '')

                # Render template
                system_prompt, user_prompt = self.render_template(
                    self._template_to_api(template),
                    variables
                )

                # Call LLM
                start_time = datetime.now(timezone.utc)
                response = self._call_llm_for_generation(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    user_token=user_token
                )
                end_time = datetime.now(timezone.utc)

                if not response:
                    errors.append({"item_ref": item_ref, "error": "LLM returned empty response"})
                    continue

                # Build messages in OpenAI format
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": user_prompt})
                messages.append({"role": "assistant", "content": response})

                # Check for canonical label match
                canonical_label_id = None
                was_auto_approved = False
                review_status = QAPairReviewStatus.PENDING

                if request.link_to_canonical and item_ref in canonical_labels_map:
                    labels = canonical_labels_map[item_ref]
                    if labels:
                        canonical_label = labels[0]  # Use first matching label
                        canonical_label_id = canonical_label.id

                        # Auto-approve if canonical label matches
                        if request.auto_approve_with_canonical:
                            # Compare generated response to canonical label
                            if self._check_canonical_match(response, canonical_label.label_data):
                                was_auto_approved = True
                                review_status = QAPairReviewStatus.AUTO_APPROVED
                                canonical_labels_repository.increment_reuse_count(
                                    self._db, canonical_label.id
                                )

                # Create QA pair
                qa_pair = QAPairDb(
                    collection_id=request.collection_id,
                    source_item_ref=item_ref,
                    messages=messages,
                    canonical_label_id=canonical_label_id,
                    review_status=review_status,
                    was_auto_approved=was_auto_approved,
                    generation_metadata={
                        "model": model,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "latency_ms": (end_time - start_time).total_seconds() * 1000,
                        "generated_at": start_time.isoformat()
                    },
                    created_by=created_by
                )
                self._db.add(qa_pair)
                pairs_generated += 1

                if was_auto_approved:
                    pairs_auto_approved += 1
                else:
                    pairs_pending += 1

            except Exception as e:
                logger.error(f"Error generating QA pair for item {i}: {e}")
                errors.append({"item_ref": str(i), "error": str(e)})

        # Update collection stats
        self._db.flush()
        training_collections_repository.recalculate_stats(self._db, request.collection_id)

        # Update collection status
        collection.status = TrainingSheetStatus.REVIEW
        collection.model_used = model
        collection.generation_config = {
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        self._db.add(collection)

        logger.info(
            f"Generated {pairs_generated} QA pairs for collection {request.collection_id}, "
            f"{pairs_auto_approved} auto-approved, {pairs_pending} pending review"
        )

        return GenerationResult(
            collection_id=request.collection_id,
            pairs_generated=pairs_generated,
            pairs_auto_approved=pairs_auto_approved,
            pairs_pending_review=pairs_pending,
            errors=errors
        )

    def _fetch_source_data(
        self,
        sheet: SheetDb,
        sample_size: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch source data from sheet using Unity Catalog connector.

        Args:
            sheet: Sheet database model with source configuration
            sample_size: Optional override for number of items to fetch

        Returns:
            List of dictionaries, one per source item
        """
        # Check if we have a workspace client
        if not self._workspace_client:
            logger.warning("No workspace client available - using mock data for development")
            return self._get_mock_data(sheet, sample_size)

        try:
            # Create connector and config from sheet
            connector, config = create_connector_from_sheet(
                sheet_db=sheet,
                workspace_client=self._workspace_client,
                settings=self._settings
            )

            # Override sample size if provided
            if sample_size:
                config.sample_size = sample_size

            # Validate source before fetching
            is_valid, error = connector.validate_source(config)
            if not is_valid:
                logger.error(f"Invalid data source: {error}")
                raise ValueError(f"Data source validation failed: {error}")

            # Fetch data based on source type
            if config.table:
                result = connector.fetch_table_data(config)
            elif config.volume_path:
                result = connector.fetch_volume_data(config)
            else:
                raise ValueError("Sheet must have either table or volume_path configured")

            logger.info(
                f"Fetched {result.sampled_count} items from {result.source} "
                f"(total: {result.total_count})"
            )

            return result.items

        except Exception as e:
            logger.error(f"Failed to fetch source data: {e}")
            raise

    def _get_mock_data(
        self,
        sheet: SheetDb,
        sample_size: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate mock data for development/testing when no workspace client available.
        """
        count = sample_size or sheet.sample_size or 10

        # Build mock items with configured column names
        mock_items = []
        for i in range(count):
            item = {}

            # Add ID column
            id_col = sheet.id_column or "id"
            item[id_col] = f"item_{i}"

            # Add text columns
            for col in (sheet.text_columns or []):
                item[col] = f"Sample {col} text for item {i}"

            # Add image columns (mock paths)
            for col in (sheet.image_columns or []):
                item[col] = f"/mock/images/{col}_{i}.png"

            # Add metadata columns
            for col in (sheet.metadata_columns or []):
                item[col] = {"mock": True, "index": i, "column": col}

            mock_items.append(item)

        logger.warning(f"Generated {count} mock items for development")
        return mock_items

    def _call_llm_for_generation(
        self,
        system_prompt: Optional[str],
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        user_token: Optional[str] = None
    ) -> Optional[str]:
        """Call LLM for QA generation"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        try:
            # Use LLMService's internal call (bypass security check for generation)
            response = self._llm_service._call_llm(
                messages=messages,
                max_tokens=max_tokens,
                user_token=user_token
            )
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _check_canonical_match(
        self,
        generated_response: str,
        canonical_label_data: Dict[str, Any]
    ) -> bool:
        """
        Check if generated response matches canonical label.

        Simple implementation - can be extended with semantic similarity.
        """
        # Extract expected answer from canonical label
        expected = canonical_label_data.get("answer") or canonical_label_data.get("output")
        if not expected:
            return False

        # Simple exact match (case-insensitive, whitespace-normalized)
        generated_norm = " ".join(generated_response.lower().split())
        expected_norm = " ".join(str(expected).lower().split())

        # Exact match
        if generated_norm == expected_norm:
            return True

        # Contains match (for extractive tasks)
        if expected_norm in generated_norm:
            return True

        return False

    # =========================================================================
    # QA PAIR CURATION
    # =========================================================================

    def get_qa_pair(self, pair_id: UUID) -> Optional[QAPair]:
        """Get QA pair by ID"""
        db_obj = qa_pairs_repository.get(self._db, pair_id)
        return self._qa_pair_to_api(db_obj) if db_obj else None

    def list_qa_pairs(
        self,
        collection_id: UUID,
        review_status: Optional[QAPairReviewStatus] = None,
        split: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[QAPair]:
        """List QA pairs for a collection"""
        db_objs = qa_pairs_repository.list_for_collection(
            self._db, collection_id, review_status, split, skip, limit
        )
        return [self._qa_pair_to_api(obj) for obj in db_objs]

    def review_qa_pair(
        self,
        pair_id: UUID,
        status: QAPairReviewStatus,
        reviewed_by: str,
        review_notes: Optional[str] = None,
        edited_messages: Optional[List[ChatMessage]] = None
    ) -> Optional[QAPair]:
        """Review a single QA pair"""
        db_obj = qa_pairs_repository.get(self._db, pair_id)
        if not db_obj:
            return None

        # If editing, save original and compute edit distance
        if edited_messages and status == QAPairReviewStatus.EDITED:
            db_obj.original_messages = db_obj.messages
            db_obj.messages = [msg.model_dump() for msg in edited_messages]
            # Simple edit distance (character count difference)
            original_text = json.dumps(db_obj.original_messages)
            edited_text = json.dumps(db_obj.messages)
            db_obj.edit_distance = abs(len(original_text) - len(edited_text))

        db_obj.review_status = status
        db_obj.reviewed_by = reviewed_by
        db_obj.reviewed_at = datetime.now(timezone.utc)
        db_obj.review_notes = review_notes
        db_obj.updated_by = reviewed_by

        self._db.add(db_obj)
        self._db.flush()

        # Update collection stats
        training_collections_repository.recalculate_stats(self._db, db_obj.collection_id)

        self._db.refresh(db_obj)
        return self._qa_pair_to_api(db_obj)

    def bulk_review_qa_pairs(
        self,
        request: QAPairBulkReview,
        reviewed_by: str
    ) -> int:
        """Bulk review multiple QA pairs"""
        count = qa_pairs_repository.bulk_update_status(
            self._db,
            request.pair_ids,
            request.review_status,
            reviewed_by
        )

        # Get collection IDs to update stats
        pairs = self._db.query(QAPairDb.collection_id).filter(
            QAPairDb.id.in_(request.pair_ids)
        ).distinct().all()

        for (collection_id,) in pairs:
            training_collections_repository.recalculate_stats(self._db, collection_id)

        return count

    def assign_splits(
        self,
        collection_id: UUID,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1
    ) -> Dict[str, int]:
        """Assign train/val/test splits to QA pairs"""
        return qa_pairs_repository.assign_splits(
            self._db, collection_id, train_ratio, val_ratio, test_ratio
        )

    def _qa_pair_to_api(self, db_obj: QAPairDb) -> QAPair:
        """Convert DB QA pair to API model"""
        return QAPair.model_validate(db_obj)

    # =========================================================================
    # SEMANTIC LINKING (Ontology Integration)
    # =========================================================================

    def link_qa_pair_to_concept(
        self,
        pair_id: UUID,
        concept_iri: str,
        updated_by: Optional[str] = None
    ) -> Optional[QAPair]:
        """Link a QA pair to an ontology concept"""
        db_obj = qa_pairs_repository.get(self._db, pair_id)
        if not db_obj:
            return None

        # Add concept IRI if not already present
        current_iris = db_obj.semantic_concept_iris or []
        if concept_iri not in current_iris:
            current_iris.append(concept_iri)
            db_obj.semantic_concept_iris = current_iris
            db_obj.updated_by = updated_by
            self._db.add(db_obj)
            self._db.flush()
            self._db.refresh(db_obj)

        logger.info(f"Linked QA pair {pair_id} to concept {concept_iri}")
        return self._qa_pair_to_api(db_obj)

    def unlink_qa_pair_from_concept(
        self,
        pair_id: UUID,
        concept_iri: str,
        updated_by: Optional[str] = None
    ) -> Optional[QAPair]:
        """Remove link between QA pair and ontology concept"""
        db_obj = qa_pairs_repository.get(self._db, pair_id)
        if not db_obj:
            return None

        current_iris = db_obj.semantic_concept_iris or []
        if concept_iri in current_iris:
            current_iris.remove(concept_iri)
            db_obj.semantic_concept_iris = current_iris
            db_obj.updated_by = updated_by
            self._db.add(db_obj)
            self._db.flush()
            self._db.refresh(db_obj)

        return self._qa_pair_to_api(db_obj)

    def list_qa_pairs_by_concept(
        self,
        query: QAPairsByConceptQuery
    ) -> List[QAPair]:
        """List QA pairs linked to an ontology concept"""
        db_objs = qa_pairs_repository.list_by_semantic_concept(
            self._db,
            query.concept_iri,
            only_approved=query.only_approved
        )

        # If including children and we have semantic models manager
        if query.include_children and self._semantic_models_manager:
            try:
                # Get child concepts from RDF graph
                child_iris = self._get_child_concepts(query.concept_iri)
                for child_iri in child_iris:
                    child_pairs = qa_pairs_repository.list_by_semantic_concept(
                        self._db, child_iri, only_approved=query.only_approved
                    )
                    db_objs.extend(child_pairs)
            except Exception as e:
                logger.warning(f"Failed to get child concepts: {e}")

        # Deduplicate and limit
        seen_ids = set()
        unique_pairs = []
        for obj in db_objs:
            if obj.id not in seen_ids:
                seen_ids.add(obj.id)
                unique_pairs.append(obj)
                if len(unique_pairs) >= query.limit:
                    break

        return [self._qa_pair_to_api(obj) for obj in unique_pairs]

    def _get_child_concepts(self, parent_iri: str) -> List[str]:
        """Get child concept IRIs from RDF graph"""
        if not self._semantic_models_manager:
            return []

        try:
            query = f"""
            SELECT ?child WHERE {{
                ?child <http://www.w3.org/2004/02/skos/core#broader> <{parent_iri}> .
            }}
            """
            results = self._semantic_models_manager.query(query)
            return [str(row.get('child', '')) for row in results if row.get('child')]
        except Exception as e:
            logger.warning(f"SPARQL query failed: {e}")
            return []

    def analyze_training_gaps(
        self,
        collection_id: Optional[UUID] = None
    ) -> List[TrainingDataGap]:
        """
        Analyze training data gaps relative to ontology coverage.

        Identifies concepts with insufficient training data.
        """
        if not self._semantic_models_manager:
            logger.warning("Semantic models manager not available for gap analysis")
            return []

        gaps = []

        try:
            # Get all concepts from ontology
            concepts = self._get_all_concepts()

            for concept in concepts:
                iri = concept.get('iri')
                label = concept.get('label')

                # Count QA pairs linked to this concept
                pairs = qa_pairs_repository.list_by_semantic_concept(
                    self._db, iri, only_approved=True
                )
                current_count = len(pairs)

                # Determine recommended count based on concept importance
                # (Simple heuristic - can be made more sophisticated)
                recommended_count = 10  # Base recommendation

                if current_count < recommended_count:
                    gap = TrainingDataGap(
                        concept_iri=iri,
                        concept_label=label,
                        gap_type="coverage",
                        severity="high" if current_count == 0 else "medium" if current_count < 5 else "low",
                        current_count=current_count,
                        recommended_count=recommended_count,
                        description=f"Concept '{label or iri}' has {current_count} training examples, "
                                   f"recommend at least {recommended_count}"
                    )
                    gaps.append(gap)

        except Exception as e:
            logger.error(f"Gap analysis failed: {e}")

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        gaps.sort(key=lambda g: severity_order.get(g.severity, 3))

        return gaps

    def _get_all_concepts(self) -> List[Dict[str, Any]]:
        """Get all concepts from ontology"""
        if not self._semantic_models_manager:
            return []

        try:
            query = """
            SELECT ?concept ?label WHERE {
                ?concept a ?type .
                OPTIONAL { ?concept <http://www.w3.org/2000/01/rdf-schema#label> ?label }
                FILTER(?type IN (
                    <http://www.w3.org/2002/07/owl#Class>,
                    <http://www.w3.org/2004/02/skos/core#Concept>
                ))
            }
            """
            results = self._semantic_models_manager.query(query)
            return [
                {"iri": str(row.get('concept', '')), "label": str(row.get('label', '')) if row.get('label') else None}
                for row in results
            ]
        except Exception as e:
            logger.warning(f"Failed to get concepts: {e}")
            return []

    # =========================================================================
    # EXPORT
    # =========================================================================

    def export_collection(
        self,
        request: ExportRequest,
        exported_by: Optional[str] = None
    ) -> ExportResult:
        """Export collection to training format"""
        collection = training_collections_repository.get(self._db, request.collection_id)
        if not collection:
            raise ValueError(f"Collection {request.collection_id} not found")

        # Get approved pairs
        pairs = qa_pairs_repository.list_approved_for_export(
            self._db,
            request.collection_id,
            splits=request.include_splits if request.include_splits else None
        )

        if not pairs:
            raise ValueError("No approved pairs to export")

        # Group by split
        split_counts = {"train": 0, "val": 0, "test": 0}
        for pair in pairs:
            if pair.split:
                split_counts[pair.split] = split_counts.get(pair.split, 0) + 1

        # Generate output path if not provided
        output_path = request.output_path or f"/tmp/training_data/{collection.name}_{collection.version}.{request.format.value}"

        # Export based on format
        if request.format == ExportFormat.JSONL:
            self._export_jsonl(pairs, output_path, request.include_metadata)
        elif request.format == ExportFormat.ALPACA:
            self._export_alpaca(pairs, output_path)
        elif request.format == ExportFormat.SHAREGPT:
            self._export_sharegpt(pairs, output_path)
        else:
            raise ValueError(f"Unsupported export format: {request.format}")

        # Update collection
        collection.last_exported_at = datetime.now(timezone.utc)
        collection.export_format = request.format.value
        collection.export_path = output_path
        collection.updated_by = exported_by
        self._db.add(collection)

        logger.info(f"Exported {len(pairs)} pairs from collection {request.collection_id} to {output_path}")

        return ExportResult(
            collection_id=request.collection_id,
            format=request.format,
            output_path=output_path,
            pairs_exported=len(pairs),
            splits=split_counts
        )

    def _export_jsonl(
        self,
        pairs: List[QAPairDb],
        output_path: str,
        include_metadata: bool = False
    ) -> None:
        """Export to JSONL (OpenAI chat format)"""
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w') as f:
            for pair in pairs:
                record = {"messages": pair.messages}
                if include_metadata:
                    record["metadata"] = {
                        "id": str(pair.id),
                        "split": pair.split,
                        "quality_score": pair.quality_score,
                        "source_item_ref": pair.source_item_ref
                    }
                f.write(json.dumps(record) + '\n')

    def _export_alpaca(self, pairs: List[QAPairDb], output_path: str) -> None:
        """Export to Alpaca format"""
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        records = []
        for pair in pairs:
            messages = pair.messages or []

            # Extract components
            instruction = ""
            input_text = ""
            output_text = ""

            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "system":
                    instruction = content
                elif role == "user":
                    input_text = content
                elif role == "assistant":
                    output_text = content

            records.append({
                "instruction": instruction or input_text,
                "input": input_text if instruction else "",
                "output": output_text
            })

        with open(output_path, 'w') as f:
            json.dump(records, f, indent=2)

    def _export_sharegpt(self, pairs: List[QAPairDb], output_path: str) -> None:
        """Export to ShareGPT format"""
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        records = []
        for pair in pairs:
            messages = pair.messages or []
            conversations = []

            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")

                # Map roles to ShareGPT format
                if role == "system":
                    conversations.append({"from": "system", "value": content})
                elif role == "user":
                    conversations.append({"from": "human", "value": content})
                elif role == "assistant":
                    conversations.append({"from": "gpt", "value": content})

            records.append({
                "id": str(pair.id),
                "conversations": conversations
            })

        with open(output_path, 'w') as f:
            json.dump(records, f, indent=2)

    # =========================================================================
    # MODEL LINEAGE
    # =========================================================================

    def create_model_lineage(
        self,
        payload: ModelLineageCreate,
        created_by: Optional[str] = None
    ) -> ModelLineage:
        """Create model training lineage record"""
        # Build data lineage from collection
        collection = training_collections_repository.get_with_stats(self._db, payload.collection_id)
        data_lineage = None
        if collection:
            data_lineage = {
                "sheet_id": str(collection.sheet_id) if collection.sheet_id else None,
                "template_id": str(collection.template_id) if collection.template_id else None,
                "qa_pair_count": collection.total_pairs,
                "approved_pair_count": collection.approved_pairs
            }

        db_obj = ModelTrainingLineageDb(
            model_name=payload.model_name,
            model_version=payload.model_version,
            model_registry_path=payload.model_registry_path,
            collection_id=payload.collection_id,
            training_job_id=payload.training_job_id,
            training_run_id=payload.training_run_id,
            base_model=payload.base_model,
            training_params=payload.training_params,
            data_lineage=data_lineage,
            training_started_at=datetime.now(timezone.utc),
            created_by=created_by
        )
        self._db.add(db_obj)
        self._db.flush()
        self._db.refresh(db_obj)

        logger.info(f"Created lineage for model '{payload.model_name}' v{payload.model_version}")
        return ModelLineage.model_validate(db_obj)

    def get_model_lineage(
        self,
        model_name: str,
        model_version: str
    ) -> Optional[ModelLineage]:
        """Get model lineage by name and version"""
        db_obj = model_training_lineage_repository.get_by_model_version(
            self._db, model_name, model_version
        )
        return ModelLineage.model_validate(db_obj) if db_obj else None

    def list_models_for_collection(
        self,
        collection_id: UUID
    ) -> List[ModelLineage]:
        """List all models trained on a collection"""
        db_objs = model_training_lineage_repository.list_for_collection(
            self._db, collection_id
        )
        return [ModelLineage.model_validate(obj) for obj in db_objs]
