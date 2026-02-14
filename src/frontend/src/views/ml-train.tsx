/**
 * MlTrain - Training job management for fine-tuning models
 *
 * Ported from VITAL TrainPage. Provides:
 * - Training jobs list with status monitoring
 * - Training collection selection for new jobs
 * - Job configuration form (model, epochs, learning rate)
 * - Job detail view with progress and results
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Play,
  ExternalLink,
  Loader2,
  Layers,
  RefreshCw,
  CheckCircle,
  Clock,
  AlertCircle,
  XCircle,
  Database,
  ArrowLeft,
  TrendingUp,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/ui/data-table';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import { cn } from '@/lib/utils';
import {
  TrainingCollection,
  TrainingCollectionStatus,
  COLLECTION_STATUS_COLORS,
} from '@/types/training-data';

// Training job interface (backend model)
interface TrainingJob {
  id: string;
  collection_id: string;
  collection_name?: string;
  model_name: string;
  base_model: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  epochs: number;
  learning_rate: number;
  batch_size: number;
  progress_percent?: number;
  best_metric?: number;
  metric_name?: string;
  mlflow_run_id?: string;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

const JOB_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  completed: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  cancelled: 'bg-muted text-muted-foreground',
};

const JOB_STATUS_ICONS: Record<string, typeof CheckCircle> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
  cancelled: AlertCircle,
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
// Job Detail Panel
// ============================================================================

interface JobDetailProps {
  job: TrainingJob;
  onBack: () => void;
  onRefresh: () => void;
}

function JobDetail({ job, onBack, onRefresh }: JobDetailProps) {
  const StatusIcon = JOB_STATUS_ICONS[job.status] || AlertCircle;
  const progress = job.progress_percent ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Jobs
        </Button>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-bold">{job.model_name || 'Training Job'}</h1>
        <p className="text-muted-foreground mt-1">
          Base model: {job.base_model} | Collection: {job.collection_name || job.collection_id?.slice(0, 8)}
        </p>
      </div>

      {/* Status */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-4">
            <Badge variant="outline" className={cn('flex items-center gap-1', JOB_STATUS_COLORS[job.status])}>
              <StatusIcon className={cn('w-3 h-3', job.status === 'running' && 'animate-spin')} />
              {job.status}
            </Badge>
            {job.best_metric !== undefined && (
              <div className="flex items-center gap-2 text-sm">
                <TrendingUp className="w-4 h-4 text-green-600" />
                <span className="font-medium">
                  Best {job.metric_name || 'score'}: {(job.best_metric * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>

          {/* Progress Bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full transition-all duration-500',
                  job.status === 'completed' ? 'bg-green-500' : 'bg-primary'
                )}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Timing */}
          <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Created:</span>
              <div>{job.created_at ? new Date(job.created_at).toLocaleString() : 'N/A'}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Started:</span>
              <div>{job.started_at ? new Date(job.started_at).toLocaleString() : 'N/A'}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Completed:</span>
              <div>{job.completed_at ? new Date(job.completed_at).toLocaleString() : 'N/A'}</div>
            </div>
          </div>

          {/* Error */}
          {job.error_message && (
            <div className="mt-4 p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
              {job.error_message}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="p-3 bg-muted rounded-lg">
              <div className="text-muted-foreground">Epochs</div>
              <div className="font-medium text-lg">{job.epochs}</div>
            </div>
            <div className="p-3 bg-muted rounded-lg">
              <div className="text-muted-foreground">Learning Rate</div>
              <div className="font-medium text-lg">{job.learning_rate}</div>
            </div>
            <div className="p-3 bg-muted rounded-lg">
              <div className="text-muted-foreground">Batch Size</div>
              <div className="font-medium text-lg">{job.batch_size}</div>
            </div>
            <div className="p-3 bg-muted rounded-lg">
              <div className="text-muted-foreground">Base Model</div>
              <div className="font-medium truncate">{job.base_model}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* MLflow Link */}
      {job.mlflow_run_id && (
        <Button variant="outline" asChild>
          <a href={`/ml-experiments/${job.mlflow_run_id}`} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="w-4 h-4 mr-2" />
            View in MLflow
          </a>
        </Button>
      )}
    </div>
  );
}

// ============================================================================
// Create Job Form
// ============================================================================

interface CreateJobFormProps {
  collection: TrainingCollection;
  onSubmit: (config: {
    model_name: string;
    base_model: string;
    epochs: number;
    learning_rate: number;
    batch_size: number;
  }) => void;
  onCancel: () => void;
  isSubmitting: boolean;
}

function CreateJobForm({ collection, onSubmit, onCancel, isSubmitting }: CreateJobFormProps) {
  const [modelName, setModelName] = useState(`${collection.name}-ft`);
  const [baseModel, setBaseModel] = useState('meta-llama/Llama-3.1-8B-Instruct');
  const [epochs, setEpochs] = useState(3);
  const [learningRate, setLearningRate] = useState(2e-5);
  const [batchSize, setBatchSize] = useState(4);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Back
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-bold">Configure Training Job</h1>
        <p className="text-muted-foreground mt-1">
          Training on: {collection.name} ({collection.qa_pair_count ?? 0} QA pairs)
        </p>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Model Name</label>
              <Input value={modelName} onChange={e => setModelName(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Base Model</label>
              <Input value={baseModel} onChange={e => setBaseModel(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Epochs</label>
              <Input type="number" value={epochs} onChange={e => setEpochs(parseInt(e.target.value) || 3)} min={1} max={50} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Learning Rate</label>
              <Input type="number" value={learningRate} onChange={e => setLearningRate(parseFloat(e.target.value) || 2e-5)} step={0.00001} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Batch Size</label>
              <Input type="number" value={batchSize} onChange={e => setBatchSize(parseInt(e.target.value) || 4)} min={1} max={64} />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
            <Button
              onClick={() => onSubmit({ model_name: modelName, base_model: baseModel, epochs, learning_rate: learningRate, batch_size: batchSize })}
              disabled={isSubmitting || !modelName}
            >
              {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Play className="w-4 h-4 mr-2" />}
              Start Training
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function MlTrain() {
  const { t } = useTranslation(['training-data', 'common']);
  const [view, setView] = useState<'jobs' | 'collections' | 'create' | 'detail'>('jobs');
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [collections, setCollections] = useState<TrainingCollection[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setDynamicTitle('Train');
  }, [setStaticSegments, setDynamicTitle]);

  // Load training jobs
  const loadJobs = async () => {
    setLoading(true);
    try {
      const resp = await get<TrainingJob[]>('/api/training-data/training-jobs');
      const data = checkApiResponse(resp, 'Training Jobs');
      setJobs(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setLoading(false);
    }
  };

  // Load collections for selection
  const loadCollections = async () => {
    try {
      const resp = await get<TrainingCollection[]>('/api/training-data/collections');
      const data = checkApiResponse(resp, 'Collections');
      setCollections(Array.isArray(data) ? data : []);
    } catch {
      // Non-critical, silently handle
    }
  };

  useEffect(() => {
    if (canRead) loadJobs();
  }, [canRead]);

  // Create job
  const handleCreateJob = async (config: {
    model_name: string;
    base_model: string;
    epochs: number;
    learning_rate: number;
    batch_size: number;
  }) => {
    if (!selectedCollectionId) return;
    setSubmitting(true);
    try {
      const resp = await post<TrainingJob>('/api/training-data/training-jobs', {
        collection_id: selectedCollectionId,
        ...config,
      });
      const job = checkApiResponse(resp, 'Create Job');
      toast({ title: 'Training job created', description: `Job ${job.id.slice(0, 8)} submitted.` });
      setSelectedJobId(job.id);
      setView('detail');
      loadJobs();
    } catch (err: unknown) {
      toast({
        title: 'Failed to create job',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const selectedJob = jobs.find(j => j.id === selectedJobId) || null;
  const selectedCollection = collections.find(c => c.id === selectedCollectionId) || null;

  // Permission guard
  if (!permissionsLoading && !canRead) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">You don't have permission to access this feature.</p>
      </div>
    );
  }

  // Job Detail View
  if (view === 'detail' && selectedJob) {
    return (
      <div className="p-6">
        <JobDetail
          job={selectedJob}
          onBack={() => { setSelectedJobId(null); setView('jobs'); }}
          onRefresh={loadJobs}
        />
      </div>
    );
  }

  // Create Job View
  if (view === 'create' && selectedCollection) {
    return (
      <div className="p-6">
        <CreateJobForm
          collection={selectedCollection}
          onSubmit={handleCreateJob}
          onCancel={() => { setSelectedCollectionId(null); setView('jobs'); }}
          isSubmitting={submitting}
        />
      </div>
    );
  }

  // Collection Selection View
  if (view === 'collections') {
    const collectionColumns: ColumnDef<TrainingCollection>[] = [
      {
        accessorKey: 'name',
        header: 'Collection',
        cell: ({ row }) => (
          <div className="flex items-center gap-3">
            <Layers className="w-4 h-4 text-green-600 flex-shrink-0" />
            <div>
              <div className="font-medium">{row.original.name}</div>
              <div className="text-sm text-muted-foreground truncate max-w-[250px]">{row.original.description}</div>
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => (
          <Badge variant="outline" className={COLLECTION_STATUS_COLORS[row.original.status] || ''}>
            {row.original.status}
          </Badge>
        ),
      },
      {
        accessorKey: 'qa_pair_count',
        header: 'QA Pairs',
        cell: ({ row }) => <span className="text-sm">{row.original.qa_pair_count ?? 0}</span>,
      },
      {
        id: 'actions',
        cell: ({ row }) => (
          <Button
            variant="default"
            size="sm"
            onClick={() => {
              setSelectedCollectionId(row.original.id);
              setView('create');
            }}
          >
            <Play className="w-3 h-3 mr-1" /> Select
          </Button>
        ),
      },
    ];

    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => setView('jobs')}>
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Jobs
          </Button>
        </div>
        <div>
          <h1 className="text-2xl font-bold">Select Training Collection</h1>
          <p className="text-muted-foreground mt-1">Choose a collection of QA pairs for fine-tuning</p>
        </div>
        <DataTable columns={collectionColumns} data={collections} />
      </div>
    );
  }

  // Jobs List View (default)
  const jobColumns: ColumnDef<TrainingJob>[] = [
    {
      accessorKey: 'model_name',
      header: 'Model',
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.model_name}</div>
          <div className="text-sm text-muted-foreground">{row.original.base_model}</div>
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const StatusIcon = JOB_STATUS_ICONS[row.original.status] || AlertCircle;
        return (
          <Badge variant="outline" className={cn('flex items-center gap-1 w-fit', JOB_STATUS_COLORS[row.original.status])}>
            <StatusIcon className={cn('w-3 h-3', row.original.status === 'running' && 'animate-spin')} />
            {row.original.status}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'progress_percent',
      header: 'Progress',
      cell: ({ row }) => (
        <div className="flex items-center gap-2 min-w-[120px]">
          <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${row.original.progress_percent ?? 0}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground">{row.original.progress_percent ?? 0}%</span>
        </div>
      ),
    },
    {
      accessorKey: 'best_metric',
      header: 'Best Score',
      cell: ({ row }) => (
        <span className="text-sm">
          {row.original.best_metric !== undefined
            ? `${(row.original.best_metric * 100).toFixed(1)}%`
            : '-'}
        </span>
      ),
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.created_at ? new Date(row.original.created_at).toLocaleDateString() : 'N/A'}
        </span>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Training Jobs</h1>
          <p className="text-muted-foreground mt-1">Monitor fine-tuning jobs and view training results</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            onClick={() => {
              loadCollections();
              setView('collections');
            }}
          >
            <Play className="w-4 h-4 mr-2" /> New Training Job
          </Button>
          <Button variant="outline" onClick={loadJobs}>
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
        </div>
      </div>

      {error && <div className="p-4 bg-destructive/10 text-destructive rounded-lg">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : (
        <DataTable
          columns={jobColumns}
          data={jobs}
          onRowClick={(row) => {
            setSelectedJobId(row.id);
            setView('detail');
          }}
        />
      )}
    </div>
  );
}
