# VITAL → Ontos Consolidation Status

**Started:** 2026-02-13
**Last Updated:** 2026-02-13
**Plan:** `~/.claude/plans/sequential-imagining-hippo.md`

## Decision

Consolidate VITAL Workbench's ML lifecycle features into Ontos rather than running two separate apps. Ontos already ported VITAL's training data model (PostgreSQL), has 5x the infrastructure (RBAC, audit, compliance, migrations, search, notifications), and running two apps with event-driven sync adds unnecessary complexity.

---

## Phase 1: Foundation — DONE

> Register VITAL as feature group in Ontos's feature system. Fix auth. Fix imports.

### Completed

| Change | File | What |
|--------|------|------|
| **Critical auth fix** | `src/backend/src/common/features.py` | Added `training-data` to `APP_FEATURES`. Without this, `PermissionChecker` defaulted to `NONE` → all 30+ training data API endpoints returned 403 for non-admin users. |
| **VITAL lifecycle features** | `src/backend/src/common/features.py` | Added `ml-deploy`, `ml-monitor`, `ml-improve` to `APP_FEATURES` with `READ_WRITE_ADMIN_LEVELS`. |
| **Broken imports (routes)** | `src/backend/src/routes/training_data_routes.py` | Fixed 6 imports: `src.backend.src.*` → `src.*`. These were ported from VITAL without adjusting for Ontos's package path. App would crash on startup with `ImportError`. |
| **Broken imports (manager)** | `src/backend/src/controller/training_data_manager.py` | Fixed 4 imports: same `src.backend.src.*` → `src.*` issue. |
| **Broken imports (repository)** | `src/backend/src/repositories/training_data_repository.py` | Fixed 2 imports. |
| **ML Lifecycle feature group** | `src/frontend/src/config/features.ts` | Added `'ML Lifecycle'` to `FeatureGroup` type. Moved `training-data` from `Operations` into it. Added `ml-deploy` (Rocket), `ml-monitor` (Activity), `ml-improve` (RefreshCcw) as `alpha` maturity features. Updated `groupOrder`. |

---

## Phase 2: Core UI Port — IN PROGRESS

> Port VITAL's stage pages + TOOLS pages into Ontos as new views. Adapt to Ontos patterns (useApi, Shadcn, permissions, breadcrumbs).

### Completed

| View | File | LOC | Source (VITAL) | Notes |
|------|------|-----|----------------|-------|
| **Deploy** | `src/frontend/src/views/ml-deploy.tsx` | ~420 | `DeployPage.tsx` (897) | 3-step deployment wizard (select model → version → configure). Endpoints table with status badges. Playground dialog for testing queries. Uses Shadcn Dialog, Switch, Select. |
| **Monitor** | `src/frontend/src/views/ml-monitor.tsx` | ~310 | `MonitorPage.tsx` (1081) | Metrics summary cards (endpoints, req/min, latency, alerts). Two tabs: endpoint metrics table + drift alerts table. Time range selector (1h/24h/7d/30d). |
| **Improve** | `src/frontend/src/views/ml-improve.tsx` | ~310 | `ImprovePage.tsx` (475) | Feedback table with thumbs up/down, add-to-training action. Stats cards. Gap analysis cards with severity colors. Improvement workflow steps. |
| **Routes** | `src/frontend/src/app.tsx` | +6 | — | Added `/ml-deploy`, `/ml-monitor`, `/ml-improve` routes with imports. |

All three views:
- Follow Ontos's exact pattern: `useApi`, `usePermissions`, `useBreadcrumbStore`, Shadcn `DataTable`, `checkApiResponse`
- Gracefully handle 404 errors (backend not yet ported) with informational alerts
- Support RBAC via the `ml-deploy`/`ml-monitor`/`ml-improve` feature IDs registered in Phase 1

### Remaining (Phase 2)

These are the VITAL pages NOT yet ported. Ordered by value:

