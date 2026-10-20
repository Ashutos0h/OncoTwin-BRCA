export type JsonScalar = string | number | boolean | null;

export interface ClinicalEvent {
  schema_version: '0.1.0';
  twin_id: string;
  event_id: string;
  event_type: 'PATHOLOGY_RESULT' | 'DIAGNOSIS' | 'BIOMARKER_RESULT' | 'TREATMENT' | 'FOLLOW_UP';
  effective_time: string;
  received_time: string;
  source: string;
  quality_status: 'valid' | 'warning' | 'invalid';
  provenance: {
    source_system: string;
    source_record_id: string;
    data_version: string;
  };
  payload: Record<string, JsonScalar>;
}

export interface TwinSummary {
  twin_id: string;
  state_version: number;
}

export interface TwinState {
  schema_version: '0.1.0';
  twin_id: string;
  state_version: number;
  as_of: string;
  event_ids: string[];
  data_version: string;
  values: Record<string, JsonScalar>;
  missing_fields: string[];
  quality_warnings: string[];
}

export interface FeatureSnapshot {
  schema_version: '0.1.0';
  twin_id: string;
  snapshot_id: string;
  state_version: number;
  created_at: string;
  data_version: string;
  feature_set_version: string;
  features: Record<string, JsonScalar>;
  missing_fields: string[];
}

export interface Prediction {
  schema_version: '0.1.0';
  twin_id: string;
  prediction_id: string;
  snapshot_id: string;
  state_version: number;
  data_version: string;
  audit_id: string;
  created_at: string;
  model_name: string;
  model_version: string;
  is_mock: boolean;
  risk_probability: number;
  horizon_months: number;
  confidence: 'not_assessed' | 'low' | 'moderate' | 'high';
  ood_flag: boolean | null;
  shap_values: Array<{ feature: string; value: number }>;
  warnings: string[];
}

export interface AuditRecord {
  schema_version: '0.1.0';
  twin_id: string;
  audit_id: string;
  recorded_at: string;
  action: 'EVENT_ACCEPTED' | 'STATE_REBUILT' | 'PREDICTION_CREATED';
  actor: string;
  event_ids: string[];
  state_version: number;
  snapshot_id: string;
  prediction_id: string;
  model_version: string;
  data_version: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ModelInfo {
  status: string;
  inference_mode: 'mock' | 'trained' | string;
  model_name: string;
  model_version: string;
  model_path?: string | null;
  features_version?: string;
}


