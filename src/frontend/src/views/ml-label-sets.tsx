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
  CanonicalLabel,
  CanonicalLabelCreate,
  LabelType,
  LabelConfidence,
  DataClassification,
  CONFIDENCE_COLORS,
} from '@/types/training-data';
import {
  Tag,
  Plus,
  Trash2,
  Loader2,
  AlertCircle,
  RefreshCw,
  Eye,
  CheckCircle,
  Shield,
  BarChart3,
  Search,
} from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

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
// Label Detail Dialog
// =============================================================================

function LabelDetailDialog({ open, onOpenChange, label }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: CanonicalLabel | null;
}) {
  if (!label) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tag className="h-5 w-5 text-cyan-600" />
            Canonical Label
          </DialogTitle>
          <DialogDescription>
            {label.label_type} — Item: {label.item_ref}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Status badges */}
          <div className="flex flex-wrap gap-2">
            <Badge className={CONFIDENCE_COLORS[label.confidence]}>
              {label.confidence} confidence
            </Badge>
            {label.is_verified && (
              <Badge variant="secondary" className="bg-green-100 text-green-800">
                <CheckCircle className="h-3 w-3 mr-1" /> Verified
              </Badge>
            )}
            <Badge variant="outline">{label.data_classification}</Badge>
          </div>

          {/* Label Data */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Label Data</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="text-sm font-mono bg-muted p-3 rounded-lg overflow-auto max-h-[200px]">
                {JSON.stringify(label.label_data, null, 2)}
              </pre>
            </CardContent>
          </Card>

          {/* Usage Info */}
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Allowed Uses</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {label.allowed_uses.length > 0
                    ? label.allowed_uses.map((u) => <Badge key={u} variant="secondary" className="text-xs">{u}</Badge>)
                    : <span className="text-sm text-muted-foreground">All uses</span>}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Prohibited Uses</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {label.prohibited_uses.length > 0
                    ? label.prohibited_uses.map((u) => <Badge key={u} variant="destructive" className="text-xs">{u}</Badge>)
                    : <span className="text-sm text-muted-foreground">None</span>}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Sheet ID:</span>
              <span className="ml-2 font-mono text-xs">{label.sheet_id}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Reuse Count:</span>
              <span className="ml-2 font-bold">{label.reuse_count}</span>
            </div>
            {label.verified_by && (
              <div>
                <span className="text-muted-foreground">Verified By:</span>
                <span className="ml-2">{label.verified_by}</span>
              </div>
            )}
            {label.verified_at && (
              <div>
                <span className="text-muted-foreground">Verified At:</span>
                <span className="ml-2"><RelativeDate date={label.verified_at} /></span>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Create Label Dialog
// =============================================================================

function CreateLabelDialog({ open, onOpenChange, onCreated }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { post } = useApi();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);

  const [sheetId, setSheetId] = useState('');
  const [itemRef, setItemRef] = useState('');
  const [labelType, setLabelType] = useState<LabelType>(LabelType.CLASSIFICATION);
  const [labelData, setLabelData] = useState('{}');
  const [confidence, setConfidence] = useState<LabelConfidence>(LabelConfidence.HIGH);
  const [dataClassification, setDataClassification] = useState<DataClassification>(DataClassification.INTERNAL);

  useEffect(() => {
    if (open) {
      setSheetId('');
      setItemRef('');
      setLabelType(LabelType.CLASSIFICATION);
      setLabelData('{}');
      setConfidence(LabelConfidence.HIGH);
      setDataClassification(DataClassification.INTERNAL);
    }
  }, [open]);

  const handleCreate = async () => {
    if (!sheetId || !itemRef) {
      toast({ title: "Missing required fields", description: "Sheet ID and Item Ref are required.", variant: "destructive" });
      return;
    }

    let parsedData: Record<string, unknown>;
    try {
      parsedData = JSON.parse(labelData);
    } catch {
      toast({ title: "Invalid JSON", description: "Label data must be valid JSON.", variant: "destructive" });
      return;
    }

    setSaving(true);
    try {
      const body: CanonicalLabelCreate = {
        sheet_id: sheetId,
        item_ref: itemRef,
        label_type: labelType,
        label_data: parsedData,
        confidence,
        data_classification: dataClassification,
      };
      await post('/api/training-data/canonical-labels', { body });
      toast({ title: "Label Created", description: "Canonical label saved successfully." });
      onOpenChange(false);
      onCreated();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create label';
      toast({ title: "Create Failed", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tag className="h-5 w-5 text-cyan-600" />
            Create Canonical Label
          </DialogTitle>
          <DialogDescription>
            Add an expert-validated label for a data item.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Sheet ID *</Label>
              <Input value={sheetId} onChange={(e) => setSheetId(e.target.value)} placeholder="Sheet UUID" className="mt-1 font-mono text-sm" />
            </div>
            <div>
              <Label>Item Ref *</Label>
              <Input value={itemRef} onChange={(e) => setItemRef(e.target.value)} placeholder="row_001" className="mt-1 font-mono text-sm" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
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
            <div>
              <Label>Confidence</Label>
              <Select value={confidence} onValueChange={(v) => setConfidence(v as LabelConfidence)}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.values(LabelConfidence).map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label>Data Classification</Label>
            <Select value={dataClassification} onValueChange={(v) => setDataClassification(v as DataClassification)}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.values(DataClassification).map((dc) => (
                  <SelectItem key={dc} value={dc}>{dc}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Label Data (JSON) *</Label>
            <Textarea
              value={labelData}
              onChange={(e) => setLabelData(e.target.value)}
              placeholder='{"class": "defect_crack", "severity": "high"}'
              rows={4}
              className="mt-1 font-mono text-sm"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Plus className="h-4 w-4 mr-2" />}
            Create Label
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Label Sets View
// =============================================================================

export default function MlLabelSets() {
  const { t } = useTranslation(['training-data', 'common']);
  const [labels, setLabels] = useState<CanonicalLabel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailLabel, setDetailLabel] = useState<CanonicalLabel | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string>('all');

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
      const typeParam = typeFilter !== 'all' ? `&label_type=${typeFilter}` : '';
      const resp = await get<{ items: CanonicalLabel[], total: number }>(`/api/training-data/canonical-labels?page_size=100${typeParam}`);
      const data = checkApiResponse(resp, 'Labels');
      setLabels(data.items || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load labels';
      setError(message);
      setLabels([]);
    } finally {
      setLoading(false);
    }
  }, [get, typeFilter]);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Canonical Labels');

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

  const handleDelete = async (labelId: string) => {
    try {
      await deleteApi(`/api/training-data/canonical-labels/${labelId}`);
      toast({ title: "Label Deleted" });
      loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete label';
      toast({ title: "Delete Failed", description: message, variant: "destructive" });
    }
  };

  // Computed stats
  const verifiedCount = labels.filter((l) => l.is_verified).length;
  const highConfidenceCount = labels.filter((l) => l.confidence === LabelConfidence.HIGH).length;
  const totalReuse = labels.reduce((sum, l) => sum + l.reuse_count, 0);

  const columns: ColumnDef<CanonicalLabel>[] = useMemo(() => [
    {
      accessorKey: 'item_ref',
      header: 'Item',
      cell: ({ row }) => (
        <div className="font-mono text-sm">{row.original.item_ref}</div>
      ),
    },
    {
      accessorKey: 'label_type',
      header: 'Type',
      cell: ({ row }) => (
        <Badge variant="outline">{row.original.label_type.replace('_', ' ')}</Badge>
      ),
    },
    {
      accessorKey: 'confidence',
      header: 'Confidence',
      cell: ({ row }) => (
        <Badge className={CONFIDENCE_COLORS[row.original.confidence]}>
          {row.original.confidence}
        </Badge>
      ),
    },
    {
      accessorKey: 'is_verified',
      header: 'Verified',
      cell: ({ row }) => row.original.is_verified
        ? <CheckCircle className="h-4 w-4 text-green-600" />
        : <span className="text-muted-foreground text-sm">No</span>,
    },
    {
      accessorKey: 'data_classification',
      header: 'Classification',
      cell: ({ row }) => (
        <Badge variant="secondary" className="text-xs">{row.original.data_classification}</Badge>
      ),
    },
    {
      accessorKey: 'reuse_count',
      header: 'Reuses',
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.original.reuse_count}</span>
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
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={(e) => { e.stopPropagation(); setDetailLabel(row.original); setDetailOpen(true); }}
            title="View Details"
          >
            <Eye className="h-4 w-4" />
          </Button>
          {canWrite && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={(e) => { e.stopPropagation(); handleDelete(row.original.id); }}
              title="Delete"
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          )}
        </div>
      ),
    },
  ], [canWrite]);

  // Guards
  if (permissionsLoading) return <ListViewSkeleton />;

  if (!canRead) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>You do not have permission to view canonical labels.</AlertDescription>
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
              ? 'Labels API is loading. Data will populate once the backend responds.'
              : error}
          </AlertDescription>
        </Alert>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Tag className="h-5 w-5 text-cyan-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Total Labels</p>
                <div className="text-2xl font-bold">{labels.length}</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><CheckCircle className="h-5 w-5 text-green-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Verified</p>
                <div className="text-2xl font-bold">{verifiedCount}</div>
                <p className="text-xs text-muted-foreground">
                  {labels.length > 0 ? `${Math.round(verifiedCount / labels.length * 100)}%` : '0%'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Shield className="h-5 w-5 text-indigo-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">High Confidence</p>
                <div className="text-2xl font-bold">{highConfidenceCount}</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><BarChart3 className="h-5 w-5 text-amber-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Total Reuses</p>
                <div className="text-2xl font-bold">{totalReuse}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Canonical Labels</h2>
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[180px] h-9"><SelectValue placeholder="Filter by type" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              {Object.values(LabelType).map((lt) => (
                <SelectItem key={lt} value={lt}>{lt.replace('_', ' ')}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
          {canWrite && (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> New Label
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={labels}
        searchColumn="item_ref"
        storageKey="ml-label-sets-sort"
      />

      {/* Create Dialog */}
      <CreateLabelDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={loadData}
      />

      {/* Detail Dialog */}
      <LabelDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        label={detailLabel}
      />
    </div>
  );
}