| View to Port | Source (VITAL) | LOC | Depends On | Priority |
|-------------|----------------|-----|------------|----------|
| **TemplateBuilder** | `TemplateBuilderPage.tsx` | 1306 | Existing `/api/training-data/templates` | High — rich syntax highlighting, variable preview, reusable IP editor |
| **SheetBuilder** | `SheetBuilder.tsx` | ~600 | Existing `/api/training-data/sheets` | High — UC table browser, column mapping, sampling config |
| **LabelSetsPage** (Canonical Labels) | `LabelSetsPage.tsx` | ~500 | Existing `/api/training-data/canonical-labels` | High — label management, verification, image annotation |
| **CuratePage** (enhanced) | `CuratePage.tsx` | 1629 | Existing `/api/training-data/collections` | Medium — multi-user labeling, task board. Existing `training-data-curation.tsx` partially covers this. |
| **TrainPage** | `TrainPage.tsx` | 572 | New backend routes (Phase 3) | Medium — model fine-tuning config, training job management |
| **DSPyOptimizationPage** | `DSPyOptimizationPage.tsx` | 646+729 | New backend routes (Phase 3) | Medium — automated prompt optimization |
| **ExampleStorePage** | `ExampleStorePage.tsx` | 637 | Existing `/api/training-data/examples` (partial) | Low — few-shot example management, effectiveness dashboard |
| **DataQualityPage** | `DataQualityPage.tsx` | ~400 | DQX iframe | Low — embedded DQX integration |
| **LabelingJobsPage** | `LabelingJobsPage.tsx` | 1099 | New backend routes | Low — multi-user labeling task board |
| **ExampleEffectivenessDashboard** | `ExampleEffectivenessDashboard.tsx` | ~400 | New backend routes | Low — DSPy effectiveness metrics |

**Estimated remaining effort:** 3-4 weeks (plan original estimate)

---

## Phase 3: Backend Services — NOT STARTED

> Port DSPy, deployment, monitoring, feedback, gap analysis services. Create Alembic migrations for new tables.

### What Needs Porting

| Service | Source (VITAL) | Target (Ontos) | Depends On |
|---------|---------------|-----------------|------------|
| **Deployment Service** | `backend/app/services/deployment_service.py` | `src/backend/src/controller/deployment_manager.py` | Databricks Model Serving SDK |
| **Monitoring Service** | `backend/app/services/monitoring_service.py` | `src/backend/src/controller/monitoring_manager.py` | Serving endpoint metrics API |
| **Feedback Service** | Part of VITAL's API routes | `src/backend/src/controller/feedback_manager.py` | New `feedback_items` table |
| **Gap Analysis Service** | `backend/app/services/gap_analysis_service.py` | `src/backend/src/controller/gap_analysis_manager.py` | Feedback + training data tables |
| **DSPy Integration** | `backend/app/services/dspy_integration_service.py` | `src/backend/src/controller/dspy_manager.py` | DSPy library, LLMService |

### New API Routes Needed

| Route Prefix | Endpoints | Powers |
|-------------|-----------|--------|
| `/api/ml-deploy` | `GET /models`, `GET /models/{name}/versions`, `POST /deploy`, `GET /endpoints`, `POST /endpoints/{name}/query` | ml-deploy.tsx |
| `/api/ml-monitor` | `GET /metrics`, `GET /alerts`, `POST /alerts/{id}/acknowledge` | ml-monitor.tsx |
| `/api/ml-improve` | `GET /feedback`, `GET /feedback/stats`, `GET /gaps`, `POST /feedback/{id}/convert` | ml-improve.tsx |

### New DB Tables (Alembic Migrations)

| Table | Purpose |
|-------|---------|
| `feedback_items` | User feedback on model predictions |
| `drift_alerts` | Drift detection alerts |
| `improvement_cycles` | Track improvement iterations |
| `dspy_optimization_runs` | DSPy optimization history |

**Estimated effort:** 2-3 weeks

---

## Phase 4: Governance Wiring — NOT STARTED

> Auto-create data contracts for training data. Port compliance rules. Sync canonical labels to glossary terms. Wire semantic model integration.

### Key Tasks

- Auto-create ODCS data contracts when training collections reach `approved` status
- Port compliance rules from `ONTOS_INTEGRATION.md` (confidence thresholds, label coverage, bias checks)
- Sync canonical label types → business glossary terms
- Wire knowledge graph: defect type → label → model lineage visualization

**Estimated effort:** 2 weeks

---

## Phase 5: Advanced Features — NOT STARTED

> DQX iframe, domain-specific tables, synthetic data, keyboard shortcuts.

### Key Tasks

- Embed DQX data quality iframe in training data views
- Port domain-specific Delta tables (defect_detections, maintenance_predictions, anomaly_alerts)
- Port synthetic data generators for Mirion use cases
- Add keyboard shortcuts (Alt+T, Alt+E, Alt+D)
- Port module/plugin system

