"""
ML Training Data Repositories

Data access layer for QA pairs, canonical labels, templates, and training collections.
Follows Ontos's CRUDBase + specialized repository pattern.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from src.common.repository import CRUDBase
from src.db_models.training_data import (
    CanonicalLabelDb,
    DSPyOptimizationRunDb,
    DSPyRunStatus,
    ExampleStoreDb,
    ModelTrainingLineageDb,
    PromptTemplateDb,
    QAPairDb,
    QAPairReviewStatus,
    SheetDb,
    TemplateStatus,
    TrainingCollectionDb,
    TrainingJobDb,
    TrainingJobStatus,
    TrainingSheetStatus,
    LabelType,
)
from src.models.training_data import (
    CanonicalLabelCreate,
    DSPyRunCreate,
    ExampleCreate,
    ModelLineageCreate,
    PromptTemplateCreate,
    QAPairCreate,
    SheetCreate,
    TrainingCollectionCreate,
    TrainingJobCreate,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SHEETS REPOSITORY
# =============================================================================

class SheetsRepository(CRUDBase[SheetDb, SheetCreate, dict]):
    """Repository for sheet (data source pointer) operations"""

    def __init__(self):
        super().__init__(SheetDb)

    def get_by_name(self, db: Session, name: str) -> Optional[SheetDb]:
        """Get sheet by name"""
        try:
            return db.query(self.model).filter(self.model.name == name).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting sheet by name: {e}")
            db.rollback()
            raise

    def get_by_source(
        self,
        db: Session,
        catalog: str,
        schema: str,
        table: str
    ) -> Optional[SheetDb]:
        """Get sheet by Unity Catalog source"""
        try:
            return db.query(self.model).filter(
                and_(
                    self.model.source_catalog == catalog,
                    self.model.source_schema == schema,
                    self.model.source_table == table
                )
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting sheet by source: {e}")
            db.rollback()
            raise

    def list_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        owner_id: Optional[str] = None
    ) -> List[SheetDb]:
        """List sheets with optional owner filter"""
        try:
            query = db.query(self.model)
            if owner_id:
                query = query.filter(self.model.owner_id == owner_id)
            return query.offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing sheets: {e}")
            db.rollback()
            raise


sheets_repository = SheetsRepository()


# =============================================================================
# PROMPT TEMPLATES REPOSITORY
# =============================================================================

class PromptTemplatesRepository(CRUDBase[PromptTemplateDb, PromptTemplateCreate, dict]):
    """Repository for prompt template operations"""

    def __init__(self):
        super().__init__(PromptTemplateDb)

    def get_by_name_version(
        self,
        db: Session,
        name: str,
        version: str
    ) -> Optional[PromptTemplateDb]:
        """Get template by name and version (unique constraint)"""
        try:
            return db.query(self.model).filter(
                and_(
                    self.model.name == name,
                    self.model.version == version
                )
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting template by name/version: {e}")
            db.rollback()
            raise

    def list_by_status(
        self,
        db: Session,
        status: TemplateStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[PromptTemplateDb]:
        """List templates by status"""
        try:
            return db.query(self.model).filter(
                self.model.status == status
            ).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing templates by status: {e}")
            db.rollback()
            raise

    def list_by_label_type(
        self,
        db: Session,
        label_type: LabelType,
        only_active: bool = True
    ) -> List[PromptTemplateDb]:
        """List templates that produce a specific label type"""
        try:
            query = db.query(self.model).filter(self.model.label_type == label_type)
            if only_active:
                query = query.filter(self.model.status == TemplateStatus.ACTIVE)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing templates by label type: {e}")
            db.rollback()
            raise

    def list_by_sheet(
        self,
        db: Session,
        sheet_id: UUID
    ) -> List[PromptTemplateDb]:
        """List templates associated with a sheet"""
        try:
            return db.query(self.model).filter(
                self.model.sheet_id == sheet_id
            ).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing templates by sheet: {e}")
            db.rollback()
            raise

    def search_by_tags(
        self,
        db: Session,
        tags: List[str],
        match_all: bool = False
    ) -> List[PromptTemplateDb]:
        """Search templates by tags"""
        try:
            if match_all:
                # All tags must be present
                query = db.query(self.model).filter(
                    self.model.tags.contains(tags)
                )
            else:
                # Any tag matches
                query = db.query(self.model).filter(
                    self.model.tags.overlap(tags)
                )
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error searching templates by tags: {e}")
            db.rollback()
            raise


prompt_templates_repository = PromptTemplatesRepository()


# =============================================================================
# CANONICAL LABELS REPOSITORY
# =============================================================================

class CanonicalLabelsRepository(CRUDBase[CanonicalLabelDb, CanonicalLabelCreate, dict]):
    """Repository for canonical label operations"""

    def __init__(self):
        super().__init__(CanonicalLabelDb)

    def get_by_composite_key(
        self,
        db: Session,
        sheet_id: UUID,
        item_ref: str,
        label_type: LabelType
    ) -> Optional[CanonicalLabelDb]:
        """Get label by composite key (sheet_id, item_ref, label_type)"""
        try:
            return db.query(self.model).filter(
                and_(
                    self.model.sheet_id == sheet_id,
                    self.model.item_ref == item_ref,
                    self.model.label_type == label_type
                )
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting canonical label by composite key: {e}")
            db.rollback()
            raise

    def list_for_item(
        self,
        db: Session,
        sheet_id: UUID,
        item_ref: str
    ) -> List[CanonicalLabelDb]:
        """Get all labels for a specific item (all label types)"""
        try:
            return db.query(self.model).filter(
                and_(
                    self.model.sheet_id == sheet_id,
                    self.model.item_ref == item_ref
                )
            ).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing labels for item: {e}")
            db.rollback()
            raise

    def list_for_sheet(
        self,
        db: Session,
        sheet_id: UUID,
        label_type: Optional[LabelType] = None,
        only_verified: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[CanonicalLabelDb]:
        """List labels for a sheet"""
        try:
            query = db.query(self.model).filter(self.model.sheet_id == sheet_id)
            if label_type:
                query = query.filter(self.model.label_type == label_type)
            if only_verified:
                query = query.filter(self.model.is_verified == True)
            return query.offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing labels for sheet: {e}")
            db.rollback()
            raise

    def bulk_lookup(
        self,
        db: Session,
        sheet_id: UUID,
        item_refs: List[str],
        label_type: Optional[LabelType] = None
    ) -> Dict[str, List[CanonicalLabelDb]]:
        """Bulk lookup labels by item refs"""
        try:
            query = db.query(self.model).filter(
                and_(
                    self.model.sheet_id == sheet_id,
                    self.model.item_ref.in_(item_refs)
                )
            )
            if label_type:
                query = query.filter(self.model.label_type == label_type)

            results: Dict[str, List[CanonicalLabelDb]] = {ref: [] for ref in item_refs}
            for label in query.all():
                results[label.item_ref].append(label)
            return results
        except SQLAlchemyError as e:
            logger.error(f"Error in bulk label lookup: {e}")
            db.rollback()
            raise

    def increment_reuse_count(self, db: Session, label_id: UUID) -> None:
        """Increment the reuse count for a label"""
        try:
            db.query(self.model).filter(self.model.id == label_id).update(
                {self.model.reuse_count: self.model.reuse_count + 1}
            )
        except SQLAlchemyError as e:
            logger.error(f"Error incrementing reuse count: {e}")
            db.rollback()
            raise


canonical_labels_repository = CanonicalLabelsRepository()


# =============================================================================
# TRAINING COLLECTIONS REPOSITORY
# =============================================================================

class TrainingCollectionsRepository(CRUDBase[TrainingCollectionDb, TrainingCollectionCreate, dict]):
    """Repository for training collection operations"""

    def __init__(self):
        super().__init__(TrainingCollectionDb)

    def get_with_stats(self, db: Session, collection_id: UUID) -> Optional[TrainingCollectionDb]:
        """Get collection with eagerly loaded relationships"""
        try:
            return db.query(self.model).options(
                selectinload(self.model.sheet),
                selectinload(self.model.template)
            ).filter(self.model.id == collection_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting collection with stats: {e}")
            db.rollback()
            raise

    def get_by_name_version(
        self,
        db: Session,
        name: str,
        version: str
    ) -> Optional[TrainingCollectionDb]:
        """Get collection by name and version"""
        try:
            return db.query(self.model).filter(
                and_(
                    self.model.name == name,
                    self.model.version == version
                )
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting collection by name/version: {e}")
            db.rollback()
            raise

    def list_by_status(
        self,
        db: Session,
        status: TrainingSheetStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[TrainingCollectionDb]:
        """List collections by status"""
        try:
            return db.query(self.model).filter(
                self.model.status == status
            ).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing collections by status: {e}")
            db.rollback()
            raise

    def update_stats(
        self,
        db: Session,
        collection_id: UUID,
        total: int,
        approved: int,
        rejected: int,
        pending: int
    ) -> None:
        """Update collection statistics"""
        try:
            db.query(self.model).filter(self.model.id == collection_id).update({
                self.model.total_pairs: total,
                self.model.approved_pairs: approved,
                self.model.rejected_pairs: rejected,
                self.model.pending_pairs: pending
            })
        except SQLAlchemyError as e:
            logger.error(f"Error updating collection stats: {e}")
            db.rollback()
            raise

    def recalculate_stats(self, db: Session, collection_id: UUID) -> Tuple[int, int, int, int]:
        """Recalculate statistics from QA pairs"""
        try:
            total = db.query(func.count(QAPairDb.id)).filter(
                QAPairDb.collection_id == collection_id
            ).scalar() or 0

            approved = db.query(func.count(QAPairDb.id)).filter(
                and_(
                    QAPairDb.collection_id == collection_id,
                    QAPairDb.review_status.in_([
                        QAPairReviewStatus.APPROVED,
                        QAPairReviewStatus.AUTO_APPROVED,
                        QAPairReviewStatus.EDITED
                    ])
                )
            ).scalar() or 0

            rejected = db.query(func.count(QAPairDb.id)).filter(
                and_(
                    QAPairDb.collection_id == collection_id,
                    QAPairDb.review_status == QAPairReviewStatus.REJECTED
                )
            ).scalar() or 0

            pending = db.query(func.count(QAPairDb.id)).filter(
                and_(
                    QAPairDb.collection_id == collection_id,
                    QAPairDb.review_status.in_([
                        QAPairReviewStatus.PENDING,
                        QAPairReviewStatus.FLAGGED
                    ])
                )
            ).scalar() or 0

            self.update_stats(db, collection_id, total, approved, rejected, pending)
            return total, approved, rejected, pending
        except SQLAlchemyError as e:
            logger.error(f"Error recalculating collection stats: {e}")
            db.rollback()
            raise


training_collections_repository = TrainingCollectionsRepository()


# =============================================================================
# QA PAIRS REPOSITORY
# =============================================================================

class QAPairsRepository(CRUDBase[QAPairDb, QAPairCreate, dict]):
    """Repository for QA pair operations"""

    def __init__(self):
        super().__init__(QAPairDb)

    def list_for_collection(
        self,
        db: Session,
        collection_id: UUID,
        review_status: Optional[QAPairReviewStatus] = None,
        split: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[QAPairDb]:
        """List QA pairs for a collection"""
        try:
            query = db.query(self.model).filter(self.model.collection_id == collection_id)
            if review_status:
                query = query.filter(self.model.review_status == review_status)
            if split:
                query = query.filter(self.model.split == split)
            return query.offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing QA pairs for collection: {e}")
            db.rollback()
            raise

    def list_approved_for_export(
        self,
        db: Session,
        collection_id: UUID,
        splits: Optional[List[str]] = None
    ) -> List[QAPairDb]:
        """List approved QA pairs for export"""
        try:
            query = db.query(self.model).filter(
                and_(
                    self.model.collection_id == collection_id,
                    self.model.review_status.in_([
                        QAPairReviewStatus.APPROVED,
                        QAPairReviewStatus.AUTO_APPROVED,
                        QAPairReviewStatus.EDITED
                    ])
                )
            )
            if splits:
                query = query.filter(self.model.split.in_(splits))
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing approved QA pairs: {e}")
            db.rollback()
            raise

    def list_by_canonical_label(
        self,
        db: Session,
        canonical_label_id: UUID
    ) -> List[QAPairDb]:
        """List QA pairs linked to a canonical label"""
        try:
            return db.query(self.model).filter(
                self.model.canonical_label_id == canonical_label_id
            ).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing QA pairs by canonical label: {e}")
            db.rollback()
            raise

    def list_by_semantic_concept(
        self,
        db: Session,
        concept_iri: str,
        only_approved: bool = True
    ) -> List[QAPairDb]:
        """List QA pairs linked to an ontology concept"""
        try:
            query = db.query(self.model).filter(
                self.model.semantic_concept_iris.contains([concept_iri])
            )
            if only_approved:
                query = query.filter(
                    self.model.review_status.in_([
                        QAPairReviewStatus.APPROVED,
                        QAPairReviewStatus.AUTO_APPROVED,
                        QAPairReviewStatus.EDITED
                    ])
                )
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing QA pairs by semantic concept: {e}")
            db.rollback()
            raise

    def bulk_update_status(
        self,
        db: Session,
        pair_ids: List[UUID],
        status: QAPairReviewStatus,
        reviewed_by: Optional[str] = None
    ) -> int:
        """Bulk update review status"""
        try:
            from datetime import datetime, timezone
            update_data = {
                self.model.review_status: status,
                self.model.updated_by: reviewed_by
            }
            if reviewed_by:
                update_data[self.model.reviewed_by] = reviewed_by
                update_data[self.model.reviewed_at] = datetime.now(timezone.utc)

            count = db.query(self.model).filter(
                self.model.id.in_(pair_ids)
            ).update(update_data, synchronize_session=False)
            return count
        except SQLAlchemyError as e:
            logger.error(f"Error in bulk status update: {e}")
            db.rollback()
            raise

    def assign_splits(
        self,
        db: Session,
        collection_id: UUID,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1
    ) -> Dict[str, int]:
        """Assign train/val/test splits to QA pairs"""
        try:
            import random

            # Get all pairs without split assignment
            pairs = db.query(self.model).filter(
                and_(
                    self.model.collection_id == collection_id,
                    or_(
                        self.model.split.is_(None),
                        self.model.split == ""
                    )
                )
            ).all()

            if not pairs:
                return {"train": 0, "val": 0, "test": 0}

            # Shuffle and assign
            random.shuffle(pairs)
            n = len(pairs)
            train_end = int(n * train_ratio)
            val_end = train_end + int(n * val_ratio)

            counts = {"train": 0, "val": 0, "test": 0}
            for i, pair in enumerate(pairs):
                if i < train_end:
                    pair.split = "train"
                    counts["train"] += 1
                elif i < val_end:
                    pair.split = "val"
                    counts["val"] += 1
                else:
                    pair.split = "test"
                    counts["test"] += 1
                db.add(pair)

            return counts
        except SQLAlchemyError as e:
            logger.error(f"Error assigning splits: {e}")
            db.rollback()
            raise

    def bulk_create(
        self,
        db: Session,
        pairs: List[QAPairCreate]
    ) -> List[QAPairDb]:
        """Bulk create QA pairs"""
        try:
            db_pairs = []
            for pair in pairs:
                db_pair = self.model(**pair.model_dump())
                db.add(db_pair)
                db_pairs.append(db_pair)
            db.flush()
            for p in db_pairs:
                db.refresh(p)
            return db_pairs
        except SQLAlchemyError as e:
            logger.error(f"Error in bulk create: {e}")
            db.rollback()
            raise


qa_pairs_repository = QAPairsRepository()


# =============================================================================
# EXAMPLE STORE REPOSITORY
# =============================================================================

class ExampleStoreRepository(CRUDBase[ExampleStoreDb, ExampleCreate, dict]):
    """Repository for example store operations"""

    def __init__(self):
        super().__init__(ExampleStoreDb)

    def search(
        self,
        db: Session,
        domain: Optional[str] = None,
        task_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        function_name: Optional[str] = None,
        capability_tags: Optional[List[str]] = None,
        only_verified: bool = False,
        limit: int = 10
    ) -> List[ExampleStoreDb]:
        """Search examples by metadata"""
        try:
            query = db.query(self.model)
            if domain:
                query = query.filter(self.model.domain == domain)
            if task_type:
                query = query.filter(self.model.task_type == task_type)
            if difficulty:
                query = query.filter(self.model.difficulty == difficulty)
            if function_name:
                query = query.filter(self.model.function_name == function_name)
            if capability_tags:
                query = query.filter(self.model.capability_tags.overlap(capability_tags))
            if only_verified:
                query = query.filter(self.model.is_verified == True)

            # Order by effectiveness and usage
            query = query.order_by(
                self.model.effectiveness_score.desc().nullslast(),
                self.model.usage_count.desc()
            )
            return query.limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error searching examples: {e}")
            db.rollback()
            raise

    def increment_usage(self, db: Session, example_id: UUID) -> None:
        """Increment usage count"""
        try:
            db.query(self.model).filter(self.model.id == example_id).update(
                {self.model.usage_count: self.model.usage_count + 1}
            )
        except SQLAlchemyError as e:
            logger.error(f"Error incrementing example usage: {e}")
            db.rollback()
            raise

    def update_effectiveness(
        self,
        db: Session,
        example_id: UUID,
        score: float
    ) -> None:
        """Update effectiveness score"""
        try:
            db.query(self.model).filter(self.model.id == example_id).update(
                {self.model.effectiveness_score: score}
            )
        except SQLAlchemyError as e:
            logger.error(f"Error updating example effectiveness: {e}")
            db.rollback()
            raise


example_store_repository = ExampleStoreRepository()


# =============================================================================
# MODEL TRAINING LINEAGE REPOSITORY
# =============================================================================

class ModelTrainingLineageRepository(CRUDBase[ModelTrainingLineageDb, ModelLineageCreate, dict]):
    """Repository for model training lineage operations"""

    def __init__(self):
        super().__init__(ModelTrainingLineageDb)

    def get_by_model_version(
        self,
        db: Session,
        model_name: str,
        model_version: str
    ) -> Optional[ModelTrainingLineageDb]:
        """Get lineage by model name and version"""
        try:
            return db.query(self.model).filter(
                and_(
                    self.model.model_name == model_name,
                    self.model.model_version == model_version
                )
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting lineage by model version: {e}")
            db.rollback()
            raise

    def list_for_collection(
        self,
        db: Session,
        collection_id: UUID
    ) -> List[ModelTrainingLineageDb]:
        """List all models trained on a collection"""
        try:
            return db.query(self.model).filter(
                self.model.collection_id == collection_id
            ).order_by(self.model.created_at.desc()).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing lineage for collection: {e}")
            db.rollback()
            raise

    def list_versions(
        self,
        db: Session,
        model_name: str
    ) -> List[ModelTrainingLineageDb]:
        """List all versions of a model"""
        try:
            return db.query(self.model).filter(
                self.model.model_name == model_name
            ).order_by(self.model.created_at.desc()).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing model versions: {e}")
            db.rollback()
            raise


model_training_lineage_repository = ModelTrainingLineageRepository()


# =============================================================================
# TRAINING JOBS REPOSITORY
# =============================================================================

class TrainingJobsRepository(CRUDBase[TrainingJobDb, TrainingJobCreate, dict]):
    """Repository for training job operations"""

    def __init__(self):
        super().__init__(TrainingJobDb)

    def list_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[TrainingJobDb]:
        """List all training jobs"""
        try:
            return db.query(self.model).order_by(
                self.model.created_at.desc()
            ).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing training jobs: {e}")
            db.rollback()
            raise

    def list_by_collection(
        self,
        db: Session,
        collection_id: UUID
    ) -> List[TrainingJobDb]:
        """List training jobs for a collection"""
        try:
            return db.query(self.model).filter(
                self.model.collection_id == collection_id
            ).order_by(self.model.created_at.desc()).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing training jobs by collection: {e}")
            db.rollback()
            raise


training_jobs_repository = TrainingJobsRepository()


# =============================================================================
# DSPY OPTIMIZATION RUNS REPOSITORY
# =============================================================================

class DSPyRunsRepository(CRUDBase[DSPyOptimizationRunDb, DSPyRunCreate, dict]):
    """Repository for DSPy optimization run operations"""

    def __init__(self):
        super().__init__(DSPyOptimizationRunDb)

    def list_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[DSPyOptimizationRunDb]:
        """List all DSPy runs"""
        try:
            return db.query(self.model).order_by(
                self.model.created_at.desc()
            ).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error listing DSPy runs: {e}")
            db.rollback()
            raise


dspy_runs_repository = DSPyRunsRepository()
