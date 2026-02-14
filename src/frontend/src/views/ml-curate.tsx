/**
 * MlCurate - Q&A pair review and labeling for training collections
 *
 * Ported from VITAL CuratePage. Provides:
 * - Training collection browser
 * - QA pair grid/list view with detail panel
 * - Status-based filtering (empty, AI generated, verified, etc.)
 * - Inline editing and verification of responses
 * - Stats bar showing review progress
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CheckCircle,
  Edit3,
  ChevronLeft,
  ChevronRight,
  Wand2,
  Loader2,
  FileText,
  X,
  LayoutGrid,
  List,
  Database,
  Layers,
  Download,
  Plus,
  RefreshCw,
  Eye,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
  QAPair,
  QAPairReviewStatus,
  REVIEW_STATUS_COLORS,
} from '@/types/training-data';

// Response source colors for QA pairs
const sourceColors: Record<string, string> = {
  empty: 'bg-muted text-muted-foreground',
  imported: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  ai_generated: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  human_labeled: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  human_verified: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  canonical: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
};

const sourceLabels: Record<string, string> = {
  empty: 'Empty',
  imported: 'Imported',
  ai_generated: 'AI Generated',
  human_labeled: 'Human Labeled',
  human_verified: 'Verified',
  canonical: 'Canonical',
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
// Stats Bar
// ============================================================================

interface StatsBarProps {
  collection: TrainingCollection;
  qaPairs: QAPair[];
}

function StatsBar({ collection, qaPairs }: StatsBarProps) {
  const total = qaPairs.length || 1;
  const approved = qaPairs.filter(q => q.review_status === 'approved').length;
  const pending = qaPairs.filter(q => q.review_status === 'pending_review').length;
  const rejected = qaPairs.filter(q => q.review_status === 'rejected').length;

  const segments = [
    { key: 'approved', count: approved, color: 'bg-green-500', label: 'Approved' },
    { key: 'pending', count: pending, color: 'bg-amber-500', label: 'Pending Review' },
    { key: 'rejected', count: rejected, color: 'bg-red-500', label: 'Rejected' },
  ];

  return (
    <div className="space-y-2">
      <div className="h-3 bg-muted rounded-full overflow-hidden flex">
        {segments.map(seg => (
          <div
            key={seg.key}
            className={cn('h-full transition-all duration-300', seg.color)}
            style={{ width: `${((seg.count || 0) / total) * 100}%` }}
            title={`${seg.label}: ${seg.count}`}
          />
        ))}
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        {segments.filter(s => s.count > 0).map(seg => (
          <div key={seg.key} className="flex items-center gap-1.5">
            <div className={cn('w-2 h-2 rounded-full', seg.color)} />
            <span>{seg.label}: {seg.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// QA Pair Card
// ============================================================================

interface QAPairCardProps {
  pair: QAPair;
  isSelected: boolean;
  onSelect: () => void;
}

function QAPairCard({ pair, isSelected, onSelect }: QAPairCardProps) {
  const statusColor = REVIEW_STATUS_COLORS[pair.review_status] || 'bg-muted text-muted-foreground';

  return (
    <div
      className={cn(
        'bg-card rounded-lg border-2 p-4 cursor-pointer transition-all',
        isSelected
          ? 'border-primary shadow-md'
          : 'border-border hover:border-muted-foreground/30'
      )}
      onClick={onSelect}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-muted-foreground">#{pair.id?.slice(0, 8)}</span>
        <Badge variant="outline" className={statusColor}>
          {pair.review_status?.replace('_', ' ')}
        </Badge>
      </div>

      {/* Question preview */}
      <div className="bg-muted rounded-lg p-3 mb-3 text-xs font-mono overflow-hidden max-h-20">
        <p className="line-clamp-3">{pair.question}</p>
      </div>

      {/* Answer preview */}
      {pair.answer ? (
        <div className="bg-primary/5 rounded-lg p-2 text-xs font-mono overflow-hidden max-h-16">
          <p className="line-clamp-2 text-primary">{pair.answer}</p>
        </div>
      ) : (
        <div className="bg-muted rounded-lg p-2 text-xs text-muted-foreground italic">
          No answer yet
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Detail Panel
// ============================================================================

interface DetailPanelProps {
  pair: QAPair;
  onClose: () => void;
  onSave: (answer: string, status: QAPairReviewStatus) => void;
  onNext: () => void;
  onPrevious: () => void;
  hasNext: boolean;
  hasPrevious: boolean;
  isSaving: boolean;
}

function DetailPanel({
  pair,
  onClose,
  onSave,
  onNext,
  onPrevious,
  hasNext,
  hasPrevious,
  isSaving,
}: DetailPanelProps) {
  const [editedAnswer, setEditedAnswer] = useState(pair.answer || '');
  const [reviewStatus, setReviewStatus] = useState<QAPairReviewStatus>(pair.review_status || 'pending_review');

  useEffect(() => {
    setEditedAnswer(pair.answer || '');
    setReviewStatus(pair.review_status || 'pending_review');
  }, [pair.id, pair.answer, pair.review_status]);

  const hasChanges = editedAnswer !== (pair.answer || '') || reviewStatus !== pair.review_status;

  return (
    <div className="w-[520px] bg-card border-l flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">QA Pair</span>
          <Badge variant="outline" className={REVIEW_STATUS_COLORS[pair.review_status] || ''}>
            {pair.review_status?.replace('_', ' ')}
          </Badge>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Source Data */}
        {pair.source_context && (
          <div>
            <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-600" />
              Source Context
            </h3>
            <div className="bg-muted rounded-lg p-3 font-mono text-xs overflow-auto max-h-32">
              <pre>{typeof pair.source_context === 'string' ? pair.source_context : JSON.stringify(pair.source_context, null, 2)}</pre>
            </div>
          </div>
        )}

        {/* Question */}
        <div>
          <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            Question
          </h3>
          <div className="bg-primary/5 rounded-lg p-3 font-mono text-sm whitespace-pre-wrap">
            {pair.question}
          </div>
        </div>

        {/* Answer Editor */}
        <div>
          <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
            <Edit3 className="w-4 h-4 text-green-600" />
            Answer
          </h3>
          <textarea
            value={editedAnswer}
            onChange={e => setEditedAnswer(e.target.value)}
            placeholder="Enter the expected answer..."
            rows={8}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary font-mono text-sm resize-none bg-background"
          />
        </div>

        {/* Review Status */}
        <div>
          <h3 className="text-sm font-medium mb-2">Review Status</h3>
          <div className="flex gap-2">
            {(['approved', 'pending_review', 'rejected'] as QAPairReviewStatus[]).map(status => (
              <Button
                key={status}
                variant={reviewStatus === status ? 'default' : 'outline'}
                size="sm"
                onClick={() => setReviewStatus(status)}
                className={reviewStatus === status ? '' : 'text-muted-foreground'}
              >
                {status === 'approved' && <CheckCircle className="w-3 h-3 mr-1" />}
                {status.replace('_', ' ')}
              </Button>
            ))}
          </div>
        </div>

        {/* Metadata */}
        {(pair.reviewed_by || pair.reviewed_at) && (
          <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t">
            {pair.reviewed_by && <div>Reviewed by: {pair.reviewed_by}</div>}
            {pair.reviewed_at && <div>Reviewed at: {new Date(pair.reviewed_at).toLocaleString()}</div>}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="border-t p-4 space-y-3">
        <Button
          onClick={() => onSave(editedAnswer, reviewStatus)}
          disabled={isSaving || !hasChanges}
          className="w-full"
        >
          {isSaving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <CheckCircle className="w-4 h-4 mr-2" />}
          Save Changes
        </Button>

        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={onPrevious} disabled={!hasPrevious}>
            <ChevronLeft className="w-4 h-4 mr-1" /> Previous
          </Button>
          <Button variant="ghost" size="sm" onClick={onNext} disabled={!hasNext}>
            Next <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function MlCurate() {
  const { t } = useTranslation(['training-data', 'common']);
  const [collections, setCollections] = useState<TrainingCollection[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [qaPairs, setQaPairs] = useState<QAPair[]>([]);
  const [selectedPairId, setSelectedPairId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<QAPairReviewStatus | ''>('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [loading, setLoading] = useState(true);
  const [pairsLoading, setPairsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const api = useApi();
  const { get, put } = api;
  const { toast } = useToast();
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const setStaticSegments = useBreadcrumbStore(state => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore(state => state.setDynamicTitle);

  const featureId = 'training-data';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  // Breadcrumbs
  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Curate & Review');
  }, [setStaticSegments, setDynamicTitle]);

  // Load collections
  useEffect(() => {
    const loadCollections = async () => {
      setLoading(true);
      try {
        const resp = await get<TrainingCollection[]>('/api/training-data/collections');
        const data = checkApiResponse(resp, 'Collections');
        setCollections(Array.isArray(data) ? data : []);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load collections');
      } finally {
        setLoading(false);
      }
    };
    if (canRead) loadCollections();
  }, [get, canRead]);

  // Load QA pairs when collection selected
  useEffect(() => {
    if (!selectedCollectionId) {
      setQaPairs([]);
      return;
    }
    const loadPairs = async () => {
      setPairsLoading(true);
      try {
        const resp = await get<QAPair[]>(
          `/api/training-data/collections/${selectedCollectionId}/qa-pairs`
        );
        const data = checkApiResponse(resp, 'QA Pairs');
        setQaPairs(Array.isArray(data) ? data : []);
      } catch (err: unknown) {
        toast({
          title: 'Failed to load QA pairs',
          description: err instanceof Error ? err.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setPairsLoading(false);
      }
    };
    loadPairs();
  }, [get, selectedCollectionId, toast]);

  // Filtered pairs
  const filteredPairs = useMemo(() => {
    if (!statusFilter) return qaPairs;
    return qaPairs.filter(p => p.review_status === statusFilter);
  }, [qaPairs, statusFilter]);

  const selectedPair = filteredPairs.find(p => p.id === selectedPairId) || null;
  const selectedIndex = filteredPairs.findIndex(p => p.id === selectedPairId);
  const selectedCollection = collections.find(c => c.id === selectedCollectionId) || null;

  // Save pair
  const handleSavePair = async (answer: string, status: QAPairReviewStatus) => {
    if (!selectedCollectionId || !selectedPairId) return;
    setSaving(true);
    try {
      await put(`/api/training-data/collections/${selectedCollectionId}/qa-pairs/${selectedPairId}`, {
        answer,
        review_status: status,
      });
      setQaPairs(prev =>
        prev.map(p => (p.id === selectedPairId ? { ...p, answer, review_status: status } : p))
      );
      toast({ title: 'Saved', description: 'QA pair updated successfully.' });
    } catch (err: unknown) {
      toast({
        title: 'Save failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (filteredPairs.length === 0) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if (e.key === 'ArrowLeft' && selectedIndex > 0) {
        e.preventDefault();
        setSelectedPairId(filteredPairs[selectedIndex - 1].id);
      } else if (e.key === 'ArrowRight' && selectedIndex < filteredPairs.length - 1) {
        e.preventDefault();
        setSelectedPairId(filteredPairs[selectedIndex + 1].id);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        setSelectedPairId(null);
      }
    },
    [filteredPairs, selectedIndex]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Permission guard
  if (!permissionsLoading && !canRead) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">You don't have permission to access this feature.</p>
      </div>
    );
  }

  // Collection browser (no collection selected)
  if (!selectedCollectionId) {
    const columns: ColumnDef<TrainingCollection>[] = [
      {
        accessorKey: 'name',
        header: 'Collection',
        cell: ({ row }) => (
          <div className="flex items-center gap-3">
            <Layers className="w-4 h-4 text-primary flex-shrink-0" />
            <div>
              <div className="font-medium">{row.original.name}</div>
              {row.original.description && (
                <div className="text-sm text-muted-foreground truncate max-w-[300px]">
                  {row.original.description}
                </div>
              )}
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
        cell: ({ row }) => (
          <span className="text-sm">{row.original.qa_pair_count ?? 0}</span>
        ),
      },
      {
        id: 'actions',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedCollectionId(row.original.id)}
          >
            <Eye className="w-4 h-4 mr-1" /> Review
          </Button>
        ),
      },
    ];

    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Curate & Review</h1>
            <p className="text-muted-foreground mt-1">
              Review and label Q&A pairs in training collections
            </p>
          </div>
          <Button variant="outline" onClick={() => setLoading(l => { /* trigger refresh */ return l; })}>
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
        </div>

        {error && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-lg">{error}</div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : (
          <DataTable columns={columns} data={collections} />
        )}
      </div>
    );
  }

  // QA Pair Review View
  return (
    <div className="flex-1 flex h-full">
      <div className="flex-1 p-6 overflow-auto">
        <div className="max-w-6xl mx-auto">
          {/* Back + Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSelectedCollectionId(null);
                  setSelectedPairId(null);
                }}
                className="mb-2"
              >
                <ChevronLeft className="w-4 h-4 mr-1" /> Back to Collections
              </Button>
              <h1 className="text-2xl font-bold">
                {selectedCollection?.name || 'Review QA Pairs'}
              </h1>
              <p className="text-muted-foreground mt-1">
                {filteredPairs.length} of {qaPairs.length} pairs shown
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
                <Button
                  variant={viewMode === 'grid' ? 'secondary' : 'ghost'}
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setViewMode('grid')}
                >
                  <LayoutGrid className="w-4 h-4" />
                </Button>
                <Button
                  variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setViewMode('list')}
                >
                  <List className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>

          {/* Stats Bar */}
          {selectedCollection && qaPairs.length > 0 && (
            <Card className="mb-6">
              <CardContent className="pt-4">
                <StatsBar collection={selectedCollection} qaPairs={qaPairs} />
              </CardContent>
            </Card>
          )}

          {/* Status Filter */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm text-muted-foreground">Filter:</span>
            {(['', 'pending_review', 'approved', 'rejected'] as const).map(status => (
              <Button
                key={status}
                variant={statusFilter === status ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter(status)}
              >
                {status ? status.replace('_', ' ') : 'All'}
              </Button>
            ))}
          </div>

          {/* QA Pairs */}
          {pairsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          ) : filteredPairs.length === 0 ? (
            <div className="text-center py-20">
              <FileText className="w-12 h-12 text-muted-foreground/50 mx-auto mb-4" />
              <h3 className="text-lg font-medium">No QA pairs to display</h3>
              <p className="text-muted-foreground mt-1">
                {statusFilter ? `No pairs with status "${statusFilter.replace('_', ' ')}"` : 'This collection has no QA pairs yet'}
              </p>
            </div>
          ) : (
            <div
              className={cn(
                viewMode === 'grid'
                  ? 'grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4'
                  : 'space-y-2'
              )}
            >
              {filteredPairs.map(pair => (
                <QAPairCard
                  key={pair.id}
                  pair={pair}
                  isSelected={pair.id === selectedPairId}
                  onSelect={() => setSelectedPairId(pair.id)}
                />
              ))}
            </div>
          )}

          {/* Row count */}
          {filteredPairs.length > 0 && (
            <div className="mt-4 text-sm text-muted-foreground text-center">
              Showing {filteredPairs.length} of {qaPairs.length} pairs
            </div>
          )}
        </div>
      </div>

      {/* Detail Panel */}
      {selectedPair && (
        <DetailPanel
          pair={selectedPair}
          onClose={() => setSelectedPairId(null)}
          onSave={handleSavePair}
          onNext={() => {
            if (selectedIndex < filteredPairs.length - 1)
              setSelectedPairId(filteredPairs[selectedIndex + 1].id);
          }}
          onPrevious={() => {
            if (selectedIndex > 0)
              setSelectedPairId(filteredPairs[selectedIndex - 1].id);
          }}
          hasNext={selectedIndex < filteredPairs.length - 1}
          hasPrevious={selectedIndex > 0}
          isSaving={saving}
        />
      )}
    </div>
  );
}