**Estimated effort:** 1-2 weeks

---

## Phase 6: Decommission — NOT STARTED

> Remove VITAL as separate deployable. Data migration. Update docs.

### Key Tasks

- Migrate any remaining data from VITAL's Delta tables to Ontos's PostgreSQL/Lakebase
- Update `mirion-vital-workbench/README.md` to point to Ontos
- Remove VITAL deployment configs (databricks.yml, app.yaml)
- Update `ONTOS_INTEGRATION.md` to reflect single-app architecture
- Archive VITAL frontend/backend code

**Estimated effort:** 1 week

---

## File Reference

### Ontos Files Modified

```
src/backend/src/common/features.py                     # Phase 1: +training-data, +ml-deploy/monitor/improve
src/backend/src/controller/training_data_manager.py     # Phase 1: fixed imports
src/backend/src/repositories/training_data_repository.py # Phase 1: fixed imports
src/backend/src/routes/training_data_routes.py          # Phase 1: fixed imports
src/frontend/src/config/features.ts                     # Phase 1: +ML Lifecycle group
src/frontend/src/app.tsx                                # Phase 2: +3 routes
```

### Ontos Files Created

```
src/frontend/src/views/ml-deploy.tsx     # Phase 2: Deploy view (~420 LOC)
src/frontend/src/views/ml-monitor.tsx    # Phase 2: Monitor view (~310 LOC)
src/frontend/src/views/ml-improve.tsx    # Phase 2: Improve view (~310 LOC)
```

### VITAL Source Files (Port From)

```
# Pages (Phase 2 remaining)
mirion-vital-workbench/frontend/src/pages/TemplateBuilderPage.tsx   (1306 LOC)
mirion-vital-workbench/frontend/src/pages/SheetBuilder.tsx          (~600 LOC)
mirion-vital-workbench/frontend/src/pages/LabelSetsPage.tsx         (~500 LOC)
mirion-vital-workbench/frontend/src/pages/CuratePage.tsx            (1629 LOC)
mirion-vital-workbench/frontend/src/pages/TrainPage.tsx             (572 LOC)
mirion-vital-workbench/frontend/src/pages/DSPyOptimizationPage.tsx  (646 LOC)
mirion-vital-workbench/frontend/src/pages/ExampleStorePage.tsx      (637 LOC)
mirion-vital-workbench/frontend/src/pages/DataQualityPage.tsx       (~400 LOC)
mirion-vital-workbench/frontend/src/pages/LabelingJobsPage.tsx      (1099 LOC)

# Backend services (Phase 3)
mirion-vital-workbench/backend/app/services/deployment_service.py
mirion-vital-workbench/backend/app/services/monitoring_service.py
mirion-vital-workbench/backend/app/services/gap_analysis_service.py
mirion-vital-workbench/backend/app/services/dspy_integration_service.py

# Components to adapt (shared)
mirion-vital-workbench/frontend/src/components/PipelineBreadcrumb.tsx  (144 LOC)
mirion-vital-workbench/frontend/src/components/WorkflowBanner.tsx      (174 LOC)
mirion-vital-workbench/frontend/src/context/WorkflowContext.tsx        (527 LOC)
mirion-vital-workbench/frontend/src/components/DataTable.tsx           (244 LOC)
```

### Key Pattern Differences (Porting Guide)

| VITAL Pattern | Ontos Pattern |
|--------------|---------------|
| `useQuery` / `useMutation` (React Query) | `useApi()` → `{ get, post, put, delete }` |
| `React.Context` (WorkflowContext) | Zustand stores |
| Custom Tailwind components | Shadcn UI (`@/components/ui/*`) |
| State-based navigation (single page) | `react-router-dom` routes |
| `fetchJson<T>()` service layer | `useApi().get<T>('/api/...')` + `checkApiResponse()` |
| `clsx()` conditional classes | `cn()` from `@/lib/utils` (or keep `clsx`) |
| `db-gray-*` custom colors | `text-muted-foreground`, `bg-muted`, etc. (Shadcn tokens) |
| No i18n | `useTranslation()` |
| No permissions | `usePermissions()` + `FeatureAccessLevel` |
| No breadcrumbs | `useBreadcrumbStore` |
