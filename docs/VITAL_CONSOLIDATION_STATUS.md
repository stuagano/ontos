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

## Phase 2: Core UI Port — DONE

> Port VITAL's stage pages + TOOLS pages into Ontos as new views. Adapt to Ontos patterns (useApi, Shadcn, permissions, breadcrumbs).

### Completed

| View | File | LOC | Source (VITAL) | Notes |
|------|------|-----|----------------|-------|
| **Deploy** | `views/ml-deploy.tsx` | ~420 | `DeployPage.tsx` (897) | 3-step deployment wizard. Endpoints table. Playground dialog. |
| **Monitor** | `views/ml-monitor.tsx` | ~310 | `MonitorPage.tsx` (1081) | Metrics cards. Endpoint metrics + drift alerts tables. Time range selector. |
| **Improve** | `views/ml-improve.tsx` | ~310 | `ImprovePage.tsx` (475) | Feedback table. Gap analysis cards. Improvement workflow. |
| **Templates** | `views/ml-template-builder.tsx` | ~480 | `TemplateBuilderPage.tsx` (1306) | Template list + create/edit dialog. System/user prompt editors. Output schema. Model settings. Live preview. |
| **Sheets** | `views/ml-sheet-builder.tsx` | ~470 | `SheetBuilder.tsx` (1725) | Sheet list + create dialog. UC source config. Column spec. Data preview + validation. |
| **Labels** | `views/ml-label-sets.tsx` | ~460 | `LabelSetsPage.tsx` (620) | Canonical label list with type filter. Create dialog. Detail dialog with usage info. |
| **Curate** | `views/ml-curate.tsx` | ~480 | `CuratePage.tsx` (1629) | Collection browser. QA pair grid/list with detail panel. Status filter. Keyboard nav. Stats bar. |
| **Train** | `views/ml-train.tsx` | ~430 | `TrainPage.tsx` (572) | Training jobs list. Collection selection. Job config form. Job detail with progress/results. |
| **DSPy** | `views/ml-dspy.tsx` | ~430 | `DSPyOptimizationPage.tsx` (729) | Template selection. Optimization config panel. Run progress monitoring. Results with sync. Code export tab. |
| **Examples** | `views/ml-examples.tsx` | ~420 | `ExampleStorePage.tsx` (637) | Example cards with effectiveness scores. Domain/difficulty filters. Create/edit dialog. Top performers sidebar. |

**Total:** 10 views ported (~4,210 LOC) from 10 VITAL pages (~8,171 LOC) — 51% compression ratio.

All views follow Ontos patterns:
- `useApi` for HTTP, `usePermissions` for RBAC, `useBreadcrumbStore` for navigation
- Shadcn `DataTable` (TanStack Table), `Dialog`, `Card`, `Badge`, `Button`
- `checkApiResponse` helper with graceful 404 handling
- Guard pattern: loading → permission → error → content
- `useTranslation` ready for i18n

### Routes Added to `app.tsx`

| Route | View |
|-------|------|
| `/ml-deploy` | MlDeploy |
| `/ml-monitor` | MlMonitor |
| `/ml-improve` | MlImprove |
| `/ml-templates` | MlTemplateBuilder |
| `/ml-sheets` | MlSheetBuilder |
| `/ml-labels` | MlLabelSets |
| `/ml-curate` | MlCurate |
| `/ml-train` | MlTrain |
| `/ml-dspy` | MlDspy |
| `/ml-examples` | MlExamples |

### Features Added to `features.ts`

All registered under `ML Lifecycle` group with `maturity: 'alpha'`:
- `ml-deploy`, `ml-monitor`, `ml-improve` (showInLanding: true)
- `ml-templates`, `ml-sheets`, `ml-labels`, `ml-curate`, `ml-train`, `ml-dspy`, `ml-examples` (showInLanding: false)

### Not Ported (Deferred to Phase 5)

