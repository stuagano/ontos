import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  Zap,
  Shield,
  UserCheck,
  Bell,
  Tag,
  Code,
  CheckCircle,
  XCircle,
  ClipboardCheck,
  Truck,
  GitBranch,
} from 'lucide-react';
import type { WorkflowStep, WorkflowTrigger, StepType } from '@/types/process-workflow';
import { 
  getTriggerTypeLabel, 
  getEntityTypeLabel,
  getStepIcon,
  getStepColor,
  resolveRecipientDisplay,
  STEP_ICONS,
  STEP_COLORS,
} from '@/lib/workflow-labels';

// Base node styles - fixed width for consistent compact sizing
const baseNodeClass = "rounded-lg shadow-md border-2 w-[180px] transition-all hover:shadow-lg";

// Trigger Node
interface TriggerNodeData {
  trigger: WorkflowTrigger;
}

export const TriggerNode = memo(({ data, selected }: NodeProps<TriggerNodeData>) => {
  const { t } = useTranslation(['common']);
  const trigger = data.trigger;

  return (
    <Card className={`${baseNodeClass} border-purple-500 bg-purple-50 dark:bg-purple-950/30 ${selected ? 'ring-2 ring-purple-500' : ''}`}>
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Zap className="h-4 w-4 text-purple-500" />
          {t('common:labels.type')}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <div className="text-xs text-muted-foreground">
          {getTriggerTypeLabel(trigger.type, t)}
        </div>
        <div className="flex flex-wrap gap-1 mt-1">
          {trigger.entity_types.slice(0, 3).map(et => (
            <Badge key={et} variant="secondary" className="text-xs px-1 py-0">
              {getEntityTypeLabel(et, t)}
            </Badge>
          ))}
          {trigger.entity_types.length > 3 && (
            <Badge variant="secondary" className="text-xs px-1 py-0">
              +{trigger.entity_types.length - 3}
            </Badge>
          )}
        </div>
      </CardContent>
      <Handle type="source" position={Position.Bottom} className="!bg-purple-500" />
    </Card>
  );
});
TriggerNode.displayName = 'TriggerNode';

// Base Step Node Component
interface StepNodeData {
  step: WorkflowStep;
  rolesMap?: Record<string, string>;  // UUID -> name mapping for display
}

const StepNodeBase = memo(({ 
  data, 
  selected, 
  icon: Icon, 
  color, 
  hasPassHandle = true,
  hasFailHandle = true,
}: NodeProps<StepNodeData> & { 
  icon: React.ElementType;
  color: string;
  hasPassHandle?: boolean;
  hasFailHandle?: boolean;
}) => {
  const step = data.step;
  
  return (
    <Card className={`${baseNodeClass} border-${color}-500 bg-${color}-50 dark:bg-${color}-950/30 ${selected ? `ring-2 ring-${color}-500` : ''}`}
      style={{ borderColor: `var(--${color}-500, #6b7280)` }}>
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Icon className={`h-4 w-4 text-${color}-500`} />
          {step.name || step.step_type}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <Badge variant="outline" className="text-xs">
          {step.step_type.replace('_', ' ')}
        </Badge>
        {step.config && Object.keys(step.config).length > 0 && (
          <div className="text-xs text-muted-foreground mt-1 truncate max-w-[140px]">
            {JSON.stringify(step.config).slice(0, 30)}...
          </div>
        )}
      </CardContent>
      {hasPassHandle && (
        <Handle 
          type="source" 
          position={Position.Bottom} 
          id="pass" 
          className="!bg-green-500"
          style={{ left: hasFailHandle ? '30%' : '50%' }}
        />
      )}
      {hasFailHandle && (
        <Handle 
          type="source" 
          position={Position.Bottom} 
          id="fail" 
          className="!bg-red-500"
          style={{ left: '70%' }}
        />
      )}
    </Card>
  );
});
StepNodeBase.displayName = 'StepNodeBase';

