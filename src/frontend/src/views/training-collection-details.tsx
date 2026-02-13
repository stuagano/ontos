import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';
import { usePermissions } from '@/stores/permissions-store';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import { FeatureAccessLevel } from '@/types/settings';
import {
  TrainingCollection,
  QAPair,
  QAPairReviewStatus,
  REVIEW_STATUS_COLORS,
  GenerationRequest,
  GenerationResult,
  ExportRequest,
  ExportResult,
  ExportFormat,
} from '@/types/training-data';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { DetailViewSkeleton } from '@/components/common/list-view-skeleton';
import { DataTable } from '@/components/ui/data-table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { RelativeDate } from '@/components/common/relative-date';
import { ColumnDef, Row } from '@tanstack/react-table';
import {
  ArrowLeft,
  Sparkles,
  Download,
  CheckCircle,
  XCircle,
  AlertCircle,
  Edit,
  Eye,
  Loader2,
  RefreshCw,
  FileText,
} from 'lucide-react';
import QAPairReviewDialog from '@/components/training-data/qa-pair-review-dialog';
import GenerationDialog from '@/components/training-data/generation-dialog';
import ExportDialog from '@/components/training-data/export-dialog';

// API response helper
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

export default function TrainingCollectionDetails() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const api = useApi();
  const { get, post, put } = api;

  // State
  const [collection, setCollection] = useState<TrainingCollection | null>(null);
  const [pairs, setPairs] = useState<QAPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPair, setSelectedPair] = useState<QAPair | null>(null);
  const [isReviewDialogOpen, setIsReviewDialogOpen] = useState(false);
  const [isGenerationDialogOpen, setIsGenerationDialogOpen] = useState(false);
  const [isExportDialogOpen, setIsExportDialogOpen] = useState(false);
  const [selectedPairIds, setSelectedPairIds] = useState<string[]>([]);
  const [isBulkReviewing, setIsBulkReviewing] = useState(false);

  // Breadcrumbs
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);
  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);

  // Permissions
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const featureId = 'training-data';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  // Fetch collection and pairs
  const fetchData = async () => {
    if (!collectionId) {
      setError('Collection ID not provided');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setStaticSegments([{ label: 'Training Data', path: '/training-data' }]);
    setDynamicTitle('Loading...');

    try {
      const [collectionResp, pairsResp] = await Promise.all([
        get<TrainingCollection>(`/api/training-data/collections/${collectionId}`),
        get<QAPair[]>(`/api/training-data/collections/${collectionId}/pairs`),
      ]);

      const collectionData = checkApiResponse(collectionResp, 'Collection');
      setCollection(collectionData);
      setDynamicTitle(collectionData.name);

      setPairs(Array.isArray(pairsResp.data) ? pairsResp.data : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load collection';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!permissionsLoading && canRead) {
      fetchData();
    }
  }, [collectionId, permissionsLoading, canRead]);

  // QA pair columns
  const pairColumns: ColumnDef<QAPair>[] = useMemo(() => [
    {
      id: 'select',
      header: ({ table }) => (
        <input
          type="checkbox"
          checked={table.getIsAllPageRowsSelected()}
          onChange={(e) => table.toggleAllPageRowsSelected(e.target.checked)}
          className="h-4 w-4"
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={(e) => row.toggleSelected(e.target.checked)}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4"
        />
      ),
      enableSorting: false,
      enableHiding: false,
    },
    {
      accessorKey: 'messages',
      header: 'Preview',
      cell: ({ row }) => {
        const messages = row.original.messages;
        const userMsg = messages.find(m => m.role === 'user');
        const assistantMsg = messages.find(m => m.role === 'assistant');
        return (
          <div className="space-y-1 max-w-[400px]">
            <div className="text-sm">
              <span className="font-medium text-blue-600">User:</span>{' '}
              <span className="truncate">{userMsg?.content?.substring(0, 100) || '-'}...</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-green-600">Assistant:</span>{' '}
              <span className="truncate">{assistantMsg?.content?.substring(0, 100) || '-'}...</span>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: 'review_status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.original.review_status;
        const colorClasses = REVIEW_STATUS_COLORS[status] || 'bg-gray-100 text-gray-800';
        return (
          <Badge className={colorClasses}>
            {status.replace('_', ' ')}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'quality_score',
      header: 'Quality',
      cell: ({ row }) => {
        const score = row.original.quality_score;
        if (score === null || score === undefined) return <span className="text-muted-foreground">-</span>;
        const color = score >= 0.8 ? 'text-green-600' : score >= 0.5 ? 'text-yellow-600' : 'text-red-600';
        return <span className={`font-medium ${color}`}>{(score * 100).toFixed(0)}%</span>;
      },
    },
    {
      accessorKey: 'split',
      header: 'Split',
      cell: ({ row }) => {
        const split = row.original.split;
        if (!split) return <span className="text-muted-foreground">-</span>;
        return <Badge variant="outline">{split}</Badge>;
      },
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => <RelativeDate date={row.original.created_at} />,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedPair(row.original);
            setIsReviewDialogOpen(true);
          }}
        >
          <Eye className="h-4 w-4" />
        </Button>
      ),
    },
  ], []);

  // Handle bulk review
  const handleBulkReview = async (status: QAPairReviewStatus, notes?: string) => {
    if (selectedPairIds.length === 0) return;

    setIsBulkReviewing(true);
    try {
      const response = await post('/api/training-data/pairs/bulk-review', {
        pair_ids: selectedPairIds,
        review_status: status,
        review_notes: notes,
      });

      if (response.error) {
        throw new Error(response.error);
      }

      // Refresh pairs
      await fetchData();
      setSelectedPairIds([]);
      toast({
        title: 'Bulk review complete',
        description: `${selectedPairIds.length} pairs updated to ${status}`,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to bulk review';
      toast({ variant: 'destructive', title: 'Error', description: message });
    } finally {
      setIsBulkReviewing(false);
    }
  };

  // Handle generation
  const handleGenerate = async (request: GenerationRequest) => {
    try {
      const response = await post<GenerationResult>(
        `/api/training-data/collections/${collectionId}/generate`,
        request
      );

      if (response.error) {
        throw new Error(response.error);
      }

      toast({
        title: 'Generation complete',
        description: `Generated ${response.data.pairs_generated} pairs (${response.data.pairs_auto_approved} auto-approved)`,
      });

      await fetchData();
      setIsGenerationDialogOpen(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Generation failed';
      toast({ variant: 'destructive', title: 'Error', description: message });
    }
  };

  // Handle export
  const handleExport = async (request: ExportRequest) => {
    try {
      const response = await post<ExportResult>(
        `/api/training-data/collections/${collectionId}/export`,
        request
      );

      if (response.error) {
        throw new Error(response.error);
      }

      toast({
        title: 'Export complete',
        description: `Exported ${response.data.pairs_exported} pairs to ${response.data.output_path}`,
      });

      setIsExportDialogOpen(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Export failed';
      toast({ variant: 'destructive', title: 'Error', description: message });
    }
  };

  // Handle pair review save
  const handlePairReviewSaved = async () => {
    await fetchData();
    setIsReviewDialogOpen(false);
    setSelectedPair(null);
  };

  // Row click handler
  const handleRowClick = (row: Row<QAPair>) => {
    setSelectedPair(row.original);
    setIsReviewDialogOpen(true);
  };

  // Loading state
  if (loading || permissionsLoading) {
    return <DetailViewSkeleton />;
  }

  // Error state
  if (error || !collection) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error || 'Collection not found'}</AlertDescription>
      </Alert>
    );
  }

  // Calculate stats
  const approvalRate = collection.total_pairs > 0
    ? ((collection.approved_pairs / collection.total_pairs) * 100).toFixed(1)
    : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/training-data')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{collection.name}</h1>
            <p className="text-muted-foreground">{collection.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => fetchData()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          {canWrite && (
            <>
              <Button variant="outline" onClick={() => setIsGenerationDialogOpen(true)}>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate
              </Button>
              <Button onClick={() => setIsExportDialogOpen(true)}>
                <Download className="mr-2 h-4 w-4" />
                Export
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Pairs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{collection.total_pairs}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Approved</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{collection.approved_pairs}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Pending Review</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-600">{collection.pending_pairs}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Approval Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{approvalRate}%</div>
            <Progress value={Number(approvalRate)} className="mt-2" />
          </CardContent>
        </Card>
      </div>

      {/* Collection Info */}
      <Card>
        <CardHeader>
          <CardTitle>Collection Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <span className="text-sm text-muted-foreground">Status</span>
              <div className="mt-1">
                <Badge className={REVIEW_STATUS_COLORS[collection.status as keyof typeof REVIEW_STATUS_COLORS] || 'bg-gray-100'}>
                  {collection.status}
                </Badge>
              </div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Version</span>
              <div className="mt-1 font-medium">{collection.version}</div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Generation Method</span>
              <div className="mt-1 font-medium">{collection.generation_method}</div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Model</span>
              <div className="mt-1 font-medium">{collection.model_used || 'Not specified'}</div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Train/Val/Test Split</span>
              <div className="mt-1 font-medium">
                {(collection.default_train_ratio * 100).toFixed(0)}% / {(collection.default_val_ratio * 100).toFixed(0)}% / {(collection.default_test_ratio * 100).toFixed(0)}%
              </div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Last Updated</span>
              <div className="mt-1">
                <RelativeDate date={collection.updated_at} />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* QA Pairs Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>QA Pairs</span>
            {selectedPairIds.length > 0 && canWrite && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {selectedPairIds.length} selected
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleBulkReview(QAPairReviewStatus.APPROVED)}
                  disabled={isBulkReviewing}
                >
                  {isBulkReviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                  Approve
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleBulkReview(QAPairReviewStatus.REJECTED)}
                  disabled={isBulkReviewing}
                >
                  {isBulkReviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                  Reject
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleBulkReview(QAPairReviewStatus.FLAGGED)}
                  disabled={isBulkReviewing}
                >
                  {isBulkReviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertCircle className="h-4 w-4" />}
                  Flag
                </Button>
              </div>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={pairColumns}
            data={pairs}
            searchColumn="messages"
            onRowClick={handleRowClick}
            storageKey={`training-pairs-${collectionId}-sort`}
            rowSelection={pairs.reduce((acc, pair, idx) => {
              if (selectedPairIds.includes(pair.id)) {
                acc[idx] = true;
              }
              return acc;
            }, {} as Record<number, boolean>)}
            onRowSelectionChange={(selection) => {
              const ids = Object.keys(selection)
                .filter(k => selection[parseInt(k)])
                .map(k => pairs[parseInt(k)].id);
              setSelectedPairIds(ids);
            }}
          />
        </CardContent>
      </Card>

      {/* Review Dialog */}
      {selectedPair && (
        <QAPairReviewDialog
          open={isReviewDialogOpen}
          onOpenChange={(open) => {
            setIsReviewDialogOpen(open);
            if (!open) setSelectedPair(null);
          }}
          pair={selectedPair}
          onSaved={handlePairReviewSaved}
          canEdit={canWrite}
        />
      )}

      {/* Generation Dialog */}
      <GenerationDialog
        open={isGenerationDialogOpen}
        onOpenChange={setIsGenerationDialogOpen}
        collectionId={collectionId!}
        onGenerate={handleGenerate}
      />

      {/* Export Dialog */}
      <ExportDialog
        open={isExportDialogOpen}
        onOpenChange={setIsExportDialogOpen}
        collectionId={collectionId!}
        onExport={handleExport}
      />
    </div>
  );
}
