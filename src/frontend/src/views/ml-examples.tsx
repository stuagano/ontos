/**
 * MlExamples - Few-shot example store for DSPy optimization
 *
 * Ported from VITAL ExampleStorePage. Provides:
 * - Example browsing with domain/difficulty filters
 * - Semantic search across examples
 * - Effectiveness tracking (score + usage count)
 * - Create/edit/delete examples
 * - Top performing examples sidebar
 */

import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Search,
  Plus,
  Filter,
  BookOpen,
  Edit,
  Trash2,
  TrendingUp,
  Zap,
  Tag,
  ChevronDown,
  X,
  Sparkles,
  CheckCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import useBreadcrumbStore from '@/stores/breadcrumb-store';
import { cn } from '@/lib/utils';

// Example store types (not yet in training-data.ts)
interface ExampleRecord {
  id: string;
  domain: string;
  difficulty: 'easy' | 'medium' | 'hard';
  input: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  explanation?: string;
  capability_tags: string[];
  effectiveness_score?: number;
  usage_count: number;
  has_embedding: boolean;
  created_at?: string;
  updated_at?: string;
}

interface ExampleCreate {
  domain: string;
  difficulty: 'easy' | 'medium' | 'hard';
  input: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  explanation?: string;
  capability_tags: string[];
}

const DOMAINS = [
  { id: 'defect_detection', label: 'Defect Detection' },
  { id: 'predictive_maintenance', label: 'Predictive Maintenance' },
  { id: 'anomaly_detection', label: 'Anomaly Detection' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'document_extraction', label: 'Document Extraction' },
  { id: 'general', label: 'General' },
];

