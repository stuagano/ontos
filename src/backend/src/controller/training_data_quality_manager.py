"""
Training Data Quality Manager

Business logic for DQX quality gate integration. Manages quality check
definitions per collection, executes checks (mock locally, DQX on Spark),
and gates training exports.

Separated from MLMonitorManager because data quality gating is pre-training,
not production monitoring.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.common.config import Settings
from src.common.logging import get_logger
from src.models.training_data_quality import (
    CheckCriticality,
    CheckResult,
    DQXResultImport,
    QualityCheck,
    QualityCheckCreate,
    QualityRun,
    QualityRunCreate,
    QualityRunStatus,
    ValidationIssue,
    ValidationResult,
)

logger = get_logger(__name__)


class TrainingDataQualityManager:
    """Manages data quality checks and gating for training collections."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
    ):
        self._db = db
        self._settings = settings

    # =========================================================================
    # CHECK CRUD
    # =========================================================================

    def create_check(
        self, payload: QualityCheckCreate, created_by: Optional[str] = None
    ) -> QualityCheck:
        """Create a quality check definition for a collection."""
        check_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        self._db.execute(
            text("""
                INSERT INTO training_data_quality_checks
                    (id, collection_id, check_name, check_function, column_name,
                     criticality, parameters, created_by, created_at)
                VALUES (:id, :collection_id, :check_name, :check_function, :column_name,
                        :criticality, :parameters, :created_by, :created_at)
            """),
            {
                "id": check_id,
                "collection_id": payload.collection_id,
                "check_name": payload.check_name,
                "check_function": payload.check_function,
                "column_name": payload.column_name,
                "criticality": payload.criticality.value,
                "parameters": json.dumps(payload.parameters) if payload.parameters else None,
                "created_by": created_by,
                "created_at": now,
            },
        )
        self._db.flush()
        logger.info(f"Created quality check '{payload.check_name}' for collection {payload.collection_id}")
        return QualityCheck(
            id=check_id,
            collection_id=payload.collection_id,
            check_name=payload.check_name,
            check_function=payload.check_function,
            column_name=payload.column_name,
            criticality=payload.criticality,
            parameters=payload.parameters,
            created_by=created_by,
            created_at=now,
        )

    def list_checks(self, collection_id: UUID) -> List[QualityCheck]:
        """List all quality checks for a collection."""
        rows = self._db.execute(
            text("""
                SELECT id, collection_id, check_name, check_function, column_name,
                       criticality, parameters, created_by, created_at
                FROM training_data_quality_checks
                WHERE collection_id = :collection_id
                ORDER BY created_at
            """),
            {"collection_id": collection_id},
        ).fetchall()
        return [
            QualityCheck(
                id=r.id,
                collection_id=r.collection_id,
                check_name=r.check_name,
                check_function=r.check_function,
                column_name=r.column_name,
                criticality=r.criticality,
                parameters=r.parameters,
                created_by=r.created_by,
                created_at=r.created_at,
            )
            for r in rows
        ]

    def delete_check(self, check_id: UUID) -> bool:
        """Delete a quality check definition."""
        result = self._db.execute(
            text("DELETE FROM training_data_quality_checks WHERE id = :id"),
            {"id": check_id},
        )
        self._db.flush()
        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"Deleted quality check {check_id}")
        return deleted

    # =========================================================================
    # EXECUTION — Mock heuristics for local dev, DQX on Spark
    # =========================================================================

    def run_quality_checks(
        self,
        collection_id: UUID,
        source: str = "mock",
        created_by: Optional[str] = None,
    ) -> QualityRun:
        """Execute quality checks against a collection's QA pairs.

        In mock mode, runs heuristic checks on QA pair content
        (message completeness, JSON validity, response length).
        """
        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Create the run record
        self._db.execute(
            text("""
                INSERT INTO training_data_quality_runs
                    (id, collection_id, status, source, started_at, created_by, created_at)
                VALUES (:id, :collection_id, 'running', :source, :started_at, :created_by, :created_at)
            """),
            {
                "id": run_id,
                "collection_id": collection_id,
                "source": source,
                "started_at": now,
                "created_by": created_by,
                "created_at": now,
            },
        )
        self._db.flush()

        try:
            # Get checks defined for this collection
            checks = self.list_checks(collection_id)
            if not checks:
                # Auto-generate default checks
                checks = self._create_default_checks(collection_id, created_by)

            # Get QA pairs for analysis
            pairs = self._db.execute(
                text("""
                    SELECT id, messages, quality_score, review_status, split
                    FROM qa_pairs
                    WHERE collection_id = :collection_id
                """),
                {"collection_id": collection_id},
            ).fetchall()

            # Run each check
            results: List[CheckResult] = []
            for check in checks:
                result = self._execute_mock_check(check, pairs)
                results.append(result)

            # Calculate summary
            passed_count = sum(1 for r in results if r.passed)
            pass_rate = passed_count / len(results) if results else 1.0
            quality_score = pass_rate  # Simplistic — can be weighted later

            # Determine run status
            has_blocking_failure = any(
                not r.passed and r.criticality == CheckCriticality.BLOCKING
                for r in results
            )
            run_status = QualityRunStatus.FAILED if has_blocking_failure else QualityRunStatus.PASSED

            completed_at = datetime.now(timezone.utc)

            # Update run record
            self._db.execute(
                text("""
                    UPDATE training_data_quality_runs
                    SET status = :status, pass_rate = :pass_rate, quality_score = :quality_score,
                        check_results = :check_results, completed_at = :completed_at
                    WHERE id = :id
                """),
                {
                    "id": run_id,
                    "status": run_status.value,
                    "pass_rate": pass_rate,
                    "quality_score": quality_score,
                    "check_results": json.dumps([r.model_dump(mode="json") for r in results]),
                    "completed_at": completed_at,
                },
            )
            self._db.flush()

            logger.info(
                f"Quality run {run_id} completed: {run_status.value} "
                f"({passed_count}/{len(results)} checks passed, score={quality_score:.2f})"
            )

            return QualityRun(
                id=run_id,
                collection_id=collection_id,
                status=run_status,
                source=source,
                pass_rate=pass_rate,
                quality_score=quality_score,
                check_results=results,
                started_at=now,
                completed_at=completed_at,
                created_by=created_by,
                created_at=now,
            )

        except Exception as e:
            logger.error(f"Quality run {run_id} failed: {e}", exc_info=True)
            self._db.execute(
                text("""
                    UPDATE training_data_quality_runs
                    SET status = 'error', completed_at = :completed_at
                    WHERE id = :id
                """),
                {"id": run_id, "completed_at": datetime.now(timezone.utc)},
            )
            self._db.flush()
            raise

    def _create_default_checks(
        self, collection_id: UUID, created_by: Optional[str] = None
    ) -> List[QualityCheck]:
        """Create sensible default checks when none are defined."""
        defaults = [
            QualityCheckCreate(
                collection_id=collection_id,
                check_name="Message completeness",
                check_function="message_completeness",
                column_name="messages",
                criticality=CheckCriticality.BLOCKING,
                parameters={"min_roles": ["system", "user", "assistant"]},
            ),
            QualityCheckCreate(
                collection_id=collection_id,
                check_name="Response JSON validity",
                check_function="json_valid_response",
                column_name="messages",
                criticality=CheckCriticality.WARNING,
            ),
            QualityCheckCreate(
                collection_id=collection_id,
                check_name="Minimum response length",
                check_function="min_response_length",
                column_name="messages",
                criticality=CheckCriticality.WARNING,
                parameters={"min_chars": 50},
            ),
            QualityCheckCreate(
                collection_id=collection_id,
                check_name="Quality score threshold",
                check_function="quality_score_threshold",
                column_name="quality_score",
                criticality=CheckCriticality.INFO,
                parameters={"min_score": 0.7},
            ),
        ]
        return [self.create_check(d, created_by) for d in defaults]

    def _execute_mock_check(self, check: QualityCheck, pairs: list) -> CheckResult:
        """Run a single heuristic check against QA pairs."""
        fn = check.check_function
        params = check.parameters or {}

        if fn == "message_completeness":
            return self._check_message_completeness(check, pairs, params)
        elif fn == "json_valid_response":
            return self._check_json_valid_response(check, pairs)
        elif fn == "min_response_length":
            return self._check_min_response_length(check, pairs, params)
        elif fn == "quality_score_threshold":
            return self._check_quality_score_threshold(check, pairs, params)
        else:
            # Unknown check — pass with info
            return CheckResult(
                check_id=check.id,
                check_name=check.check_name,
                passed=True,
                criticality=check.criticality,
                message=f"Check '{fn}' not implemented in mock mode — skipped",
            )

    def _check_message_completeness(
        self, check: QualityCheck, pairs: list, params: Dict[str, Any]
    ) -> CheckResult:
        """Verify all QA pairs have the required message roles."""
        required_roles = set(params.get("min_roles", ["system", "user", "assistant"]))
        incomplete = 0
        for pair in pairs:
            messages = pair.messages if isinstance(pair.messages, list) else []
            roles = {m.get("role") for m in messages if isinstance(m, dict)}
            if not required_roles.issubset(roles):
                incomplete += 1

        passed = incomplete == 0
        return CheckResult(
            check_id=check.id,
            check_name=check.check_name,
            passed=passed,
            criticality=check.criticality,
            message=f"{len(pairs) - incomplete}/{len(pairs)} pairs have all required roles"
            if passed
            else f"{incomplete}/{len(pairs)} pairs missing required roles {required_roles}",
            details={"incomplete_count": incomplete, "total": len(pairs)},
        )

    def _check_json_valid_response(
        self, check: QualityCheck, pairs: list
    ) -> CheckResult:
        """Check that assistant responses contain valid JSON."""
        invalid = 0
        for pair in pairs:
            messages = pair.messages if isinstance(pair.messages, list) else []
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "assistant":
                    content = m.get("content", "")
                    try:
                        json.loads(content)
                    except (json.JSONDecodeError, TypeError):
                        # Not JSON — that's fine if it's plain text
                        pass
                    else:
                        continue
                    # If we get here, content might be plain text (acceptable)
                    # Only flag if it looks like it should be JSON but isn't
                    if content.strip().startswith("{") or content.strip().startswith("["):
                        try:
                            json.loads(content)
                        except (json.JSONDecodeError, TypeError):
                            invalid += 1

        passed = invalid == 0
        return CheckResult(
            check_id=check.id,
            check_name=check.check_name,
            passed=passed,
            criticality=check.criticality,
            message=f"All responses have valid JSON" if passed else f"{invalid} responses have malformed JSON",
            details={"invalid_count": invalid, "total": len(pairs)},
        )

    def _check_min_response_length(
        self, check: QualityCheck, pairs: list, params: Dict[str, Any]
    ) -> CheckResult:
        """Check that assistant responses meet minimum length."""
        min_chars = params.get("min_chars", 50)
        short = 0
        for pair in pairs:
            messages = pair.messages if isinstance(pair.messages, list) else []
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "assistant":
                    if len(m.get("content", "")) < min_chars:
                        short += 1

        passed = short == 0
        return CheckResult(
            check_id=check.id,
            check_name=check.check_name,
            passed=passed,
            criticality=check.criticality,
            message=f"All responses >= {min_chars} chars" if passed else f"{short} responses below {min_chars} chars",
            details={"short_count": short, "min_chars": min_chars, "total": len(pairs)},
        )

    def _check_quality_score_threshold(
        self, check: QualityCheck, pairs: list, params: Dict[str, Any]
    ) -> CheckResult:
        """Check that average quality score meets threshold."""
        min_score = params.get("min_score", 0.7)
        scores = [p.quality_score for p in pairs if p.quality_score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        passed = avg_score >= min_score

        return CheckResult(
            check_id=check.id,
            check_name=check.check_name,
            passed=passed,
            criticality=check.criticality,
            message=f"Avg quality score {avg_score:.2f} >= {min_score}" if passed
            else f"Avg quality score {avg_score:.2f} below threshold {min_score}",
            details={"avg_score": avg_score, "min_score": min_score, "scored_pairs": len(scores)},
        )

    # =========================================================================
    # SCORING — Propagate run results to qa_pairs.quality_score
    # =========================================================================

    def update_qa_pair_quality(self, collection_id: UUID, quality_score: float) -> int:
        """Update quality_score on all QA pairs in a collection based on run results."""
        result = self._db.execute(
            text("""
                UPDATE qa_pairs
                SET quality_score = :quality_score, updated_at = :updated_at
                WHERE collection_id = :collection_id AND quality_score IS NULL
            """),
            {
                "quality_score": quality_score,
                "collection_id": collection_id,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        self._db.flush()
        updated = result.rowcount
        logger.info(f"Updated quality_score to {quality_score:.2f} on {updated} pairs in collection {collection_id}")
        return updated

    # =========================================================================
    # GATE — Validate collection for training export
    # =========================================================================

    def validate_for_training(self, collection_id: UUID) -> ValidationResult:
        """Check if a collection passes quality gate for training export.

        Returns pass/fail with blocking issues, warnings, and info.
        """
        # Get the latest completed run
        row = self._db.execute(
            text("""
                SELECT id, status, pass_rate, quality_score, check_results
                FROM training_data_quality_runs
                WHERE collection_id = :collection_id AND status IN ('passed', 'failed')
                ORDER BY completed_at DESC
                LIMIT 1
            """),
            {"collection_id": collection_id},
        ).fetchone()

        if not row:
            return ValidationResult(
                collection_id=collection_id,
                is_valid=False,
                blocking_issues=[
                    ValidationIssue(
                        check_name="No quality run",
                        criticality=CheckCriticality.BLOCKING,
                        message="No completed quality run found. Run quality checks before export.",
                    )
                ],
            )

        # Parse check results
        check_results_raw = row.check_results or []
        if isinstance(check_results_raw, str):
            check_results_raw = json.loads(check_results_raw)

        blocking: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        info: List[ValidationIssue] = []

        for cr in check_results_raw:
            if cr.get("passed"):
                continue
            issue = ValidationIssue(
                check_name=cr.get("check_name", "unknown"),
                criticality=cr.get("criticality", "warning"),
                message=cr.get("message", "Check failed"),
            )
            crit = cr.get("criticality", "warning")
            if crit == "blocking":
                blocking.append(issue)
            elif crit == "warning":
                warnings.append(issue)
            else:
                info.append(issue)

        return ValidationResult(
            collection_id=collection_id,
            is_valid=len(blocking) == 0,
            quality_score=row.quality_score,
            blocking_issues=blocking,
            warnings=warnings,
            info=info,
            latest_run_id=row.id,
        )

    # =========================================================================
    # IMPORT — Accept results from VITAL's DQX proxy
    # =========================================================================

    def import_dqx_results(
        self,
        collection_id: UUID,
        payload: DQXResultImport,
        created_by: Optional[str] = None,
    ) -> QualityRun:
        """Import quality check results pushed from VITAL's DQX proxy."""
        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        results = payload.check_results
        passed_count = sum(1 for r in results if r.passed)
        pass_rate = passed_count / len(results) if results else 1.0
        quality_score = pass_rate

        has_blocking_failure = any(
            not r.passed and r.criticality == CheckCriticality.BLOCKING
            for r in results
        )
        run_status = QualityRunStatus.FAILED if has_blocking_failure else QualityRunStatus.PASSED

        self._db.execute(
            text("""
                INSERT INTO training_data_quality_runs
                    (id, collection_id, status, source, pass_rate, quality_score,
                     check_results, started_at, completed_at, created_by, created_at)
                VALUES (:id, :collection_id, :status, :source, :pass_rate, :quality_score,
                        :check_results, :started_at, :completed_at, :created_by, :created_at)
            """),
            {
                "id": run_id,
                "collection_id": collection_id,
                "status": run_status.value,
                "source": payload.source,
                "pass_rate": pass_rate,
                "quality_score": quality_score,
                "check_results": json.dumps([r.model_dump(mode="json") for r in results]),
                "started_at": now,
                "completed_at": now,
                "created_by": created_by,
                "created_at": now,
            },
        )
        self._db.flush()

        logger.info(
            f"Imported DQX results for collection {collection_id}: "
            f"{run_status.value} ({passed_count}/{len(results)} passed)"
        )

        return QualityRun(
            id=run_id,
            collection_id=collection_id,
            status=run_status,
            source=payload.source,
            pass_rate=pass_rate,
            quality_score=quality_score,
            check_results=results,
            started_at=now,
            completed_at=now,
            created_by=created_by,
            created_at=now,
        )

    # =========================================================================
    # HISTORY
    # =========================================================================

    def list_runs(self, collection_id: UUID) -> List[QualityRun]:
        """List all quality runs for a collection."""
        rows = self._db.execute(
            text("""
                SELECT id, collection_id, status, source, pass_rate, quality_score,
                       check_results, started_at, completed_at, created_by, created_at
                FROM training_data_quality_runs
                WHERE collection_id = :collection_id
                ORDER BY created_at DESC
            """),
            {"collection_id": collection_id},
        ).fetchall()

        results = []
        for r in rows:
            check_results_raw = r.check_results
            if isinstance(check_results_raw, str):
                check_results_raw = json.loads(check_results_raw)
            check_results = (
                [CheckResult(**cr) for cr in check_results_raw]
                if check_results_raw
                else None
            )
            results.append(
                QualityRun(
                    id=r.id,
                    collection_id=r.collection_id,
                    status=r.status,
                    source=r.source,
                    pass_rate=r.pass_rate,
                    quality_score=r.quality_score,
                    check_results=check_results,
                    started_at=r.started_at,
                    completed_at=r.completed_at,
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
            )
        return results