// Validation Node
export const ValidationNode = memo((props: NodeProps<StepNodeData>) => (
  <Card className={`${baseNodeClass} border-blue-500 bg-blue-50 dark:bg-blue-950/30 ${props.selected ? 'ring-2 ring-blue-500' : ''}`}>
    <Handle type="target" position={Position.Top} className="!bg-gray-400" />
    <CardHeader className="p-3 pb-2">
      <CardTitle className="text-sm flex items-center gap-2">
        <Shield className="h-4 w-4 text-blue-500" />
        {props.data.step.name || 'Validation'}
      </CardTitle>
    </CardHeader>
    <CardContent className="p-3 pt-0">
      <Badge variant="outline" className="text-xs">validation</Badge>
      {(props.data.step.config as { rule?: string })?.rule && (
        <div className="text-xs text-muted-foreground mt-1 truncate max-w-[140px] font-mono">
          {((props.data.step.config as { rule?: string }).rule || '').slice(0, 25)}...
        </div>
      )}
    </CardContent>
    <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" style={{ left: '30%' }} />
    <Handle type="source" position={Position.Bottom} id="fail" className="!bg-red-500" style={{ left: '70%' }} />
  </Card>
));
ValidationNode.displayName = 'ValidationNode';

// Approval Node
export const ApprovalNode = memo((props: NodeProps<StepNodeData>) => {
  const approversValue = (props.data.step.config as { approvers?: string })?.approvers;
  const displayName = resolveRecipientDisplay(approversValue, props.data.rolesMap || {});
  
  return (
    <Card className={`${baseNodeClass} border-amber-500 bg-amber-50 dark:bg-amber-950/30 ${props.selected ? 'ring-2 ring-amber-500' : ''}`}>
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <UserCheck className="h-4 w-4 text-amber-500" />
          {props.data.step.name || 'Approval'}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <Badge variant="outline" className="text-xs">approval</Badge>
        {approversValue && (
          <div className="text-xs text-muted-foreground mt-1">
            {displayName}
          </div>
        )}
      </CardContent>
      <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" style={{ left: '30%' }} />
      <Handle type="source" position={Position.Bottom} id="fail" className="!bg-red-500" style={{ left: '70%' }} />
    </Card>
  );
});
ApprovalNode.displayName = 'ApprovalNode';

// Notification Node
export const NotificationNode = memo((props: NodeProps<StepNodeData>) => {
  const recipientsValue = (props.data.step.config as { recipients?: string })?.recipients;
  const displayName = resolveRecipientDisplay(recipientsValue, props.data.rolesMap || {});
  
  return (
    <Card className={`${baseNodeClass} border-cyan-500 bg-cyan-50 dark:bg-cyan-950/30 ${props.selected ? 'ring-2 ring-cyan-500' : ''}`}>
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Bell className="h-4 w-4 text-cyan-500" />
          {props.data.step.name || 'Notification'}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <Badge variant="outline" className="text-xs">notification</Badge>
        {recipientsValue && (
          <div className="text-xs text-muted-foreground mt-1">
            To: {displayName}
          </div>
        )}
      </CardContent>
      <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" />
    </Card>
  );
});
NotificationNode.displayName = 'NotificationNode';

// Assign Tag Node
export const AssignTagNode = memo((props: NodeProps<StepNodeData>) => (
  <Card className={`${baseNodeClass} border-teal-500 bg-teal-50 dark:bg-teal-950/30 ${props.selected ? 'ring-2 ring-teal-500' : ''}`}>
    <Handle type="target" position={Position.Top} className="!bg-gray-400" />
    <CardHeader className="p-3 pb-2">
      <CardTitle className="text-sm flex items-center gap-2">
        <Tag className="h-4 w-4 text-teal-500" />
        {props.data.step.name || 'Assign Tag'}
      </CardTitle>
    </CardHeader>
    <CardContent className="p-3 pt-0">
      <Badge variant="outline" className="text-xs">assign_tag</Badge>
      {(props.data.step.config as { key?: string })?.key && (
        <div className="text-xs text-muted-foreground mt-1">
          Key: {(props.data.step.config as { key?: string }).key}
        </div>
      )}
    </CardContent>
    <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" />
  </Card>
));
AssignTagNode.displayName = 'AssignTagNode';

