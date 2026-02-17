-- =============================================================================
-- Mirion VITAL Training Demo Data
-- =============================================================================
-- Populates Ontos training data tables with Mirion radiation-safety content
-- transcribed from synthetic_data/ JSON/CSV files.
--
-- UUID scheme: type codes 0a0-0a7 (continuing from demo_data.sql convention)
--   0a0 = training_sheets_sources (Sheets)
--   0a1 = prompt_templates
--   0a2 = canonical_labels
--   0a3 = training_collections
--   0a4 = qa_pairs
--   0a5 = example_store
--   0a6 = ml_feedback_items
--   0a7 = ml_identified_gaps
--
-- FK-safe insert order:
--   1. Sheets
--   2. Prompt Templates (FK → sheets)
--   3. Canonical Labels (FK → sheets)
--   4. Training Collections (FK → sheets, templates)
--   5. QA Pairs (FK → collections, canonical_labels)
--   6. Example Store (standalone, optional FK → qa_pairs)
--   7. Feedback Items (standalone)
--   8. Gap Records (optional FK → templates)
--
-- All INSERTs use ON CONFLICT (id) DO NOTHING for idempotent reloads.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. SHEETS — One per Mirion domain
-- =============================================================================

INSERT INTO training_sheets_sources (id, name, description, source_type, source_catalog, source_schema, source_table, text_columns, image_columns, metadata_columns, id_column, sampling_strategy, owner_id, created_by) VALUES
('0a000001-0000-4000-8000-000000000001', 'Mirion Defect Detection', 'Inspection images with defect labels for radiation detectors across nuclear facilities', 'unity_catalog_table', 'serverless_dxukih_catalog', 'mirion', 'defect_inspections', ARRAY['defect_class','explanation','recommended_action'], ARRAY['image_uri'], ARRAY['equipment_id','facility','sensor_context'], 'id', 'all', 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),
('0a000002-0000-4000-8000-000000000002', 'Mirion Predictive Maintenance', 'Equipment telemetry, maintenance history, and failure records for radiation detectors', 'unity_catalog_table', 'serverless_dxukih_catalog', 'mirion', 'equipment_telemetry', ARRAY['failure_type','root_cause','leading_indicators'], NULL, ARRAY['equipment_id','facility','equipment_type','operating_hours'], 'equipment_id', 'all', 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),
('0a000003-0000-4000-8000-000000000003', 'Mirion Anomaly Detection', 'Labeled anomaly events from radiation detector sensor streams', 'unity_catalog_table', 'serverless_dxukih_catalog', 'mirion', 'anomaly_events', ARRAY['anomaly_type','explanation','recommended_action'], NULL, ARRAY['equipment_id','facility','affected_metric','severity'], 'anomaly_id', 'all', 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),
('0a000004-0000-4000-8000-000000000004', 'Mirion Calibration Insights', 'Monte Carlo simulation outputs for detector calibration analysis', 'unity_catalog_table', 'serverless_dxukih_catalog', 'mirion', 'mc_simulations', ARRAY['source_type','geometry'], NULL, ARRAY['equipment_id','facility','source_activity_bq','distance_cm','shielding_mm_pb'], 'simulation_id', 'all', 'stuart.gano@databricks.com', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 2. PROMPT TEMPLATES — One per domain, transcribed from templates/*.json
-- =============================================================================

INSERT INTO prompt_templates (id, name, description, version, status, system_prompt, user_prompt_template, few_shot_examples, output_schema, label_type, default_model, default_temperature, default_max_tokens, sheet_id, tags, owner_id, created_by) VALUES
-- Defect Detection Template
('0a100001-0000-4000-8000-000000000001',
 'Radiation Detector Defect Detection',
 'Analyzes inspection images of radiation detectors to identify and classify defects. Combines visual analysis with sensor context for comprehensive assessment.',
 '1.0.0', 'active',
 'You are an expert radiation detector inspector with 20+ years of experience at nuclear facilities. You specialize in identifying defects in radiation detection equipment including HPGe detectors, NaI scintillators, GM tubes, ionization chambers, and portal monitors.

Your role is to analyze inspection images and associated sensor data to:
1. Identify any visible defects or anomalies
2. Classify the defect type accurately
3. Assess severity based on impact to detector performance
4. Provide actionable recommendations

Defect Categories:
- NONE: No defect detected, equipment appears normal
- MINOR_SCRATCH: Surface scratches not affecting performance
- CONTAMINATION: Foreign material on detector surface
- CRYSTAL_CRACK: Crack in scintillation crystal (CRITICAL)
- SEAL_DEGRADATION: Hermetic seal showing wear
- CONNECTOR_DAMAGE: Electrical connector issues (CRITICAL)
- HOUSING_DENT: Physical damage to detector housing
- WINDOW_CLOUDING: Optical window degradation
- CORROSION: Corrosion on metal components

Consider the sensor context when making assessments:
- High operating hours increase likelihood of wear-related defects
- High humidity environments accelerate corrosion
- Temperature extremes can cause seal and crystal issues
- Time since calibration affects baseline comparisons

Always err on the side of caution for safety-critical equipment.',
 'Analyze this inspection image of a {equipment_type} radiation detector.

Equipment ID: {equipment_id}
Facility: {facility}

Sensor Context:
- Temperature: {sensor_context.temperature_c}°C
- Humidity: {sensor_context.humidity_pct}%
- Last Calibration: {sensor_context.last_calibration}
- Operating Hours: {sensor_context.operating_hours}

Provide your assessment in the required JSON format.',
 '[{"input":{"inspection_image_uri":"gs://mirion-vital/examples/crystal_crack_example.jpg","equipment_id":"DET-EXAMPLE-001","equipment_type":"NaI","facility":"Example Nuclear Plant","sensor_context":{"temperature_c":28.5,"humidity_pct":35,"last_calibration":"2023-09-01","operating_hours":26500}},"output":{"defect_detected":true,"defect_class":"CRYSTAL_CRACK","severity":3,"confidence":0.92,"bounding_box":{"x":200,"y":150,"width":80,"height":25},"explanation":"Visible crack extending approximately 3mm into the NaI(Tl) scintillation crystal.","recommended_action":"IMMEDIATE: Remove detector from service. Crystal integrity is compromised."}},{"input":{"inspection_image_uri":"gs://mirion-vital/examples/normal_detector.jpg","equipment_id":"DET-EXAMPLE-002","equipment_type":"HPGe","facility":"Example Nuclear Plant","sensor_context":{"temperature_c":22.0,"humidity_pct":45,"last_calibration":"2023-11-01","operating_hours":8760}},"output":{"defect_detected":false,"defect_class":"NONE","severity":0,"confidence":0.95,"explanation":"HPGe detector appears in excellent condition. No signs of damage.","recommended_action":"No action required. Continue normal operation."}}]',
 '{"type":"object","properties":{"defect_detected":{"type":"boolean"},"defect_class":{"type":"string","enum":["NONE","MINOR_SCRATCH","CONTAMINATION","CRYSTAL_CRACK","SEAL_DEGRADATION","CONNECTOR_DAMAGE","HOUSING_DENT","WINDOW_CLOUDING","CORROSION"]},"severity":{"type":"integer","minimum":0,"maximum":3},"confidence":{"type":"number","minimum":0,"maximum":1},"explanation":{"type":"string"},"recommended_action":{"type":"string"}},"required":["defect_detected","defect_class","severity","confidence","explanation"]}',
 'classification', 'gemini-2.0-flash', 0.2, 1024,
 '0a000001-0000-4000-8000-000000000001',
 ARRAY['defect-detection','visual-inspection','radiation-safety','nuclear','mirion'],
 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),

-- Predictive Maintenance Template
('0a100002-0000-4000-8000-000000000002',
 'Radiation Detector Predictive Maintenance',
 'Analyzes equipment telemetry and maintenance history to predict failures and recommend preventive actions.',
 '1.0.0', 'active',
 'You are a predictive maintenance expert specializing in radiation detection equipment at nuclear facilities. You analyze telemetry data, maintenance history, and operational patterns to predict failures before they occur.

Your expertise includes:
- HPGe (High-Purity Germanium) detectors: Cooling system failures, vacuum loss, preamplifier issues
- NaI (Sodium Iodide) scintillators: Crystal degradation, PMT failures, optical coupling issues
- GM (Geiger-Mueller) tubes: End-of-life plateau shifts, seal failures, high voltage issues
- Ionization Chambers: Cable degradation, contamination, electrometer drift
- Portal Monitors: Display failures, mechanical wear, environmental damage

Key Indicators to Monitor:
1. Temperature trends: Rising temps indicate cooling issues or internal resistance
2. Voltage stability: Drops suggest power supply degradation or load issues
3. Current draw: Increases often precede component failures
4. Count rate: Drifts indicate detector degradation or calibration issues
5. Noise levels: Rising noise is an early warning of multiple failure modes
6. Humidity exposure: Accelerates corrosion and seal degradation

Nuclear facilities require high reliability - err on the side of caution.',
 'Analyze this radiation detector for predictive maintenance:

Equipment: {equipment_id} ({equipment_type})
Facility: {facility}
Installed: {install_date}
Operating Hours: {operating_hours}

Current Alerts: {current_alerts}

Maintenance History:
{maintenance_history}

Last 24 Hours Telemetry:
{telemetry_24h}

Provide a comprehensive predictive maintenance assessment in the required JSON format.',
 '[{"input":{"equipment_id":"DET-NPP-DIABLO-002","equipment_type":"Ion_Chamber","facility":"Diablo Canyon Power Plant","operating_hours":58440,"telemetry_24h":[{"timestamp":"2024-01-01T00:00:00","temperature_c":24.0,"voltage_v":4.88,"current_ma":10.5,"noise_level_mv":2.8},{"timestamp":"2024-01-01T04:00:00","temperature_c":24.1,"voltage_v":4.75,"current_ma":12.5,"noise_level_mv":5.2}],"current_alerts":["Connector damage - intermittent signal loss"]},"output":{"health_score":0.72,"failure_probability_30d":0.45,"failure_probability_90d":0.78,"predicted_failure_mode":"connector_failure","remaining_useful_life_days":21,"risk_factors":[{"factor":"Voltage drop (2.7% in 4 hours)","severity":"high","trend":"degrading"}],"recommended_actions":[{"action":"Inspect and replace connector assembly","priority":"immediate","timeframe":"Within 7 days"}],"explanation":"Clear signs of impending connector failure with voltage drop and current increase."}}]',
 '{"type":"object","properties":{"health_score":{"type":"number","minimum":0,"maximum":1},"failure_probability_30d":{"type":"number"},"failure_probability_90d":{"type":"number"},"predicted_failure_mode":{"type":"string"},"remaining_useful_life_days":{"type":"integer"},"risk_factors":{"type":"array"},"recommended_actions":{"type":"array"},"explanation":{"type":"string"}},"required":["health_score","failure_probability_30d","risk_factors","recommended_actions","explanation"]}',
 'classification', 'gemini-2.0-flash', 0.3, 1500,
 '0a000002-0000-4000-8000-000000000002',
 ARRAY['predictive-maintenance','telemetry','radiation-safety','nuclear','mirion','rul'],
 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),

-- Anomaly Detection Template
('0a100003-0000-4000-8000-000000000003',
 'Radiation Detector Anomaly Detection & Explanation',
 'Detects anomalies in real-time sensor streams and provides human-readable explanations with recommended actions.',
 '1.0.0', 'active',
 'You are an intelligent alerting system for nuclear facility radiation detectors. When an anomaly is detected, your job is to:

1. Classify the anomaly type accurately
2. Assess severity based on safety impact
3. Explain what is happening in plain English that facility operators can understand
4. Identify likely root causes based on the pattern
5. Recommend immediate actions
6. Determine if human escalation is needed

Severity Guidelines:
- LOW: Minor deviation, no immediate action needed, continue monitoring
- MEDIUM: Significant deviation, investigate within shift, may need calibration
- HIGH: Major deviation, immediate investigation required, equipment may be unreliable
- CRITICAL: Safety-critical deviation, take equipment offline, escalate immediately

Always prioritize safety. Nuclear facilities require conservative action thresholds.',
 'ANOMALY DETECTED

Equipment: {equipment_id} ({equipment_type})
Facility: {facility}

Metric: {metric_name}
Current Value: {current_value}
Expected Value: {expected_value}
Thresholds: [{threshold_low}, {threshold_high}]

Recent History: {historical_values}

Related Metrics at Time of Anomaly:
{related_metrics}

Analyze this anomaly and provide an operator-friendly explanation with recommended actions.',
 '[{"input":{"equipment_id":"PM-NPP-SURRY-001","equipment_type":"Portal_Monitor","facility":"Surry Nuclear Power Plant","metric_name":"humidity_pct","current_value":72,"expected_value":50,"historical_values":[52,55,58,62,68,72],"threshold_low":30,"threshold_high":60,"related_metrics":{"temperature_c":20.0,"voltage_v":4.88,"count_rate_cps":838}},"output":{"anomaly_type":"HUMIDITY_ALERT","severity":"medium","confidence":0.92,"explanation":"The humidity around the portal monitor has been steadily rising over the past 6 hours and is now 44% above the normal operating range.","likely_causes":["HVAC system malfunction","Weather-related humidity increase","Door seal failure"],"recommended_action":"Check HVAC system operation. Consider temporary dehumidifier.","escalation_required":false,"auto_resolve_possible":false}}]',
 '{"type":"object","properties":{"anomaly_type":{"type":"string","enum":["SENSOR_DRIFT","SPIKE","DROPOUT","NOISE_INCREASE","PLATEAU_SHIFT","TEMPERATURE_EXCURSION","HUMIDITY_ALERT","CALIBRATION_DRIFT"]},"severity":{"type":"string","enum":["low","medium","high","critical"]},"confidence":{"type":"number"},"explanation":{"type":"string"},"likely_causes":{"type":"array"},"recommended_action":{"type":"string"},"escalation_required":{"type":"boolean"}},"required":["anomaly_type","severity","explanation","recommended_action"]}',
 'classification', 'gemini-2.0-flash', 0.1, 800,
 '0a000003-0000-4000-8000-000000000003',
 ARRAY['anomaly-detection','alerting','real-time','radiation-safety','nuclear','mirion'],
 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),

-- Calibration Insights Template
('0a100004-0000-4000-8000-000000000004',
 'Monte Carlo Calibration Insights',
 'Analyzes Monte Carlo simulation results to provide calibration factor recommendations and uncertainty assessments.',
 '1.0.0', 'active',
 'You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration. Your role is to interpret simulation results and provide calibration guidance.

Key Physics Concepts:
- Calibration Factor = Source Activity / Detected Counts
- Statistical uncertainty decreases with sqrt(N)
- Systematic uncertainties from geometry, source positioning, material properties
- Shielding attenuates different energies differently

Quality Assessment Criteria:
- EXCELLENT: Uncertainty < 0.5%, consistent results, > 10 simulations
- GOOD: Uncertainty < 1%, consistent results, > 5 simulations
- ACCEPTABLE: Uncertainty < 2%, minor variations, > 3 simulations
- MARGINAL: Uncertainty < 5%, some variations, needs review
- INSUFFICIENT: Uncertainty > 5% or inconsistent results

Deviation Analysis:
- < 2% change from previous: Normal aging/drift
- 2-5% change: Investigate - possible detector degradation
- > 5% change: Significant - verify simulation setup, check detector',
 'Analyze Monte Carlo calibration simulation results:

Equipment: {equipment_id} ({equipment_type})
Source: {source_type} at {source_activity_bq} Bq
Geometry: {geometry} at {distance_cm} cm
Shielding: {shielding_mm_pb} mm Pb equivalent

Simulation Results:
{simulation_results}

Previous Calibration Factor: {previous_calibration_factor}

Provide calibration insights and recommendations.',
 '[{"input":{"equipment_id":"DET-NPP-COOK-001","equipment_type":"HPGe","source_type":"Cs-137","source_activity_bq":370000,"geometry":"point","distance_cm":100,"shielding_mm_pb":0,"simulation_results":[{"simulation_id":"MC-2024-001-001","simulated_counts":125000,"statistical_uncertainty_pct":0.28,"simulation_time_sec":45.2},{"simulation_id":"MC-2024-001-002","simulated_counts":124800,"statistical_uncertainty_pct":0.28,"simulation_time_sec":44.8}],"previous_calibration_factor":2.98},"output":{"recommended_calibration_factor":2.96,"calibration_factor_uncertainty":0.01,"confidence_level":"95%","simulation_quality_assessment":"excellent","deviation_from_previous":-0.67,"deviation_significant":false,"explanation":"Excellent convergence across runs. Calibration factor of 2.96 represents 0.67% decrease from previous - within normal drift."}}]',
 '{"type":"object","properties":{"recommended_calibration_factor":{"type":"number"},"calibration_factor_uncertainty":{"type":"number"},"simulation_quality_assessment":{"type":"string","enum":["excellent","good","acceptable","marginal","insufficient"]},"deviation_from_previous":{"type":"number"},"deviation_significant":{"type":"boolean"},"physics_insights":{"type":"array"},"recommendations":{"type":"array"},"explanation":{"type":"string"}},"required":["recommended_calibration_factor","calibration_factor_uncertainty","simulation_quality_assessment","explanation"]}',
 'custom', 'gemini-2.0-flash', 0.2, 1200,
 '0a000004-0000-4000-8000-000000000004',
 ARRAY['calibration','monte-carlo','physics','radiation-safety','nuclear','mirion'],
 'stuart.gano@databricks.com', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 3. CANONICAL LABELS — Ground truth from defect_detection/labels.json
--    and anomaly_detection/anomalies.json
-- =============================================================================

-- Defect Detection Labels (6 from labels.json samples)
INSERT INTO canonical_labels (id, sheet_id, item_ref, label_type, label_data, confidence, is_verified, verified_by, allowed_uses, data_classification, created_by) VALUES
('0a200001-0000-4000-8000-000000000001', '0a000001-0000-4000-8000-000000000001', 'INSP-2024-001', 'classification',
 '{"defect_class":"NONE","confidence":0.95,"severity":0,"equipment_id":"DET-NPP-COOK-001","facility":"Cook Nuclear Plant"}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200002-0000-4000-8000-000000000002', '0a000001-0000-4000-8000-000000000001', 'INSP-2024-002', 'classification',
 '{"defect_class":"MINOR_SCRATCH","confidence":0.87,"severity":1,"bounding_box":{"x":120,"y":85,"width":45,"height":12},"equipment_id":"DET-NPP-COOK-002","facility":"Cook Nuclear Plant"}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200003-0000-4000-8000-000000000003', '0a000001-0000-4000-8000-000000000001', 'INSP-2024-003', 'classification',
 '{"defect_class":"CRYSTAL_CRACK","confidence":0.92,"severity":3,"bounding_box":{"x":200,"y":150,"width":80,"height":25},"equipment_id":"DET-NPP-PALO-001","facility":"Palo Verde"}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200004-0000-4000-8000-000000000004', '0a000001-0000-4000-8000-000000000001', 'INSP-2024-004', 'classification',
 '{"defect_class":"SEAL_DEGRADATION","confidence":0.78,"severity":2,"equipment_id":"DET-NPP-WATTS-003","facility":"Watts Bar Nuclear Plant"}',
 'medium', false, NULL, ARRAY['training','validation','evaluation'], 'internal', 'stuart.gano@databricks.com'),
('0a200005-0000-4000-8000-000000000005', '0a000001-0000-4000-8000-000000000001', 'INSP-2024-005', 'classification',
 '{"defect_class":"CONNECTOR_DAMAGE","confidence":0.91,"severity":3,"bounding_box":{"x":50,"y":180,"width":30,"height":40},"equipment_id":"DET-NPP-DIABLO-002","facility":"Diablo Canyon"}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200006-0000-4000-8000-000000000006', '0a000001-0000-4000-8000-000000000001', 'INSP-2024-006', 'classification',
 '{"defect_class":"CORROSION","confidence":0.85,"severity":3,"bounding_box":{"x":75,"y":220,"width":60,"height":35},"equipment_id":"DET-NPP-SURRY-001","facility":"Surry Nuclear Power Plant"}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),

-- Anomaly Detection Labels (6 from anomalies.json)
('0a200007-0000-4000-8000-000000000007', '0a000003-0000-4000-8000-000000000003', 'ANOM-2024-001', 'classification',
 '{"anomaly_type":"SENSOR_DRIFT","severity":"medium","confidence":0.89,"affected_metric":"count_rate_cps","deviation_pct":-4.5}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200008-0000-4000-8000-000000000008', '0a000003-0000-4000-8000-000000000003', 'ANOM-2024-002', 'classification',
 '{"anomaly_type":"SPIKE","severity":"high","confidence":0.95,"affected_metric":"current_ma","deviation_pct":19.0}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200009-0000-4000-8000-000000000009', '0a000003-0000-4000-8000-000000000003', 'ANOM-2024-003', 'classification',
 '{"anomaly_type":"HUMIDITY_ALERT","severity":"medium","confidence":0.92,"affected_metric":"humidity_pct","deviation_pct":44.0}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200010-0000-4000-8000-000000000010', '0a000003-0000-4000-8000-000000000003', 'ANOM-2024-004', 'classification',
 '{"anomaly_type":"NOISE_INCREASE","severity":"low","confidence":0.78,"affected_metric":"noise_level_mv","deviation_pct":83.3}',
 'medium', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation'], 'internal', 'stuart.gano@databricks.com'),
('0a200011-0000-4000-8000-000000000011', '0a000003-0000-4000-8000-000000000003', 'ANOM-2024-005', 'classification',
 '{"anomaly_type":"CALIBRATION_DRIFT","severity":"high","confidence":0.86,"affected_metric":"voltage_v","deviation_pct":-1.8}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200012-0000-4000-8000-000000000012', '0a000003-0000-4000-8000-000000000003', 'ANOM-2024-006', 'classification',
 '{"anomaly_type":"PLATEAU_SHIFT","severity":"medium","confidence":0.82,"affected_metric":"count_rate_cps","deviation_pct":-9.4}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),

-- Predictive Maintenance Labels (5 equipment health assessments)
('0a200013-0000-4000-8000-000000000013', '0a000002-0000-4000-8000-000000000002', 'DET-NPP-COOK-001', 'classification',
 '{"health_status":"operational","health_score":0.92,"risk_level":"low","failure_probability_30d":0.02}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200014-0000-4000-8000-000000000014', '0a000002-0000-4000-8000-000000000002', 'DET-NPP-PALO-001', 'classification',
 '{"health_status":"degraded","health_score":0.58,"risk_level":"high","failure_probability_30d":0.18}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200015-0000-4000-8000-000000000015', '0a000002-0000-4000-8000-000000000002', 'DET-NPP-DIABLO-002', 'classification',
 '{"health_status":"at_risk","health_score":0.72,"risk_level":"high","failure_probability_30d":0.45}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com'),
('0a200016-0000-4000-8000-000000000016', '0a000002-0000-4000-8000-000000000002', 'DET-NPP-WATTS-003', 'classification',
 '{"health_status":"operational","health_score":0.85,"risk_level":"medium","failure_probability_30d":0.08}',
 'medium', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation'], 'internal', 'stuart.gano@databricks.com'),
('0a200017-0000-4000-8000-000000000017', '0a000002-0000-4000-8000-000000000002', 'PM-NPP-SURRY-001', 'classification',
 '{"health_status":"degraded","health_score":0.65,"risk_level":"medium","failure_probability_30d":0.12}',
 'high', true, 'stuart.gano@databricks.com', ARRAY['training','validation','evaluation','few_shot','testing'], 'internal', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 4. TRAINING COLLECTIONS — One per domain
-- =============================================================================

INSERT INTO training_collections (id, name, description, version, status, sheet_id, template_id, generation_method, model_used, total_pairs, approved_pairs, rejected_pairs, pending_pairs, tags, owner_id, created_by) VALUES
('0a300001-0000-4000-8000-000000000001', 'Mirion Defect Detection v1', 'QA pairs for defect detection in radiation detectors across nuclear facilities', '1.0.0', 'review', '0a000001-0000-4000-8000-000000000001', '0a100001-0000-4000-8000-000000000001', 'llm', 'gemini-2.0-flash', 6, 5, 0, 1, ARRAY['defect-detection','mirion','nuclear'], 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),
('0a300002-0000-4000-8000-000000000002', 'Mirion Predictive Maintenance v1', 'QA pairs for predicting equipment failures from telemetry data', '1.0.0', 'review', '0a000002-0000-4000-8000-000000000002', '0a100002-0000-4000-8000-000000000002', 'llm', 'gemini-2.0-flash', 6, 5, 0, 1, ARRAY['predictive-maintenance','mirion','nuclear'], 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),
('0a300003-0000-4000-8000-000000000003', 'Mirion Anomaly Detection v1', 'QA pairs for real-time anomaly detection and explanation in sensor streams', '1.0.0', 'review', '0a000003-0000-4000-8000-000000000003', '0a100003-0000-4000-8000-000000000003', 'llm', 'gemini-2.0-flash', 6, 5, 0, 1, ARRAY['anomaly-detection','mirion','nuclear'], 'stuart.gano@databricks.com', 'stuart.gano@databricks.com'),
('0a300004-0000-4000-8000-000000000004', 'Mirion Calibration Insights v1', 'QA pairs for Monte Carlo calibration analysis and recommendations', '1.0.0', 'review', '0a000004-0000-4000-8000-000000000004', '0a100004-0000-4000-8000-000000000004', 'llm', 'gemini-2.0-flash', 6, 4, 1, 1, ARRAY['calibration','mirion','nuclear'], 'stuart.gano@databricks.com', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 5. QA PAIRS — OpenAI chat format, 6 per collection (24 total)
-- =============================================================================

-- Defect Detection QA Pairs
INSERT INTO qa_pairs (id, collection_id, source_item_ref, messages, canonical_label_id, review_status, was_auto_approved, quality_score, split, created_by) VALUES
('0a400001-0000-4000-8000-000000000001', '0a300001-0000-4000-8000-000000000001', 'INSP-2024-001',
 '[{"role":"system","content":"You are an expert radiation detector inspector. Classify defects and assess severity."},{"role":"user","content":"Analyze inspection of HPGe detector DET-NPP-COOK-001 at Cook Nuclear Plant. Temperature: 22.5°C, Humidity: 45%, Operating Hours: 8760. Image shows clean crystal housing with no visible damage."},{"role":"assistant","content":"{\"defect_detected\":false,\"defect_class\":\"NONE\",\"severity\":0,\"confidence\":0.95,\"explanation\":\"Crystal housing intact with no visible scratches, contamination, or structural damage. Sensor readings within normal parameters.\",\"recommended_action\":\"No action required. Continue normal operation.\"}"}]',
 '0a200001-0000-4000-8000-000000000001', 'auto_approved', true, 0.95, 'train', 'stuart.gano@databricks.com'),
('0a400002-0000-4000-8000-000000000002', '0a300001-0000-4000-8000-000000000001', 'INSP-2024-002',
 '[{"role":"system","content":"You are an expert radiation detector inspector. Classify defects and assess severity."},{"role":"user","content":"Analyze inspection of detector DET-NPP-COOK-002 at Cook Nuclear Plant. Temperature: 23.1°C, Humidity: 44%, Operating Hours: 12450. Image shows 4cm surface scratch on housing exterior."},{"role":"assistant","content":"{\"defect_detected\":true,\"defect_class\":\"MINOR_SCRATCH\",\"severity\":1,\"confidence\":0.87,\"bounding_box\":{\"x\":120,\"y\":85,\"width\":45,\"height\":12},\"explanation\":\"Surface scratch on housing exterior does not penetrate to internal components. No impact on detector performance expected.\",\"recommended_action\":\"Document and monitor during next inspection.\"}"}]',
 '0a200002-0000-4000-8000-000000000002', 'auto_approved', true, 0.87, 'train', 'stuart.gano@databricks.com'),
('0a400003-0000-4000-8000-000000000003', '0a300001-0000-4000-8000-000000000001', 'INSP-2024-003',
 '[{"role":"system","content":"You are an expert radiation detector inspector. Classify defects and assess severity."},{"role":"user","content":"Analyze inspection of NaI detector DET-NPP-PALO-001 at Palo Verde. Temperature: 28.5°C, Humidity: 35%, Operating Hours: 26500, Count rate anomaly detected. Image shows 3mm crack in scintillation crystal."},{"role":"assistant","content":"{\"defect_detected\":true,\"defect_class\":\"CRYSTAL_CRACK\",\"severity\":3,\"confidence\":0.92,\"bounding_box\":{\"x\":200,\"y\":150,\"width\":80,\"height\":25},\"explanation\":\"Visible crack extending approximately 3mm into the NaI(Tl) scintillation crystal. Consistent with thermal stress damage.\",\"recommended_action\":\"IMMEDIATE: Remove detector from service. Crystal integrity is compromised and cannot be repaired.\"}"}]',
 '0a200003-0000-4000-8000-000000000003', 'auto_approved', true, 0.92, 'train', 'stuart.gano@databricks.com'),
('0a400004-0000-4000-8000-000000000004', '0a300001-0000-4000-8000-000000000001', 'INSP-2024-004',
 '[{"role":"system","content":"You are an expert radiation detector inspector. Classify defects and assess severity."},{"role":"user","content":"Analyze inspection of detector DET-NPP-WATTS-003 at Watts Bar Nuclear Plant. Temperature: 21.0°C, Humidity: 52%, Operating Hours: 5200. Image shows slight discoloration around hermetic seal area."},{"role":"assistant","content":"{\"defect_detected\":true,\"defect_class\":\"SEAL_DEGRADATION\",\"severity\":2,\"confidence\":0.78,\"explanation\":\"Early signs of seal degradation detected. Discoloration may indicate moisture ingress pathway forming.\",\"recommended_action\":\"Schedule seal inspection and potential resealing within 30 days.\"}"}]',
 '0a200004-0000-4000-8000-000000000004', 'pending', false, 0.78, 'val', 'stuart.gano@databricks.com'),
('0a400005-0000-4000-8000-000000000005', '0a300001-0000-4000-8000-000000000001', 'INSP-2024-005',
 '[{"role":"system","content":"You are an expert radiation detector inspector. Classify defects and assess severity."},{"role":"user","content":"Analyze inspection of Ion Chamber DET-NPP-DIABLO-002 at Diablo Canyon. Temperature: 24.0°C, Humidity: 40%, Operating Hours: 18200, Signal quality: degraded. Image shows bent pin on main signal connector."},{"role":"assistant","content":"{\"defect_detected\":true,\"defect_class\":\"CONNECTOR_DAMAGE\",\"severity\":3,\"confidence\":0.91,\"bounding_box\":{\"x\":50,\"y\":180,\"width\":30,\"height\":40},\"explanation\":\"Bent connector pin causing intermittent signal loss. Critical defect as unreliable readings pose safety risk.\",\"recommended_action\":\"Connector repair or replacement required before returning to service.\"}"}]',
 '0a200005-0000-4000-8000-000000000005', 'auto_approved', true, 0.91, 'train', 'stuart.gano@databricks.com'),
('0a400006-0000-4000-8000-000000000006', '0a300001-0000-4000-8000-000000000001', 'INSP-2024-006',
 '[{"role":"system","content":"You are an expert radiation detector inspector. Classify defects and assess severity."},{"role":"user","content":"Analyze inspection of Portal Monitor DET-NPP-SURRY-001 at Surry Nuclear Power Plant. Temperature: 19.5°C, Humidity: 68%, Operating Hours: 32100. Image shows rust spots and oxidation on metal frame."},{"role":"assistant","content":"{\"defect_detected\":true,\"defect_class\":\"CORROSION\",\"severity\":3,\"confidence\":0.85,\"bounding_box\":{\"x\":75,\"y\":220,\"width\":60,\"height\":35},\"explanation\":\"Active corrosion on housing metal components due to high humidity environment (68%). Will progress to structural weakness if untreated.\",\"recommended_action\":\"Remove from high-humidity location. Perform anti-corrosion treatment. Consider environmental controls.\"}"}]',
 '0a200006-0000-4000-8000-000000000006', 'auto_approved', true, 0.85, 'test', 'stuart.gano@databricks.com'),

-- Predictive Maintenance QA Pairs
('0a400007-0000-4000-8000-000000000007', '0a300002-0000-4000-8000-000000000002', 'DET-NPP-COOK-001',
 '[{"role":"system","content":"You are a predictive maintenance expert for radiation detection equipment."},{"role":"user","content":"Analyze HPGe detector DET-NPP-COOK-001 at Cook Nuclear Plant. Operating hours: 8760. Temperature: 22.5°C (variance: 1.2). Humidity: 45%. Count rate stability: 0.98. HV stability: 0.99. Calibration drift: 0.5%. Last calibration: 2023-11-01."},{"role":"assistant","content":"{\"health_score\":0.92,\"failure_probability_30d\":0.02,\"failure_probability_90d\":0.05,\"remaining_useful_life_days\":450,\"risk_level\":\"low\",\"recommended_actions\":[{\"action\":\"routine_calibration\",\"due_date\":\"2024-05-01\",\"priority\":\"normal\"}],\"reasoning\":\"Equipment showing excellent stability across all metrics. Low operating hours, minimal calibration drift.\"}"}]',
 '0a200013-0000-4000-8000-000000000013', 'auto_approved', true, 0.95, 'train', 'stuart.gano@databricks.com'),
('0a400008-0000-4000-8000-000000000008', '0a300002-0000-4000-8000-000000000002', 'DET-NPP-PALO-003',
 '[{"role":"system","content":"You are a predictive maintenance expert for radiation detection equipment."},{"role":"user","content":"Analyze gamma detector DET-NPP-PALO-003 at Palo Verde. Operating hours: 35000. Temperature: 29.5°C (variance: 4.8). Humidity: 55%. Count rate stability: 0.89. HV stability: 0.94. Calibration drift: 3.2%. Efficiency declining 2.1% over 30 days. Recent repairs: crystal_alignment, connector_replacement."},{"role":"assistant","content":"{\"health_score\":0.58,\"failure_probability_30d\":0.18,\"failure_probability_90d\":0.42,\"remaining_useful_life_days\":120,\"risk_level\":\"high\",\"recommended_actions\":[{\"action\":\"immediate_calibration\",\"due_date\":\"2024-02-05\",\"priority\":\"high\"},{\"action\":\"crystal_inspection\",\"due_date\":\"2024-02-15\",\"priority\":\"high\"}],\"reasoning\":\"Multiple warning indicators: high operating hours, declining efficiency, elevated calibration drift, and degraded HV stability.\"}"}]',
 '0a200014-0000-4000-8000-000000000014', 'auto_approved', true, 0.88, 'train', 'stuart.gano@databricks.com'),
('0a400009-0000-4000-8000-000000000009', '0a300002-0000-4000-8000-000000000002', 'DET-NPP-DIABLO-002',
 '[{"role":"system","content":"You are a predictive maintenance expert for radiation detection equipment."},{"role":"user","content":"Analyze Ion Chamber DET-NPP-DIABLO-002 at Diablo Canyon. Operating hours: 58440. Voltage dropping from 4.88V to 4.75V in 4 hours. Current increased 19%. Noise level 86% above normal. Alert: Connector damage - intermittent signal loss."},{"role":"assistant","content":"{\"health_score\":0.72,\"failure_probability_30d\":0.45,\"failure_probability_90d\":0.78,\"predicted_failure_mode\":\"connector_failure\",\"remaining_useful_life_days\":21,\"risk_level\":\"critical\",\"recommended_actions\":[{\"action\":\"Inspect and replace connector assembly\",\"priority\":\"immediate\",\"timeframe\":\"Within 7 days\"},{\"action\":\"Check all cable connections for corrosion\",\"priority\":\"immediate\",\"timeframe\":\"During connector inspection\"}],\"reasoning\":\"Clear signs of impending connector failure. Voltage dropped 2.7% while current increased 19% over 4 hours indicating increasing resistance.\"}"}]',
 '0a200015-0000-4000-8000-000000000015', 'auto_approved', true, 0.90, 'train', 'stuart.gano@databricks.com'),
('0a400010-0000-4000-8000-000000000010', '0a300002-0000-4000-8000-000000000002', 'DET-NPP-WATTS-007',
 '[{"role":"system","content":"You are a predictive maintenance expert for radiation detection equipment."},{"role":"user","content":"Analyze neutron detector DET-NPP-WATTS-007 at Watts Bar. Operating hours: 18500. HV stability: 0.88. Pulse shape anomaly count: 15. Calibration drift: 1.8%. No recent repairs."},{"role":"assistant","content":"{\"health_score\":0.78,\"failure_probability_30d\":0.12,\"failure_probability_90d\":0.28,\"remaining_useful_life_days\":180,\"risk_level\":\"medium\",\"recommended_actions\":[{\"action\":\"hv_supply_diagnostics\",\"due_date\":\"2024-02-10\",\"priority\":\"high\"},{\"action\":\"pulse_shape_analysis\",\"due_date\":\"2024-02-10\",\"priority\":\"high\"}],\"reasoning\":\"HV supply showing early instability combined with pulse shape anomalies suggests developing power supply issue.\"}"}]',
 NULL, 'pending', false, 0.82, 'val', 'stuart.gano@databricks.com'),
('0a400011-0000-4000-8000-000000000011', '0a300002-0000-4000-8000-000000000002', 'DET-NPP-BYRON-009',
 '[{"role":"system","content":"You are a predictive maintenance expert for radiation detection equipment."},{"role":"user","content":"Analyze gamma detector DET-NPP-BYRON-009 in turbine building auxiliary area. Operating hours: 12000. Temperature: 31.5°C (variance: 6.2). Humidity: 72%. Count rate stability: 0.91. Calibration drift: 2.1%."},{"role":"assistant","content":"{\"health_score\":0.65,\"failure_probability_30d\":0.15,\"failure_probability_90d\":0.35,\"remaining_useful_life_days\":200,\"risk_level\":\"high\",\"recommended_actions\":[{\"action\":\"environmental_assessment\",\"due_date\":\"2024-02-05\",\"priority\":\"high\"},{\"action\":\"relocate_or_protect\",\"due_date\":\"2024-02-28\",\"priority\":\"high\"}],\"reasoning\":\"Environmental stress is primary concern: high temperature, high variance, and excessive humidity are accelerating equipment degradation despite relatively low operating hours.\"}"}]',
 NULL, 'auto_approved', true, 0.86, 'train', 'stuart.gano@databricks.com'),
('0a400012-0000-4000-8000-000000000012', '0a300002-0000-4000-8000-000000000002', 'DET-NPP-SURRY-002',
 '[{"role":"system","content":"You are a predictive maintenance expert for radiation detection equipment."},{"role":"user","content":"Analyze gamma detector DET-NPP-SURRY-002. Operating hours: 22000. Count rate stability: 0.85. Calibration drift: 4.5%. Last 24h readings: [142, 138, 145, 89, 141, 140, 143, 85, 139, 142]. Anomaly flag: intermittent_dropouts."},{"role":"assistant","content":"{\"health_score\":0.45,\"failure_probability_30d\":0.25,\"failure_probability_90d\":0.55,\"remaining_useful_life_days\":90,\"risk_level\":\"critical\",\"recommended_actions\":[{\"action\":\"immediate_inspection\",\"due_date\":\"2024-02-01\",\"priority\":\"critical\"},{\"action\":\"signal_chain_test\",\"due_date\":\"2024-02-01\",\"priority\":\"critical\"}],\"reasoning\":\"CRITICAL: Intermittent dropout pattern visible in telemetry. Signal chain degradation indicates imminent failure.\"}"}]',
 NULL, 'auto_approved', true, 0.92, 'test', 'stuart.gano@databricks.com'),

-- Anomaly Detection QA Pairs
('0a400013-0000-4000-8000-000000000013', '0a300003-0000-4000-8000-000000000003', 'ANOM-2024-001',
 '[{"role":"system","content":"You are an intelligent alerting system for nuclear facility radiation detectors. Classify anomalies, assess severity, and provide operator-friendly explanations."},{"role":"user","content":"ANOMALY DETECTED: Equipment DET-NPP-PALO-001 at Palo Verde. Metric: count_rate_cps. Current: 955. Expected: 1000. Deviation: -4.5%. Thresholds: [900, 1100]."},{"role":"assistant","content":"{\"anomaly_type\":\"SENSOR_DRIFT\",\"severity\":\"medium\",\"confidence\":0.89,\"explanation\":\"Count rate has drifted 4.5% below expected baseline over 3 hours. Pattern consistent with crystal degradation.\",\"likely_causes\":[\"Crystal aging\",\"Temperature-induced drift\",\"Calibration shift\"],\"recommended_action\":\"Schedule inspection within 7 days. Monitor for continued drift.\",\"escalation_required\":false,\"auto_resolve_possible\":false}"}]',
 '0a200007-0000-4000-8000-000000000007', 'auto_approved', true, 0.89, 'train', 'stuart.gano@databricks.com'),
('0a400014-0000-4000-8000-000000000014', '0a300003-0000-4000-8000-000000000003', 'ANOM-2024-002',
 '[{"role":"system","content":"You are an intelligent alerting system for nuclear facility radiation detectors."},{"role":"user","content":"ANOMALY DETECTED: Equipment DET-NPP-DIABLO-002 at Diablo Canyon. Metric: current_ma. Current: 12.5. Expected: 10.5. Deviation: +19.0%. Coincides with voltage drop."},{"role":"assistant","content":"{\"anomaly_type\":\"SPIKE\",\"severity\":\"high\",\"confidence\":0.95,\"explanation\":\"Current draw spiked 19% above normal. Coincides with voltage drop. Pattern indicates connector resistance increase.\",\"likely_causes\":[\"Connector corrosion\",\"Loose connection\",\"Cable degradation\"],\"recommended_action\":\"Immediate inspection of connector.\",\"escalation_required\":true,\"auto_resolve_possible\":false}"}]',
 '0a200008-0000-4000-8000-000000000008', 'auto_approved', true, 0.95, 'train', 'stuart.gano@databricks.com'),
('0a400015-0000-4000-8000-000000000015', '0a300003-0000-4000-8000-000000000003', 'ANOM-2024-003',
 '[{"role":"system","content":"You are an intelligent alerting system for nuclear facility radiation detectors."},{"role":"user","content":"ANOMALY DETECTED: Equipment PM-NPP-SURRY-001 at Surry. Metric: humidity_pct. Current: 72. Expected: 50. Deviation: +44.0%. History: [52, 55, 58, 62, 68, 72]. Related: temperature_c=20.0, voltage_v=4.88."},{"role":"assistant","content":"{\"anomaly_type\":\"HUMIDITY_ALERT\",\"severity\":\"medium\",\"confidence\":0.92,\"explanation\":\"Humidity has been steadily rising over past 6 hours and is now 44% above normal operating range. Accelerates corrosion.\",\"likely_causes\":[\"HVAC malfunction\",\"Weather-related humidity increase\",\"Door seal failure\"],\"recommended_action\":\"Check HVAC system. Consider temporary dehumidifier.\",\"escalation_required\":false,\"auto_resolve_possible\":false}"}]',
 '0a200009-0000-4000-8000-000000000009', 'auto_approved', true, 0.92, 'train', 'stuart.gano@databricks.com'),
('0a400016-0000-4000-8000-000000000016', '0a300003-0000-4000-8000-000000000003', 'ANOM-2024-004',
 '[{"role":"system","content":"You are an intelligent alerting system for nuclear facility radiation detectors."},{"role":"user","content":"ANOMALY DETECTED: Equipment DET-NPP-PALO-001 at Palo Verde. Metric: noise_level_mv. Current: 5.5. Expected: 3.0. Deviation: +83.3%."},{"role":"assistant","content":"{\"anomaly_type\":\"NOISE_INCREASE\",\"severity\":\"low\",\"confidence\":0.78,\"explanation\":\"Noise floor increased 83%. Often precedes more serious failures. May indicate EMI or internal component degradation.\",\"likely_causes\":[\"EMI interference\",\"Preamplifier degradation\",\"Grounding issue\"],\"recommended_action\":\"Monitor closely. Check for nearby EMI sources. Schedule diagnostic if trend continues.\",\"escalation_required\":false,\"auto_resolve_possible\":true}"}]',
 '0a200010-0000-4000-8000-000000000010', 'pending', false, 0.78, 'val', 'stuart.gano@databricks.com'),
('0a400017-0000-4000-8000-000000000017', '0a300003-0000-4000-8000-000000000003', 'ANOM-2024-005',
 '[{"role":"system","content":"You are an intelligent alerting system for nuclear facility radiation detectors."},{"role":"user","content":"ANOMALY DETECTED: Equipment DET-NPP-WATTS-003 at Watts Bar. Metric: voltage_v. Current: 4.91. Expected: 5.00. Deviation: -1.8%. Combined with humidity trend."},{"role":"assistant","content":"{\"anomaly_type\":\"CALIBRATION_DRIFT\",\"severity\":\"high\",\"confidence\":0.86,\"explanation\":\"High voltage drifted 1.8% below setpoint. Combined with humidity trend, suggests seal degradation affecting HV stability.\",\"likely_causes\":[\"Seal degradation\",\"Moisture ingress\",\"HV supply aging\"],\"recommended_action\":\"Recalibrate within 14 days. Inspect seal integrity.\",\"escalation_required\":true,\"auto_resolve_possible\":false}"}]',
 '0a200011-0000-4000-8000-000000000011', 'auto_approved', true, 0.86, 'train', 'stuart.gano@databricks.com'),
('0a400018-0000-4000-8000-000000000018', '0a300003-0000-4000-8000-000000000003', 'ANOM-2024-006',
 '[{"role":"system","content":"You are an intelligent alerting system for nuclear facility radiation detectors."},{"role":"user","content":"ANOMALY DETECTED: Equipment PM-NPP-SURRY-001 at Surry. Metric: count_rate_cps. Current: 815. Expected: 900. Deviation: -9.4%."},{"role":"assistant","content":"{\"anomaly_type\":\"PLATEAU_SHIFT\",\"severity\":\"medium\",\"confidence\":0.82,\"explanation\":\"Operating plateau shifted down 9.4%. Characteristic of detector aging combined with environmental stress.\",\"likely_causes\":[\"Detector aging\",\"Sustained environmental stress\",\"Gas depletion (if gas-filled)\"],\"recommended_action\":\"Full recalibration required. Assess remaining useful life.\",\"escalation_required\":false,\"auto_resolve_possible\":false}"}]',
 '0a200012-0000-4000-8000-000000000012', 'auto_approved', true, 0.82, 'test', 'stuart.gano@databricks.com'),

-- Calibration Insights QA Pairs
('0a400019-0000-4000-8000-000000000019', '0a300004-0000-4000-8000-000000000004', 'MC-COOK-001-Cs137',
 '[{"role":"system","content":"You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration."},{"role":"user","content":"Analyze Monte Carlo calibration for HPGe detector DET-NPP-COOK-001. Source: Cs-137 at 370000 Bq. Geometry: point at 100 cm, no shielding. Results: [125000 counts (0.28%), 124800 counts (0.28%), 125200 counts (0.28%)]. Previous calibration factor: 2.98."},{"role":"assistant","content":"{\"recommended_calibration_factor\":2.96,\"calibration_factor_uncertainty\":0.01,\"confidence_level\":\"95%\",\"simulation_quality_assessment\":\"excellent\",\"deviation_from_previous\":-0.67,\"deviation_significant\":false,\"physics_insights\":[\"Simulated efficiency of 33.8% is consistent with HPGe at 662 keV\",\"Count rate variation of 0.16% indicates excellent convergence\"],\"recommendations\":[\"Accept calibration factor of 2.96 ± 0.01\",\"Update detector efficiency tables\"],\"additional_simulations_needed\":false,\"explanation\":\"Excellent convergence with 0.67% decrease from previous value - within normal drift.\"}"}]',
 NULL, 'auto_approved', true, 0.95, 'train', 'stuart.gano@databricks.com'),
('0a400020-0000-4000-8000-000000000020', '0a300004-0000-4000-8000-000000000004', 'MC-PALO-001-Co60',
 '[{"role":"system","content":"You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration."},{"role":"user","content":"Analyze Monte Carlo calibration for NaI detector DET-NPP-PALO-001. Source: Co-60 at 185000 Bq. Geometry: cylindrical at 50 cm, 2mm Pb shielding. Results: [89500 counts (0.45%), 88900 counts (0.47%), 90100 counts (0.44%)]. Previous calibration factor: 2.08."},{"role":"assistant","content":"{\"recommended_calibration_factor\":2.07,\"calibration_factor_uncertainty\":0.02,\"confidence_level\":\"95%\",\"simulation_quality_assessment\":\"good\",\"deviation_from_previous\":-0.48,\"deviation_significant\":false,\"physics_insights\":[\"NaI efficiency at 1.17/1.33 MeV dual peaks consistent with expectations\",\"2mm Pb shielding attenuates primarily through Compton scattering at these energies\"],\"recommendations\":[\"Accept calibration factor\",\"Consider additional simulations with varied geometries\"],\"additional_simulations_needed\":false,\"explanation\":\"Good convergence. 0.48% decrease from previous is within normal range for Co-60 calibration.\"}"}]',
 NULL, 'auto_approved', true, 0.88, 'train', 'stuart.gano@databricks.com'),
('0a400021-0000-4000-8000-000000000021', '0a300004-0000-4000-8000-000000000004', 'MC-WATTS-003-Am241',
 '[{"role":"system","content":"You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration."},{"role":"user","content":"Analyze Monte Carlo calibration for GM tube DET-NPP-WATTS-003. Source: Am-241 at 400000 Bq. Geometry: point at 25 cm, no shielding. Results: [45200 counts (1.2%), 44800 counts (1.3%)]. Previous calibration factor: 8.85."},{"role":"assistant","content":"{\"recommended_calibration_factor\":8.89,\"calibration_factor_uncertainty\":0.12,\"confidence_level\":\"90%\",\"simulation_quality_assessment\":\"acceptable\",\"deviation_from_previous\":0.45,\"deviation_significant\":false,\"physics_insights\":[\"Am-241 59.5 keV photons have high attenuation - positioning accuracy critical\",\"Only 2 simulations - more runs recommended for higher confidence\"],\"recommendations\":[\"Run 3-5 additional simulations for better statistics\",\"Verify source positioning accuracy\"],\"additional_simulations_needed\":true,\"explanation\":\"Acceptable but limited. 2 simulations insufficient for high confidence. Recommend additional runs.\"}"}]',
 NULL, 'pending', false, 0.72, 'val', 'stuart.gano@databricks.com'),
('0a400022-0000-4000-8000-000000000022', '0a300004-0000-4000-8000-000000000004', 'MC-DIABLO-002-Cs137',
 '[{"role":"system","content":"You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration."},{"role":"user","content":"Analyze Monte Carlo calibration for Ion Chamber DET-NPP-DIABLO-002. Source: Cs-137 at 370000 Bq. Geometry: distributed at 75 cm, 5mm Pb shielding. Results: [68000 counts (0.8%), 72500 counts (0.75%), 69200 counts (0.82%)]. Previous calibration factor: 5.12."},{"role":"assistant","content":"{\"recommended_calibration_factor\":5.30,\"calibration_factor_uncertainty\":0.08,\"confidence_level\":\"90%\",\"simulation_quality_assessment\":\"marginal\",\"deviation_from_previous\":3.52,\"deviation_significant\":true,\"physics_insights\":[\"3.5% deviation exceeds normal drift threshold of 2%\",\"Run-to-run variation of 6.2% suggests inconsistent geometry modeling\"],\"recommendations\":[\"Investigate cause of 3.5% deviation before accepting\",\"Verify distributed source geometry parameters\",\"Check detector for degradation\"],\"additional_simulations_needed\":true,\"explanation\":\"CAUTION: 3.5% deviation from previous factor is concerning. Run-to-run variation too high. Do not accept without investigation.\"}"}]',
 NULL, 'rejected', false, 0.60, 'test', 'stuart.gano@databricks.com'),
('0a400023-0000-4000-8000-000000000023', '0a300004-0000-4000-8000-000000000004', 'MC-SURRY-001-Co60',
 '[{"role":"system","content":"You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration."},{"role":"user","content":"Analyze Monte Carlo calibration for Portal Monitor PM-NPP-SURRY-001. Source: Co-60 at 185000 Bq. Geometry: distributed at 200 cm, no shielding. Results: [32100 counts (0.6%), 32300 counts (0.58%), 31900 counts (0.62%), 32200 counts (0.59%)]. Previous calibration factor: 5.78."},{"role":"assistant","content":"{\"recommended_calibration_factor\":5.76,\"calibration_factor_uncertainty\":0.04,\"confidence_level\":\"95%\",\"simulation_quality_assessment\":\"good\",\"deviation_from_previous\":-0.35,\"deviation_significant\":false,\"physics_insights\":[\"Portal monitor efficiency at 200 cm consistent with inverse-square law\",\"4 simulations provide adequate statistics\"],\"recommendations\":[\"Accept calibration factor\",\"Continue annual calibration schedule\"],\"additional_simulations_needed\":false,\"explanation\":\"Good convergence. 0.35% decrease within normal drift for portal monitor.\"}"}]',
 NULL, 'auto_approved', true, 0.90, 'train', 'stuart.gano@databricks.com'),
('0a400024-0000-4000-8000-000000000024', '0a300004-0000-4000-8000-000000000004', 'MC-COOK-001-Am241',
 '[{"role":"system","content":"You are a radiation physics expert specializing in Monte Carlo simulations for detector calibration."},{"role":"user","content":"Analyze Monte Carlo calibration for HPGe detector DET-NPP-COOK-001. Source: Am-241 at 400000 Bq. Geometry: point at 50 cm, 1mm Pb shielding. Results: [85600 counts (0.35%), 85400 counts (0.36%), 85800 counts (0.34%), 85500 counts (0.35%)]. Previous calibration factor: 4.68."},{"role":"assistant","content":"{\"recommended_calibration_factor\":4.67,\"calibration_factor_uncertainty\":0.02,\"confidence_level\":\"95%\",\"simulation_quality_assessment\":\"excellent\",\"deviation_from_previous\":-0.21,\"deviation_significant\":false,\"physics_insights\":[\"Am-241 at 59.5 keV benefits from HPGe high-Z material for photoelectric absorption\",\"1mm Pb has significant effect at this energy - 68% attenuation expected\",\"Excellent run-to-run consistency validates geometry model\"],\"recommendations\":[\"Accept calibration factor of 4.67 ± 0.02\",\"Document shielded configuration for future reference\"],\"additional_simulations_needed\":false,\"explanation\":\"Excellent convergence for Am-241 shielded configuration. Factor consistent with previous.\"}"}]',
 NULL, 'auto_approved', true, 0.93, 'train', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 6. EXAMPLE STORE — Few-shot examples from examples/*.json
-- =============================================================================

-- Defect Detection Examples (8 from examples/defect_detection.json)
INSERT INTO example_store (id, input_text, output_text, domain, task_type, difficulty, capability_tags, is_verified, created_by) VALUES
('0a500001-0000-4000-8000-000000000001',
 'Front view of gamma detector DET-NPP-COOK-001 showing clean crystal housing with no visible damage. Temperature: 22.5°C, Humidity: 45%, Operating Hours: 8760.',
 '{"defect_class":"NONE","confidence":0.95,"severity":0,"action_required":"none","reasoning":"Crystal housing intact with no visible scratches, contamination, or structural damage."}',
 'defect_detection', 'classification', 'easy', ARRAY['no_defect','routine_inspection'], true, 'stuart.gano@databricks.com'),
('0a500002-0000-4000-8000-000000000002',
 'Side view of detector DET-NPP-COOK-002 showing 4cm surface scratch on housing exterior. Temperature: 23.1°C, Humidity: 44%, Operating Hours: 12450.',
 '{"defect_class":"MINOR_SCRATCH","confidence":0.87,"severity":1,"action_required":"monitor","reasoning":"Surface scratch on housing exterior does not penetrate to internal components."}',
 'defect_detection', 'classification', 'easy', ARRAY['minor_defect','cosmetic_damage'], true, 'stuart.gano@databricks.com'),
('0a500003-0000-4000-8000-000000000003',
 'Crystal chamber view of detector DET-NPP-PALO-001 showing 3mm crack extending into scintillation crystal. Temperature: 28.5°C, Humidity: 35%, Operating Hours: 26500. Count rate anomaly detected.',
 '{"defect_class":"CRYSTAL_CRACK","confidence":0.92,"severity":3,"action_required":"immediate_replacement","reasoning":"Critical defect: crack in scintillation crystal correlates with 15% efficiency drop."}',
 'defect_detection', 'classification', 'medium', ARRAY['critical_defect','crystal_damage','immediate_action'], true, 'stuart.gano@databricks.com'),
('0a500004-0000-4000-8000-000000000004',
 'Seal inspection of detector DET-NPP-WATTS-003 showing slight discoloration around hermetic seal area. Temperature: 21.0°C, Humidity: 52%, Operating Hours: 5200.',
 '{"defect_class":"SEAL_DEGRADATION","confidence":0.78,"severity":2,"action_required":"schedule_maintenance","reasoning":"Early signs of seal degradation. Discoloration may indicate moisture ingress pathway."}',
 'defect_detection', 'classification', 'hard', ARRAY['seal_inspection','early_warning','preventive_maintenance'], true, 'stuart.gano@databricks.com'),
('0a500005-0000-4000-8000-000000000005',
 'Connector view of detector DET-NPP-DIABLO-002 showing bent pin on main signal connector. Temperature: 24.0°C, Operating Hours: 18200. Signal quality: degraded, intermittent readings.',
 '{"defect_class":"CONNECTOR_DAMAGE","confidence":0.91,"severity":3,"action_required":"immediate_repair","reasoning":"Bent connector pin causing intermittent signal loss. Critical safety risk."}',
 'defect_detection', 'classification', 'medium', ARRAY['connector_damage','signal_issues','troubleshooting'], true, 'stuart.gano@databricks.com'),
('0a500006-0000-4000-8000-000000000006',
 'Housing exterior of detector DET-NPP-SURRY-001 showing rust spots and oxidation on metal frame. Temperature: 19.5°C, Humidity: 68%, Operating Hours: 32100. High humidity area.',
 '{"defect_class":"CORROSION","confidence":0.85,"severity":3,"action_required":"relocate_and_treat","reasoning":"Active corrosion due to high humidity environment (68%)."}',
 'defect_detection', 'classification', 'medium', ARRAY['corrosion','environmental','preventive_action'], true, 'stuart.gano@databricks.com'),
('0a500007-0000-4000-8000-000000000007',
 'Optical window view of detector DET-MED-CLINIC-005 showing slight hazing on detector window surface. Temperature: 22.0°C, Operating Hours: 4500. Medical imaging application.',
 '{"defect_class":"WINDOW_CLOUDING","confidence":0.72,"severity":2,"action_required":"clean_and_reassess","reasoning":"Possible window clouding. Could be surface contamination rather than permanent degradation."}',
 'defect_detection', 'classification', 'hard', ARRAY['window_inspection','ambiguous_case','cleaning_protocol'], true, 'stuart.gano@databricks.com'),
('0a500008-0000-4000-8000-000000000008',
 'Full detector assembly DET-NPP-BYRON-001 showing foreign particle lodged between housing and mounting bracket. Temperature: 25.0°C, Operating Hours: 15000. Vibration detected.',
 '{"defect_class":"CONTAMINATION","confidence":0.88,"severity":2,"action_required":"remove_debris","reasoning":"Foreign debris in mounting area likely source of vibration. Could lead to connector fatigue."}',
 'defect_detection', 'classification', 'medium', ARRAY['contamination','debris','vibration','mounting'], true, 'stuart.gano@databricks.com'),

-- Predictive Maintenance Examples (8 from examples/predictive_maintenance.json)
('0a500009-0000-4000-8000-000000000009',
 'Equipment DET-NPP-COOK-001 (gamma_detector). Operating hours: 8760. Temperature: 22.5°C (variance: 1.2). Humidity: 45%. Count rate stability: 0.98. HV stability: 0.99. Calibration drift: 0.5%. Last calibration: 2023-11-01.',
 '{"failure_probability_30d":0.02,"failure_probability_90d":0.05,"remaining_useful_life_days":450,"risk_level":"low","reasoning":"Excellent stability across all metrics. Low operating hours, minimal calibration drift."}',
 'predictive_maintenance', 'classification', 'easy', ARRAY['healthy_equipment','low_risk','routine_maintenance'], true, 'stuart.gano@databricks.com'),
('0a500010-0000-4000-8000-000000000010',
 'Equipment DET-NPP-PALO-003 (gamma_detector). Operating hours: 35000. Temperature: 29.5°C (variance: 4.8). Humidity: 55%. Count rate stability: 0.89. HV stability: 0.94. Calibration drift: 3.2%. Efficiency declining 2.1% over 30 days.',
 '{"failure_probability_30d":0.18,"failure_probability_90d":0.42,"remaining_useful_life_days":120,"risk_level":"high","reasoning":"Multiple warning indicators: high operating hours, declining efficiency, elevated calibration drift."}',
 'predictive_maintenance', 'classification', 'medium', ARRAY['high_risk','aging_equipment','multiple_indicators'], true, 'stuart.gano@databricks.com'),
('0a500011-0000-4000-8000-000000000011',
 'Equipment DET-NPP-WATTS-007 (neutron_detector). Operating hours: 18500. HV stability: 0.88. Pulse shape anomaly count: 15. Calibration drift: 1.8%.',
 '{"failure_probability_30d":0.12,"failure_probability_90d":0.28,"remaining_useful_life_days":180,"risk_level":"medium","reasoning":"HV supply showing early instability combined with pulse shape anomalies suggests developing power supply issue."}',
 'predictive_maintenance', 'classification', 'medium', ARRAY['hv_supply','pulse_anomaly','subsystem_failure'], true, 'stuart.gano@databricks.com'),
('0a500012-0000-4000-8000-000000000012',
 'Equipment DET-MED-HOSPITAL-012 (scintillation_detector). Operating hours: 5200. Temperature: 21.0°C (variance: 0.8). Energy resolution: 7.8 keV (stable). Climate-controlled hospital setting.',
 '{"failure_probability_30d":0.01,"failure_probability_90d":0.03,"remaining_useful_life_days":800,"risk_level":"low","reasoning":"Medical imaging detector in excellent condition. Controlled environment, excellent energy resolution."}',
 'predictive_maintenance', 'classification', 'easy', ARRAY['medical_application','healthy','quality_critical'], true, 'stuart.gano@databricks.com'),
('0a500013-0000-4000-8000-000000000013',
 'Equipment DET-NPP-DIABLO-005 (area_monitor). Operating hours: 52000. Calibration drift: 2.5%. Background rate increase: 8%. 18 maintenance events. Planned decommission: 2025-06-01.',
 '{"failure_probability_30d":0.08,"failure_probability_90d":0.22,"remaining_useful_life_days":250,"risk_level":"medium","reasoning":"Aging area monitor approaching planned decommission. Focus on maintaining acceptable performance through remaining service life."}',
 'predictive_maintenance', 'classification', 'hard', ARRAY['end_of_life','decommission_planning','cost_benefit'], true, 'stuart.gano@databricks.com'),
('0a500014-0000-4000-8000-000000000014',
 'Equipment DET-NPP-BYRON-009 (gamma_detector). Operating hours: 12000. Temperature: 31.5°C (variance: 6.2). Humidity: 72%. Located in turbine building auxiliary area.',
 '{"failure_probability_30d":0.15,"failure_probability_90d":0.35,"remaining_useful_life_days":200,"risk_level":"high","reasoning":"Environmental stress is primary concern: high temperature, high variance, excessive humidity accelerating degradation."}',
 'predictive_maintenance', 'classification', 'medium', ARRAY['environmental_stress','humidity','temperature'], true, 'stuart.gano@databricks.com'),
('0a500015-0000-4000-8000-000000000015',
 'Equipment DET-NPP-SURRY-002 (gamma_detector). Operating hours: 22000. Count rate stability: 0.85. Calibration drift: 4.5%. Last 24h readings: [142, 138, 145, 89, 141, 140, 143, 85, 139, 142]. Anomaly: intermittent dropouts.',
 '{"failure_probability_30d":0.25,"failure_probability_90d":0.55,"remaining_useful_life_days":90,"risk_level":"critical","reasoning":"CRITICAL: Intermittent dropout pattern visible. Signal chain degradation indicates imminent failure."}',
 'predictive_maintenance', 'classification', 'hard', ARRAY['critical_failure','intermittent','signal_chain'], true, 'stuart.gano@databricks.com'),
('0a500016-0000-4000-8000-000000000016',
 'Equipment DET-NPP-COOK-015 (neutron_detector). Operating hours: 28000. He-3 pressure: 3.8 psi (spec: 4.0). Pressure history: [4.0, 3.95, 3.9, 3.85, 3.8].',
 '{"failure_probability_30d":0.10,"failure_probability_90d":0.30,"remaining_useful_life_days":365,"risk_level":"medium","reasoning":"He-3 pressure declining. Slow leak in neutron detector tube. Early intervention preferred over tube replacement."}',
 'predictive_maintenance', 'classification', 'hard', ARRAY['neutron_detector','he3','slow_leak','specialized'], true, 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 7. FEEDBACK ITEMS — Mix of positive and negative feedback
-- =============================================================================

INSERT INTO ml_feedback_items (id, model_name, endpoint_name, query, response, rating, feedback_type, category, comment, is_converted, created_by) VALUES
('0a600001-0000-4000-8000-000000000001', 'mirion-defect-detection-v1', 'mirion-defect-ep',
 'Analyze inspection image of HPGe detector showing hairline crack near crystal mount',
 '{"defect_class":"CRYSTAL_CRACK","severity":3,"confidence":0.88}',
 5, 'positive', NULL,
 'Correctly identified subtle hairline crack that was difficult to spot. Good severity assessment.',
 false, 'inspector.jones@mirion.com'),
('0a600002-0000-4000-8000-000000000002', 'mirion-defect-detection-v1', 'mirion-defect-ep',
 'Analyze inspection image of GM tube with minor surface scuff',
 '{"defect_class":"SEAL_DEGRADATION","severity":2,"confidence":0.65}',
 2, 'negative', 'wrong_format',
 'Misclassified surface scuff as seal degradation. Should be MINOR_SCRATCH with severity 1.',
 false, 'inspector.smith@mirion.com'),
('0a600003-0000-4000-8000-000000000003', 'mirion-predictive-maintenance-v1', 'mirion-pm-ep',
 'Predict maintenance for HPGe detector with 45000 operating hours and declining count rate',
 '{"health_score":0.55,"failure_probability_30d":0.22,"risk_level":"high"}',
 4, 'positive', NULL,
 'Good prediction but could provide more specific recommended actions for HPGe cooling system checks.',
 false, 'maint.engineer@mirion.com'),
('0a600004-0000-4000-8000-000000000004', 'mirion-anomaly-detection-v1', 'mirion-anomaly-ep',
 'Explain anomaly: count rate dropped 15% suddenly during routine operation',
 '{"anomaly_type":"SENSOR_DRIFT","severity":"medium"}',
 2, 'negative', 'incomplete',
 'Should be classified as DROPOUT not SENSOR_DRIFT - 15% sudden drop is not gradual drift. Missing escalation recommendation.',
 false, 'operator.williams@mirion.com'),
('0a600005-0000-4000-8000-000000000005', 'mirion-calibration-insights-v1', 'mirion-cal-ep',
 'Analyze MC results for Cs-137 calibration with 8 simulations showing 0.3% uncertainty',
 '{"simulation_quality_assessment":"excellent","recommended_calibration_factor":3.15}',
 5, 'positive', NULL,
 'Excellent physics reasoning. Correctly identified all systematic uncertainty sources.',
 false, 'physicist.chen@mirion.com'),
('0a600006-0000-4000-8000-000000000006', 'mirion-predictive-maintenance-v1', 'mirion-pm-ep',
 'Analyze equipment with conflicting signals: improving temperature but degrading HV stability',
 '{"health_score":0.75,"risk_level":"medium","failure_probability_30d":0.10}',
 3, 'neutral', NULL,
 'Reasonable overall assessment but failed to flag the HV stability trend as the dominant risk factor. Temperature improvement is environmental, not equipment health.',
 false, 'maint.engineer@mirion.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 8. GAP RECORDS — Identified gaps in model coverage
-- =============================================================================

INSERT INTO ml_identified_gaps (id, gap_type, severity, description, model_name, template_id, affected_queries_count, error_rate, suggested_action, estimated_records_needed, status, priority) VALUES
('0a700001-0000-4000-8000-000000000001', 'coverage', 'high',
 'No training examples for simultaneous multi-defect scenarios (e.g., corrosion + seal degradation together)',
 'mirion-defect-detection-v1', '0a100001-0000-4000-8000-000000000001',
 12, 0.35, 'Create multi-defect training examples combining common co-occurring defect pairs', 20, 'identified', 1),
('0a700002-0000-4000-8000-000000000002', 'quality', 'medium',
 'Low confidence on window clouding vs contamination differentiation (72% avg confidence)',
 'mirion-defect-detection-v1', '0a100001-0000-4000-8000-000000000001',
 8, 0.28, 'Add more edge-case examples showing visual differences between clouding and contamination', 15, 'in_progress', 2),
('0a700003-0000-4000-8000-000000000003', 'coverage', 'critical',
 'No training data for neutron detector He-3 pressure degradation patterns',
 'mirion-predictive-maintenance-v1', '0a100002-0000-4000-8000-000000000002',
 5, 0.60, 'Collect He-3 pressure trend data from field deployments and create specialized training examples', 10, 'identified', 0),
('0a700004-0000-4000-8000-000000000004', 'distribution', 'medium',
 'Anomaly detection training data skewed toward medium severity - insufficient critical/low examples',
 'mirion-anomaly-detection-v1', '0a100003-0000-4000-8000-000000000003',
 15, 0.18, 'Balance severity distribution in training set: add more critical and low severity examples', 12, 'identified', 2)
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 9. QUALITY CHECKS — Sample check definitions (requires quality tables)
-- =============================================================================

INSERT INTO training_data_quality_checks (id, collection_id, check_name, check_function, column_name, criticality, parameters, created_by) VALUES
('0a800001-0000-4000-8000-000000000001', '0a300001-0000-4000-8000-000000000001', 'Message completeness', 'message_completeness', 'messages', 'blocking', '{"min_roles":["system","user","assistant"]}', 'stuart.gano@databricks.com'),
('0a800002-0000-4000-8000-000000000002', '0a300001-0000-4000-8000-000000000001', 'Response JSON validity', 'json_valid_response', 'messages', 'warning', NULL, 'stuart.gano@databricks.com'),
('0a800003-0000-4000-8000-000000000003', '0a300001-0000-4000-8000-000000000001', 'Minimum response length', 'min_response_length', 'messages', 'warning', '{"min_chars":50}', 'stuart.gano@databricks.com'),
('0a800004-0000-4000-8000-000000000004', '0a300001-0000-4000-8000-000000000001', 'Quality score threshold', 'quality_score_threshold', 'quality_score', 'info', '{"min_score":0.7}', 'stuart.gano@databricks.com'),
('0a800005-0000-4000-8000-000000000005', '0a300002-0000-4000-8000-000000000002', 'Message completeness', 'message_completeness', 'messages', 'blocking', '{"min_roles":["system","user","assistant"]}', 'stuart.gano@databricks.com'),
('0a800006-0000-4000-8000-000000000006', '0a300002-0000-4000-8000-000000000002', 'Response JSON validity', 'json_valid_response', 'messages', 'warning', NULL, 'stuart.gano@databricks.com'),
('0a800007-0000-4000-8000-000000000007', '0a300003-0000-4000-8000-000000000003', 'Message completeness', 'message_completeness', 'messages', 'blocking', '{"min_roles":["system","user","assistant"]}', 'stuart.gano@databricks.com'),
('0a800008-0000-4000-8000-000000000008', '0a300004-0000-4000-8000-000000000004', 'Message completeness', 'message_completeness', 'messages', 'blocking', '{"min_roles":["system","user","assistant"]}', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 10. QUALITY RUNS — Sample run for defect detection collection
-- =============================================================================

INSERT INTO training_data_quality_runs (id, collection_id, status, source, pass_rate, quality_score, check_results, started_at, completed_at, created_by) VALUES
('0a900001-0000-4000-8000-000000000001', '0a300001-0000-4000-8000-000000000001', 'passed', 'mock', 1.0, 1.0,
 '[{"check_id":"0a800001-0000-4000-8000-000000000001","check_name":"Message completeness","passed":true,"criticality":"blocking","message":"6/6 pairs have all required roles","details":{"incomplete_count":0,"total":6}},{"check_id":"0a800002-0000-4000-8000-000000000002","check_name":"Response JSON validity","passed":true,"criticality":"warning","message":"All responses have valid JSON","details":{"invalid_count":0,"total":6}},{"check_id":"0a800003-0000-4000-8000-000000000003","check_name":"Minimum response length","passed":true,"criticality":"warning","message":"All responses >= 50 chars","details":{"short_count":0,"min_chars":50,"total":6}},{"check_id":"0a800004-0000-4000-8000-000000000004","check_name":"Quality score threshold","passed":true,"criticality":"info","message":"Avg quality score 0.88 >= 0.7","details":{"avg_score":0.88,"min_score":0.7,"scored_pairs":6}}]',
 '2026-02-17T10:00:00+00:00', '2026-02-17T10:00:01+00:00', 'stuart.gano@databricks.com')
ON CONFLICT (id) DO NOTHING;

COMMIT;
