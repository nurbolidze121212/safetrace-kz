export type Evidence = {
  id: string; quote: string; source_id: string; method: string; at: string;
  url?: string; material_id?: string; confidence?: number; polygon?: number[][];
  note?: string; case_id?: string;
}
export type GraphNode = { id: string; type: string; label: string; evidence_ids: string[]; case_id?: string; material_id?: string; stopped?: boolean }
export type Edge = { id: string; source: string; target: string; type: string; label: string; evidence_ids: string[]; method: string; status: string; at: string }
export type GraphData = { nodes: GraphNode[]; edges: Edge[]; evidence: Evidence[]; limitation?: string }
export type Score = { value: number; level: string; meaning: string; contributions: { key: string; title: string; weight: number; evidence_ids: string[] }[] }
export type Summary = { id: string; title: string; mode: string; status: string; created_at: string; score?: Score; progress: number; stage: string; sufficient_data?: boolean; material_count: number; decision?: string }
export type OCRLine = { text: string; confidence: number; uncertain?: boolean; warnings?: string[]; evidence_id: string; polygon: number[][] }
export type QRCode = { text: string; valid_url: boolean; reason?: string; truncated: boolean; polygon: number[][]; evidence_id: string }
export type Material = { id: string; text: string; url: string; source: string; image_id?: string; published_at?: string; ocr?: { text: string; width: number; height: number; model: string; lines: OCRLine[]; raw_lines?: { text: string; confidence: number; polygon: number[][] }[]; rotation_ccw?: number }; qr?: { codes: QRCode[]; width: number; height: number; decoder: string; limitations: string } }
export type PageContext = { context: string; language: string; contradictions: string[] }
export type Observation = { id: string; url: string; at: string; status_code: number | null; text: string; stop?: string; location?: string; evidence_id: string; method: string; depth?: number; links?: { url: string; quote: string }[]; reused_from?: string; context?: PageContext }
export type Relation = { from: string | null; to: string; type: string; quote: string; observation_id: string; at: string; method: string; evidence_id: string }
export type Trace = { observations: Observation[]; relations?: Relation[]; requests?: number }
export type AnalysisSnapshot = { at?: string; analysis_id?: string; trace?: Trace; score?: Score; versions?: Record<string, string>; evidence?: Evidence[]; materials?: Material[] }
export type Case = Summary & {
  materials: Material[]; graph: GraphData; limitations: string[];
  context?: { language: string; context: string; contradictions: string[] }; provider?: string;
  claims?: { quote: string; source_id: string; start: number; end: number; evidence_id: string }[];
  trace: Trace; decisions: { id: number; at: string; decision: string; comment: string }[];
  elapsed_ms?: number; stages: Record<string, string>; versions?: Record<string, string>;
  analysis_id?: string; analyzed_at?: string; history?: AnalysisSnapshot[];
}
export type Health = { provider_available: boolean; ocr_installed: boolean; offline: boolean; allowed_hosts: string[]; local_mode: string }
export type Demo = { id: string; title: string; subtitle: string }
export type Metrics = { n: number; tp: number; fp: number; tn: number; fn: number; precision: number | null; recall: number; f1: number; fpr: number; coverage: number; insufficient: number; precision_ci: number[]; fpr_ci: number[]; p50_ms: number; p95_ms: number }
export type Evaluation = { available: boolean; message?: string; dataset_version?: string; evaluation_id?: string; evaluation_label?: string; versions?: Record<string, string>; available_versions?: { id: string; label: string; test_count: number; rules?: string; full?: Metrics }[]; limitations?: string[]; variants?: Record<string, Metrics>; slices?: Record<string, Metrics>; errors?: { id: string; truth: number; predicted: number; title: string }[]; image_count?: number; test_count?: number; frozen_at?: string }
export type CreateInput = { title: string; mode: string; materials: { text: string; url: string; source: string; image_id: string | null }[] }
