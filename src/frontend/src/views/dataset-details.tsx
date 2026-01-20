import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
import { RatingPanel } from '@/components/ratings';
import TagChip from '@/components/ui/tag-chip';
import { CommentSidebar } from '@/components/comments';
import ConceptSelectDialog from '@/components/semantic/concept-select-dialog';
import LinkedConceptChips from '@/components/semantic/linked-concept-chips';
import type { EntitySemanticLink } from '@/types/semantic-link';
import { Label } from '@/components/ui/label';
import { Plus, Server } from 'lucide-react';

export default function DatasetDetails() {
  const { t } = useTranslation(['datasets', 'common']);
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
    setStaticSegments([{ label: t('title'), path: '/datasets' }]);
    setDynamicTitle(dataset?.name || t('details.loading'));

    return () => {
      setStaticSegments([]);
      setDynamicTitle(null);
    };
  }, [setStaticSegments, setDynamicTitle, dataset?.name, t]);

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

      if (!response.ok) throw new Error(t('details.subscription.error'));

      const data = await response.json();
      setSubscriptionStatus(data);
      fetchSubscribers();

      toast({
        title: isSubscribed ? t('details.subscription.unsubscribed') : t('details.subscription.subscribed'),
        description: isSubscribed
          ? t('details.subscription.unsubscribeMessage')
          : t('details.subscription.subscribeMessage'),
      });
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: t('details.subscription.error'),
        variant: 'destructive',
      });
    } finally {
      setSubscribing(false);
    }
  };

  // Delete dataset
  const handleDelete = async () => {
    if (!datasetId || !dataset) return;
    if (!confirm(t('details.deleteConfirm', { name: dataset.name }))) return;

    try {
      const response = await fetch(`/api/datasets/${datasetId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(t('details.deleteError'));

      toast({
        title: t('messages.success'),
        description: t('details.deleteSuccess'),
      });
      navigate('/datasets');
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: t('details.deleteError'),
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
        throw new Error(data.detail || t('details.publish.error'));
      }
      
      toast({
        title: t('messages.success'),
        description: t('details.publish.success'),
      });
      fetchDataset();
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: err instanceof Error ? err.message : t('details.publish.error'),
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
        throw new Error(data.detail || t('details.publish.unpublishError'));
      }
      
      toast({
        title: t('messages.success'),
        description: t('details.publish.unpublishSuccess'),
      });
      fetchDataset();
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: err instanceof Error ? err.message : t('details.publish.unpublishError'),
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
      if (!response.ok) throw new Error(t('details.conceptLinkError'));
      await fetchSemanticLinks();
      setConceptDialogOpen(false);
      toast({ title: t('details.subscription.subscribed'), description: t('details.conceptLinked') });
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: err instanceof Error ? err.message : t('details.conceptLinkError'),
        variant: 'destructive',
      });
    }
  };

  // Remove semantic link
  const removeSemanticLink = async (linkId: string) => {
    try {
      const response = await fetch(`/api/semantic-links/${linkId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(t('details.conceptUnlinkError'));
      await fetchSemanticLinks();
      toast({ title: t('details.subscription.unsubscribed'), description: t('details.conceptUnlinked') });
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: err instanceof Error ? err.message : t('details.conceptUnlinkError'),
        variant: 'destructive',
      });
    }
  };

  // Delete instance
  const handleDeleteInstance = async (instanceId: string) => {
    if (!datasetId) return;
    if (!confirm(t('details.instances.removeConfirm'))) return;

    try {
      const response = await fetch(`/api/datasets/${datasetId}/instances/${instanceId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(t('details.instances.removeError'));

      toast({
        title: t('messages.success'),
        description: t('details.instances.removeSuccess'),
      });
      fetchInstances();
    } catch (err) {
      toast({
        title: t('messages.error'),
        description: t('details.instances.removeError'),
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
          {t('details.backToList')}
        </Button>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error || t('details.notFound')}</AlertDescription>
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
          {t('details.backToList')}
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
                <p>{subscriptionStatus?.subscribed ? t('details.unsubscribe') : t('details.subscribe')}</p>
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
              {t('details.publishToMarketplace')}
            </Button>
          )}
          {dataset.published && (
            <Button variant="outline" onClick={handleUnpublish} disabled={publishing}>
              {publishing ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4 mr-2" />
              )}
              {t('details.unpublish')}
            </Button>
          )}
          <Button variant="outline" onClick={() => setOpenEditDialog(true)}>
            <Pencil className="h-4 w-4 mr-2" />
            {t('details.edit')}
          </Button>
          <Button variant="destructive" onClick={handleDelete}>
            <Trash2 className="h-4 w-4 mr-2" />
            {t('details.delete')}
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
            {dataset.description || t('details.noDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid md:grid-cols-3 gap-x-6 gap-y-2">
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">{t('details.coreMetadata.status')}:</Label>
              <div className="flex items-center gap-1.5">
                <Badge
                  variant="outline"
                  className={DATASET_STATUS_COLORS[status] || 'bg-gray-100'}
                >
                  {t(`status.${status}`) || DATASET_STATUS_LABELS[status] || status}
                </Badge>
                {dataset.published && (
                  <Badge variant="default" className="bg-green-600 text-xs">{t('details.published')}</Badge>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">{t('details.coreMetadata.version')}:</Label>
              <Badge variant="outline" className="text-xs">{dataset.version || 'N/A'}</Badge>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">{t('details.coreMetadata.owner')}:</Label>
              {dataset.owner_team_id && dataset.owner_team_name ? (
                <span
                  className="text-xs cursor-pointer text-primary hover:underline truncate"
                  onClick={() => navigate(`/teams/${dataset.owner_team_id}`)}
                  title={`Team ID: ${dataset.owner_team_id}`}
                >
                  {dataset.owner_team_name}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">{dataset.owner_team_name || t('details.coreMetadata.notAssigned')}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">{t('details.coreMetadata.project')}:</Label>
              {dataset.project_id && dataset.project_name ? (
                <span
                  className="text-xs cursor-pointer text-primary hover:underline truncate"
                  onClick={() => navigate(`/projects/${dataset.project_id}`)}
                  title={`Project ID: ${dataset.project_id}`}
                >
                  {dataset.project_name}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">{dataset.project_name || t('details.coreMetadata.notAssigned')}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">{t('details.coreMetadata.created')}:</Label>
              <span className="text-xs text-muted-foreground truncate">
                <RelativeDate date={dataset.created_at} />
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground min-w-[4rem]">{t('details.coreMetadata.updated')}:</Label>
              <span className="text-xs text-muted-foreground truncate">
                <RelativeDate date={dataset.updated_at} />
              </span>
            </div>
          </div>

          <div className="pt-2 border-t">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex-1 min-w-0">
                <Label className="text-xs text-muted-foreground mb-1.5 block">{t('details.coreMetadata.tags')}:</Label>
                <div className="flex flex-wrap gap-1">
                  {dataset.tags && dataset.tags.length > 0 ? (
                    dataset.tags.map((tag, idx) => (
                      <TagChip key={idx} tag={tag} size="sm" />
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">{t('details.coreMetadata.noTags')}</span>
                  )}
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <Label className="text-xs text-muted-foreground mb-1.5 block">{t('details.coreMetadata.linkedConcepts')}:</Label>
                <LinkedConceptChips
                  links={semanticLinks}
                  onRemove={(id) => removeSemanticLink(id)}
                  trailing={<Button size="sm" variant="outline" onClick={() => setConceptDialogOpen(true)} className="h-6 text-xs">{t('details.coreMetadata.addConcept')}</Button>}
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
            {t('details.overview.title')}
          </CardTitle>
          <CardDescription>
            {t('details.overview.subtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                {t('details.overview.version')}
              </label>
              <p className="text-sm">{dataset.version || '-'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                {t('details.overview.physicalInstances')}
              </label>
              <p className="text-sm">
                {t('details.overview.instanceCount', { count: dataset.instance_count || 0 })}
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
            {t('details.contract.title')}
          </CardTitle>
          <CardDescription>
            {t('details.contract.subtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {dataset.contract_id ? (
            <div className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <p className="font-medium">{dataset.contract_name || t('details.contract.linkedContract')}</p>
                <p className="text-sm text-muted-foreground">
                  {t('details.contract.description')}
                </p>
              </div>
              <Button variant="outline" asChild>
                <Link to={`/data-contracts/${dataset.contract_id}`}>
                  <ExternalLink className="h-4 w-4 mr-2" />
                  {t('details.contract.viewContract')}
                </Link>
              </Button>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>{t('details.contract.noContract')}</p>
              <p className="text-sm">
                {t('details.contract.noContractHint')}
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
                {t('details.instances.title')}
                {instances.length > 0 && (
                  <Badge variant="secondary">{instances.length}</Badge>
                )}
              </CardTitle>
              <CardDescription>
                {t('details.instances.subtitle')}
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={handleAddInstance}>
              <Plus className="h-4 w-4 mr-2" />
              {t('details.instances.addInstance')}
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
                        {t(`instanceRole.${role}`) || DATASET_INSTANCE_ROLE_LABELS[role] || role}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        ({roleInstances.length})
                      </span>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t('details.instances.table.name')}</TableHead>
                          <TableHead>{t('details.instances.table.environment')}</TableHead>
                          <TableHead>{t('details.instances.table.physicalPath')}</TableHead>
                          <TableHead>{t('details.instances.table.contract')}</TableHead>
                          <TableHead>{t('details.instances.table.tags')}</TableHead>
                          <TableHead>{t('details.instances.table.status')}</TableHead>
                          <TableHead className="text-right">{t('details.instances.table.actions')}</TableHead>
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
                                  {t(`instanceStatus.${instStatus}`) || DATASET_INSTANCE_STATUS_LABELS[instStatus] || instStatus}
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
              <p>{t('details.instances.noInstances')}</p>
              <p className="text-sm">
                {t('details.instances.noInstancesHint')}
              </p>
              <Button variant="outline" size="sm" className="mt-4" onClick={handleAddInstance}>
                <Plus className="h-4 w-4 mr-2" />
                {t('details.instances.addFirstInstance')}
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
            {t('details.subscribers.title')}
            {subscribers && (
              <Badge variant="secondary">{subscribers.subscriber_count}</Badge>
            )}
          </CardTitle>
          <CardDescription>
            {t('details.subscribers.subtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {subscribers && subscribers.subscribers.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('details.subscribers.table.email')}</TableHead>
                  <TableHead>{t('details.subscribers.table.subscribed')}</TableHead>
                  <TableHead>{t('details.subscribers.table.reason')}</TableHead>
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
              <p>{t('details.subscribers.noSubscribers')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Metadata Panel - Rich texts, links, documents */}
      {datasetId && (
        <EntityMetadataPanel entityId={datasetId} entityType="dataset" />
      )}

      {/* Ratings Panel */}
      {datasetId && (
        <RatingPanel
          entityType="dataset"
          entityId={datasetId}
          title={t('details.ratings.title', 'Ratings & Reviews')}
          showDistribution
          allowSubmit
        />
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