const DIFFICULTIES = [
  { id: 'easy', label: 'Easy', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  { id: 'medium', label: 'Medium', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  { id: 'hard', label: 'Hard', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
];

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
// Effectiveness Indicator
// ============================================================================

function EffectivenessIndicator({ score, usageCount }: { score?: number; usageCount: number }) {
  if (score === undefined || score === null) {
    return (
      <span className="text-xs text-muted-foreground flex items-center gap-1">
        <AlertCircle className="w-3 h-3" /> No data
      </span>
    );
  }

  const color = score >= 0.8 ? 'text-green-600' : score >= 0.5 ? 'text-amber-600' : 'text-red-600';
  const bg = score >= 0.8 ? 'bg-green-50 dark:bg-green-900/20' : score >= 0.5 ? 'bg-amber-50 dark:bg-amber-900/20' : 'bg-red-50 dark:bg-red-900/20';

  return (
    <div className={cn('flex items-center gap-2 px-2 py-1 rounded', bg)}>
      <TrendingUp className={cn('w-3 h-3', color)} />
      <span className={cn('text-xs font-medium', color)}>{(score * 100).toFixed(0)}%</span>
      <span className="text-xs text-muted-foreground">({usageCount} uses)</span>
    </div>
  );
}

// ============================================================================
// Example Card
// ============================================================================

function ExampleCard({
  example,
  onEdit,
  onDelete,
}: {
  example: ExampleRecord;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const diffConfig = DIFFICULTIES.find(d => d.id === example.difficulty) || DIFFICULTIES[1];
  const domainLabel = DOMAINS.find(d => d.id === example.domain)?.label || example.domain;

  return (
    <Card className="hover:border-primary/30 transition-all">
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className="p-2 bg-primary/10 rounded-lg shrink-0">
              <BookOpen className="w-5 h-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline">{domainLabel}</Badge>
                <Badge variant="outline" className={diffConfig.color}>{diffConfig.label}</Badge>
                {example.has_embedding && (
                  <Badge variant="outline" className="text-purple-600">
                    <Sparkles className="w-3 h-3 mr-1" /> Embedded
                  </Badge>
                )}
              </div>

              {example.explanation && (
                <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{example.explanation}</p>
              )}

              {/* Input/Output Preview */}
              <div className="mt-3 space-y-2">
                <div className="text-xs">
                  <span className="text-muted-foreground font-medium">Input:</span>
                  <code className="ml-2 bg-muted px-1.5 py-0.5 rounded text-xs">
                    {JSON.stringify(example.input).slice(0, 80)}
                    {JSON.stringify(example.input).length > 80 && '...'}
                  </code>
                </div>
                <div className="text-xs">
                  <span className="text-muted-foreground font-medium">Output:</span>
                  <code className="ml-2 bg-muted px-1.5 py-0.5 rounded text-xs">
                    {JSON.stringify(example.expected_output).slice(0, 80)}
                    {JSON.stringify(example.expected_output).length > 80 && '...'}
                  </code>
                </div>
              </div>

              {/* Tags */}
              {example.capability_tags.length > 0 && (
                <div className="mt-3 flex items-center gap-1 flex-wrap">
                  <Tag className="w-3 h-3 text-muted-foreground" />
                  {example.capability_tags.slice(0, 4).map(tag => (
                    <Badge key={tag} variant="secondary" className="text-xs">{tag}</Badge>
                  ))}
                  {example.capability_tags.length > 4 && (
                    <span className="text-xs text-muted-foreground">+{example.capability_tags.length - 4}</span>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1 ml-2">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onEdit}>
              <Edit className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={onDelete}>
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className="mt-4 pt-3 border-t flex items-center justify-between">
          <EffectivenessIndicator score={example.effectiveness_score} usageCount={example.usage_count} />
          <span className="text-xs text-muted-foreground">
            {example.updated_at ? new Date(example.updated_at).toLocaleDateString() : ''}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Create/Edit Dialog
// ============================================================================

function ExampleFormDialog({
  open,
  onOpenChange,
  example,
  onSave,
  saving,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  example: ExampleRecord | null;
  onSave: (data: ExampleCreate) => void;
  saving: boolean;
}) {
  const [domain, setDomain] = useState(example?.domain || 'general');
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>(example?.difficulty || 'medium');
  const [inputJson, setInputJson] = useState(example ? JSON.stringify(example.input, null, 2) : '{}');
  const [outputJson, setOutputJson] = useState(example ? JSON.stringify(example.expected_output, null, 2) : '{}');
  const [explanation, setExplanation] = useState(example?.explanation || '');
  const [tags, setTags] = useState(example?.capability_tags.join(', ') || '');

  useEffect(() => {
    if (example) {
      setDomain(example.domain);
      setDifficulty(example.difficulty);
      setInputJson(JSON.stringify(example.input, null, 2));
      setOutputJson(JSON.stringify(example.expected_output, null, 2));
      setExplanation(example.explanation || '');
      setTags(example.capability_tags.join(', '));
    } else {
      setDomain('general');
      setDifficulty('medium');
      setInputJson('{}');
      setOutputJson('{}');
      setExplanation('');
      setTags('');
    }
  }, [example, open]);

  const handleSubmit = () => {
    try {
      onSave({
        domain,
        difficulty,
        input: JSON.parse(inputJson),
        expected_output: JSON.parse(outputJson),
        explanation: explanation || undefined,
        capability_tags: tags.split(',').map(t => t.trim()).filter(Boolean),
      });
    } catch {
      // JSON parse error handled by form validation
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{example ? 'Edit Example' : 'New Example'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Domain</label>
              <select
                value={domain}
                onChange={e => setDomain(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg text-sm bg-background"
              >
                {DOMAINS.map(d => <option key={d.id} value={d.id}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Difficulty</label>
              <select
                value={difficulty}
                onChange={e => setDifficulty(e.target.value as 'easy' | 'medium' | 'hard')}
                className="w-full px-3 py-2 border rounded-lg text-sm bg-background"
              >
                {DIFFICULTIES.map(d => <option key={d.id} value={d.id}>{d.label}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Input (JSON)</label>
            <textarea
              value={inputJson}
              onChange={e => setInputJson(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border rounded-lg font-mono text-sm resize-none bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Expected Output (JSON)</label>
            <textarea
              value={outputJson}
              onChange={e => setOutputJson(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border rounded-lg font-mono text-sm resize-none bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Explanation</label>
            <Input value={explanation} onChange={e => setExplanation(e.target.value)} placeholder="Why is this a good example?" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tags (comma-separated)</label>
            <Input value={tags} onChange={e => setTags(e.target.value)} placeholder="classification, defect, weld" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            {example ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function MlExamples() {
  const { t } = useTranslation(['training-data', 'common']);
  const [examples, setExamples] = useState<ExampleRecord[]>([]);
  const [topExamples, setTopExamples] = useState<ExampleRecord[]>([]);
  const [searchText, setSearchText] = useState('');
  const [domainFilter, setDomainFilter] = useState('');
  const [difficultyFilter, setDifficultyFilter] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingExample, setEditingExample] = useState<ExampleRecord | null>(null);

  const api = useApi();
  const { get, post, put, delete: deleteApi } = api;
  const { toast } = useToast();
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const setStaticSegments = useBreadcrumbStore(state => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore(state => state.setDynamicTitle);

  const featureId = 'training-data';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Example Store');
  }, [setStaticSegments, setDynamicTitle]);

  // Load examples
  const loadExamples = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (domainFilter) params.set('domain', domainFilter);
      if (difficultyFilter) params.set('difficulty', difficultyFilter);
      const qs = params.toString();
      const resp = await get<ExampleRecord[]>(`/api/training-data/examples${qs ? `?${qs}` : ''}`);
      const data = checkApiResponse(resp, 'Examples');
      setExamples(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      toast({
        title: 'Failed to load examples',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  // Load top examples
  const loadTopExamples = async () => {
    try {
      const resp = await get<ExampleRecord[]>('/api/training-data/examples/top?limit=5');
      const data = checkApiResponse(resp, 'Top Examples');
      setTopExamples(Array.isArray(data) ? data : []);
    } catch {
      // Non-critical
    }
  };

  useEffect(() => {
    if (canRead) {
      loadExamples();
      loadTopExamples();
    }
  }, [canRead, domainFilter, difficultyFilter]);

  // Filtered by search
  const displayExamples = useMemo(() => {
    if (!searchText || searchText.length < 3) return examples;
    const query = searchText.toLowerCase();
    return examples.filter(
      e =>
        e.explanation?.toLowerCase().includes(query) ||
        JSON.stringify(e.input).toLowerCase().includes(query) ||
        e.capability_tags.some(t => t.toLowerCase().includes(query))
    );
  }, [examples, searchText]);

  // Save example
  const handleSave = async (data: ExampleCreate) => {
    setSaving(true);
    try {
      if (editingExample) {
        await put(`/api/training-data/examples/${editingExample.id}`, data);
        toast({ title: 'Example updated' });
      } else {
        await post('/api/training-data/examples', data);
        toast({ title: 'Example created' });
      }
      setDialogOpen(false);
      setEditingExample(null);
      loadExamples();
      loadTopExamples();
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

  // Delete example
  const handleDelete = async (id: string) => {
    try {
      await deleteApi(`/api/training-data/examples/${id}`);
      toast({ title: 'Example deleted' });
      loadExamples();
      loadTopExamples();
    } catch (err: unknown) {
      toast({
        title: 'Delete failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const hasFilters = !!domainFilter || !!difficultyFilter || searchText.length > 2;

  // Permission guard
  if (!permissionsLoading && !canRead) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">You don't have permission to access this feature.</p>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Example Store</h1>
            <p className="text-muted-foreground mt-1">
              Manage few-shot learning examples for AI training and inference
            </p>
          </div>
          {canWrite && (
            <Button onClick={() => { setEditingExample(null); setDialogOpen(true); }}>
              <Plus className="w-4 h-4 mr-2" /> New Example
            </Button>
          )}
        </div>

        {/* Search and Filters */}
        <Card className="mb-6">
          <CardContent className="pt-4">
            <div className="flex items-center gap-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search examples by text..."
                  value={searchText}
                  onChange={e => setSearchText(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Button
                variant={showFilters ? 'secondary' : 'outline'}
                onClick={() => setShowFilters(!showFilters)}
              >
                <Filter className="w-4 h-4 mr-2" />
                Filters
                {hasFilters && <span className="w-2 h-2 bg-primary rounded-full ml-2" />}
                <ChevronDown className={cn('w-4 h-4 ml-1 transition-transform', showFilters && 'rotate-180')} />
              </Button>
            </div>

            {showFilters && (
              <div className="mt-4 pt-4 border-t flex items-center gap-4">
                <select
                  value={domainFilter}
                  onChange={e => setDomainFilter(e.target.value)}
                  className="px-3 py-2 border rounded-lg text-sm bg-background"
                >
                  <option value="">All Domains</option>
                  {DOMAINS.map(d => <option key={d.id} value={d.id}>{d.label}</option>)}
                </select>
                <select
                  value={difficultyFilter}
                  onChange={e => setDifficultyFilter(e.target.value)}
                  className="px-3 py-2 border rounded-lg text-sm bg-background"
                >
                  <option value="">All Difficulties</option>
                  {DIFFICULTIES.map(d => <option key={d.id} value={d.id}>{d.label}</option>)}
                </select>
                {hasFilters && (
                  <Button variant="ghost" size="sm" onClick={() => { setDomainFilter(''); setDifficultyFilter(''); setSearchText(''); }}>
                    <X className="w-3 h-3 mr-1" /> Clear
                  </Button>
                )}
                <span className="ml-auto text-sm text-muted-foreground">
                  {displayExamples.length} example{displayExamples.length !== 1 && 's'}
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Examples Grid */}
          <div className="lg:col-span-3">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
              </div>
            ) : displayExamples.length === 0 ? (
              <Card className="py-20 text-center">
                <CardContent>
                  <BookOpen className="w-12 h-12 text-muted-foreground/50 mx-auto mb-4" />
                  <h3 className="text-lg font-medium">
                    {searchText.length > 2 ? 'No examples match your search' : 'No examples yet'}
                  </h3>
                  <p className="text-muted-foreground mt-1">
                    {searchText.length > 2 ? 'Try adjusting your search or filters' : 'Create your first example to get started'}
                  </p>
                  {!searchText && canWrite && (
                    <Button className="mt-4" onClick={() => { setEditingExample(null); setDialogOpen(true); }}>
                      Create Example
                    </Button>
                  )}
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {displayExamples.map(example => (
                  <ExampleCard
                    key={example.id}
                    example={example}
                    onEdit={() => { setEditingExample(example); setDialogOpen(true); }}
                    onDelete={() => handleDelete(example.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1 space-y-6">
            {/* Top Performing */}
            {topExamples.length > 0 && (
              <Card className="bg-primary/5 border-primary/20">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Zap className="w-4 h-4" /> Top Performing
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {topExamples.map((example, index) => (
                      <div key={example.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-background/50 transition-colors">
                        <span className="text-lg font-bold text-primary/30 w-6">#{index + 1}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm truncate">{example.explanation || JSON.stringify(example.input).slice(0, 50)}</p>
                          <p className="text-xs text-muted-foreground">
                            {DOMAINS.find(d => d.id === example.domain)?.label || example.domain}
                          </p>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-medium text-green-600">
                            {example.effectiveness_score ? `${(example.effectiveness_score * 100).toFixed(0)}%` : '-'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Stats */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Quick Stats</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total Examples</span>
                    <span className="font-medium">{examples.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Domains</span>
                    <span className="font-medium">{new Set(examples.map(e => e.domain)).size}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Sparkles className="w-3 h-3" /> With Embeddings
                    </span>
                    <span className="font-medium text-primary">
                      {examples.filter(e => e.has_embedding).length}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Create/Edit Dialog */}
      <ExampleFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        example={editingExample}
        onSave={handleSave}
        saving={saving}
      />
    </div>
  );
}
