import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
  Loader2,
  Target,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Lightbulb,
} from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

interface FeedbackItem {
  id: string;
  endpoint_id?: string;
  rating: 'positive' | 'negative';
  input_text?: string;
  feedback_text?: string;
  created_at?: string;
}

interface FeedbackStats {
  total_count: number;
  positive_count: number;
  negative_count: number;
  positive_rate: number;
}

interface Gap {
  id: string;
  category: string;
  severity: 'high' | 'medium' | 'low';
  description: string;
  occurrence_count: number;
  suggested_action?: string;
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
// Severity Colors
// =============================================================================

const SEVERITY_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-800 border-red-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-blue-100 text-blue-800 border-blue-200",
};

// =============================================================================
// Stats Card
// =============================================================================

interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  iconColor?: string;
}

function StatsCard({ title, value, subtitle, icon: Icon, iconColor = 'text-muted-foreground' }: StatsCardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-muted rounded-lg">
            <Icon className={`h-5 w-5 ${iconColor}`} />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <div className="text-2xl font-bold">{value}</div>
            {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Gap Card
// =============================================================================

function GapCard({ gap }: { gap: Gap }) {
  return (
    <Card className={SEVERITY_COLORS[gap.severity]}>
      <CardContent className="pt-4 pb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="font-medium">{gap.category}</span>
          <Badge variant="outline">{gap.occurrence_count} occurrences</Badge>
        </div>
        <p className="text-sm opacity-90">{gap.description}</p>
        {gap.suggested_action && (
          <p className="text-xs mt-2 opacity-75 flex items-center gap-1">
            <Lightbulb className="h-3 w-3" />
            {gap.suggested_action}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Improve View
// =============================================================================

export default function MlImprove() {
  const { t } = useTranslation(['ml-improve', 'common']);
  const [feedbackItems, setFeedbackItems] = useState<FeedbackItem[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'feedback' | 'gaps'>('feedback');
  const [ratingFilter, setRatingFilter] = useState<'all' | 'positive' | 'negative'>('all');

  const api = useApi();
  const { get, post } = api;
  const { toast } = useToast();

  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Permissions
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const featureId = 'ml-improve';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);
  const canWrite = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_WRITE);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ratingParam = ratingFilter === 'all' ? '' : `&rating=${ratingFilter}`;
      const [feedbackResp, statsResp, gapsResp] = await Promise.all([
        get<FeedbackItem[]>(`/api/ml-improve/feedback?limit=20${ratingParam}`),
        get<FeedbackStats>('/api/ml-improve/feedback/stats?days=30'),
        get<Gap[]>('/api/ml-improve/gaps?limit=10'),
      ]);
      const feedback = checkApiResponse(feedbackResp, 'Feedback');
      const statsData = checkApiResponse(statsResp, 'Stats');
      const gapsData = checkApiResponse(gapsResp, 'Gaps');
      setFeedbackItems(Array.isArray(feedback) ? feedback : []);
      setStats(statsData);
      setGaps(Array.isArray(gapsData) ? gapsData : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load improvement data';
      setError(message);
      setFeedbackItems([]);
      setStats(null);
      setGaps([]);
    } finally {
      setLoading(false);
    }
  }, [get, ratingFilter]);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Improve');

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

  // Handle adding feedback to training data
  const handleAddToTraining = async (feedbackId: string) => {
    try {
      await post(`/api/ml-improve/feedback/${feedbackId}/convert`, { body: {} });
      toast({ title: "Added to Training Data", description: "Item is now in the curation queue." });
      loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to convert feedback';
      toast({ title: "Failed", description: message, variant: "destructive" });
    }
  };

  // Feedback table columns
  const feedbackColumns: ColumnDef<FeedbackItem>[] = useMemo(() => [
    {
      accessorKey: 'rating',
      header: 'Rating',
      cell: ({ row }) => row.original.rating === 'positive'
        ? <ThumbsUp className="h-4 w-4 text-green-600" />
        : <ThumbsDown className="h-4 w-4 text-red-600" />,
    },
    {
      accessorKey: 'endpoint_id',
      header: 'Endpoint',
      cell: ({ row }) => (
        <span className="text-sm truncate max-w-[150px] block">
          {row.original.endpoint_id || 'N/A'}
        </span>
      ),
    },
    {
      accessorKey: 'input_text',
      header: 'Input',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground truncate max-w-[250px] block">
          {row.original.input_text?.slice(0, 100) || 'No input'}
        </span>
      ),
    },
    {
      accessorKey: 'feedback_text',
      header: 'Comment',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground truncate max-w-[200px] block">
          {row.original.feedback_text || 'No comment'}
        </span>
      ),
    },
    {
      accessorKey: 'created_at',
      header: 'Time',
      cell: ({ row }) => row.original.created_at
        ? <RelativeDate date={row.original.created_at} />
        : <span className="text-sm text-muted-foreground">N/A</span>,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => canWrite ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={(e) => { e.stopPropagation(); handleAddToTraining(row.original.id); }}
          title="Add to Training Data"
        >
          <CheckCircle2 className="h-4 w-4 text-indigo-600" />
        </Button>
      ) : null,
    },
  ], [canWrite]);

  // Guards
  if (permissionsLoading) return <ListViewSkeleton />;

  if (!canRead) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>You do not have permission to view improvement tools.</AlertDescription>
      </Alert>
    );
  }

  if (loading) return <ListViewSkeleton />;

  return (
    <div className="space-y-6">
      {/* Error banner (non-fatal) */}
      {error && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error.includes('404') || error.includes('Not Found')
              ? 'Improvement API is being ported (Phase 3). Feedback and gaps will populate once backend routes are implemented.'
              : error}
          </AlertDescription>
        </Alert>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard
          title="Total Feedback"
          value={stats?.total_count || 0}
          subtitle="Last 30 days"
          icon={MessageSquare}
        />
        <StatsCard
          title="Positive"
          value={stats ? `${Math.round(stats.positive_rate * 100)}%` : '0%'}
          subtitle={`${stats?.positive_count || 0} responses`}
          icon={ThumbsUp}
          iconColor="text-green-600"
        />
        <StatsCard
          title="Negative"
          value={stats ? `${Math.round((1 - stats.positive_rate) * 100)}%` : '0%'}
          subtitle={`${stats?.negative_count || 0} responses`}
          icon={ThumbsDown}
          iconColor="text-red-600"
        />
        <StatsCard
          title="Gaps Identified"
          value={gaps.length}
          subtitle={`${gaps.filter(g => g.severity === 'high').length} high priority`}
          icon={Target}
          iconColor="text-indigo-600"
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'feedback' | 'gaps')}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="feedback">
              <MessageSquare className="mr-2 h-4 w-4" />
              Recent Feedback
            </TabsTrigger>
            <TabsTrigger value="gaps">
              <Target className="mr-2 h-4 w-4" />
              Gap Analysis
              {gaps.filter(g => g.severity === 'high').length > 0 && (
                <Badge variant="destructive" className="ml-2 h-5 min-w-[20px] px-1">
                  {gaps.filter(g => g.severity === 'high').length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            {activeTab === 'feedback' && (
              <>
                {['all', 'positive', 'negative'].map((filter) => (
                  <Button
                    key={filter}
                    variant={ratingFilter === filter ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setRatingFilter(filter as typeof ratingFilter)}
                  >
                    {filter === 'all' ? 'All' : filter === 'positive' ? 'Positive' : 'Negative'}
                  </Button>
                ))}
              </>
            )}
            <Button variant="outline" size="sm" onClick={loadData}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        <TabsContent value="feedback" className="mt-4">
          <DataTable
            columns={feedbackColumns}
            data={feedbackItems}
            searchColumn="input_text"
            storageKey="ml-improve-feedback-sort"
          />
        </TabsContent>

        <TabsContent value="gaps" className="mt-4 space-y-4">
          {gaps.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Target className="h-10 w-10 text-muted-foreground/30 mb-3" />
                <p className="text-muted-foreground">No gaps identified</p>
                <p className="text-sm text-muted-foreground/70 mt-1">Run gap analysis after collecting feedback</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {gaps.map((gap) => (
                <GapCard key={gap.id} gap={gap} />
              ))}
            </div>
          )}

          {/* Improvement Workflow */}
          <Card className="bg-indigo-50 dark:bg-indigo-950 border-indigo-200 dark:border-indigo-800">
            <CardHeader>
              <CardTitle className="text-indigo-800 dark:text-indigo-200 text-base">
                Improvement Workflow
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-indigo-700 dark:text-indigo-300">
              {[
                'Review negative feedback and add to training data',
                'Run gap analysis to identify patterns',
                'Curate new training data in the Training Data view',
                'Retrain model and redeploy',
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div className="w-5 h-5 rounded-full bg-indigo-200 dark:bg-indigo-800 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
                    {i + 1}
                  </div>
                  <span>{step}</span>
                </div>
              ))}
              <Button className="w-full mt-4" variant="default">
                Start Improvement Cycle
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
