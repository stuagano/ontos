/**
 * MlDspy - DSPy optimization for prompt engineering
 *
 * Ported from VITAL DSPyOptimizationPage. Provides:
 * - Template selection for optimization
 * - Optimization configuration (optimizer type, trials, metrics)
 * - Run progress monitoring with real-time updates
 * - Results panel with sync to example store
 * - Code export preview
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Play,
  Pause,
  RefreshCw,
  Download,
  Code,
  Zap,
  TrendingUp,
  CheckCircle,
  XCircle,
  Clock,
  ChevronDown,
  Copy,
  Settings,
  Loader2,
  Wand2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import { cn } from '@/lib/utils';
import { PromptTemplate, TemplateStatus } from '@/types/training-data';

// DSPy-specific types
interface OptimizationConfig {
  optimizer_type: string;
  max_bootstrapped_demos: number;
  max_labeled_demos: number;
  num_trials: number;
  max_runtime_minutes: number;
  metric_name: string;
}

interface OptimizationRun {
  run_id: string;
  template_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  trials_completed: number;
  trials_total: number;
  current_best_score?: number;
  best_score?: number;
  top_example_ids: string[];
  started_at?: string;
  completed_at?: string;
  estimated_completion?: string;
  error_message?: string;
}

interface DSPyExport {
  program_code: string;
  is_valid: boolean;
  num_examples_included: number;
  examples_json?: string;
}

const OPTIMIZERS = [
  { id: 'BootstrapFewShot', label: 'Bootstrap Few-Shot', description: 'Automatically finds optimal few-shot examples' },
  { id: 'BootstrapFewShotWithRandomSearch', label: 'Bootstrap + Random Search', description: 'Combines bootstrapping with random search for better coverage' },
  { id: 'MIPRO', label: 'MIPRO', description: 'Multi-prompt Instruction Proposal Optimizer - optimizes instructions too' },
];

const DEFAULT_CONFIG: OptimizationConfig = {
  optimizer_type: 'BootstrapFewShot',
  max_bootstrapped_demos: 4,
  max_labeled_demos: 16,
  num_trials: 100,
  max_runtime_minutes: 60,
  metric_name: 'accuracy',
};

const RUN_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-muted text-muted-foreground',
};

// Helper function for API response checking
const checkApiResponse = <T,>(
  response: { data?: T | { detail?: string }; error?: string | null },
  name: string
): T => {
  if (response.error) throw new Error(`${name}: ${response.error}`);
  if (response.data && typeof response.data === 'object' && 'detail' in response.data)
    throw new Error(`${name}: ${(response.data as { detail: string }).detail}`);
  if (response.data === null || response.data === undefined)
    throw new Error(`${name} returned empty data.`);
  return response.data as T;
};

// ============================================================================
// Optimization Config Panel
// ============================================================================

function ConfigPanel({
  config,
  onChange,
}: {
  config: OptimizationConfig;
  onChange: (config: OptimizationConfig) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Card>
      <CardHeader
        className="cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="w-4 h-4" />
            Optimization Settings
          </CardTitle>
          <ChevronDown className={cn('w-4 h-4 transition-transform', expanded && 'rotate-180')} />
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-4">
          {/* Optimizer Type */}
          <div>
            <label className="block text-sm font-medium mb-1">Optimizer</label>
            <select
              value={config.optimizer_type}
              onChange={e => onChange({ ...config, optimizer_type: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm bg-background"
            >
              {OPTIMIZERS.map(opt => (
                <option key={opt.id} value={opt.id}>{opt.label}</option>
              ))}
            </select>
            <p className="mt-1 text-xs text-muted-foreground">
              {OPTIMIZERS.find(o => o.id === config.optimizer_type)?.description}
            </p>
          </div>

          {/* Grid of numeric inputs */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Max Bootstrapped Demos</label>
              <Input type="number" value={config.max_bootstrapped_demos} onChange={e => onChange({ ...config, max_bootstrapped_demos: parseInt(e.target.value) || 4 })} min={1} max={20} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Max Labeled Demos</label>
              <Input type="number" value={config.max_labeled_demos} onChange={e => onChange({ ...config, max_labeled_demos: parseInt(e.target.value) || 16 })} min={1} max={100} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Number of Trials</label>
              <Input type="number" value={config.num_trials} onChange={e => onChange({ ...config, num_trials: parseInt(e.target.value) || 100 })} min={10} max={1000} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Max Runtime (minutes)</label>
              <Input type="number" value={config.max_runtime_minutes} onChange={e => onChange({ ...config, max_runtime_minutes: parseInt(e.target.value) || 60 })} min={5} max={240} />
            </div>
          </div>

          {/* Metric */}
          <div>
            <label className="block text-sm font-medium mb-1">Optimization Metric</label>
            <Input value={config.metric_name} onChange={e => onChange({ ...config, metric_name: e.target.value })} placeholder="accuracy" />
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ============================================================================
// Progress Indicator
// ============================================================================

function RunProgress({ run }: { run: OptimizationRun }) {
  const progress = run.trials_total > 0
    ? Math.round((run.trials_completed / run.trials_total) * 100)
    : 0;

  const StatusIcon = {
    pending: Clock,
    running: RefreshCw,
    completed: CheckCircle,
    failed: XCircle,
    cancelled: Pause,
  }[run.status] || Clock;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-4">
          <Badge variant="outline" className={cn('flex items-center gap-1', RUN_STATUS_COLORS[run.status])}>
            <StatusIcon className={cn('w-3 h-3', run.status === 'running' && 'animate-spin')} />
            {run.status}
          </Badge>
          {run.current_best_score !== undefined && (
            <div className="flex items-center gap-2 text-sm">
              <TrendingUp className="w-4 h-4 text-green-600" />
              <span className="font-medium">Best: {(run.current_best_score * 100).toFixed(1)}%</span>
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{run.trials_completed} / {run.trials_total} trials</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={cn('h-full transition-all duration-500', run.status === 'completed' ? 'bg-green-500' : 'bg-primary')}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {run.started_at && (
          <div className="mt-3 text-xs text-muted-foreground">
            Started: {new Date(run.started_at).toLocaleString()}
            {run.estimated_completion && run.status === 'running' && (
              <span className="ml-4">
                Est. completion: {new Date(run.estimated_completion).toLocaleTimeString()}
              </span>
            )}
          </div>
        )}

        {run.error_message && (
          <div className="mt-3 p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
            {run.error_message}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function MlDspy() {
  const { t } = useTranslation(['training-data', 'common']);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [config, setConfig] = useState<OptimizationConfig>(DEFAULT_CONFIG);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<OptimizationRun | null>(null);
  const [exportResult, setExportResult] = useState<DSPyExport | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const api = useApi();
  const { get, post } = api;
  const { toast } = useToast();
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const setStaticSegments = useBreadcrumbStore(state => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore(state => state.setDynamicTitle);

  const featureId = 'training-data';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('DSPy Optimization');
  }, [setStaticSegments, setDynamicTitle]);

  // Load templates
  useEffect(() => {
    const loadTemplates = async () => {
      setLoading(true);
      try {
        const resp = await get<PromptTemplate[]>('/api/training-data/templates');
        const data = checkApiResponse(resp, 'Templates');
        setTemplates(Array.isArray(data) ? data : []);
      } catch (err: unknown) {
        toast({
          title: 'Failed to load templates',
          description: err instanceof Error ? err.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    };
    if (canRead) loadTemplates();
  }, [get, canRead, toast]);

  // Poll active run
  useEffect(() => {
    if (!activeRunId) return;

    const pollRun = async () => {
      try {
        const resp = await get<OptimizationRun>(`/api/training-data/dspy/runs/${activeRunId}`);
        const data = checkApiResponse(resp, 'Run');
        setActiveRun(data);
      } catch {
        // Silently handle polling errors
      }
    };

    pollRun();
    const interval = setInterval(() => {
      if (activeRun?.status === 'running' || activeRun?.status === 'pending') {
        pollRun();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [activeRunId, activeRun?.status, get]);

  const selectedTemplate = templates.find(t => t.id === selectedTemplateId) || null;

  // Export code
  const handleExport = async () => {
    if (!selectedTemplateId) return;
    setExporting(true);
    try {
      const resp = await post<DSPyExport>(`/api/training-data/dspy/export/${selectedTemplateId}`, {
        include_examples: true,
        max_examples: 10,
        include_optimizer_setup: true,
      });
      const data = checkApiResponse(resp, 'Export');
      setExportResult(data);
      toast({ title: 'Code exported', description: 'DSPy code generated successfully.' });
    } catch (err: unknown) {
      toast({
        title: 'Export failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setExporting(false);
    }
  };

  // Start optimization
  const handleStartOptimization = async () => {
    if (!selectedTemplateId) return;
    setStarting(true);
    try {
      const resp = await post<OptimizationRun>('/api/training-data/dspy/runs', {
        template_id: selectedTemplateId,
        config,
      });
      const data = checkApiResponse(resp, 'Create Run');
      setActiveRunId(data.run_id);
      setActiveRun(data);
      toast({ title: 'Optimization started', description: `Run ${data.run_id.slice(0, 8)}...` });
    } catch (err: unknown) {
      toast({
        title: 'Failed to start optimization',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setStarting(false);
    }
  };

  // Cancel run
  const handleCancelRun = async () => {
    if (!activeRunId) return;
    try {
      await post(`/api/training-data/dspy/runs/${activeRunId}/cancel`, {});
      toast({ title: 'Run cancelled' });
      setActiveRun(prev => prev ? { ...prev, status: 'cancelled' } : null);
    } catch (err: unknown) {
      toast({
        title: 'Cancel failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  // Sync results
  const handleSyncResults = async () => {
    if (!activeRunId) return;
    setSyncing(true);
    try {
      await post(`/api/training-data/dspy/runs/${activeRunId}/sync`, {});
      toast({ title: 'Results synced', description: 'Examples updated in store.' });
    } catch (err: unknown) {
      toast({
        title: 'Sync failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setSyncing(false);
    }
  };

  // Copy code
  const handleCopyCode = () => {
    if (exportResult?.program_code) {
      navigator.clipboard.writeText(exportResult.program_code);
      toast({ title: 'Copied to clipboard' });
    }
  };

  // Permission guard
  if (!permissionsLoading && !canRead) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">You don't have permission to access this feature.</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Zap className="w-6 h-6 text-primary" />
          DSPy Optimization
        </h1>
        <p className="text-muted-foreground mt-1">
          Automatically optimize prompt templates and select best few-shot examples
        </p>
      </div>

      {/* Template Selection */}
      {!selectedTemplateId ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Select a Template</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : templates.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">
                No templates found. Create a prompt template first.
              </p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {templates.map(template => (
                  <button
                    key={template.id}
                    onClick={() => setSelectedTemplateId(template.id)}
                    className="p-4 text-left border rounded-lg hover:border-primary hover:bg-primary/5 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <Wand2 className="w-4 h-4 text-primary mt-1 flex-shrink-0" />
                      <div>
                        <div className="font-medium">{template.name}</div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {template.label_type} · {template.status}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Selected template info */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Wand2 className="w-5 h-5 text-primary" />
                  <div>
                    <div className="font-medium">{selectedTemplate?.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {selectedTemplate?.label_type} · {selectedTemplate?.status}
                    </div>
                  </div>
                </div>
                <Button variant="outline" size="sm" onClick={() => {
                  setSelectedTemplateId(null);
                  setExportResult(null);
                  setActiveRunId(null);
                  setActiveRun(null);
                }}>
                  Change Template
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Tabs */}
          <Tabs defaultValue="optimize">
            <TabsList>
              <TabsTrigger value="optimize" className="flex items-center gap-2">
                <Zap className="w-4 h-4" /> Optimize
              </TabsTrigger>
              <TabsTrigger value="export" className="flex items-center gap-2">
                <Code className="w-4 h-4" /> Export Code
              </TabsTrigger>
            </TabsList>

            {/* Optimize Tab */}
            <TabsContent value="optimize" className="space-y-4 mt-4">
              <ConfigPanel config={config} onChange={setConfig} />

              {!activeRun && (
                <Button onClick={handleStartOptimization} disabled={starting}>
                  {starting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                  {starting ? 'Starting...' : 'Start Optimization'}
                </Button>
              )}

              {activeRun && (
                <>
                  <RunProgress run={activeRun} />

                  {activeRun.status === 'running' && (
                    <Button variant="outline" onClick={handleCancelRun} className="text-destructive">
                      <Pause className="w-4 h-4 mr-2" /> Cancel Run
                    </Button>
                  )}

                  {/* Results */}
                  {activeRun.status === 'completed' && (
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-lg">Results</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="flex items-center justify-between p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                          <div>
                            <div className="text-sm text-green-700 dark:text-green-400">Best Score</div>
                            <div className="text-2xl font-bold text-green-800 dark:text-green-300">
                              {activeRun.best_score !== undefined
                                ? `${(activeRun.best_score * 100).toFixed(1)}%`
                                : 'N/A'}
                            </div>
                          </div>
                          <CheckCircle className="w-8 h-8 text-green-500" />
                        </div>

                        {activeRun.top_example_ids.length > 0 && (
                          <div>
                            <div className="text-sm font-medium mb-2">Top Performing Examples</div>
                            <div className="flex flex-wrap gap-2">
                              {activeRun.top_example_ids.slice(0, 5).map(id => (
                                <Badge key={id} variant="secondary" className="font-mono text-xs">
                                  {id.slice(0, 8)}...
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}

                        <Button onClick={handleSyncResults} disabled={syncing} className="w-full">
                          <RefreshCw className={cn('w-4 h-4 mr-2', syncing && 'animate-spin')} />
                          {syncing ? 'Syncing...' : 'Sync Results to Example Store'}
                        </Button>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </TabsContent>

            {/* Export Tab */}
            <TabsContent value="export" className="space-y-4 mt-4">
              {!exportResult ? (
                <Button onClick={handleExport} disabled={exporting}>
                  {exporting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Code className="w-4 h-4 mr-2" />}
                  {exporting ? 'Generating...' : 'Generate DSPy Code'}
                </Button>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <Button variant="outline" size="sm" onClick={handleCopyCode}>
                      <Copy className="w-4 h-4 mr-1" /> Copy
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => {
                      if (!exportResult.program_code) return;
                      const blob = new Blob([exportResult.program_code], { type: 'text/x-python' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = 'dspy_program.py';
                      a.click();
                      URL.revokeObjectURL(url);
                    }}>
                      <Download className="w-4 h-4 mr-1" /> Download .py
                    </Button>
                    {exportResult.is_valid ? (
                      <Badge variant="outline" className="text-green-600">
                        <CheckCircle className="w-3 h-3 mr-1" /> Valid Python
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-red-600">
                        <XCircle className="w-3 h-3 mr-1" /> Validation errors
                      </Badge>
                    )}
                  </div>

                  {/* Code Preview */}
                  <div className="bg-zinc-900 rounded-lg overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2 bg-zinc-800 border-b border-zinc-700">
                      <span className="text-sm text-zinc-300 font-medium">dspy_program.py</span>
                    </div>
                    <pre className="p-4 text-sm text-green-400 overflow-x-auto max-h-96">
                      <code>{exportResult.program_code}</code>
                    </pre>
                  </div>

                  {exportResult.examples_json && (
                    <details className="text-sm">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                        View examples JSON ({exportResult.num_examples_included} examples)
                      </summary>
                      <pre className="mt-2 p-3 bg-muted rounded-lg overflow-x-auto text-xs">
                        {exportResult.examples_json}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
