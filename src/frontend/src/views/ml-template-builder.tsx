import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ListViewSkeleton } from '@/components/common/list-view-skeleton';
import { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import { RelativeDate } from '@/components/common/relative-date';
import { useApi } from '@/hooks/use-api';
import { useToast } from "@/hooks/use-toast";
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import {
  PromptTemplate,
  PromptTemplateCreate,
  TemplateStatus,
  LabelType,
  TEMPLATE_STATUS_COLORS,
} from '@/types/training-data';
import {
  Wand2,
  Plus,
  Trash2,
  Save,
  Loader2,
  Database,
  FileText,
  Play,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Eye,
} from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

interface OutputField {
  id: string;
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  description: string;
  required: boolean;
}

// Helper function for API response checking
type CheckApiResponseFn = <T>(
  response: { data?: T | { detail?: string }, error?: string | null | undefined },
  name: string
) => T;

const checkApiResponse: CheckApiResponseFn = (response, name) => {
  if (response.error) {
    throw new Error(`${name} fetch failed: ${response.error}`);
  }
  if (response.data && typeof response.data === 'object' && 'detail' in response.data && typeof response.data.detail === 'string') {
    throw new Error(`${name} fetch failed: ${response.data.detail}`);
  }
  if (response.data === null || response.data === undefined) {
    throw new Error(`${name} fetch returned null or undefined data.`);
  }
  return response.data as T;
};

// =============================================================================
// Preview Panel
// =============================================================================

function PreviewPanel({ systemPrompt, userPrompt, outputFields }: {
  systemPrompt: string;
  userPrompt: string;
  outputFields: OutputField[];
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 bg-muted flex items-center justify-between text-left"
      >
        <span className="font-medium text-sm flex items-center gap-2">
          <Play className="h-4 w-4" />
          Live Preview
        </span>
        {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>

      {expanded && (
        <div className="p-4 space-y-3">
          {systemPrompt && (
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">System Prompt</div>
              <div className="p-3 bg-gray-900 text-gray-100 rounded text-sm font-mono whitespace-pre-wrap">
                {systemPrompt}
              </div>
            </div>
          )}
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">User Prompt Template</div>
            <div className="p-3 bg-blue-900 text-blue-100 rounded text-sm font-mono whitespace-pre-wrap">
              {userPrompt || <span className="text-blue-400 italic">Enter a prompt template...</span>}
            </div>
          </div>
          {outputFields.length > 0 && (
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">Output Schema</div>
              <div className="p-3 bg-purple-900 text-purple-100 rounded text-sm font-mono">
                {`{\n${outputFields.map((f) => `  "${f.name}": <${f.type}>${f.required ? '' : '?'}`).join(',\n')}\n}`}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Output Field Editor
// =============================================================================

function OutputFieldRow({ field, onChange, onDelete }: {
  field: OutputField;
  onChange: (f: OutputField) => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-start gap-3 p-3 bg-muted rounded-lg">
      <div className="flex-1 grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Field Name</Label>
          <Input
            value={field.name}
            onChange={(e) => onChange({ ...field, name: e.target.value })}
            placeholder="field_name"
            className="font-mono text-sm mt-1"
          />
        </div>
        <div>
          <Label className="text-xs">Type</Label>
          <Select value={field.type} onValueChange={(v) => onChange({ ...field, type: v as OutputField['type'] })}>
            <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="string">String</SelectItem>
              <SelectItem value="number">Number</SelectItem>
              <SelectItem value="boolean">Boolean</SelectItem>
              <SelectItem value="array">Array</SelectItem>
              <SelectItem value="object">Object</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="col-span-2">
          <Label className="text-xs">Description</Label>
          <Input
            value={field.description}
            onChange={(e) => onChange({ ...field, description: e.target.value })}
            placeholder="What this field represents..."
            className="mt-1"
          />
        </div>
      </div>
      <div className="flex flex-col items-center gap-2 pt-5">
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={field.required}
            onChange={(e) => onChange({ ...field, required: e.target.checked })}
            className="rounded"
          />
          Required
        </label>
        <Button variant="ghost" size="icon" onClick={onDelete} className="h-7 w-7">
          <Trash2 className="h-3.5 w-3.5 text-destructive" />
        </Button>
      </div>
    </div>
  );
}

// =============================================================================
// Template Form Dialog
// =============================================================================

function TemplateFormDialog({ open, onOpenChange, template, onSaved }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template: PromptTemplate | null;
  onSaved: () => void;
}) {
  const { get, post, put } = useApi();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('You are an expert assistant helping with data analysis and classification.');
  const [userPromptTemplate, setUserPromptTemplate] = useState('');
  const [labelType, setLabelType] = useState<LabelType>(LabelType.CLASSIFICATION);
  const [model, setModel] = useState('databricks-meta-llama-3-1-70b-instruct');
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [outputFields, setOutputFields] = useState<OutputField[]>([]);

  // Load template data when editing
  useEffect(() => {
    if (template) {
      setName(template.name);
      setDescription(template.description || '');
      setSystemPrompt(template.system_prompt || '');
      setUserPromptTemplate(template.user_prompt_template);
      setLabelType(template.label_type || LabelType.CLASSIFICATION);
      setModel(template.default_model || 'databricks-meta-llama-3-1-70b-instruct');
      setTemperature(template.default_temperature ?? 0.7);
      setMaxTokens(template.default_max_tokens ?? 1024);
      const schema = template.output_schema;
      if (schema && typeof schema === 'object') {
        const fields = Object.entries(schema).map(([key, val]) => ({
          id: crypto.randomUUID(),
          name: key,
          type: (typeof val === 'string' ? val : 'string') as OutputField['type'],
          description: '',
          required: true,
        }));
        setOutputFields(fields);
      }
    } else {
      setName('');
      setDescription('');
      setSystemPrompt('You are an expert assistant helping with data analysis and classification.');
      setUserPromptTemplate('');
      setLabelType(LabelType.CLASSIFICATION);
      setModel('databricks-meta-llama-3-1-70b-instruct');
      setTemperature(0.7);
      setMaxTokens(1024);
      setOutputFields([]);
    }
  }, [template, open]);

  const addOutputField = () => {
    setOutputFields((prev) => [...prev, {
      id: crypto.randomUUID(),
      name: '',
      type: 'string',
      description: '',
      required: true,
    }]);
  };

  const handleSave = async () => {
    if (!name || !userPromptTemplate) {
      toast({ title: "Missing fields", description: "Name and prompt template are required.", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      const outputSchema = outputFields.length > 0
        ? Object.fromEntries(outputFields.map((f) => [f.name, f.type]))
        : undefined;

      const body: PromptTemplateCreate = {
        name,
        description: description || undefined,
        system_prompt: systemPrompt || undefined,
        user_prompt_template: userPromptTemplate,
        label_type: labelType,
        default_model: model,
        default_temperature: temperature,
        default_max_tokens: maxTokens,
        output_schema: outputSchema,
      };

      if (template) {
        await put(`/api/training-data/templates/${template.id}`, { body });
      } else {
        await post('/api/training-data/templates', { body });
      }
      toast({ title: template ? "Template Updated" : "Template Created", description: `"${name}" saved successfully.` });
      onOpenChange(false);
      onSaved();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save template';
      toast({ title: "Save Failed", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="h-5 w-5" />
            {template ? 'Edit Template' : 'Create Template'}
          </DialogTitle>
          <DialogDescription>
            Build a prompt template using {'{{column_name}}'} syntax to reference data columns.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Template Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Template Name *</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., Defect Classification" className="mt-1" />
            </div>
            <div>
              <Label>Label Type</Label>
              <Select value={labelType} onValueChange={(v) => setLabelType(v as LabelType)}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.values(LabelType).map((lt) => (
                    <SelectItem key={lt} value={lt}>{lt.replace('_', ' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does this template do?" className="mt-1" />
            </div>
          </div>

          {/* Prompt Template */}
          <div className="space-y-4">
            <div>
              <Label>System Prompt</Label>
              <Textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder="You are an expert..."
                rows={3}
                className="mt-1 font-mono text-sm"
              />
            </div>
            <div>
              <Label>User Prompt Template *</Label>
              <Textarea
                value={userPromptTemplate}
                onChange={(e) => setUserPromptTemplate(e.target.value)}
                placeholder={'Analyze the following data:\n\nEquipment: {{equipment_id}}\nReading: {{sensor_value}}\n\nClassify the defect type.'}
                rows={8}
                className="mt-1 font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Use {'{{column_name}}'} syntax to reference data columns
              </p>
            </div>
          </div>

          {/* Output Schema */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <Label>Output Schema</Label>
                <p className="text-xs text-muted-foreground">Define the structure of AI-generated responses</p>
              </div>
              <Button variant="outline" size="sm" onClick={addOutputField}>
                <Plus className="h-3.5 w-3.5 mr-1" /> Add Field
              </Button>
            </div>
            <div className="space-y-2">
              {outputFields.length > 0 ? (
                outputFields.map((field, i) => (
                  <OutputFieldRow
                    key={field.id}
                    field={field}
                    onChange={(f) => setOutputFields((prev) => prev.map((p, j) => j === i ? f : p))}
                    onDelete={() => setOutputFields((prev) => prev.filter((_, j) => j !== i))}
                  />
                ))
              ) : (
                <div className="text-center py-6 text-muted-foreground">
                  <FileText className="h-6 w-6 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No output fields defined</p>
                </div>
              )}
            </div>
          </div>

          {/* Model Settings */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="databricks-meta-llama-3-1-70b-instruct">Llama 3.1 70B</SelectItem>
                  <SelectItem value="databricks-meta-llama-3-1-405b-instruct">Llama 3.1 405B</SelectItem>
                  <SelectItem value="databricks-dbrx-instruct">DBRX</SelectItem>
                  <SelectItem value="databricks-mixtral-8x7b-instruct">Mixtral 8x7B</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Max Tokens</Label>
              <Input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 1024)}
                min={1}
                max={4096}
                className="mt-1"
              />
            </div>
            <div className="col-span-2">
              <Label>Temperature: {temperature}</Label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full mt-1"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>
          </div>

          {/* Live Preview */}
          <PreviewPanel
            systemPrompt={systemPrompt}
            userPrompt={userPromptTemplate}
            outputFields={outputFields}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            {template ? 'Update Template' : 'Create Template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Template Builder View
// =============================================================================

export default function MlTemplateBuilder() {
  const { t } = useTranslation(['training-data', 'common']);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PromptTemplate | null>(null);

  const api = useApi();
  const { get, delete: deleteApi } = api;
  const { toast } = useToast();

  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Permissions
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const featureId = 'training-data';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await get<PromptTemplate[]>('/api/training-data/templates?limit=100');
      const data = checkApiResponse(resp, 'Templates');
      setTemplates(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load templates';
      setError(message);
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, [get]);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Template Builder');

    if (!permissionsLoading && canRead) {
      loadData();
    } else if (!permissionsLoading && !canRead) {
      setLoading(false);
    }

    return () => {
      setStaticSegments([]);
      setDynamicTitle(null);
    };
  }, [canRead, permissionsLoading, loadData, setStaticSegments, setDynamicTitle]);

  const handleDelete = async (templateId: string) => {
    try {
      await deleteApi(`/api/training-data/templates/${templateId}`);
      toast({ title: "Template Deleted" });
      loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete template';
      toast({ title: "Delete Failed", description: message, variant: "destructive" });
    }
  };

  const columns: ColumnDef<PromptTemplate>[] = useMemo(() => [
    {
      accessorKey: 'name',
      header: 'Template',
      cell: ({ row }) => (
        <div>
          <div className="font-medium flex items-center gap-2">
            <Wand2 className="h-4 w-4 text-purple-600 flex-shrink-0" />
            {row.original.name}
          </div>
          {row.original.description && (
            <span className="text-sm text-muted-foreground">{row.original.description}</span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <Badge className={TEMPLATE_STATUS_COLORS[row.original.status]}>
          {row.original.status}
        </Badge>
      ),
    },
    {
      accessorKey: 'label_type',
      header: 'Label Type',
      cell: ({ row }) => (
        <span className="text-sm">{row.original.label_type?.replace('_', ' ') || 'N/A'}</span>
      ),
    },
    {
      accessorKey: 'default_model',
      header: 'Model',
      cell: ({ row }) => (
        <span className="text-sm font-mono truncate max-w-[150px] block">
          {row.original.default_model || 'Default'}
        </span>
      ),
    },
    {
      accessorKey: 'updated_at',
      header: 'Updated',
      cell: ({ row }) => row.original.updated_at
        ? <RelativeDate date={row.original.updated_at} />
        : <span className="text-sm text-muted-foreground">N/A</span>,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => canWrite ? (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={(e) => { e.stopPropagation(); setEditingTemplate(row.original); setFormOpen(true); }}
            title="Edit"
          >
            <Eye className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={(e) => { e.stopPropagation(); handleDelete(row.original.id); }}
            title="Delete"
          >
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      ) : null,
    },
  ], [canWrite]);

  // Guards
  if (permissionsLoading) return <ListViewSkeleton />;

  if (!canRead) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>You do not have permission to view templates.</AlertDescription>
      </Alert>
    );
  }

  if (loading) return <ListViewSkeleton />;

  return (
    <div className="space-y-6">
      {/* Error banner */}
      {error && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error.includes('404') || error.includes('Not Found')
              ? 'Template API is loading. Templates will populate once the backend responds.'
              : error}
          </AlertDescription>
        </Alert>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Wand2 className="h-5 w-5 text-purple-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Total Templates</p>
                <div className="text-2xl font-bold">{templates.length}</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><FileText className="h-5 w-5 text-green-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Active</p>
                <div className="text-2xl font-bold">
                  {templates.filter((t) => t.status === TemplateStatus.ACTIVE).length}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Database className="h-5 w-5 text-blue-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Draft</p>
                <div className="text-2xl font-bold">
                  {templates.filter((t) => t.status === TemplateStatus.DRAFT).length}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><FileText className="h-5 w-5 text-muted-foreground" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Archived</p>
                <div className="text-2xl font-bold">
                  {templates.filter((t) => t.status === TemplateStatus.ARCHIVED).length}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Prompt Templates</h2>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
          {canWrite && (
            <Button size="sm" onClick={() => { setEditingTemplate(null); setFormOpen(true); }}>
              <Plus className="mr-2 h-4 w-4" /> New Template
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={templates}
        searchColumn="name"
        storageKey="ml-template-builder-sort"
      />

      {/* Create/Edit Dialog */}
      <TemplateFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        template={editingTemplate}
        onSaved={loadData}
      />
    </div>
  );
}
