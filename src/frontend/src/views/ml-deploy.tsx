import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
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
  Rocket,
  Server,
  Play,
  Send,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  AlertCircle,
  Zap,
  Loader2,
  ExternalLink,
  X,
  ChevronRight,
} from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

interface UCModel {
  name: string;
  full_name: string;
  description?: string;
}

interface UCModelVersion {
  version: number;
  status: string;
  description?: string;
}

interface ServingEndpoint {
  name: string;
  state: string;
  creator?: string;
  config_update?: string;
  created_at?: string;
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
// Endpoint Status Config
// =============================================================================

const STATUS_COLORS: Record<string, string> = {
  READY: "bg-green-100 text-green-800 border-green-200",
  NOT_READY: "bg-amber-100 text-amber-800 border-amber-200",
  PENDING: "bg-blue-100 text-blue-800 border-blue-200",
  FAILED: "bg-red-100 text-red-800 border-red-200",
};

// =============================================================================
// Deployment Wizard Dialog
// =============================================================================

interface DeploymentWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

function DeploymentWizard({ open, onOpenChange, onSuccess }: DeploymentWizardProps) {
  const [step, setStep] = useState(1);
  const [selectedModel, setSelectedModel] = useState<UCModel | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<UCModelVersion | null>(null);
  const [endpointName, setEndpointName] = useState("");
  const [workloadSize, setWorkloadSize] = useState("Small");
  const [scaleToZero, setScaleToZero] = useState(true);
  const [deploying, setDeploying] = useState(false);

  const [models, setModels] = useState<UCModel[]>([]);
  const [versions, setVersions] = useState<UCModelVersion[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);

  const api = useApi();
  const { get, post } = api;
  const { toast } = useToast();

  const resetWizard = () => {
    setStep(1);
    setSelectedModel(null);
    setSelectedVersion(null);
    setEndpointName("");
    setWorkloadSize("Small");
    setScaleToZero(true);
  };

  // Load models when dialog opens
  useEffect(() => {
    if (!open) return;
    const loadModels = async () => {
      setModelsLoading(true);
      try {
        const resp = await get<UCModel[]>('/api/ml-deploy/models');
        const data = checkApiResponse(resp, 'Models');
        setModels(Array.isArray(data) ? data : []);
      } catch {
        setModels([]);
      } finally {
        setModelsLoading(false);
      }
    };
    loadModels();
  }, [open, get]);

  // Load versions when model is selected
  useEffect(() => {
    if (!selectedModel) return;
    const loadVersions = async () => {
      setVersionsLoading(true);
      try {
        const resp = await get<UCModelVersion[]>(`/api/ml-deploy/models/${encodeURIComponent(selectedModel.full_name)}/versions`);
        const data = checkApiResponse(resp, 'Versions');
        setVersions(Array.isArray(data) ? data : []);
      } catch {
        setVersions([]);
      } finally {
        setVersionsLoading(false);
      }
    };
    loadVersions();
  }, [selectedModel, get]);

  const handleDeploy = async () => {
    if (!selectedModel || !selectedVersion) return;
    setDeploying(true);
    try {
      await post('/api/ml-deploy/deploy', {
        body: {
          model_name: selectedModel.full_name,
          model_version: String(selectedVersion.version),
          endpoint_name: endpointName || undefined,
          workload_size: workloadSize,
          scale_to_zero: scaleToZero,
        },
      });
      toast({ title: "Deployment Started", description: "Your model is being deployed to a serving endpoint." });
      onSuccess();
      onOpenChange(false);
      resetWizard();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Deployment failed';
      toast({ title: "Deployment Failed", description: message, variant: "destructive" });
    } finally {
      setDeploying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) resetWizard(); onOpenChange(o); }}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Rocket className="h-5 w-5 text-cyan-600" />
            Deploy Model
          </DialogTitle>
          <DialogDescription>Step {step} of 3 — {step === 1 ? 'Select Model' : step === 2 ? 'Choose Version' : 'Configure'}</DialogDescription>
        </DialogHeader>

