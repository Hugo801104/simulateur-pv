/** Types des échanges entre l'interface et le moteur Python (voir engine/pvsim/api.py). */

export interface FieldError {
  field: string;
  message: string;
}

export type EngineResult<T> = ({ ok: true } & T) | { ok: false; errors: FieldError[] };

export type ParamGroups = Record<string, Record<string, string | number | null | number[]>>;

export interface WeatherSummary {
  source: string;
  source_label: string;
  latitude: number;
  longitude: number;
  elevation: number | null;
  start: string;
  end: string;
  hours: number;
  ghi_kwh_m2: number;
  temp_mean_c: number;
  notes: string[];
}

export interface LoadSummary {
  start: string;
  end: string;
  hours: number;
  total_kwh: number;
  warnings: string[];
}

export interface Totals {
  pv_kwh: number;
  load_kwh: number;
  direct_kwh: number;
  battery_charge_kwh: number;
  battery_discharge_kwh: number;
  export_kwh: number;
  import_kwh: number;
  self_supplied_kwh: number;
  self_consumption_rate: number;
  self_sufficiency_rate: number;
}

export interface EconomicsResult {
  capex_eur: number;
  npv_eur: number;
  irr: number | null;
  payback_years: number | null;
  discounted_payback_years: number | null;
  lcoe_eur_per_kwh: number | null;
  year1_savings_eur: number;
  year1_bill_without_pv_eur: number;
  year1_bill_with_pv_eur: number;
  yearly: {
    year: number[];
    production_kwh: number[];
    savings_eur: number[];
    sales_eur: number[];
    opex_eur: number[];
    replacements_eur: number[];
    cashflow_eur: number[];
    cumulative_eur: number[];
    cumulative_discounted_eur: number[];
  };
}

export interface SimulationResult {
  warnings: string[];
  notes: string[];
  weather: WeatherSummary;
  specific_yield_kwh_per_kwc: number;
  poa_kwh_m2: number;
  totals: Totals;
  economics: EconomicsResult;
  monthly: Record<
    'month' | 'pv_kwh' | 'load_kwh' | 'direct_kwh' | 'battery_charge_kwh' | 'battery_discharge_kwh' | 'export_kwh' | 'import_kwh',
    number[]
  >;
  daily_profile: Record<'hour' | 'pv_kwh' | 'load_kwh' | 'import_kwh' | 'export_kwh', number[]>;
}

export interface OptimisationRow {
  pv_kwc: number;
  battery_kwh: number;
  battery_kw: number;
  pv_kwh: number;
  self_consumption_rate: number;
  self_sufficiency_rate: number;
  capex_eur: number;
  npv_eur: number;
  irr: number | null;
  payback_years: number | null;
  lcoe_eur_per_kwh: number | null;
}

export interface OptimisationResult {
  warnings: string[];
  notes: string[];
  optimisation: { objective: 'npv' | 'irr'; rows: OptimisationRow[]; best: OptimisationRow | null };
}

export interface EngineInfo {
  engine_version: string;
  pvlib: string;
  numpy: string;
  pandas: string;
  scipy: string;
}

export interface AdviceRow {
  key?: string;
  label?: string;
  panels: number;
  pv_kwc: number;
  battery_kwh: number;
  battery_kw: number;
  totals: Totals;
  capex_eur: number;
  npv_eur: number;
  irr: number | null;
  payback_years: number | null;
  lcoe_eur_per_kwh: number | null;
  year1_savings_eur: number;
  year1_bill_without_pv_eur: number;
  year1_bill_with_pv_eur: number;
}

export interface AdviceItem {
  category: string;
  title: string;
  text: string;
  level: 'conseil' | 'attention' | 'info';
  sources: string[];
}

export interface AdviceResult {
  recommendation: AdviceRow & {
    module: { label: string; technology: string; power_wc: number; width_m: number; length_m: number; efficiency_pct: number; area_m2: number };
    tilt_deg: number;
    azimuths_deg: number[];
    occupied_area_m2: number;
    cumulative_eur: number[];
    plateau: { min_kwc: number; max_kwc: number };
    break_even_capex_eur: number | null;
    profitable: boolean;
  };
  roof: { max_panels: number; max_kwc: number; fit_panels: number; occupation: number; flat: boolean };
  production: { specific_yield_kwh_per_kwc: number; ideal_yield_kwh_per_kwc: number; orientation_ratio: number };
  consumption: { annual_kwh: number; estimated: boolean; basis: string };
  options: AdviceRow[];
  grid: { panels: number; pv_kwc: number; battery_kwh: number; npv_eur: number; capex_eur: number }[];
  monthly: SimulationResult['monthly'];
  advice: AdviceItem[];
  steps: { title: string; text: string; sources: string[] }[];
  notes: string[];
  assumptions: string[];
  sources: Record<string, { title: string; url: string }>;
  verified_on: string;
}

/** Méthodes exposées par le worker. */
export interface EngineApi {
  info(): EngineResult<EngineInfo>;
  set_weather(source: string, raw: string): EngineResult<{ weather: WeatherSummary }>;
  set_load_csv(text: string, timezone: string, unit: string): EngineResult<{ load: LoadSummary }>;
  clear_load_csv(): EngineResult<object>;
  simulate(paramsJson: string): EngineResult<SimulationResult>;
  optimise(paramsJson: string): EngineResult<OptimisationResult>;
  hourly_csv(): EngineResult<{ csv: string }>;
  advise(houseJson: string): EngineResult<{ advice: AdviceResult; weather: WeatherSummary }>;
}

export type EngineMethod = keyof EngineApi;

export type WorkerRequest = { id: number; method: EngineMethod; args: string[] };

export type WorkerMessage =
  | { type: 'progress'; step: string; detail: string }
  | { type: 'ready'; info: EngineInfo; totalBytes: number }
  | { type: 'boot-error'; message: string }
  | { type: 'result'; id: number; result: string }
  | { type: 'error'; id: number; message: string };
