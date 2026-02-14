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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  Sheet,
  SheetCreate,
  SheetSourceType,
  SheetSamplingStrategy,
  SheetPreviewResult,
  SheetValidationResult,
} from '@/types/training-data';
import {
  Table2,
  Plus,
  Trash2,
  Loader2,
  Database,
  FileText,
  AlertCircle,
  RefreshCw,
  Eye,
  Columns,
  Download,
  CheckCircle,
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
// Sheet Detail Dialog
// =============================================================================

function SheetDetailDialog({ open, onOpenChange, sheet }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sheet: Sheet | null;
}) {
  const { get } = useApi();
  const [preview, setPreview] = useState<SheetPreviewResult | null>(null);
  const [validation, setValidation] = useState<SheetValidationResult | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => {
    if (open && sheet) {
      setLoadingPreview(true);
      Promise.all([
        get<SheetPreviewResult>(`/api/training-data/sheets/${sheet.id}/preview?limit=10`),
        get<SheetValidationResult>(`/api/training-data/sheets/${sheet.id}/validate`),
      ])
        .then(([previewResp, validationResp]) => {
          try { setPreview(checkApiResponse(previewResp, 'Preview')); } catch { setPreview(null); }
          try { setValidation(checkApiResponse(validationResp, 'Validation')); } catch { setValidation(null); }
        })
        .finally(() => setLoadingPreview(false));
    }
  }, [open, sheet, get]);

  if (!sheet) return null;

  const allColumns = [
    ...(sheet.text_columns || []),
    ...(sheet.image_columns || []),
    ...(sheet.metadata_columns || []),
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Table2 className="h-5 w-5 text-blue-600" />
            {sheet.name}
          </DialogTitle>
          <DialogDescription>
            {sheet.description || `Source: ${sheet.source_table || sheet.source_path || 'N/A'}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Source Info */}
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Source Type</p>
                <p className="font-medium">{sheet.source_type}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Sampling</p>
                <p className="font-medium">{sheet.sampling_strategy}{sheet.sample_size ? ` (${sheet.sample_size})` : ''}</p>
              </CardContent>
            </Card>
          </div>

          {/* Validation Status */}
          {validation && (
            <Alert variant={validation.valid ? "default" : "destructive"}>
              {validation.valid
                ? <CheckCircle className="h-4 w-4" />
                : <AlertCircle className="h-4 w-4" />}
              <AlertDescription>
                {validation.valid
                  ? `Source validated: ${validation.source || sheet.source_table}`
                  : `Validation failed: ${validation.error}`}
              </AlertDescription>
            </Alert>
          )}

          {/* Columns */}
          <div>
            <h3 className="text-sm font-semibold mb-2">Columns ({allColumns.length})</h3>
            <div className="flex flex-wrap gap-2">
              {sheet.text_columns?.map((col) => (
                <Badge key={col} variant="secondary" className="font-mono text-xs">
                  <FileText className="h-3 w-3 mr-1" />{col}
                </Badge>
              ))}
              {sheet.image_columns?.map((col) => (
                <Badge key={col} variant="outline" className="font-mono text-xs text-purple-600">
                  <Eye className="h-3 w-3 mr-1" />{col}
                </Badge>
              ))}
              {sheet.metadata_columns?.map((col) => (
                <Badge key={col} variant="outline" className="font-mono text-xs text-muted-foreground">
                  <Database className="h-3 w-3 mr-1" />{col}
                </Badge>
              ))}
            </div>
          </div>

          {/* Data Preview */}
          <div>
            <h3 className="text-sm font-semibold mb-2">Data Preview</h3>
            {loadingPreview ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : preview && preview.items.length > 0 ? (
              <div className="border rounded-lg overflow-auto max-h-[300px]">
                <table className="w-full text-sm">
                  <thead className="bg-muted sticky top-0">
                    <tr>
                      {(preview.columns || allColumns).map((col) => (
                        <th key={col} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {preview.items.slice(0, 10).map((row, idx) => (
                      <tr key={idx} className="hover:bg-muted/50">
                        {(preview.columns || allColumns).map((col) => (
                          <td key={col} className="px-3 py-2 truncate max-w-[200px]">
                            {String(row[col] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.total_available && (
                  <div className="px-3 py-2 bg-muted text-xs text-muted-foreground border-t">
                    Showing {Math.min(10, preview.items.length)} of {preview.total_available.toLocaleString()} rows
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Table2 className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No preview available</p>
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
// Create Sheet Dialog
// =============================================================================

function CreateSheetDialog({ open, onOpenChange, onCreated }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { post } = useApi();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [sourceType, setSourceType] = useState<SheetSourceType>(SheetSourceType.UNITY_CATALOG_TABLE);
  const [sourceCatalog, setSourceCatalog] = useState('');
  const [sourceSchema, setSourceSchema] = useState('');
  const [sourceTable, setSourceTable] = useState('');
  const [textColumns, setTextColumns] = useState('');
  const [imageColumns, setImageColumns] = useState('');
  const [metadataColumns, setMetadataColumns] = useState('');
  const [samplingStrategy, setSamplingStrategy] = useState<SheetSamplingStrategy>(SheetSamplingStrategy.ALL);
  const [sampleSize, setSampleSize] = useState<number | undefined>(undefined);

  const handleCreate = async () => {
    if (!name) {
      toast({ title: "Name required", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      const body: SheetCreate = {
        name,
        description: description || undefined,
        source_type: sourceType,
        source_catalog: sourceCatalog || undefined,
        source_schema: sourceSchema || undefined,
        source_table: sourceTable || undefined,
        text_columns: textColumns ? textColumns.split(',').map((s) => s.trim()) : undefined,
        image_columns: imageColumns ? imageColumns.split(',').map((s) => s.trim()) : undefined,
        metadata_columns: metadataColumns ? metadataColumns.split(',').map((s) => s.trim()) : undefined,
        sampling_strategy: samplingStrategy,
        sample_size: sampleSize,
      };
      await post('/api/training-data/sheets', { body });
      toast({ title: "Sheet Created", description: `"${name}" created successfully.` });
      onOpenChange(false);
      onCreated();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create sheet';
      toast({ title: "Create Failed", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setSourceCatalog('');
      setSourceSchema('');
      setSourceTable('');
      setTextColumns('');
      setImageColumns('');
      setMetadataColumns('');
      setSamplingStrategy(SheetSamplingStrategy.ALL);
      setSampleSize(undefined);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Table2 className="h-5 w-5 text-blue-600" />
            Create AI Sheet
          </DialogTitle>
          <DialogDescription>
            Connect to a Unity Catalog table or volume to create a new dataset.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label>Sheet Name *</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., sensor_readings_2024" className="mt-1" />
            </div>
            <div className="col-span-2">
              <Label>Description</Label>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is this dataset for?" rows={2} className="mt-1" />
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <Label>Source Type</Label>
              <Select value={sourceType} onValueChange={(v) => setSourceType(v as SheetSourceType)}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={SheetSourceType.UNITY_CATALOG_TABLE}>Unity Catalog Table</SelectItem>
                  <SelectItem value={SheetSourceType.UNITY_CATALOG_VOLUME}>Unity Catalog Volume</SelectItem>
                  <SelectItem value={SheetSourceType.DELTA_TABLE}>Delta Table</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label>Catalog</Label>
                <Input value={sourceCatalog} onChange={(e) => setSourceCatalog(e.target.value)} placeholder="catalog_name" className="mt-1" />
              </div>
              <div>
                <Label>Schema</Label>
                <Input value={sourceSchema} onChange={(e) => setSourceSchema(e.target.value)} placeholder="schema_name" className="mt-1" />
              </div>
              <div>
                <Label>Table</Label>
                <Input value={sourceTable} onChange={(e) => setSourceTable(e.target.value)} placeholder="table_name" className="mt-1" />
              </div>
            </div>

            <div>
              <Label>Text Columns</Label>
              <Input value={textColumns} onChange={(e) => setTextColumns(e.target.value)} placeholder="col1, col2, col3" className="mt-1" />
              <p className="text-xs text-muted-foreground mt-1">Comma-separated column names</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Image Columns</Label>
                <Input value={imageColumns} onChange={(e) => setImageColumns(e.target.value)} placeholder="image_path, image_url" className="mt-1" />
              </div>
              <div>
                <Label>Metadata Columns</Label>
                <Input value={metadataColumns} onChange={(e) => setMetadataColumns(e.target.value)} placeholder="created_at, source" className="mt-1" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Sampling Strategy</Label>
                <Select value={samplingStrategy} onValueChange={(v) => setSamplingStrategy(v as SheetSamplingStrategy)}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.values(SheetSamplingStrategy).map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {samplingStrategy !== SheetSamplingStrategy.ALL && (
                <div>
                  <Label>Sample Size</Label>
                  <Input
                    type="number"
                    value={sampleSize || ''}
                    onChange={(e) => setSampleSize(e.target.value ? parseInt(e.target.value) : undefined)}
                    placeholder="1000"
                    className="mt-1"
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Plus className="h-4 w-4 mr-2" />}
            Create Sheet
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Sheet Builder View
// =============================================================================

export default function MlSheetBuilder() {
  const { t } = useTranslation(['training-data', 'common']);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailSheet, setDetailSheet] = useState<Sheet | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

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
      const resp = await get<{ items: Sheet[], total: number }>('/api/training-data/sheets?page_size=100');
      const data = checkApiResponse(resp, 'Sheets');
      setSheets(data.items || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load sheets';
      setError(message);
      setSheets([]);
    } finally {
      setLoading(false);
    }
  }, [get]);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Sheet Builder');

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

  const handleDelete = async (sheetId: string) => {
    try {
      await deleteApi(`/api/training-data/sheets/${sheetId}`);
      toast({ title: "Sheet Deleted" });
      loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete sheet';
      toast({ title: "Delete Failed", description: message, variant: "destructive" });
    }
  };

  const columns: ColumnDef<Sheet>[] = useMemo(() => [
    {
      accessorKey: 'name',
      header: 'Sheet',
      cell: ({ row }) => (
        <div>
          <div className="font-medium flex items-center gap-2">
            <Table2 className="h-4 w-4 text-blue-600 flex-shrink-0" />
            {row.original.name}
          </div>
          {row.original.description && (
            <span className="text-sm text-muted-foreground truncate block max-w-[300px]">{row.original.description}</span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'source_type',
      header: 'Source',
      cell: ({ row }) => (
        <Badge variant="outline" className="font-mono text-xs">
          {row.original.source_type}
        </Badge>
      ),
    },
    {
      id: 'columns',
      header: 'Columns',
      cell: ({ row }) => {
        const total = (row.original.text_columns?.length || 0)
          + (row.original.image_columns?.length || 0)
          + (row.original.metadata_columns?.length || 0);
        return <span className="text-sm">{total} columns</span>;
      },
    },
    {
      accessorKey: 'sampling_strategy',
      header: 'Sampling',
      cell: ({ row }) => (
        <span className="text-sm">{row.original.sampling_strategy}{row.original.sample_size ? ` (${row.original.sample_size})` : ''}</span>
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
            onClick={(e) => { e.stopPropagation(); setDetailSheet(row.original); setDetailOpen(true); }}
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
        <AlertDescription>You do not have permission to view sheets.</AlertDescription>
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
              ? 'Sheets API is loading. Data will populate once the backend responds.'
              : error}
          </AlertDescription>
        </Alert>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Table2 className="h-5 w-5 text-blue-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Total Sheets</p>
                <div className="text-2xl font-bold">{sheets.length}</div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Columns className="h-5 w-5 text-green-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">Total Columns</p>
                <div className="text-2xl font-bold">
                  {sheets.reduce((sum, s) =>
                    sum + (s.text_columns?.length || 0) + (s.image_columns?.length || 0) + (s.metadata_columns?.length || 0), 0
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg"><Database className="h-5 w-5 text-purple-600" /></div>
              <div>
                <p className="text-sm text-muted-foreground">UC Table Sources</p>
                <div className="text-2xl font-bold">
                  {sheets.filter((s) => s.source_type === SheetSourceType.UNITY_CATALOG_TABLE).length}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">AI Sheets</h2>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
          {canWrite && (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> New Sheet
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={sheets}
        searchColumn="name"
        storageKey="ml-sheet-builder-sort"
      />

      {/* Create Dialog */}
      <CreateSheetDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={loadData}
      />

      {/* Detail Dialog */}
      <SheetDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        sheet={detailSheet}
      />
    </div>
  );
}
