export interface ScanItem {
  path: string;
  name: string;
  size: number;
  size_human: string;
  is_dir: boolean;
  children_count: number;
  safety: 'red' | 'yellow' | 'green';
}

export interface DriveInfo {
  drive: string;
  total: number;
  used: number;
  free: number;
  error?: string;
}

export interface ScanProgress {
  running: boolean;
  progress: number;
  current_path: string;
  result_count: number;
  error: string | null;
}

export interface ExplainResponse {
  path: string;
  safety: 'red' | 'yellow' | 'green';
  size_human: string;
  explanation: string;
  backend_used: 'local' | 'api';
}

export interface ScanConfig {
  root: string;
  min_size_mb: number;
  max_depth: number;
}

export type AiBackend = 'local' | 'api' | 'auto';

export interface AppSettings {
  aiBackend: AiBackend;
  apiKey: string;
  useEnvKey: boolean;
  baseUrl: string;
  model: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  context_length: number;
  pricing: Record<string, string>;
}
