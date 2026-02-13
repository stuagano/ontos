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
  Activity,
  AlertTriangle,
  AlertCircle,
  Clock,
  Zap,
  CheckCircle,
  XCircle,
  RefreshCw,
  Server,
  Loader2,
  TrendingUp,
  TrendingDown,
  BarChart3,
  ArrowUpRight,
} from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

interface EndpointMetrics {
  endpoint_name: string;
  state: string;
  requests_per_minute: number;
  avg_latency_ms: number;
  error_rate: number;
  p99_latency_ms: number;
  created_at?: string;
}

interface DriftAlert {
  id: string;
  endpoint_name: string;
  metric: string;
  severity: 'low' | 'medium' | 'high';
  message: string;
  detected_at: string;
  acknowledged: boolean;
}

type TimeRange = '1h' | '24h' | '7d' | '30d';

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
// Status Colors
// =============================================================================

const SEVERITY_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-800 border-red-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-blue-100 text-blue-800 border-blue-200",
};

const STATE_COLORS: Record<string, string> = {
  READY: "bg-green-100 text-green-800",
  NOT_READY: "bg-amber-100 text-amber-800",
  FAILED: "bg-red-100 text-red-800",
};

// =============================================================================
// Metric Card Component
// =============================================================================

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
}

function MetricCard({ title, value, subtitle, icon: Icon, trend, trendValue }: MetricCardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <div className="text-2xl font-bold mt-1">{value}</div>
            {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="p-2 bg-muted rounded-lg">
              <Icon className="h-5 w-5 text-muted-foreground" />
            </div>
            {trend && trendValue && (
              <div className={`flex items-center gap-1 text-xs ${
                trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-muted-foreground'
              }`}>
                {trend === 'up' ? <TrendingUp className="h-3 w-3" /> : trend === 'down' ? <TrendingDown className="h-3 w-3" /> : null}
                {trendValue}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Monitor View
// =============================================================================

export default function MlMonitor() {
  const { t } = useTranslation(['ml-monitor', 'common']);
  const [metrics, setMetrics] = useState<EndpointMetrics[]>([]);
  const [alerts, setAlerts] = useState<DriftAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>('24h');
  const [activeTab, setActiveTab] = useState<'overview' | 'alerts'>('overview');

  const api = useApi();
  const { get } = api;
  const { toast } = useToast();

  const setStaticSegments = useBreadcrumbStore((state) => state.setStaticSegments);
  const setDynamicTitle = useBreadcrumbStore((state) => state.setDynamicTitle);

  // Permissions
  const { hasPermission, isLoading: permissionsLoading } = usePermissions();
  const featureId = 'ml-monitor';
  const canRead = !permissionsLoading && hasPermission(featureId, FeatureAccessLevel.READ_ONLY);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [metricsResp, alertsResp] = await Promise.all([
        get<EndpointMetrics[]>(`/api/ml-monitor/metrics?time_range=${timeRange}`),
        get<DriftAlert[]>('/api/ml-monitor/alerts'),
      ]);
      const metricsData = checkApiResponse(metricsResp, 'Metrics');
      const alertsData = checkApiResponse(alertsResp, 'Alerts');
      setMetrics(Array.isArray(metricsData) ? metricsData : []);
      setAlerts(Array.isArray(alertsData) ? alertsData : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load monitoring data';
      setError(message);
      setMetrics([]);
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [get, timeRange]);

  useEffect(() => {
    setStaticSegments([]);
    setDynamicTitle('Monitor');

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

  // Summary stats
  const totalRequests = metrics.reduce((sum, m) => sum + m.requests_per_minute, 0);
  const avgLatency = metrics.length > 0
    ? Math.round(metrics.reduce((sum, m) => sum + m.avg_latency_ms, 0) / metrics.length)
    : 0;
  const avgErrorRate = metrics.length > 0
    ? (metrics.reduce((sum, m) => sum + m.error_rate, 0) / metrics.length * 100).toFixed(1)
    : '0.0';
  const unacknowledgedAlerts = alerts.filter(a => !a.acknowledged).length;

  // Endpoint metrics table columns
  const metricsColumns: ColumnDef<EndpointMetrics>[] = useMemo(() => [
    {
      accessorKey: 'endpoint_name',
      header: 'Endpoint',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-rose-600 flex-shrink-0" />
          <span className="font-medium">{row.original.endpoint_name}</span>
        </div>
      ),
    },
    {
      accessorKey: 'state',
      header: 'Status',
      cell: ({ row }) => (
        <Badge className={STATE_COLORS[row.original.state] || 'bg-gray-100 text-gray-800'}>
          {row.original.state}
        </Badge>
      ),
    },
    {
      accessorKey: 'requests_per_minute',
      header: 'Req/min',
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.original.requests_per_minute.toLocaleString()}</span>
      ),
    },
    {
      accessorKey: 'avg_latency_ms',
      header: 'Avg Latency',
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.original.avg_latency_ms}ms</span>
      ),
    },
    {
      accessorKey: 'p99_latency_ms',
      header: 'P99 Latency',
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.original.p99_latency_ms}ms</span>
      ),
    },
    {
      accessorKey: 'error_rate',
      header: 'Error Rate',
      cell: ({ row }) => {
        const rate = row.original.error_rate * 100;
        return (
          <span className={`font-mono text-sm ${rate > 5 ? 'text-red-600 font-medium' : ''}`}>
            {rate.toFixed(1)}%
          </span>
        );
      },
    },
  ], []);

  // Alerts table columns
  const alertColumns: ColumnDef<DriftAlert>[] = useMemo(() => [
    {
      accessorKey: 'severity',
      header: 'Severity',
      cell: ({ row }) => (
        <Badge className={SEVERITY_COLORS[row.original.severity]}>
          {row.original.severity}
        </Badge>
      ),
    },
    {
      accessorKey: 'endpoint_name',
      header: 'Endpoint',
      cell: ({ row }) => <span className="font-medium">{row.original.endpoint_name}</span>,
    },
    {
      accessorKey: 'metric',
      header: 'Metric',
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.metric}</span>,
    },
    {
      accessorKey: 'message',
      header: 'Message',
      cell: ({ row }) => <span className="text-sm">{row.original.message}</span>,
    },
    {
      accessorKey: 'detected_at',
      header: 'Detected',
      cell: ({ row }) => <RelativeDate date={row.original.detected_at} />,
    },
    {
      accessorKey: 'acknowledged',
      header: 'Status',
      cell: ({ row }) => row.original.acknowledged
        ? <Badge variant="secondary">Acknowledged</Badge>
        : <Badge variant="destructive">New</Badge>,
    },
  ], []);

  // Guards
  if (permissionsLoading) return <ListViewSkeleton />;

  if (!canRead) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>You do not have permission to view model monitoring.</AlertDescription>
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
              ? 'Monitoring API is being ported (Phase 3). Metrics will populate once backend routes are implemented.'
              : error}
          </AlertDescription>
        </Alert>
      )}

      {/* Summary Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="Active Endpoints"
          value={metrics.filter(m => m.state === 'READY').length}
          subtitle={`${metrics.length} total`}
          icon={Server}
        />
        <MetricCard
          title="Total Requests/min"
          value={totalRequests.toLocaleString()}
          subtitle="Across all endpoints"
          icon={Zap}
          trend="up"
          trendValue="+12%"
        />
        <MetricCard
          title="Avg Latency"
          value={`${avgLatency}ms`}
          subtitle="Across all endpoints"
          icon={Clock}
        />
        <MetricCard
          title="Drift Alerts"
          value={unacknowledgedAlerts}
          subtitle={`${alerts.length} total`}
          icon={AlertTriangle}
          trend={unacknowledgedAlerts > 0 ? 'down' : 'neutral'}
          trendValue={unacknowledgedAlerts > 0 ? 'Action needed' : 'All clear'}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'overview' | 'alerts')}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="overview">
              <BarChart3 className="mr-2 h-4 w-4" />
              Endpoint Metrics
            </TabsTrigger>
            <TabsTrigger value="alerts">
              <AlertTriangle className="mr-2 h-4 w-4" />
              Drift Alerts
              {unacknowledgedAlerts > 0 && (
                <Badge variant="destructive" className="ml-2 h-5 min-w-[20px] px-1">
                  {unacknowledgedAlerts}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            {['1h', '24h', '7d', '30d'].map((range) => (
              <Button
                key={range}
                variant={timeRange === range ? 'default' : 'outline'}
                size="sm"
                onClick={() => setTimeRange(range as TimeRange)}
              >
                {range}
              </Button>
            ))}
            <Button variant="outline" size="sm" onClick={loadData}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        <TabsContent value="overview" className="mt-4">
          <DataTable
            columns={metricsColumns}
            data={metrics}
            searchColumn="endpoint_name"
            storageKey="ml-monitor-metrics-sort"
          />
        </TabsContent>

        <TabsContent value="alerts" className="mt-4">
          <DataTable
            columns={alertColumns}
            data={alerts}
            searchColumn="endpoint_name"
            storageKey="ml-monitor-alerts-sort"
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