        {/* Progress Steps */}
        <div className="flex items-center gap-2 py-2">
          {[1, 2, 3].map((s) => (
            <div key={s} className="flex items-center gap-2 flex-1">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                s < step ? 'bg-cyan-600 text-white' :
                s === step ? 'bg-cyan-100 text-cyan-700 border-2 border-cyan-600' :
                'bg-muted text-muted-foreground'
              }`}>
                {s < step ? <CheckCircle className="w-4 h-4" /> : s}
              </div>
              {s < 3 && <div className={`flex-1 h-1 rounded ${s < step ? 'bg-cyan-600' : 'bg-muted'}`} />}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="min-h-[300px] max-h-[400px] overflow-y-auto">
          {step === 1 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Select a model from Unity Catalog</p>
              {modelsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : models.length > 0 ? (
                models.map((model) => (
                  <button
                    key={model.full_name}
                    onClick={() => setSelectedModel(model)}
                    className={`w-full p-4 rounded-lg border-2 text-left transition-all ${
                      selectedModel?.full_name === model.full_name
                        ? 'border-cyan-500 bg-cyan-50 dark:bg-cyan-950'
                        : 'border-border hover:border-cyan-300'
                    }`}
                  >
                    <div className="font-medium">{model.name}</div>
                    <div className="text-sm text-muted-foreground font-mono">{model.full_name}</div>
                    {model.description && <div className="text-sm text-muted-foreground mt-1">{model.description}</div>}
                  </button>
                ))
              ) : (
                <div className="text-center py-12">
                  <Server className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                  <p className="text-muted-foreground">No models found in Unity Catalog</p>
                  <p className="text-sm text-muted-foreground/70 mt-1">Train a model first to deploy it</p>
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Select model version to deploy</p>
              <div className="p-3 bg-muted rounded-lg text-sm">
                <span className="text-muted-foreground">Model:</span>{' '}
                <span className="font-mono">{selectedModel?.full_name}</span>
              </div>
              {versionsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : versions.length > 0 ? (
                versions.map((version) => (
                  <button
                    key={version.version}
                    onClick={() => setSelectedVersion(version)}
                    className={`w-full p-4 rounded-lg border-2 text-left transition-all ${
                      selectedVersion?.version === version.version
                        ? 'border-cyan-500 bg-cyan-50 dark:bg-cyan-950'
                        : 'border-border hover:border-cyan-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Version {version.version}</span>
                      <Badge variant={version.status === "READY" ? "default" : "secondary"}>
                        {version.status}
                      </Badge>
                    </div>
                    {version.description && <div className="text-sm text-muted-foreground mt-1">{version.description}</div>}
                  </button>
                ))
              ) : (
                <div className="text-center py-12">
                  <p className="text-muted-foreground">No versions found</p>
                </div>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <p className="text-sm text-muted-foreground">Configure deployment settings</p>
              <div className="p-3 bg-muted rounded-lg text-sm space-y-1">
                <div><span className="text-muted-foreground">Model:</span> <span className="font-mono">{selectedModel?.full_name}</span></div>
                <div><span className="text-muted-foreground">Version:</span> <span className="font-medium">{selectedVersion?.version}</span></div>
              </div>

              <div className="space-y-2">
                <Label>Endpoint Name (optional)</Label>
                <Input
                  value={endpointName}
                  onChange={(e) => setEndpointName(e.target.value)}
                  placeholder={`${selectedModel?.name?.toLowerCase().replace(/_/g, "-")}-v${selectedVersion?.version}`}
                />
                <p className="text-xs text-muted-foreground">Leave blank to auto-generate</p>
              </div>

              <div className="space-y-2">
                <Label>Workload Size</Label>
                <Select value={workloadSize} onValueChange={setWorkloadSize}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Small">Small</SelectItem>
                    <SelectItem value="Medium">Medium</SelectItem>
                    <SelectItem value="Large">Large</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
                <div>
                  <div className="font-medium">Scale to Zero</div>
                  <div className="text-sm text-muted-foreground">Save costs by scaling down when idle</div>
                </div>
                <Switch checked={scaleToZero} onCheckedChange={setScaleToZero} />
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="flex justify-between sm:justify-between">
          <Button variant="ghost" onClick={() => step > 1 ? setStep(step - 1) : onOpenChange(false)}>
            {step > 1 ? 'Back' : 'Cancel'}
          </Button>
          <Button
            onClick={() => step < 3 ? setStep(step + 1) : handleDeploy()}
            disabled={(step === 1 && !selectedModel) || (step === 2 && !selectedVersion) || deploying}
          >
            {deploying ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Deploying...</>
            ) : step < 3 ? (
              <>Next<ChevronRight className="ml-2 h-4 w-4" /></>
            ) : (
              <><Rocket className="mr-2 h-4 w-4" />Deploy</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Playground Dialog
// =============================================================================

interface PlaygroundProps {
  endpoint: ServingEndpoint | null;
  onClose: () => void;
}

function PlaygroundDialog({ endpoint, onClose }: PlaygroundProps) {
  const [input, setInput] = useState('{\n  "prompt": "Hello, how can I help you?"\n}');
  const [output, setOutput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [querying, setQuerying] = useState(false);
  const { post } = useApi();
  const { toast } = useToast();

  const handleSubmit = async () => {
    if (!endpoint) return;
    try {
      const parsed = JSON.parse(input);
      setQuerying(true);
      setError(null);
      const resp = await post<{ predictions: unknown }>(`/api/ml-deploy/endpoints/${endpoint.name}/query`, { body: parsed });
      const data = checkApiResponse(resp, 'Query');
      setOutput(JSON.stringify(data.predictions, null, 2));
    } catch (err: unknown) {
      if (err instanceof SyntaxError) {
        toast({ title: "Invalid JSON", description: "Please check your input format", variant: "destructive" });
      } else {
        setError(err instanceof Error ? err.message : 'Query failed');
      }
    } finally {
      setQuerying(false);
    }
  };

  return (
    <Dialog open={!!endpoint} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-cyan-600" />
            Playground — {endpoint?.name}
          </DialogTitle>
          <DialogDescription>Send a request to test the serving endpoint</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4 min-h-[300px]">
          {/* Input */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Input (JSON)</Label>
              <Button size="sm" onClick={handleSubmit} disabled={querying}>
                {querying ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                Send
              </Button>
            </div>
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="flex-1 font-mono text-sm min-h-[250px]"
              placeholder='{"prompt": "..."}'
            />
          </div>

          {/* Output */}
          <div className="flex flex-col gap-2">
            <Label>Output</Label>
            <div className="flex-1 p-3 bg-muted border rounded-md overflow-auto min-h-[250px]">
              {querying ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : error ? (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : output ? (
                <pre className="text-sm font-mono whitespace-pre-wrap">{output}</pre>
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                  Send a request to see the response
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Deploy View
// =============================================================================

export default function MlDeploy() {
  const { t } = useTranslation(['ml-deploy', 'common']);
  const [endpoints, setEndpoints] = useState<ServingEndpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [playgroundEndpoint, setPlaygroundEndpoint] = useState<ServingEndpoint | null>(null);

  const api = useApi();
  const { get } = api;
  const { toast } = useToast();

  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Permissions
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const featureId = 'ml-deploy';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  const loadEndpoints = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await get<ServingEndpoint[]>('/api/ml-deploy/endpoints');
      const data = checkApiResponse(resp, 'Endpoints');
      setEndpoints(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load endpoints';
      setError(message);
      setEndpoints([]);
    } finally {
      setLoading(false);
    }
  }, [get]);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Deploy');

    if (!permissionsLoading && canRead) {
      loadEndpoints();
    } else if (!permissionsLoading && !canRead) {
      setLoading(false);
    }

    return () => {
      setStaticSegments([]);
      setDynamicTitle(null);
    };
  }, [canRead, permissionsLoading, loadEndpoints, setStaticSegments, setDynamicTitle]);

  // Stats
  const readyCount = endpoints.filter(e => e.state === 'READY').length;
  const startingCount = endpoints.filter(e => e.state === 'NOT_READY').length;
  const failedCount = endpoints.filter(e => e.state === 'FAILED').length;

  // Table columns
  const columns: ColumnDef<ServingEndpoint>[] = useMemo(() => [
    {
      accessorKey: 'name',
      header: 'Endpoint Name',
      cell: ({ row }) => (
        <div className="flex items-center gap-3">
          <Server className="h-4 w-4 text-cyan-600 flex-shrink-0" />
          <div>
            <div className="font-medium">{row.original.name}</div>
            {row.original.creator && (
              <div className="text-sm text-muted-foreground">by {row.original.creator}</div>
            )}
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'state',
      header: 'Status',
      cell: ({ row }) => (
        <Badge className={STATUS_COLORS[row.original.state] || 'bg-gray-100 text-gray-800'}>
          {row.original.state}
        </Badge>
      ),
    },
    {
      accessorKey: 'creator',
      header: 'Creator',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">{row.original.creator || 'System'}</span>
      ),
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => row.original.created_at
        ? <RelativeDate date={row.original.created_at} />
        : <span className="text-sm text-muted-foreground">N/A</span>,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          {row.original.state === 'READY' && (
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => { e.stopPropagation(); setPlaygroundEndpoint(row.original); }}
              title="Open Playground"
            >
              <Play className="h-4 w-4" />
            </Button>
          )}
        </div>
      ),
    },
  ], []);

  // Guards
  if (permissionsLoading) return <ListViewSkeleton />;

  if (!canRead) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>You do not have permission to view model deployments.</AlertDescription>
      </Alert>
    );
  }

  if (loading) return <ListViewSkeleton />;

  return (
    <div className="space-y-6">
      {/* Error banner (non-fatal - endpoint not implemented yet) */}
      {error && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error.includes('404') || error.includes('Not Found')
              ? 'Deployment API is being ported (Phase 3). The endpoint list will populate once backend routes are implemented.'
              : error}
          </AlertDescription>
        </Alert>
      )}

      {/* Stats Cards */}
      {endpoints.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="flex items-center gap-3 pt-6">
              <div className="p-2 bg-green-50 dark:bg-green-950 rounded-lg">
                <CheckCircle className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <div className="text-2xl font-bold">{readyCount}</div>
                <div className="text-sm text-muted-foreground">Ready</div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center gap-3 pt-6">
              <div className="p-2 bg-amber-50 dark:bg-amber-950 rounded-lg">
                <Clock className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <div className="text-2xl font-bold">{startingCount}</div>
                <div className="text-sm text-muted-foreground">Starting</div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center gap-3 pt-6">
              <div className="p-2 bg-red-50 dark:bg-red-950 rounded-lg">
                <XCircle className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <div className="text-2xl font-bold">{failedCount}</div>
                <div className="text-sm text-muted-foreground">Failed</div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Endpoints Table */}
      <DataTable
        columns={columns}
        data={endpoints}
        searchColumn="name"
        storageKey="ml-deploy-sort"
        onRowClick={(row) => {
          if (row.original.state === 'READY') setPlaygroundEndpoint(row.original);
        }}
        toolbarActions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={loadEndpoints}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
            {canWrite && (
              <Button size="sm" onClick={() => setShowWizard(true)}>
                <Rocket className="mr-2 h-4 w-4" />
                Deploy Model
              </Button>
            )}
          </div>
        }
      />

      {/* Deployment Wizard */}
      <DeploymentWizard
        open={showWizard}
        onOpenChange={setShowWizard}
        onSuccess={loadEndpoints}
      />

      {/* Playground */}
      <PlaygroundDialog
        endpoint={playgroundEndpoint}
        onClose={() => setPlaygroundEndpoint(null)}
      />
    </div>
  );
}