// Conditional Node
export const ConditionalNode = memo((props: NodeProps<StepNodeData>) => (
  <Card className={`${baseNodeClass} border-violet-500 bg-violet-50 dark:bg-violet-950/30 ${props.selected ? 'ring-2 ring-violet-500' : ''}`}>
    <Handle type="target" position={Position.Top} className="!bg-gray-400" />
    <CardHeader className="p-3 pb-2">
      <CardTitle className="text-sm flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-violet-500" />
        {props.data.step.name || 'Conditional'}
      </CardTitle>
    </CardHeader>
    <CardContent className="p-3 pt-0">
      <Badge variant="outline" className="text-xs">conditional</Badge>
      {(props.data.step.config as { condition?: string })?.condition && (
        <div className="text-xs text-muted-foreground mt-1 truncate max-w-[140px] font-mono">
          {((props.data.step.config as { condition?: string }).condition || '').slice(0, 25)}...
        </div>
      )}
    </CardContent>
    <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" style={{ left: '30%' }} />
    <Handle type="source" position={Position.Bottom} id="fail" className="!bg-red-500" style={{ left: '70%' }} />
  </Card>
));
ConditionalNode.displayName = 'ConditionalNode';

// Script Node
export const ScriptNode = memo((props: NodeProps<StepNodeData>) => (
  <Card className={`${baseNodeClass} border-slate-500 bg-slate-50 dark:bg-slate-950/30 ${props.selected ? 'ring-2 ring-slate-500' : ''}`}>
    <Handle type="target" position={Position.Top} className="!bg-gray-400" />
    <CardHeader className="p-3 pb-2">
      <CardTitle className="text-sm flex items-center gap-2">
        <Code className="h-4 w-4 text-slate-500" />
        {props.data.step.name || 'Script'}
      </CardTitle>
    </CardHeader>
    <CardContent className="p-3 pt-0">
      <Badge variant="outline" className="text-xs">
        {(props.data.step.config as { language?: string })?.language || 'script'}
      </Badge>
    </CardContent>
    <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" style={{ left: '30%' }} />
    <Handle type="source" position={Position.Bottom} id="fail" className="!bg-red-500" style={{ left: '70%' }} />
  </Card>
));
ScriptNode.displayName = 'ScriptNode';

// End Node (Pass/Fail)
export const EndNode = memo((props: NodeProps<StepNodeData>) => {
  const isPass = props.data.step.step_type === 'pass';
  const Icon = isPass ? CheckCircle : XCircle;
  const color = isPass ? 'green' : 'red';
  
  return (
    <Card className={`${baseNodeClass} border-${color}-500 bg-${color}-50 dark:bg-${color}-950/30 ${props.selected ? `ring-2 ring-${color}-500` : ''}`}
      style={{ borderColor: isPass ? '#22c55e' : '#ef4444' }}>
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Icon className={`h-4 w-4 ${isPass ? 'text-green-500' : 'text-red-500'}`} />
          {props.data.step.name || (isPass ? 'Success' : 'Failure')}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <Badge variant={isPass ? 'default' : 'destructive'} className="text-xs">
          {isPass ? 'pass' : 'fail'}
        </Badge>
        {!isPass && (props.data.step.config as { message?: string })?.message && (
          <div className="text-xs text-muted-foreground mt-1">
            {(props.data.step.config as { message?: string }).message}
          </div>
        )}
      </CardContent>
    </Card>
  );
});
EndNode.displayName = 'EndNode';

// Policy Check Node
export const PolicyCheckNode = memo((props: NodeProps<StepNodeData>) => {
  const policyName = (props.data.step.config as { policy_name?: string })?.policy_name;
  const policyId = (props.data.step.config as { policy_id?: string })?.policy_id;
  
  return (
    <Card className={`${baseNodeClass} border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30 ${props.selected ? 'ring-2 ring-indigo-500' : ''}`}>
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <ClipboardCheck className="h-4 w-4 text-indigo-500" />
          {props.data.step.name || 'Policy Check'}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <Badge variant="outline" className="text-xs">policy_check</Badge>
        {policyName && (
          <div className="text-xs text-muted-foreground mt-1">
            Policy: {policyName}
          </div>
        )}
        {!policyName && policyId && (
          <div className="text-xs text-muted-foreground mt-1 truncate max-w-[140px]">
            ID: {policyId.slice(0, 8)}...
          </div>
        )}
        {!policyName && !policyId && (
          <div className="text-xs text-amber-500 mt-1">
            No policy selected
          </div>
        )}
      </CardContent>
      <Handle type="source" position={Position.Bottom} id="pass" className="!bg-green-500" style={{ left: '30%' }} />
      <Handle type="source" position={Position.Bottom} id="fail" className="!bg-red-500" style={{ left: '70%' }} />
    </Card>
  );
});
PolicyCheckNode.displayName = 'PolicyCheckNode';

