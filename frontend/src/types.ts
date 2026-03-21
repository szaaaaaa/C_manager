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

export interface ExplainResponse {
  path: string;
  safety: 'red' | 'yellow' | 'green';
  size_human: string;
  explanation: string;
  backend_used: string;
}

export interface ScanConfig {
  root: string;
  min_size_mb: number;
  max_depth: number;
}

export interface AppSettings {
  apiKey: string;
  useEnvKey: boolean;
  baseUrl: string;
  model: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  context_length: number;
}
