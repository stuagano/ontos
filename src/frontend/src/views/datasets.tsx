import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { DataTable } from '@/components/ui/data-table';
import { Skeleton } from '@/components/ui/skeleton';
import { RelativeDate } from '@/components/common/relative-date';
import { useToast } from '@/hooks/use-toast';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import { useProjectContext } from '@/stores/project-store';
import {
  Plus,
  Trash2,
  AlertCircle,
  Search,
  Database,
  FileText,
  Users,
  Server,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type {
  DatasetListItem,
  DatasetStatus,
} from '@/types/dataset';
import {
  DATASET_STATUS_LABELS,
  DATASET_STATUS_COLORS,
} from '@/types/dataset';
import DatasetFormDialog from '@/components/datasets/dataset-form-dialog';

export default function Datasets() {
  const { t } = useTranslation(['datasets', 'common']);
  const { toast } = useToast();
  const navigate = useNavigate();
  const { currentProject, hasProjectContext } = useProjectContext();
  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Data state
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog state
  const [openCreateDialog, setOpenCreateDialog] = useState(false);

  // Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Fetch datasets
  const fetchDatasets = useCallback(async () => {
    try {
      setLoading(true);

      const params = new URLSearchParams();
      if (hasProjectContext && currentProject) {
        params.append('project_id', currentProject.id);
      }
      if (searchQuery) {
        params.append('search', searchQuery);
      }
      if (statusFilter && statusFilter !== 'all') {
        params.append('status', statusFilter);
      }

      const queryString = params.toString();
      const endpoint = `/api/datasets${queryString ? `?${queryString}` : ''}`;

      const response = await fetch(endpoint);
      if (!response.ok) throw new Error('Failed to fetch datasets');
      const data = await response.json();
      setDatasets(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch datasets');
    } finally {
      setLoading(false);
    }
  }, [hasProjectContext, currentProject, searchQuery, statusFilter]);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  useEffect(() => {
    // Set breadcrumbs
    setStaticSegments([]);
    setDynamicTitle(t('title'));

    return () => {
      setStaticSegments([]);
      setDynamicTitle(null);
    };
  }, [setStaticSegments, setDynamicTitle, t]);

  // Delete dataset
  const deleteDataset = async (id: string) => {
    if (!confirm(t('messages.deleteConfirm'))) return;

    try {
      const response = await fetch(`/api/datasets/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(t('messages.deleteError'));
      await fetchDatasets();
      toast({
        title: t('messages.success'),
        description: t('messages.deleteSuccess'),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : t('messages.deleteError');
      toast({
        title: t('messages.error'),
        description: message,
        variant: 'destructive',
      });
    }
  };

  // Loading skeleton
  if (loading) {
    return (
      <div className="py-6 space-y-6">
        {/* Header skeleton */}
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-9 w-48" />
            <Skeleton className="h-4 w-72" />
          </div>
          <Skeleton className="h-10 w-32" />
        </div>

        {/* Filters skeleton */}
        <div className="flex flex-wrap items-center gap-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-32" />
        </div>

        {/* Table skeleton */}
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      </div>
    );
  }

  // Table columns
  const columns: ColumnDef<DatasetListItem>[] = [
    {
      accessorKey: 'name',
      header: t('table.name'),
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span
            className="font-medium text-primary hover:underline cursor-pointer"
            onClick={() => navigate(`/datasets/${row.original.id}`)}
          >
            {row.original.name}
          </span>
          {row.original.description && (
            <span className="text-xs text-muted-foreground line-clamp-1">
              {row.original.description}
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: t('table.status'),
      cell: ({ row }) => {
        const status = row.original.status as DatasetStatus;
        return (
          <Badge
            variant="outline"
            className={DATASET_STATUS_COLORS[status] || 'bg-gray-100'}
          >
            {t(`status.${status}`) || DATASET_STATUS_LABELS[status] || status}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'instance_count',
      header: t('table.instances'),
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          <Server className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm">
            {row.original.instance_count || 0}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'contract_name',
      header: t('table.contract'),
      cell: ({ row }) => {
        if (!row.original.contract_id) {
          return <span className="text-muted-foreground text-sm">-</span>;
        }
        return (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className="flex items-center gap-1 cursor-pointer hover:text-primary"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/data-contracts/${row.original.contract_id}`);
                  }}
                >
                  <FileText className="h-3 w-3" />
                  <span className="text-sm truncate max-w-[150px]">
                    {row.original.contract_name || t('table.viewContract')}
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>{t('table.viewContract')}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      },
    },
    {
      accessorKey: 'owner_team_name',
      header: t('table.owner'),
      cell: ({ row }) => {
        if (!row.original.owner_team_id) {
          return <span className="text-muted-foreground text-sm">-</span>;
        }
        return (
          <div className="flex items-center gap-1">
            <Users className="h-3 w-3 text-muted-foreground" />
            <span className="text-sm">{row.original.owner_team_name || t('table.owner')}</span>
          </div>
        );
      },
    },
    {
      accessorKey: 'subscriber_count',
      header: t('table.subscribers'),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.subscriber_count || 0}
        </span>
      ),
    },
    {
      accessorKey: 'version',
      header: t('table.version'),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground font-mono">
          {row.original.version || '-'}
        </span>
      ),
    },
    {
      accessorKey: 'updated_at',
      header: t('table.updated'),
      cell: ({ row }) => (
        <RelativeDate date={row.original.updated_at} />
      ),
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-destructive hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteDataset(row.original.id);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{t('table.deleteDataset')}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      ),
    },
  ];

  return (
    <div className="py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Database className="w-8 h-8" />
            {t('title')}
          </h1>
          <p className="text-muted-foreground">
            {t('subtitle')}
          </p>
        </div>
        <Button onClick={() => setOpenCreateDialog(true)}>
          <Plus className="h-4 w-4 mr-2" />
          {t('newDataset')}
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t('searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder={t('table.status')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('filters.allStatus')}</SelectItem>
            <SelectItem value="draft">{t('filters.draft')}</SelectItem>
            <SelectItem value="active">{t('filters.active')}</SelectItem>
            <SelectItem value="deprecated">{t('filters.deprecated')}</SelectItem>
            <SelectItem value="retired">{t('filters.retired')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Data Table */}
      <DataTable
        columns={columns}
        data={datasets}
        onRowClick={(row) => navigate(`/datasets/${row.id}`)}
      />

      {/* Create Dialog */}
      <DatasetFormDialog
        open={openCreateDialog}
        onOpenChange={setOpenCreateDialog}
        onSuccess={() => {
          fetchDatasets();
          setOpenCreateDialog(false);
        }}
      />
    </div>
  );
}