| View | Reason |
|------|--------|
| **DataQualityPage** | DQX iframe integration — needs DQX endpoint configuration |
| **LabelingJobsPage** | Multi-user labeling task board — needs new backend routes (Phase 3) |
| **ExampleEffectivenessDashboard** | DSPy effectiveness metrics — needs backend analytics endpoints |

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
| **Training Job Service** | Part of VITAL's API routes | New routes in `training_data_routes.py` | Databricks Jobs SDK |
| **Example Store Service** | Part of VITAL's API routes | New routes in `training_data_routes.py` | Existing example_store DB model |

### New API Routes Needed

| Route Prefix | Endpoints | Powers |
|-------------|-----------|--------|
| `/api/ml-deploy` | `GET /models`, `GET /models/{name}/versions`, `POST /deploy`, `GET /endpoints`, `POST /endpoints/{name}/query` | ml-deploy.tsx |
| `/api/ml-monitor` | `GET /metrics`, `GET /alerts`, `POST /alerts/{id}/acknowledge` | ml-monitor.tsx |
| `/api/ml-improve` | `GET /feedback`, `GET /feedback/stats`, `GET /gaps`, `POST /feedback/{id}/convert` | ml-improve.tsx |
| `/api/training-data/training-jobs` | `GET /`, `POST /`, `GET /{id}` | ml-train.tsx |
| `/api/training-data/dspy` | `POST /export/{id}`, `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel`, `POST /runs/{id}/sync` | ml-dspy.tsx |
| `/api/training-data/examples` | `GET /`, `GET /top`, `POST /`, `PUT /{id}`, `DELETE /{id}` | ml-examples.tsx |
| `/api/training-data/collections/{id}/qa-pairs` | `GET /`, `PUT /{pairId}` | ml-curate.tsx |

### New DB Tables (Alembic Migrations)

| Table | Purpose |
|-------|---------|
| `feedback_items` | User feedback on model predictions |
| `drift_alerts` | Drift detection alerts |
| `improvement_cycles` | Track improvement iterations |
| `dspy_optimization_runs` | DSPy optimization history |
| `training_jobs` | Model fine-tuning job tracking |

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
- Port remaining views: DataQualityPage, LabelingJobsPage, ExampleEffectivenessDashboard

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
src/backend/src/common/features.py                      # Phase 1: +training-data, +ml-deploy/monitor/improve
src/backend/src/controller/training_data_manager.py      # Phase 1: fixed imports
src/backend/src/repositories/training_data_repository.py # Phase 1: fixed imports
src/backend/src/routes/training_data_routes.py           # Phase 1: fixed imports
src/frontend/src/config/features.ts                      # Phase 1+2: +ML Lifecycle group, +10 features
src/frontend/src/app.tsx                                 # Phase 2: +10 routes, +10 imports
```

### Ontos Files Created

```
src/frontend/src/views/ml-deploy.tsx           # Phase 2: Deploy view (~420 LOC)
src/frontend/src/views/ml-monitor.tsx          # Phase 2: Monitor view (~310 LOC)
src/frontend/src/views/ml-improve.tsx          # Phase 2: Improve view (~310 LOC)
src/frontend/src/views/ml-template-builder.tsx # Phase 2: Template Builder (~480 LOC)
src/frontend/src/views/ml-sheet-builder.tsx    # Phase 2: Sheet Builder (~470 LOC)
src/frontend/src/views/ml-label-sets.tsx       # Phase 2: Label Sets (~460 LOC)
src/frontend/src/views/ml-curate.tsx           # Phase 2: Curate & Review (~480 LOC)
src/frontend/src/views/ml-train.tsx            # Phase 2: Training Jobs (~430 LOC)
src/frontend/src/views/ml-dspy.tsx             # Phase 2: DSPy Optimizer (~430 LOC)
src/frontend/src/views/ml-examples.tsx         # Phase 2: Example Store (~420 LOC)
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
