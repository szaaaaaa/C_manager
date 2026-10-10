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

export interface ScanIssue {
  path: string;
  stage: string;
  error: string;
}

export interface ScanSummary {
  status: 'completed' | 'partial' | 'cancelled' | 'failed';
  engine: string;
  entries_scanned: number;
  files_matched: number;
  issues: ScanIssue[];
  excluded_links: string[];
  elapsed_ms: number;
}

export interface ScanProgress extends Omit<ScanSummary, 'status'> {
  status: ScanSummary['status'] | 'running';
  error: string | null;
}

export interface ScanConfig {
  root: string;
  min_size_mb: number;
}

export type ModelSource = 'local' | 'api';

export interface AppSettings {
  apiKey: string;
  useEnvKey: boolean;
  baseUrl: string;
  model: string;
  modelSource: ModelSource;
  tavilyKey: string;
}

export interface LocalModelStatus {
  loaded: boolean;
  model_name: string;
  error: string | null;
}

export type FileCategory = '全部' | '文档' | '图片' | '压缩包' | '视频' | '音频' | '其他';

export interface ModelInfo {
  id: string;
  name: string;
  context_length: number;
}
