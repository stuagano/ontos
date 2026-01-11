import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useToast } from '@/hooks/use-toast';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import {
  ArrowLeft,
  Pencil,
  Trash2,
  AlertCircle,
  Table2,
  FileText,
  Users,
  Bell,
  BellOff,
  ExternalLink,
  Rocket,
  XCircle,
  Loader2,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type {
  Dataset,
  DatasetStatus,
  DatasetSubscriptionResponse,
  DatasetSubscribersListResponse,
  DatasetInstance,
  DatasetInstanceListResponse,
  DatasetInstanceEnvironment,
} from '@/types/dataset';
import {
  DATASET_STATUS_LABELS,
  DATASET_STATUS_COLORS,
  DATASET_INSTANCE_STATUS_LABELS,
  DATASET_INSTANCE_STATUS_COLORS,
  DATASET_INSTANCE_ROLE_LABELS,
  DATASET_INSTANCE_ROLE_COLORS,
  DATASET_INSTANCE_ENVIRONMENT_LABELS,
  DATASET_INSTANCE_ENVIRONMENT_COLORS,
} from '@/types/dataset';
import type { DatasetInstanceRole } from '@/types/dataset';
import type { DatasetInstanceStatus } from '@/types/dataset';
import { RelativeDate } from '@/components/common/relative-date';
import DatasetFormDialog from '@/components/datasets/dataset-form-dialog';
import DatasetInstanceFormDialog from '@/components/datasets/dataset-instance-form-dialog';
import EntityMetadataPanel from '@/components/metadata/entity-metadata-panel';
import TagChip from '@/components/ui/tag-chip';
import { CommentSidebar } from '@/components/comments';
import ConceptSelectDialog from '@/components/semantic/concept-select-dialog';
import LinkedConceptChips from '@/components/semantic/linked-concept-chips';
import type { EntitySemanticLink } from '@/types/semantic-link';
import { Label } from '@/components/ui/label';
import { Plus, Server } from 'lucide-react';

export default function DatasetDetails() {
  const { datasetId } = useParams<{ datasetId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Data state
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Subscription state
  const [subscriptionStatus, setSubscriptionStatus] = useState<DatasetSubscriptionResponse | null>(null);
  const [subscribers, setSubscribers] = useState<DatasetSubscribersListResponse | null>(null);
  const [subscribing, setSubscribing] = useState(false);

  // Publishing state
  const [publishing, setPublishing] = useState(false);

  // Dialog state
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [isCommentSidebarOpen, setIsCommentSidebarOpen] = useState(false);
  const [conceptDialogOpen, setConceptDialogOpen] = useState(false);
  const [openInstanceDialog, setOpenInstanceDialog] = useState(false);
  const [editingInstance, setEditingInstance] = useState<DatasetInstance | null>(null);

  // Semantic links state
  const [semanticLinks, setSemanticLinks] = useState<EntitySemanticLink[]>([]);

  // Instances state
  const [instances, setInstances] = useState<DatasetInstance[]>([]);
  const [instancesLoading, setInstancesLoading] = useState(false);

  // Fetch dataset
  const fetchDataset = useCallback(async () => {
    if (!datasetId) return;

    try {
      setLoading(true);
      const response = await fetch(`/api/datasets/${datasetId}`);
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Dataset not found');
        }
        throw new Error('Failed to fetch dataset');
      }
      const data = await response.json();
      setDataset(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch dataset');
    } finally {
      setLoading(false);
    }
  }, [datasetId]);

  // Fetch subscription status
  const fetchSubscriptionStatus = useCallback(async () => {
    if (!datasetId) return;

    try {
      const response = await fetch(`/api/datasets/${datasetId}/subscription`);
      if (response.ok) {
        const data = await response.json();
        setSubscriptionStatus(data);
      }
    } catch (err) {
      console.warn('Failed to fetch subscription status:', err);
    }
  }, [datasetId]);

  // Fetch subscribers
  const fetchSubscribers = useCallback(async () => {
    if (!datasetId) return;

    try {
      const response = await fetch(`/api/datasets/${datasetId}/subscribers`);
      if (response.ok) {
        const data = await response.json();
        setSubscribers(data);
      }
    } catch (err) {
      console.warn('Failed to fetch subscribers:', err);
    }
  }, [datasetId]);

  // Fetch semantic links
  const fetchSemanticLinks = useCallback(async () => {
    if (!datasetId) return;

    try {
      const response = await fetch(`/api/semantic-links/entity/dataset/${datasetId}`);
      if (response.ok) {
        const data = await response.json();
        setSemanticLinks(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.warn('Failed to fetch semantic links:', err);
      setSemanticLinks([]);
    }
  }, [datasetId]);

  // Fetch instances
  const fetchInstances = useCallback(async () => {
    if (!datasetId) return;

    try {
      setInstancesLoading(true);
      const response = await fetch(`/api/datasets/${datasetId}/instances`);
      if (response.ok) {
        const data: DatasetInstanceListResponse = await response.json();
        setInstances(data.instances || []);
      }
    } catch (err) {
      console.warn('Failed to fetch instances:', err);
      setInstances([]);
    } finally {
      setInstancesLoading(false);
    }
  }, [datasetId]);

  useEffect(() => {
    fetchDataset();
    fetchSubscriptionStatus();
    fetchSubscribers();
    fetchSemanticLinks();
    fetchInstances();
  }, [fetchDataset, fetchSubscriptionStatus, fetchSubscribers, fetchSemanticLinks, fetchInstances]);

  useEffect(() => {
    // Set breadcrumbs
    setStaticSegments([{ label: 'Datasets', path: '/datasets' }]);
    setDynamicTitle(dataset?.name || 'Loading...');

    return () => {
      setStaticSegments([]);
      setDynamicTitle(null);
    };
  }, [setStaticSegments, setDynamicTitle, dataset?.name]);

  // Toggle subscription
  const toggleSubscription = async () => {
    if (!datasetId) return;

    setSubscribing(true);
    try {
      const isSubscribed = subscriptionStatus?.subscribed;
      const method = isSubscribed ? 'DELETE' : 'POST';
      const response = await fetch(`/api/datasets/${datasetId}/subscribe`, {
        method,
      });

      if (!response.ok) throw new Error('Failed to update subscription');

      const data = await response.json();
      setSubscriptionStatus(data);
      fetchSubscribers();

      toast({
        title: isSubscribed ? 'Unsubscribed' : 'Subscribed',
        description: isSubscribed
          ? 'You will no longer receive updates for this dataset'
          : 'You will receive updates for this dataset',
      });
    } catch (err) {
      toast({
        title: 'Error',
        description: 'Failed to update subscription',
        variant: 'destructive',
      });
    } finally {
      setSubscribing(false);
    }
  };

  // Delete dataset
  const handleDelete = async () => {
    if (!datasetId || !dataset) return;
    if (!confirm(`Are you sure you want to delete "${dataset.name}"?`)) return;

    try {
      const response = await fetch(`/api/datasets/${datasetId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete dataset');

      toast({
        title: 'Success',
        description: 'Dataset deleted successfully',
      });
      navigate('/datasets');
    } catch (err) {
      toast({
        title: 'Error',
        description: 'Failed to delete dataset',
        variant: 'destructive',
      });
    }
  };

  // Publish dataset to marketplace
  const handlePublish = async () => {
    if (!datasetId) return;
    
    setPublishing(true);
    try {
      const response = await fetch(`/api/datasets/${datasetId}/publish`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to publish dataset');
      }
      
      toast({
        title: 'Success',
        description: 'Dataset published to marketplace',
      });
      fetchDataset();
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to publish dataset',
        variant: 'destructive',
      });
    } finally {
      setPublishing(false);
    }
  };

  // Unpublish dataset from marketplace
  const handleUnpublish = async () => {
    if (!datasetId) return;
    
    setPublishing(true);
    try {
      const response = await fetch(`/api/datasets/${datasetId}/unpublish`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to unpublish dataset');
      }
      
      toast({
        title: 'Success',
        description: 'Dataset removed from marketplace',
      });
      fetchDataset();
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to unpublish dataset',
        variant: 'destructive',
      });
    } finally {
      setPublishing(false);
    }
  };

  // Add semantic link
  const addSemanticLink = async (iri: string) => {
    if (!datasetId) return;
    try {
      const response = await fetch('/api/semantic-links/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_id: datasetId,
          entity_type: 'dataset',
          iri,
        }),
      });
      if (!response.ok) throw new Error('Failed to add concept');
      await fetchSemanticLinks();
      setConceptDialogOpen(false);
      toast({ title: 'Linked', description: 'Business concept linked to dataset.' });
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to link business concept',
        variant: 'destructive',
      });
    }
  };

  // Remove semantic link
  const removeSemanticLink = async (linkId: string) => {
    try {
      const response = await fetch(`/api/semantic-links/${linkId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error('Failed to remove concept');
      await fetchSemanticLinks();
      toast({ title: 'Unlinked', description: 'Business concept unlinked from dataset.' });
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to unlink business concept',
        variant: 'destructive',
      });
    }
  };

  // Delete instance
  const handleDeleteInstance = async (instanceId: string) => {
    if (!datasetId) return;
    if (!confirm('Are you sure you want to remove this instance?')) return;

    try {
      const response = await fetch(`/api/datasets/${datasetId}/instances/${instanceId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to remove instance');

      toast({
        title: 'Success',
        description: 'Instance removed successfully',
      });
      fetchInstances();
    } catch (err) {
      toast({
        title: 'Error',
        description: 'Failed to remove instance',
        variant: 'destructive',
      });
    }
  };

  // Edit instance
  const handleEditInstance = (instance: DatasetInstance) => {
    setEditingInstance(instance);
    setOpenInstanceDialog(true);
  };

  // Add new instance
  const handleAddInstance = () => {
    setEditingInstance(null);
    setOpenInstanceDialog(true);
  };

  if (loading) {
    return (
      <div className="py-6 space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10" />
          <div className="space-y-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-96" />
          </div>
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !dataset) {
    return (
      <div className="py-6 space-y-6">
        <Button variant="outline" size="sm" onClick={() => navigate('/datasets')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to List
        </Button>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error || 'Dataset not found'}</AlertDescription>
        </Alert>
      </div>
    );
  }

  const status = dataset.status as DatasetStatus;

  return (
    <div className="py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Button variant="outline" size="sm" onClick={() => navigate('/datasets')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to List
        </Button>
        <div className="flex items-center gap-2">
          <CommentSidebar
            entityType="dataset"
            entityId={datasetId!}
            isOpen={isCommentSidebarOpen}
            onToggle={() => setIsCommentSidebarOpen(!isCommentSidebarOpen)}
            className="h-8"
          />
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={toggleSubscription}
                  disabled={subscribing}
                >
                  {subscriptionStatus?.subscribed ? (
                    <BellOff className="h-4 w-4" />
                  ) : (
                    <Bell className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{subscriptionStatus?.subscribed ? 'Unsubscribe' : 'Subscribe'}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {/* Publish/Unpublish buttons */}
          {!dataset.published && ['active', 'approved', 'certified'].includes(dataset.status) && (
            <Button onClick={handlePublish} disabled={publishing}>
              {publishing ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4 mr-2" />
              )}
              Publish to Marketplace
            </Button>
          )}
          {dataset.published && (
            <Button variant="outline" onClick={handleUnpublish} disabled={publishing}>
              {publishing ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4 mr-2" />
              )}
              Unpublish
            </Button>
          )}
          <Button variant="outline" onClick={() => setOpenEditDialog(true)}>
            <Pencil className="h-4 w-4 mr-2" />
            Edit
          </Button>
          <Button variant="destructive" onClick={handleDelete}>
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      {/* Core Metadata Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl font-bold flex items-center">
            <Table2 className="mr-3 h-7 w-7 text-primary" />
            {dataset.name}
          </CardTitle>
          <CardDescription className="pt-1">
            {dataset.description || 'No description provided'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid md:grid-cols-3 gap-x-6 gap-y-2">
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">Status:</Label>
              <div className="flex items-center gap-1.5">
                <Badge
                  variant="outline"
                  className={DATASET_STATUS_COLORS[status] || 'bg-gray-100'}
                >
                  {DATASET_STATUS_LABELS[status] || status}
                </Badge>
                {dataset.published && (
                  <Badge variant="default" className="bg-green-600 text-xs">Published</Badge>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">Version:</Label>
              <Badge variant="outline" className="text-xs">{dataset.version || 'N/A'}</Badge>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">Owner:</Label>
              {dataset.owner_team_id && dataset.owner_team_name ? (
                <span
                  className="text-xs cursor-pointer text-primary hover:underline truncate"
                  onClick={() => navigate(`/teams/${dataset.owner_team_id}`)}
                  title={`Team ID: ${dataset.owner_team_id}`}
                >
                  {dataset.owner_team_name}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">{dataset.owner_team_name || 'Not assigned'}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">Project:</Label>
              {dataset.project_id && dataset.project_name ? (
                <span
                  className="text-xs cursor-pointer text-primary hover:underline truncate"
                  onClick={() => navigate(`/projects/${dataset.project_id}`)}
                  title={`Project ID: ${dataset.project_id}`}
                >
                  {dataset.project_name}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">{dataset.project_name || 'Not assigned'}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">Created:</Label>
              <span className="text-xs text-muted-foreground truncate">
                <RelativeDate date={dataset.created_at} />
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">Updated:</Label>
              <span className="text-xs text-muted-foreground truncate">
                <RelativeDate date={dataset.updated_at} />
              </span>
            </div>
          </div>

          <div className="pt-2 border-t">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex-1 min-w-0">
                <Label className="text-xs text-muted-foreground mb-1.5 block">Tags:</Label>
                <div className="flex flex-wrap gap-1">
                  {dataset.tags && dataset.tags.length > 0 ? (
                    dataset.tags.map((tag, idx) => (
                      <TagChip key={idx} tag={tag} size="sm" />
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">No tags</span>
                  )}
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <Label className="text-xs text-muted-foreground mb-1.5 block">Linked Business Concepts:</Label>
                <LinkedConceptChips
                  links={semanticLinks}
                  onRemove={(id) => removeSemanticLink(id)}
                  trailing={<Button size="sm" variant="outline" onClick={() => setConceptDialogOpen(true)} className="h-6 text-xs">Add</Button>}
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dataset Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Table2 className="h-5 w-5" />
            Dataset Overview
          </CardTitle>
          <CardDescription>
            Version and instance information
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Version
              </label>
              <p className="text-sm">{dataset.version || '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Physical Instances
              </label>
              <p className="text-sm">
                {dataset.instance_count || 0} instance{(dataset.instance_count || 0) !== 1 ? 's' : ''}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Contract Link */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Data Contract
          </CardTitle>
          <CardDescription>
            The contract this dataset implements
          </CardDescription>
        </CardHeader>
        <CardContent>
          {dataset.contract_id ? (
            <div className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <p className="font-medium">{dataset.contract_name || 'Linked Contract'}</p>
                <p className="text-sm text-muted-foreground">
                  This dataset implements the schema and quality requirements from this contract
                </p>
              </div>
              <Button variant="outline" asChild>
                <Link to={`/data-contracts/${dataset.contract_id}`}>
                  <ExternalLink className="h-4 w-4 mr-2" />
                  View Contract
                </Link>
              </Button>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>No contract assigned</p>
              <p className="text-sm">
                Assign a contract to define schema and quality requirements
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Physical Instances */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                Physical Instances
                {instances.length > 0 && (
                  <Badge variant="secondary">{instances.length}</Badge>
                )}
              </CardTitle>
              <CardDescription>
                Physical implementations across different systems and environments
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={handleAddInstance}>
              <Plus className="h-4 w-4 mr-2" />
              Add Instance
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {instancesLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : instances.length > 0 ? (
            <div className="space-y-4">
              {/* Group instances by role */}
              {(['main', 'dimension', 'lookup', 'reference', 'staging'] as DatasetInstanceRole[]).map((role) => {
                const roleInstances = instances.filter((i) => (i.role || 'main') === role);
                if (roleInstances.length === 0) return null;
                
                return (
                  <div key={role} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={DATASET_INSTANCE_ROLE_COLORS[role] || 'bg-gray-100'}
                      >
                        {DATASET_INSTANCE_ROLE_LABELS[role] || role}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        ({roleInstances.length})
                      </span>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Name</TableHead>
                          <TableHead>Environment</TableHead>
                          <TableHead>Physical Path</TableHead>
                          <TableHead>Contract</TableHead>
                          <TableHead>Tags</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {roleInstances.map((instance) => {
                          const instStatus = instance.status as DatasetInstanceStatus;
                          const instEnv = instance.environment as DatasetInstanceEnvironment | undefined;
                          return (
                            <TableRow key={instance.id}>
                              <TableCell>
                                <div className="flex flex-col">
                                  <span className="font-medium">
                                    {instance.display_name || instance.physical_path.split('.').pop()}
                                  </span>
                                  {instance.server_type && (
                                    <span className="text-xs text-muted-foreground capitalize">
                                      {instance.server_type}
                                    </span>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                {instEnv ? (
                                  <Badge
                                    variant="outline"
                                    className={DATASET_INSTANCE_ENVIRONMENT_COLORS[instEnv] || 'bg-gray-100'}
                                  >
                                    {DATASET_INSTANCE_ENVIRONMENT_LABELS[instEnv] || instEnv}
                                  </Badge>
                                ) : instance.server_environment ? (
                                  <Badge variant="outline" className="capitalize">
                                    {instance.server_environment}
                                  </Badge>
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </TableCell>
                              <TableCell>
                                <code className="text-sm bg-muted px-2 py-1 rounded">
                                  {instance.physical_path}
                                </code>
                              </TableCell>
                              <TableCell>
                                {instance.contract_name ? (
                                  <TooltipProvider>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Link
                                          to={`/data-contracts/${instance.contract_id}`}
                                          className="text-sm hover:underline text-blue-600 dark:text-blue-400"
                                        >
                                          v{instance.contract_version || '-'}
                                        </Link>
                                      </TooltipTrigger>
                                      <TooltipContent>
                                        <p>{instance.contract_name}</p>
                                      </TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </TableCell>
                              <TableCell>
                                {instance.tags && instance.tags.length > 0 ? (
                                  <div className="flex flex-wrap gap-1">
                                    {instance.tags.slice(0, 3).map((tag, idx) => (
                                      <TagChip key={idx} tag={tag} size="sm" />
                                    ))}
                                    {instance.tags.length > 3 && (
                                      <span className="text-xs text-muted-foreground">
                                        +{instance.tags.length - 3}
                                      </span>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </TableCell>
                              <TableCell>
                                <Badge
                                  variant="outline"
                                  className={DATASET_INSTANCE_STATUS_COLORS[instStatus] || 'bg-gray-100'}
                                >
                                  {DATASET_INSTANCE_STATUS_LABELS[instStatus] || instStatus}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex justify-end gap-1">
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => handleEditInstance(instance)}
                                  >
                                    <Pencil className="h-4 w-4" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => handleDeleteInstance(instance.id)}
                                  >
                                    <Trash2 className="h-4 w-4 text-destructive" />
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Server className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>No physical instances</p>
              <p className="text-sm">
                Add instances to track where this dataset is physically implemented
              </p>
              <Button variant="outline" size="sm" className="mt-4" onClick={handleAddInstance}>
                <Plus className="h-4 w-4 mr-2" />
                Add First Instance
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Subscribers */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Subscribers
            {subscribers && (
              <Badge variant="secondary">{subscribers.subscriber_count}</Badge>
            )}
          </CardTitle>
          <CardDescription>
            Users receiving updates about this dataset
          </CardDescription>
        </CardHeader>
        <CardContent>
          {subscribers && subscribers.subscribers.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Subscribed</TableHead>
                  <TableHead>Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subscribers.subscribers.map((sub, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{sub.email}</TableCell>
                    <TableCell>
                      <RelativeDate date={sub.subscribed_at} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {sub.reason || '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>No subscribers yet</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Metadata Panel - Rich texts, links, documents */}
      {datasetId && (
        <EntityMetadataPanel entityId={datasetId} entityType="dataset" />
      )}

      {/* Edit Dialog */}
      <DatasetFormDialog
        open={openEditDialog}
        onOpenChange={setOpenEditDialog}
        dataset={dataset}
        onSuccess={() => {
          fetchDataset();
          setOpenEditDialog(false);
        }}
      />

      {/* Concept Select Dialog */}
      <ConceptSelectDialog
        isOpen={conceptDialogOpen}
        onOpenChange={setConceptDialogOpen}
        onSelect={addSemanticLink}
      />

      {/* Instance Form Dialog */}
      {datasetId && (
        <DatasetInstanceFormDialog
          open={openInstanceDialog}
          onOpenChange={(open) => {
            setOpenInstanceDialog(open);
            if (!open) setEditingInstance(null);
          }}
          datasetId={datasetId}
          instance={editingInstance}
          onSuccess={() => {
            fetchInstances();
            setOpenInstanceDialog(false);
            setEditingInstance(null);
          }}
        />
      )}
    </div>
  );
}

