import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Plus, Database, FileText, Sparkles, Download, Archive, Eye, Loader2 } from 'lucide-react';
import { ListViewSkeleton } from '@/components/common/list-view-skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ColumnDef } from "@tanstack/react-table";
import { useApi } from '@/hooks/use-api';
import {
  TrainingCollection,
  TrainingCollectionStatus,
  COLLECTION_STATUS_COLORS,
  Sheet,
  PromptTemplate,
} from '@/types/training-data';
import { useToast } from "@/hooks/use-toast";
import { Toaster } from "@/components/ui/toaster";
import { RelativeDate } from '@/components/common/relative-date';
import { useNavigate } from 'react-router-dom';
import { DataTable } from "@/components/ui/data-table";
import TrainingCollectionFormDialog from '@/components/training-data/training-collection-form-dialog';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

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

export default function TrainingDataCuration() {
  const { t } = useTranslation(['training-data', 'common']);
  const [collections, setCollections] = useState<TrainingCollection[]>([]);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [collectionToEdit, setCollectionToEdit] = useState<TrainingCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'collections' | 'sheets' | 'templates'>('collections');

  const api = useApi();
  const { get, post, delete: deleteApi } = api;
  const { toast } = useToast();
  const navigate = useNavigate();
  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Permissions
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const featureId = 'training-data';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  // Load initial data
  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Training Data Curation');

    const loadInitialData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [collectionsResp, sheetsResp, templatesResp] = await Promise.all([
          get<TrainingCollection[]>('/api/training-data/collections'),
          get<Sheet[]>('/api/training-data/sheets'),
          get<PromptTemplate[]>('/api/training-data/templates'),
        ]);

        const collectionsData = checkApiResponse(collectionsResp, 'Collections');
        const sheetsData = checkApiResponse(sheetsResp, 'Sheets');
        const templatesData = checkApiResponse(templatesResp, 'Templates');

        setCollections(Array.isArray(collectionsData) ? collectionsData : []);
        setSheets(Array.isArray(sheetsData) ? sheetsData : []);
        setTemplates(Array.isArray(templatesData) ? templatesData : []);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to load data';
        setError(message);
        setCollections([]);
        setSheets([]);
        setTemplates([]);
      } finally {
        setLoading(false);
      }
    };

    if (!permissionsLoading && canRead) {
      loadInitialData();
    }
  }, [permissionsLoading, canRead, get, setStaticSegments, setDynamicTitle]);

  // Collection columns
  const collectionColumns: ColumnDef<TrainingCollection>[] = useMemo(() => [
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="font-medium">{row.original.name}</span>
          {row.original.description && (
            <span className="text-sm text-muted-foreground truncate max-w-[300px]">
              {row.original.description}
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.original.status;
        const colorClasses = COLLECTION_STATUS_COLORS[status] || 'bg-gray-100 text-gray-800';
        return (
          <Badge className={colorClasses}>
            {status.replace('_', ' ')}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'total_pairs',
      header: 'QA Pairs',
      cell: ({ row }) => (
        <div className="flex flex-col text-sm">
          <span>{row.original.total_pairs} total</span>
          <span className="text-green-600">{row.original.approved_pairs} approved</span>
          <span className="text-yellow-600">{row.original.pending_pairs} pending</span>
        </div>
      ),
    },
    {
      accessorKey: 'generation_method',
      header: 'Method',
      cell: ({ row }) => (
        <Badge variant="outline">
          {row.original.generation_method}
        </Badge>
      ),
    },
    {
      accessorKey: 'version',
      header: 'Version',
    },
    {
      accessorKey: 'updated_at',
      header: 'Updated',
      cell: ({ row }) => <RelativeDate date={row.original.updated_at} />,
    },
  ], []);

  // Sheet columns
  const sheetColumns: ColumnDef<Sheet>[] = useMemo(() => [
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="font-medium">{row.original.name}</span>
          {row.original.description && (
            <span className="text-sm text-muted-foreground truncate max-w-[300px]">
              {row.original.description}
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'source_type',
      header: 'Source',
      cell: ({ row }) => {
        const source = row.original;
        let sourceLabel = source.source_type.replace('_', ' ');
        if (source.source_table) {
          sourceLabel = `${source.source_catalog}.${source.source_schema}.${source.source_table}`;
        }
        return <span className="font-mono text-sm">{sourceLabel}</span>;
      },
    },
    {
      accessorKey: 'text_columns',
      header: 'Text Columns',
      cell: ({ row }) => (
        <span className="text-sm">
          {row.original.text_columns?.join(', ') || '-'}
        </span>
      ),
    },
    {
      accessorKey: 'sampling_strategy',
      header: 'Sampling',
      cell: ({ row }) => (
        <Badge variant="outline">
          {row.original.sampling_strategy}
          {row.original.sample_size && ` (${row.original.sample_size})`}
        </Badge>
      ),
    },
    {
      accessorKey: 'updated_at',
      header: 'Updated',
      cell: ({ row }) => <RelativeDate date={row.original.updated_at} />,
    },
  ], []);

  // Template columns
  const templateColumns: ColumnDef<PromptTemplate>[] = useMemo(() => [
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="font-medium">{row.original.name}</span>
          {row.original.description && (
            <span className="text-sm text-muted-foreground truncate max-w-[300px]">
              {row.original.description}
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.original.status;
        const statusColors: Record<string, string> = {
          draft: 'bg-gray-100 text-gray-800',
          active: 'bg-green-100 text-green-800',
          deprecated: 'bg-yellow-100 text-yellow-800',
          archived: 'bg-gray-100 text-gray-600',
        };
        return (
          <Badge className={statusColors[status] || 'bg-gray-100 text-gray-800'}>
            {status}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'label_type',
      header: 'Label Type',
      cell: ({ row }) => (
        <Badge variant="outline">
          {row.original.label_type || 'custom'}
        </Badge>
      ),
    },
    {
      accessorKey: 'version',
      header: 'Version',
    },
    {
      accessorKey: 'updated_at',
      header: 'Updated',
      cell: ({ row }) => <RelativeDate date={row.original.updated_at} />,
    },
  ], []);

  // Handle collection row click
  const handleCollectionRowClick = (row: { original: TrainingCollection }) => {
    navigate(`/training-data/collections/${row.original.id}`);
  };

  // Handle collection create/update
  const handleCollectionSaved = (collection: TrainingCollection) => {
    if (collectionToEdit) {
      setCollections(prev => prev.map(c => c.id === collection.id ? collection : c));
    } else {
      setCollections(prev => [...prev, collection]);
    }
    setIsCreateDialogOpen(false);
    setCollectionToEdit(null);
    toast({
      title: collectionToEdit ? 'Collection updated' : 'Collection created',
      description: `"${collection.name}" has been ${collectionToEdit ? 'updated' : 'created'} successfully.`,
    });
  };

  // Loading state
  if (loading || permissionsLoading) {
    return <ListViewSkeleton />;
  }

  // Permission denied
  if (!canRead) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          You do not have permission to view training data.
        </AlertDescription>
      </Alert>
    );
  }

  // Error state
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <Toaster />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Training Data Curation</h1>
          <p className="text-muted-foreground">
            Manage ML training collections, data sheets, and prompt templates
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          <TabsTrigger value="collections" className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            Collections ({collections.length})
          </TabsTrigger>
          <TabsTrigger value="sheets" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Sheets ({sheets.length})
          </TabsTrigger>
          <TabsTrigger value="templates" className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Templates ({templates.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="collections" className="mt-4">
          <DataTable
            columns={collectionColumns}
            data={collections}
            searchColumn="name"
            onRowClick={handleCollectionRowClick}
            storageKey="training-collections-sort"
            toolbarActions={
              canWrite && (
                <Button onClick={() => setIsCreateDialogOpen(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  New Collection
                </Button>
              )
            }
            bulkActions={(selectedRows) => (
              <div className="flex items-center gap-2">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="outline" size="sm" disabled>
                        <Download className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Export selected</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="outline" size="sm" disabled>
                        <Archive className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Archive selected</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            )}
          />
        </TabsContent>

        <TabsContent value="sheets" className="mt-4">
          <DataTable
            columns={sheetColumns}
            data={sheets}
            searchColumn="name"
            storageKey="training-sheets-sort"
            toolbarActions={
              canWrite && (
                <Button onClick={() => toast({ title: 'Coming soon', description: 'Sheet creation dialog will be added.' })}>
                  <Plus className="mr-2 h-4 w-4" />
                  New Sheet
                </Button>
              )
            }
          />
        </TabsContent>

        <TabsContent value="templates" className="mt-4">
          <DataTable
            columns={templateColumns}
            data={templates}
            searchColumn="name"
            storageKey="training-templates-sort"
            toolbarActions={
              canWrite && (
                <Button onClick={() => toast({ title: 'Coming soon', description: 'Template creation dialog will be added.' })}>
                  <Plus className="mr-2 h-4 w-4" />
                  New Template
                </Button>
              )
            }
          />
        </TabsContent>
      </Tabs>

      {/* Collection Form Dialog */}
      <TrainingCollectionFormDialog
        open={isCreateDialogOpen || !!collectionToEdit}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateDialogOpen(false);
            setCollectionToEdit(null);
          }
        }}
        collection={collectionToEdit}
        sheets={sheets}
        templates={templates}
        onSaved={handleCollectionSaved}
      />
    </div>
  );
}
