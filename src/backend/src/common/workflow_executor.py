"""
Workflow Executor for executing process workflows.

Handles step-by-step execution with branching, including:
- Validation steps (using compliance DSL)
- Approval steps (creates approval requests)
- Notification steps
- Tag assignment/removal
- Conditional branching
- Script execution
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.db_models.process_workflows import WorkflowStepDb, WorkflowExecutionDb
from src.models.process_workflows import (
    ProcessWorkflow,
    WorkflowStep,
    WorkflowExecution,
    WorkflowExecutionCreate,
    TriggerContext,
    StepType,
    ExecutionStatus,
    StepExecutionStatus,
    WorkflowStepExecutionResult,
)
from src.repositories.process_workflows_repository import workflow_execution_repo
from src.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StepContext:
    """Context for step execution."""
    entity: Dict[str, Any]
    entity_type: str
    entity_id: str
    entity_name: Optional[str]
    user_email: Optional[str]
    trigger_context: Optional[TriggerContext]
    execution_id: str
    workflow_id: str
    workflow_name: str
    step_results: Dict[str, Any]  # Results from previous steps


@dataclass
class StepResult:
    """Result of step execution."""
    passed: bool
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    blocking: bool = False  # If True, workflow pauses (e.g., approval)


class StepHandler(ABC):
    """Base class for step handlers."""

    def __init__(self, db: Session, config: Dict[str, Any]):
        self._db = db
        self._config = config

    @abstractmethod
    def execute(self, context: StepContext) -> StepResult:
        """Execute the step.
        
        Args:
            context: Step execution context
            
        Returns:
            StepResult with execution outcome
        """
        pass


class ValidationStepHandler(StepHandler):
    """Handler for validation steps using compliance DSL."""

    def execute(self, context: StepContext) -> StepResult:
        from src.common.compliance_dsl import evaluate_rule_on_object
        
        rule = self._config.get('rule', '')
        if not rule:
            return StepResult(passed=False, error="No rule configured")
        
        try:
            passed, message = evaluate_rule_on_object(rule, context.entity)
            return StepResult(
                passed=passed,
                message=message,
                data={'rule': rule}
            )
        except Exception as e:
            logger.exception(f"Validation step failed: {e}")
            return StepResult(
                passed=False,
                error=str(e)
            )


class ApprovalStepHandler(StepHandler):
    """Handler for approval steps - creates actionable notifications and pauses workflow."""

    def execute(self, context: StepContext) -> StepResult:
        from uuid import uuid4
        from src.models.notifications import Notification, NotificationType
        from src.repositories.notification_repository import notification_repo
        
        approvers = self._config.get('approvers', '')
        timeout_days = self._config.get('timeout_days', 7)
        require_all = self._config.get('require_all', False)
        approval_message = self._config.get('message', '')
        
        if not approvers:
            return StepResult(passed=False, error="No approvers configured")
        
        try:
            # Resolve approvers - returns list of (identifier, role_id or None)
            resolved_approvers = self._resolve_approvers(approvers, context)
            
            if not resolved_approvers:
                return StepResult(passed=False, error="Could not resolve any approvers")
            
            entity_display = context.entity_name or context.entity_id
            
            # Create actionable notification for each approver
            created_count = 0
            for approver_id, role_uuid in resolved_approvers:
                try:
                    # Build description with request details
                    description = (
                        f"Approval requested for {context.entity_type} '{entity_display}'.\n\n"
                        f"Requested by: {context.user_email or 'Unknown'}\n"
                    )
                    if approval_message:
                        description += f"\nMessage: {approval_message}"
                    if context.entity.get('message'):
                        description += f"\nMessage: {context.entity.get('message')}"
                    if context.entity.get('justification'):
                        description += f"\nJustification: {context.entity.get('justification')}"
                    
                    notification = Notification(
                        id=str(uuid4()),
                        created_at=datetime.utcnow(),
                        type=NotificationType.ACTION_REQUIRED,
                        title="Approval Required",
                        subtitle=f"{context.entity_type}: {entity_display}",
                        description=description,
                        recipient=approver_id,  # Keep for backwards compat / email recipients
                        recipient_role_id=role_uuid,  # Store role UUID if this is a role
                        action_type="workflow_approval",
                        action_payload={
                            "execution_id": context.execution_id,
                            "workflow_id": context.workflow_id,
                            "workflow_name": context.workflow_name,
                            "entity_type": context.entity_type,
                            "entity_id": context.entity_id,
                            "entity_name": context.entity_name,
                            "requester_email": context.user_email,
                            "timeout_days": timeout_days,
                        },
                        can_delete=False,  # Must respond to this notification
                        read=False,
                    )
                    notification_repo.create(db=self._db, obj_in=notification)
                    created_count += 1
                    logger.info(f"Approval notification created for {approver_id}" + (f" (role: {role_uuid})" if role_uuid else ""))
                except Exception as e:
                    logger.warning(f"Failed to create approval notification for {approver_id}: {e}")
            
            if created_count == 0:
                return StepResult(
                    passed=False,
                    error="Failed to create approval notifications",
                    data={'approvers': [a[0] for a in resolved_approvers]}
                )
            
            # Return blocking=True to pause workflow and wait for approval
            return StepResult(
                passed=True,  # Initial pass, actual result comes when approval is handled
                message=f"Approval requested from: {', '.join(a[0] for a in resolved_approvers)}",
                data={
                    'approvers': [a[0] for a in resolved_approvers],
                    'timeout_days': timeout_days,
                    'require_all': require_all,
                    'status': 'pending',
                    'notifications_created': created_count,
                },
                blocking=True,  # Pause workflow until resume_workflow() is called
            )
        except Exception as e:
            logger.exception(f"Approval step failed: {e}")
            return StepResult(passed=False, error=str(e))

    def _lookup_role_id(self, role_name: str) -> Optional[str]:
        """Look up a role by name (flexible matching) and return its UUID."""
        from src.db_models.settings import AppRoleDb
        
        # Try exact match first
        role = self._db.query(AppRoleDb).filter(AppRoleDb.name == role_name).first()
        if role:
            return role.id
        
        # Try normalized match (case-insensitive, no spaces)
        normalized = role_name.lower().replace(' ', '')
        all_roles = self._db.query(AppRoleDb).all()
        for r in all_roles:
            if r.name.lower().replace(' ', '') == normalized:
                return r.id
        
        return None

    def _resolve_approvers(self, approvers: str, context: StepContext) -> List[tuple]:
        """Resolve approver specification to list of (identifier, role_uuid) tuples.
        
        Returns:
            List of (identifier, role_uuid) where:
            - identifier: email, username, or role name for display
            - role_uuid: UUID if this is a role-based approver, None for direct users
        """
        from src.db_models.settings import AppRoleDb
        
        # Map shorthand names to role names (legacy support)
        role_aliases = {
            'domain_owners': 'DomainOwner',
            'project_owners': 'ProjectOwner',
            'data_stewards': 'DataSteward',
            'admins': 'Admin',
        }
        
        if approvers == 'requester':
            return [(context.user_email, None)] if context.user_email else []
        elif approvers in role_aliases:
            # Legacy: shorthand alias
            role_name = role_aliases[approvers]
            role_id = self._lookup_role_id(role_name)
            return [(role_name, role_id)]
        elif '@' in approvers:
            # Assume it's an email or comma-separated emails
            return [(e.strip(), None) for e in approvers.split(',')]
        else:
            # Check if it's a role UUID (preferred - new format)
            role_by_id = self._db.query(AppRoleDb).filter(AppRoleDb.id == approvers).first()
            if role_by_id:
                # It's a UUID - use role name for display, UUID for matching
                return [(role_by_id.name, role_by_id.id)]
            
            # Fallback: Assume it's a role name (legacy support)
            role_id = self._lookup_role_id(approvers)
            return [(approvers, role_id)]


class NotificationStepHandler(StepHandler):
    """Handler for notification steps - sends notifications via NotificationsManager."""

    def execute(self, context: StepContext) -> StepResult:
        from uuid import uuid4
        from src.models.notifications import Notification, NotificationType
        from src.repositories.notification_repository import notification_repo
        
        recipients = self._config.get('recipients', '')
        template = self._config.get('template', '')
        custom_message = self._config.get('custom_message')
        
        if not recipients:
            return StepResult(passed=False, error="No recipients configured")
        
        try:
            # Resolve recipients
            resolved_recipients = self._resolve_recipients(recipients, context)
            
            # Build notification message
            message = custom_message or self._get_template_message(template, context)
            title = self._get_template_title(template, context)
            
            # Determine notification type based on template
            notification_type = self._get_notification_type(template)
            
            # Determine if this is an actionable notification (for approvals)
            action_type = None
            action_payload = None
            can_delete = True
            
            if template in ('approval_requested', 'request_submitted'):
                # This will be handled by the approval step, not notification
                pass
            elif template in ('request_approved', 'request_rejected'):
                can_delete = True
            
            # Create notifications for each recipient
            created_count = 0
            for recipient_id, role_uuid in resolved_recipients:
                try:
                    notification = Notification(
                        id=str(uuid4()),
                        created_at=datetime.utcnow(),
                        type=notification_type,
                        title=title,
                        subtitle=f"{context.entity_type}: {context.entity_name}",
                        description=message,
                        recipient=recipient_id,
                        recipient_role_id=role_uuid,
                        action_type=action_type,
                        action_payload=action_payload,
                        can_delete=can_delete,
                        read=False,
                    )
                    notification_repo.create(db=self._db, obj_in=notification)
                    created_count += 1
                    logger.info(f"Notification created for {recipient_id}: {title}")
                except Exception as e:
                    logger.warning(f"Failed to create notification for {recipient_id}: {e}")
            
            if created_count == 0:
                return StepResult(
                    passed=False,
                    error="Failed to create any notifications",
                    data={'recipients': [r[0] for r in resolved_recipients], 'template': template}
                )
            
            return StepResult(
                passed=True,
                message=f"Notification sent to: {', '.join(r[0] for r in resolved_recipients)}",
                data={
                    'recipients': [r[0] for r in resolved_recipients],
                    'template': template,
                    'message': message,
                    'created_count': created_count,
                }
            )
        except Exception as e:
            logger.exception(f"Notification step failed: {e}")
            return StepResult(passed=False, error=str(e))

    def _lookup_role_id(self, role_name: str) -> Optional[str]:
        """Look up a role by name (flexible matching) and return its UUID."""
        from src.db_models.settings import AppRoleDb
        
        # Try exact match first
        role = self._db.query(AppRoleDb).filter(AppRoleDb.name == role_name).first()
        if role:
            return role.id
        
        # Try normalized match (case-insensitive, no spaces)
        normalized = role_name.lower().replace(' ', '')
        all_roles = self._db.query(AppRoleDb).all()
        for r in all_roles:
            if r.name.lower().replace(' ', '') == normalized:
                return r.id
        
        return None

    def _resolve_recipients(self, recipients: str, context: StepContext) -> List[tuple]:
        """Resolve recipient specification to list of (identifier, role_uuid) tuples."""
        from src.db_models.settings import AppRoleDb
        
        role_aliases = {
            'domain_owners': 'DomainOwner',
            'data_stewards': 'DataSteward',
        }
        
        if recipients == 'requester':
            return [(context.user_email, None)] if context.user_email else []
        elif recipients == 'owner':
            owner = context.entity.get('owner')
            return [(owner, None)] if owner else []
        elif recipients in role_aliases:
            # Legacy: shorthand alias
            role_name = role_aliases[recipients]
            role_id = self._lookup_role_id(role_name)
            return [(role_name, role_id)]
        elif '@' in recipients:
            return [(e.strip(), None) for e in recipients.split(',')]
        else:
            # Check if it's a role UUID (preferred - new format)
            role_by_id = self._db.query(AppRoleDb).filter(AppRoleDb.id == recipients).first()
            if role_by_id:
                # It's a UUID - use role name for display, UUID for matching
                return [(role_by_id.name, role_by_id.id)]
            
            # Fallback: Assume it's a role name (legacy support)
            role_id = self._lookup_role_id(recipients)
            return [(recipients, role_id)]

    def _get_template_title(self, template: str, context: StepContext) -> str:
        """Get notification title from template."""
        entity_display = context.entity_name or context.entity_id
        titles = {
            'validation_failed': "Validation Failed",
            'validation_passed': "Validation Passed",
            'product_approved': "Data Product Approved",
            'product_rejected': "Data Product Rejected",
            'approval_requested': "Approval Requested",
            'request_submitted': "Request Submitted",
            'request_approved': "Request Approved",
            'request_rejected': "Request Denied",
            'dataset_updated': "Dataset Updated",
            'pii_detected': "PII Detected",
        }
        return titles.get(template, "Workflow Notification")

    def _get_template_message(self, template: str, context: StepContext) -> str:
        """Get message from template."""
        entity_display = context.entity_name or context.entity_id
        templates = {
            'validation_failed': f"Validation failed for {context.entity_type} '{entity_display}'",
            'validation_passed': f"Validation passed for {context.entity_type} '{entity_display}'",
            'product_approved': f"Data product '{entity_display}' has been approved",
            'product_rejected': f"Data product '{entity_display}' has been rejected",
            'approval_requested': f"Approval requested for {context.entity_type} '{entity_display}'",
            'request_submitted': f"Your request for {context.entity_type} '{entity_display}' has been submitted and is pending review.",
            'request_approved': f"Your request for {context.entity_type} '{entity_display}' has been approved.",
            'request_rejected': f"Your request for {context.entity_type} '{entity_display}' has been denied.",
            'dataset_updated': f"Dataset '{entity_display}' has been updated.",
            'pii_detected': f"Potential PII detected in {context.entity_type} '{entity_display}'. Please review.",
        }
        return templates.get(template, f"Workflow notification for {entity_display}")

    def _get_notification_type(self, template: str) -> 'NotificationType':
        """Get notification type based on template."""
        from src.models.notifications import NotificationType
        
        if template in ('validation_failed', 'request_rejected', 'product_rejected', 'pii_detected'):
            return NotificationType.ERROR
        elif template in ('approval_requested',):
            return NotificationType.ACTION_REQUIRED
        elif template in ('validation_passed', 'request_approved', 'product_approved'):
            return NotificationType.SUCCESS
        else:
            return NotificationType.INFO


class AssignTagStepHandler(StepHandler):
    """Handler for tag assignment steps."""

    def execute(self, context: StepContext) -> StepResult:
        key = self._config.get('key', '')
        value = self._config.get('value')
        value_source = self._config.get('value_source')
        
        if not key:
            return StepResult(passed=False, error="No tag key configured")
        
        try:
            # Resolve value
            if value_source:
                resolved_value = self._resolve_value_source(value_source, context)
            else:
                resolved_value = value
            
            if not resolved_value:
                return StepResult(passed=False, error="Could not resolve tag value")
            
            # Assign tag to entity
            # TODO: Integrate with TagsManager
            logger.info(f"Assigning tag {key}={resolved_value} to {context.entity_type} {context.entity_id}")
            
            # Update entity tags in context
            if 'tags' not in context.entity:
                context.entity['tags'] = {}
            context.entity['tags'][key] = resolved_value
            
            return StepResult(
                passed=True,
                message=f"Assigned tag {key}={resolved_value}",
                data={'key': key, 'value': resolved_value}
            )
        except Exception as e:
            logger.exception(f"Assign tag step failed: {e}")
            return StepResult(passed=False, error=str(e))

    def _resolve_value_source(self, source: str, context: StepContext) -> Optional[str]:
        """Resolve dynamic value source."""
        if source == 'current_user':
            return context.user_email
        elif source == 'project_name':
            return context.entity.get('project_name') or context.entity.get('project_id')
        elif source == 'entity_name':
            return context.entity_name
        elif source == 'timestamp':
            return datetime.utcnow().isoformat()
        else:
            return None


class RemoveTagStepHandler(StepHandler):
    """Handler for tag removal steps."""

    def execute(self, context: StepContext) -> StepResult:
        key = self._config.get('key', '')
        
        if not key:
            return StepResult(passed=False, error="No tag key configured")
        
        try:
            # Remove tag from entity
            # TODO: Integrate with TagsManager
            logger.info(f"Removing tag {key} from {context.entity_type} {context.entity_id}")
            
            # Update entity tags in context
            if 'tags' in context.entity and key in context.entity['tags']:
                del context.entity['tags'][key]
            
            return StepResult(
                passed=True,
                message=f"Removed tag {key}",
                data={'key': key}
            )
        except Exception as e:
            logger.exception(f"Remove tag step failed: {e}")
            return StepResult(passed=False, error=str(e))


class ConditionalStepHandler(StepHandler):
    """Handler for conditional branching steps."""

    def execute(self, context: StepContext) -> StepResult:
        from src.common.compliance_dsl import Lexer, Parser, Evaluator
        
        condition = self._config.get('condition', '')
        if not condition:
            return StepResult(passed=False, error="No condition configured")
        
        try:
            # Parse and evaluate condition
            lexer = Lexer(condition)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            ast = parser.parse_expression()
            evaluator = Evaluator(context.entity)
            result = evaluator.evaluate(ast)
            
            return StepResult(
                passed=bool(result),
                message=f"Condition evaluated to: {result}",
                data={'condition': condition, 'result': result}
            )
        except Exception as e:
            logger.exception(f"Conditional step failed: {e}")
            return StepResult(passed=False, error=str(e))


class ScriptStepHandler(StepHandler):
    """Handler for script execution steps."""

    def execute(self, context: StepContext) -> StepResult:
        language = self._config.get('language', 'python')
        code = self._config.get('code', '')
        timeout_seconds = self._config.get('timeout_seconds', 60)
        
        if not code:
            return StepResult(passed=False, error="No code configured")
        
        try:
            if language == 'python':
                result = self._execute_python(code, context, timeout_seconds)
            elif language == 'sql':
                result = self._execute_sql(code, context, timeout_seconds)
            else:
                return StepResult(passed=False, error=f"Unsupported language: {language}")
            
            return result
        except Exception as e:
            logger.exception(f"Script step failed: {e}")
            return StepResult(passed=False, error=str(e))

    def _execute_python(self, code: str, context: StepContext, timeout: int) -> StepResult:
        """Execute Python code in a sandboxed environment."""
        # Build safe context
        safe_globals = {
            'entity': context.entity.copy(),
            'entity_type': context.entity_type,
            'entity_id': context.entity_id,
            'entity_name': context.entity_name,
            'user_email': context.user_email,
            'step_results': context.step_results.copy(),
        }
        
        local_vars: Dict[str, Any] = {}
        
        try:
            # Execute with timeout would require threading/subprocess
            # For now, simple exec with limited builtins
            exec(code, {'__builtins__': {}}, local_vars)
            
            result = local_vars.get('result', {'passed': True})
            if isinstance(result, dict):
                return StepResult(
                    passed=result.get('passed', True),
                    message=result.get('message'),
                    data=result.get('data'),
                )
            else:
                return StepResult(passed=bool(result))
        except Exception as e:
            return StepResult(passed=False, error=str(e))

    def _execute_sql(self, code: str, context: StepContext, timeout: int) -> StepResult:
        """Execute SQL code (placeholder - needs proper implementation)."""
        # TODO: Implement SQL execution via workspace client
        logger.warning("SQL execution not yet implemented")
        return StepResult(
            passed=True,
            message="SQL execution not yet implemented",
            data={'sql': code}
        )


class PassStepHandler(StepHandler):
    """Handler for terminal success steps."""

    def execute(self, context: StepContext) -> StepResult:
        return StepResult(passed=True, message="Workflow completed successfully")


class FailStepHandler(StepHandler):
    """Handler for terminal failure steps."""

    def execute(self, context: StepContext) -> StepResult:
        message = self._config.get('message', 'Workflow failed')
        return StepResult(passed=False, message=message)


class DeliveryStepHandler(StepHandler):
    """Handler for delivery steps - triggers change delivery via DeliveryService.
    
    Config options:
        change_type: Type of change (grant, revoke, tag_assign, etc.)
        modes: Optional list of delivery modes (direct, indirect, manual)
                If not specified, uses configured defaults
    """

    def execute(self, context: StepContext) -> StepResult:
        from src.controller.delivery_service import (
            get_delivery_service, 
            DeliveryPayload, 
            DeliveryChangeType,
            DeliveryMode,
        )
        
        change_type_str = self._config.get('change_type', 'grant')
        modes_str = self._config.get('modes', [])  # Empty = use defaults
        
        try:
            # Parse change type
            try:
                change_type = DeliveryChangeType(change_type_str)
            except ValueError:
                change_type = DeliveryChangeType.GRANT  # Default
            
            # Parse modes if specified
            modes = None
            if modes_str:
                modes = []
                for m in modes_str:
                    try:
                        modes.append(DeliveryMode(m))
                    except ValueError:
                        logger.warning(f"Unknown delivery mode: {m}")
            
            # Build payload from context
            payload = DeliveryPayload(
                change_type=change_type,
                entity_type=context.entity_type,
                entity_id=context.entity_id,
                data={
                    'entity': context.entity,
                    **self._config.get('data', {}),
                },
                user=context.user_email,
            )
            
            # Get delivery service and execute
            try:
                delivery_service = get_delivery_service()
            except RuntimeError:
                return StepResult(
                    passed=False,
                    error="Delivery service not initialized"
                )
            
            results = delivery_service.deliver(payload, modes=modes)
            
            if results.all_success:
                return StepResult(
                    passed=True,
                    message=f"Delivered via {len(results.results)} mode(s)",
                    data=results.to_dict()
                )
            elif results.any_success:
                return StepResult(
                    passed=True,
                    message=f"Partially delivered ({len([r for r in results.results if r.success])}/{len(results.results)} modes succeeded)",
                    data=results.to_dict()
                )
            else:
                return StepResult(
                    passed=False,
                    error="; ".join(results.errors) if results.errors else "All delivery modes failed",
                    data=results.to_dict()
                )
                
        except Exception as e:
            logger.exception(f"Delivery step failed: {e}")
            return StepResult(passed=False, error=str(e))


class PolicyCheckStepHandler(StepHandler):
    """Handler for policy check steps - evaluates existing compliance policy by UUID."""

    def execute(self, context: StepContext) -> StepResult:
        from src.db_models.compliance import CompliancePolicyDb
        from src.common.compliance_dsl import evaluate_rule_on_object
        
        policy_id = self._config.get('policy_id', '')
        if not policy_id:
            return StepResult(passed=False, error="No policy_id configured")
        
        try:
            # Look up policy by UUID
            policy = self._db.get(CompliancePolicyDb, policy_id)
            if not policy:
                return StepResult(
                    passed=False, 
                    error=f"Policy not found: {policy_id}",
                    data={'policy_id': policy_id}
                )
            
            # Skip inactive policies (treated as pass)
            if not policy.is_active:
                return StepResult(
                    passed=True, 
                    message=f"Policy '{policy.name}' is inactive, skipped",
                    data={'policy_id': policy_id, 'policy_name': policy.name, 'skipped': True}
                )
            
            # Evaluate the policy's rule against the entity
            passed, technical_message = evaluate_rule_on_object(policy.rule, context.entity)
            
            # Combine human-readable failure message with technical details
            if passed:
                message = technical_message
            else:
                # Show human-readable message first, then technical details
                if policy.failure_message:
                    message = f"{policy.failure_message}\n\nTechnical: {technical_message}"
                else:
                    message = technical_message
            
            return StepResult(
                passed=passed,
                message=message,
                data={
                    'policy_id': policy_id, 
                    'policy_name': policy.name, 
                    'rule': policy.rule,
                    'severity': policy.severity,
                    'failure_message': policy.failure_message,
                    'technical_message': technical_message,
                }
            )
        except Exception as e:
            logger.exception(f"Policy check step failed: {e}")
            return StepResult(
                passed=False, 
                error=str(e),
                data={'policy_id': policy_id}
            )


class WorkflowExecutor:
    """Executes process workflows."""

    # Step handler registry
    HANDLERS: Dict[str, type] = {
        'validation': ValidationStepHandler,
        'approval': ApprovalStepHandler,
        'notification': NotificationStepHandler,
        'assign_tag': AssignTagStepHandler,
        'remove_tag': RemoveTagStepHandler,
        'conditional': ConditionalStepHandler,
        'script': ScriptStepHandler,
        'pass': PassStepHandler,
        'fail': FailStepHandler,
        'policy_check': PolicyCheckStepHandler,
        'delivery': DeliveryStepHandler,
    }

    def __init__(self, db: Session):
        self._db = db

    def execute_workflow(
        self,
        workflow: ProcessWorkflow,
        entity: Dict[str, Any],
        *,
        entity_type: str,
        entity_id: str,
        entity_name: Optional[str] = None,
        user_email: Optional[str] = None,
        trigger_context: Optional[TriggerContext] = None,
        blocking: bool = True,
    ) -> WorkflowExecution:
        """Execute a workflow against an entity.
        
        Args:
            workflow: Workflow to execute
            entity: Entity data dictionary
            entity_type: Type of entity
            entity_id: Entity identifier
            entity_name: Entity name (optional)
            user_email: User who triggered the workflow
            trigger_context: Full trigger context
            blocking: If True, run synchronously; if False, queue for async execution
            
        Returns:
            WorkflowExecution with results
        """
        # Create execution record
        execution_create = WorkflowExecutionCreate(
            workflow_id=workflow.id,
            trigger_context=trigger_context,
            triggered_by=user_email,
        )
        db_execution = workflow_execution_repo.create(self._db, execution_create)
        
        # Build step context
        context = StepContext(
            entity=entity.copy(),
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            user_email=user_email,
            trigger_context=trigger_context,
            execution_id=db_execution.id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            step_results={},
        )
        
        # Build step lookup
        steps_by_id = {s.step_id: s for s in workflow.steps}
        
        # Execute steps
        success_count = 0
        failure_count = 0
        current_step_id = workflow.steps[0].step_id if workflow.steps else None
        final_status = ExecutionStatus.RUNNING
        error_message = None
        
        while current_step_id:
            step = steps_by_id.get(current_step_id)
            if not step:
                error_message = f"Step not found: {current_step_id}"
                final_status = ExecutionStatus.FAILED
                break
            
            # Execute step
            start_time = time.time()
            result = self._execute_step(step, context)
            duration_ms = (time.time() - start_time) * 1000
            
            # Record step execution
            step_status = StepExecutionStatus.SUCCEEDED if result.passed else StepExecutionStatus.FAILED
            workflow_execution_repo.add_step_execution(
                self._db,
                execution_id=db_execution.id,
                step_id=step.id,
                status=step_status.value,
                passed=result.passed,
                result_data=result.data,
                error_message=result.error,
                duration_ms=duration_ms,
            )
            
            # Store result in context for subsequent steps
            context.step_results[step.step_id] = {
                'passed': result.passed,
                'message': result.message,
                'data': result.data,
            }
            
            # Update counters
            if result.passed:
                success_count += 1
            else:
                failure_count += 1
            
            # Check for blocking step (e.g., approval)
            if result.blocking:
                final_status = ExecutionStatus.PAUSED
                workflow_execution_repo.update_status(
                    self._db,
                    db_execution.id,
                    status=final_status.value,
                    current_step_id=current_step_id,
                    success_count=success_count,
                    failure_count=failure_count,
                )
                break
            
            # Determine next step
            if result.passed:
                current_step_id = step.on_pass
            else:
                current_step_id = step.on_fail
            
            # If no next step, we're done
            if not current_step_id:
                if result.passed:
                    final_status = ExecutionStatus.SUCCEEDED
                else:
                    final_status = ExecutionStatus.FAILED
                    error_message = result.message or result.error
        
        # Finalize execution
        if final_status != ExecutionStatus.PAUSED:
            workflow_execution_repo.update_status(
                self._db,
                db_execution.id,
                status=final_status.value,
                success_count=success_count,
                failure_count=failure_count,
                error_message=error_message,
                finished_at=datetime.utcnow().isoformat(),
            )
        
        # Return execution with results
        db_execution = workflow_execution_repo.get(self._db, db_execution.id)
        return self._db_to_model(db_execution, workflow.name)

    def resume_workflow(
        self,
        execution_id: str,
        step_result: bool,
        *,
        result_data: Optional[Dict[str, Any]] = None,
        user_email: Optional[str] = None,
    ) -> Optional[WorkflowExecution]:
        """Resume a paused workflow after approval/external action.
        
        When a workflow pauses at a blocking step (e.g., approval), this method
        resumes execution from where it left off, using the step_result to
        determine which branch (on_pass or on_fail) to follow.
        
        Args:
            execution_id: ID of paused execution
            step_result: Result of the paused step (True=approved, False=rejected)
            result_data: Additional result data from the approval response
            user_email: Email of user who responded to the approval
            
        Returns:
            Updated WorkflowExecution, or None if execution not found/not paused
        """
        db_execution = workflow_execution_repo.get(self._db, execution_id)
        if not db_execution or db_execution.status != 'paused':
            logger.warning(f"Cannot resume workflow {execution_id}: not found or not paused")
            return None
        
        # Get workflow
        from src.repositories.process_workflows_repository import process_workflow_repo
        db_workflow = process_workflow_repo.get(self._db, db_execution.workflow_id)
        if not db_workflow:
            logger.error(f"Workflow {db_execution.workflow_id} not found for execution {execution_id}")
            return None
        
        # Convert to ProcessWorkflow model
        from src.controller.workflows_manager import WorkflowsManager
        workflows_manager = WorkflowsManager(self._db)
        workflow = workflows_manager._db_to_model(db_workflow)
        
        # Build step lookup
        steps_by_id = {s.step_id: s for s in workflow.steps}
        
        # Find the current (paused) step
        current_step_id = db_execution.current_step_id
        if not current_step_id or current_step_id not in steps_by_id:
            logger.error(f"Current step {current_step_id} not found in workflow")
            return None
        
        current_step = steps_by_id[current_step_id]
        
        # Record the approval result for the paused step
        workflow_execution_repo.add_step_execution(
            self._db,
            execution_id=execution_id,
            step_id=current_step.id,
            status=StepExecutionStatus.SUCCEEDED.value if step_result else StepExecutionStatus.FAILED.value,
            passed=step_result,
            result_data={
                'approval_result': 'approved' if step_result else 'rejected',
                'responded_by': user_email,
                **(result_data or {}),
            },
            error_message=None if step_result else (result_data or {}).get('reason', 'Request denied'),
            duration_ms=0,  # Approval duration not tracked this way
        )
        
        # Determine next step based on approval result
        next_step_id = current_step.on_pass if step_result else current_step.on_fail
        
        logger.info(
            f"Resuming workflow {execution_id} from step '{current_step_id}' "
            f"({'approved' if step_result else 'rejected'}) -> next step: {next_step_id}"
        )
        
        # Rebuild trigger context
        trigger_context = None
        if db_execution.trigger_context:
            try:
                tc_data = json.loads(db_execution.trigger_context)
                trigger_context = TriggerContext(**tc_data)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Rebuild step context from execution
        # Get entity data from trigger context or create minimal context
        entity_data = {}
        if trigger_context and trigger_context.entity_data:
            entity_data = trigger_context.entity_data
        
        context = StepContext(
            entity=entity_data.copy(),
            entity_type=trigger_context.entity_type if trigger_context else 'unknown',
            entity_id=trigger_context.entity_id if trigger_context else execution_id,
            entity_name=trigger_context.entity_name if trigger_context else None,
            user_email=user_email or (trigger_context.user_email if trigger_context else None),
            trigger_context=trigger_context,
            execution_id=execution_id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            step_results={current_step_id: {
                'passed': step_result,
                'message': 'approved' if step_result else 'rejected',
                'data': result_data,
            }},
        )
        
        # Continue execution from next step
        success_count = db_execution.success_count
        failure_count = db_execution.failure_count
        
        # Count the approval step
        if step_result:
            success_count += 1
        else:
            failure_count += 1
        
        final_status = ExecutionStatus.RUNNING
        error_message = None
        
        while next_step_id:
            step = steps_by_id.get(next_step_id)
            if not step:
                error_message = f"Step not found: {next_step_id}"
                final_status = ExecutionStatus.FAILED
                break
            
            # Execute step
            start_time = time.time()
            result = self._execute_step(step, context)
            duration_ms = (time.time() - start_time) * 1000
            
            # Record step execution
            step_status = StepExecutionStatus.SUCCEEDED if result.passed else StepExecutionStatus.FAILED
            workflow_execution_repo.add_step_execution(
                self._db,
                execution_id=execution_id,
                step_id=step.id,
                status=step_status.value,
                passed=result.passed,
                result_data=result.data,
                error_message=result.error,
                duration_ms=duration_ms,
            )
            
            # Store result in context for subsequent steps
            context.step_results[step.step_id] = {
                'passed': result.passed,
                'message': result.message,
                'data': result.data,
            }
            
            # Update counters
            if result.passed:
                success_count += 1
            else:
                failure_count += 1
            
            # Check for another blocking step
            if result.blocking:
                final_status = ExecutionStatus.PAUSED
                workflow_execution_repo.update_status(
                    self._db,
                    execution_id,
                    status=final_status.value,
                    current_step_id=next_step_id,
                    success_count=success_count,
                    failure_count=failure_count,
                )
                break
            
            # Determine next step
            if result.passed:
                next_step_id = step.on_pass
            else:
                next_step_id = step.on_fail
            
            # If no next step, we're done
            if not next_step_id:
                if result.passed:
                    final_status = ExecutionStatus.SUCCEEDED
                else:
                    final_status = ExecutionStatus.FAILED
                    error_message = result.message or result.error
        
        # Finalize execution if not paused again
        if final_status != ExecutionStatus.PAUSED:
            workflow_execution_repo.update_status(
                self._db,
                execution_id,
                status=final_status.value,
                current_step_id=None,
                success_count=success_count,
                failure_count=failure_count,
                error_message=error_message,
                finished_at=datetime.utcnow().isoformat(),
            )
            
            # Handle entity status updates based on workflow outcome
            self._handle_workflow_completion(
                trigger_context=trigger_context,
                workflow=workflow,
                succeeded=(final_status == ExecutionStatus.SUCCEEDED),
            )
        
        # Return updated execution
        db_execution = workflow_execution_repo.get(self._db, execution_id)
        return self._db_to_model(db_execution, workflow.name)

    def _handle_workflow_completion(
        self,
        trigger_context: Optional[TriggerContext],
        workflow: ProcessWorkflow,
        succeeded: bool,
    ) -> None:
        """Handle entity status updates when a workflow completes.
        
        Based on the trigger type and entity type, update the entity's status
        to reflect the workflow outcome (e.g., dataset -> "active" on approval).
        """
        if not trigger_context:
            return
        
        entity_type = trigger_context.entity_type
        entity_id = trigger_context.entity_id
        trigger_type = workflow.trigger.trigger_type if workflow.trigger else None
        
        if not entity_type or not entity_id or not trigger_type:
            return
        
        try:
            # Handle dataset review completion
            if entity_type == 'dataset' and trigger_type in ('on_request_review', 'ON_REQUEST_REVIEW'):
                from src.repositories.datasets_repository import dataset_repo
                db_dataset = dataset_repo.get(db=self._db, id=entity_id)
                if db_dataset:
                    if succeeded:
                        db_dataset.status = 'active'
                        logger.info(f"Dataset {entity_id} status updated to 'active' after review approval")
                    else:
                        # Revert to draft on rejection
                        db_dataset.status = 'draft'
                        logger.info(f"Dataset {entity_id} status reverted to 'draft' after review rejection")
                    self._db.commit()
                    
            # Handle data contract deploy completion
            elif entity_type == 'data_contract' and trigger_type in ('on_request_publish', 'ON_REQUEST_PUBLISH'):
                from src.repositories.data_contracts_repository import data_contract_repo
                db_contract = data_contract_repo.get(db=self._db, id=entity_id)
                if db_contract:
                    if succeeded:
                        db_contract.status = 'deployed'
                        logger.info(f"Data contract {entity_id} status updated to 'deployed' after approval")
                    else:
                        db_contract.status = 'draft'
                        logger.info(f"Data contract {entity_id} status reverted to 'draft' after rejection")
                    self._db.commit()
                    
            # Handle data product activation completion
            elif entity_type == 'data_product' and trigger_type in ('on_request_review', 'ON_REQUEST_REVIEW'):
                from src.repositories.data_products_repository import data_product_repo
                db_product = data_product_repo.get(db=self._db, id=entity_id)
                if db_product:
                    if succeeded:
                        db_product.status = 'active'
                        logger.info(f"Data product {entity_id} status updated to 'active' after approval")
                    else:
                        db_product.status = 'draft'
                        logger.info(f"Data product {entity_id} status reverted to 'draft' after rejection")
                    self._db.commit()
                    
        except Exception as e:
            logger.error(f"Error updating entity status after workflow completion: {e}", exc_info=True)
            # Don't fail the workflow for status update issues
    
    def _execute_step(self, step: WorkflowStep, context: StepContext) -> StepResult:
        """Execute a single step."""
        step_type = step.step_type.value if hasattr(step.step_type, 'value') else step.step_type
        handler_class = self.HANDLERS.get(step_type)
        
        if not handler_class:
            return StepResult(passed=False, error=f"Unknown step type: {step_type}")
        
        try:
            handler = handler_class(self._db, step.config or {})
            return handler.execute(context)
        except Exception as e:
            logger.exception(f"Step execution failed: {e}")
            return StepResult(passed=False, error=str(e))

    def _db_to_model(self, db_execution: WorkflowExecutionDb, workflow_name: str) -> WorkflowExecution:
        """Convert database execution to model."""
        trigger_context = None
        if db_execution.trigger_context:
            try:
                tc_data = json.loads(db_execution.trigger_context)
                trigger_context = TriggerContext(**tc_data)
            except (json.JSONDecodeError, TypeError):
                pass
        
        step_executions = []
        for se in db_execution.step_executions:
            step_executions.append(WorkflowStepExecutionResult(
                id=se.id,
                step_id=se.step_id,
                status=StepExecutionStatus(se.status),
                passed=se.passed,
                result_data=json.loads(se.result_data) if se.result_data else None,
                error_message=se.error_message,
                duration_ms=se.duration_ms,
                started_at=se.started_at,
                finished_at=se.finished_at,
            ))
        
        return WorkflowExecution(
            id=db_execution.id,
            workflow_id=db_execution.workflow_id,
            trigger_context=trigger_context,
            status=ExecutionStatus(db_execution.status),
            current_step_id=db_execution.current_step_id,
            success_count=db_execution.success_count,
            failure_count=db_execution.failure_count,
            error_message=db_execution.error_message,
            started_at=db_execution.started_at,
            finished_at=db_execution.finished_at,
            triggered_by=db_execution.triggered_by,
            step_executions=step_executions,
            workflow_name=workflow_name,
        )

