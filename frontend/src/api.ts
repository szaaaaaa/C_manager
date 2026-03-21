import type { DriveInfo, ExplainResponse, ScanConfig, ScanItem, ScanProgress } from './types';

const BASE = 'http://localhost:8765';

export async function fetchDriveInfo(drive = 'C:\\'): Promise<DriveInfo> {
  const res = await fetch(`${BASE}/api/drive-info?drive=${encodeURIComponent(drive)}`);
  if (!res.ok) throw new Error(`drive-info ${res.status}`);
  return res.json();
}

export async function startScan(config: ScanConfig): Promise<void> {
  const res = await fetch(`${BASE}/api/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `scan ${res.status}`);
  }
}

export async function fetchScanResults(): Promise<{ running: boolean; results: ScanItem[]; error: string | null }> {
  const res = await fetch(`${BASE}/api/scan/results`);
  if (!res.ok) throw new Error(`results ${res.status}`);
  return res.json();
}

export function subscribeScanProgress(
  onData: (p: ScanProgress) => void,
  onDone: () => void,
  onError: (e: Error) => void
): () => void {
  const es = new EventSource(`${BASE}/api/scan/progress`);
  es.onmessage = (e) => {
    try {
      const data: ScanProgress = JSON.parse(e.data);
      onData(data);
      if (!data.running) {
        es.close();
        onDone();
      }
    } catch {
      // ignore parse errors
    }
  };
  es.onerror = () => {
    es.close();
    onError(new Error('SSE connection failed'));
  };
  return () => es.close();
}

export async function explainItem(
  path: string,
  sizeBytes: number,
  isDir: boolean,
  apiKey: string,
  baseUrl: string,
  model: string
): Promise<ExplainResponse> {
  const res = await fetch(`${BASE}/api/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path,
      size_bytes: sizeBytes,
      is_dir: isDir,
      api_key: apiKey,
      base_url: baseUrl,
      model,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `explain ${res.status}`);
  }
  return res.json();
}
