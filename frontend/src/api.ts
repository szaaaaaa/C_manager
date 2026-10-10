import { invoke, Channel } from '@tauri-apps/api/core';
import type { DriveInfo, ExplainResponse, LocalModelStatus, ModelInfo, ScanConfig, ScanItem, ScanSummary } from './types';

export async function checkAdmin(): Promise<boolean> {
  return invoke<boolean>('check_admin');
}

export async function relaunchAsAdmin(): Promise<void> {
  return invoke('relaunch_as_admin');
}

export async function fetchDriveInfo(drive = 'C:\\'): Promise<DriveInfo> {
  return invoke<DriveInfo>('get_drive_info', { drive });
}

export type ScanMessage =
  | { type: 'verification'; verification: NonNullable<ScanSummary['verification']> }
  | { type: 'progress'; entries_scanned: number; files_matched: number }
  | { type: 'files'; sequence: number; files: ScanItem[]; checksum: string };

async function verifyBatch(position: number, files: ScanItem[], checksum: string): Promise<boolean> {
  if (!files.every(file => Number.isSafeInteger(file.size) && file.size >= 0)) return false;
  const bytes = new TextEncoder().encode(JSON.stringify([
    position, files.map(file => [file.path, String(file.size)]),
  ]));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  return hex === checksum;
}

interface ScanCompletion {
  scan_id: number;
  summary: ScanSummary;
  batches_sent: number;
  transport_error: string | null;
}

export async function scanDrive(
  root: string,
  minSizeMb: number,
  onMessage: (msg: ScanMessage) => void,
  engine: ScanConfig['engine'] = 'mft_dual',
): Promise<ScanCompletion & { stream_verified: boolean }> {
  const channel = new Channel<ScanMessage>();
  let batches = 0;
  let files = 0;
  let valid = true;
  let accepting = true;
  let pending = Promise.resolve();
  channel.onmessage = (message) => {
    if (!accepting) return;
    if (message.type === 'files') {
      if (message.sequence !== batches) {
        valid = false;
        return;
      }
      batches += 1;
      pending = pending.then(async () => {
        if (!await verifyBatch(message.sequence, message.files, message.checksum)) {
          valid = false;
          return;
        }
        files += message.files.length;
        onMessage(message);
      }).catch(() => { valid = false; });
      return;
    }
    onMessage(message);
  };
  try {
    const completion = await invoke<ScanCompletion>('scan_drive', { root, minSizeMb, engine, onEvent: channel });
    accepting = false;
    await pending;
    return { ...completion, stream_verified: valid && !completion.transport_error
      && batches === completion.batches_sent && files === completion.summary.files_matched };
  } finally {
    // Any late channel messages are superseded by the retained backend result pages.
    accepting = false;
    await pending;
  }
}

export async function getScanResults(scanId: number, offset: number): Promise<ScanItem[]> {
  const page = await invoke<{ files: ScanItem[]; checksum: string }>(
    'get_scan_results', { scanId, offset, limit: 1000 });
  if (!await verifyBatch(offset, page.files, page.checksum)) {
    throw new Error('扫描结果核对失败：路径或大小不一致');
  }
  return page.files;
}

export async function explainItem(
  path: string,
  sizeBytes: number,
  isDir: boolean,
  apiKey: string,
  baseUrl: string,
  model: string,
  useLocal: boolean,
  tavilyKey: string = '',
): Promise<ExplainResponse> {
  return invoke<ExplainResponse>('explain_item', {
    path,
    sizeBytes,
    isDir,
    apiKey,
    baseUrl,
    model,
    useLocal,
    tavilyKey,
  });
}

export async function fetchModels(
  apiKey: string,
  baseUrl: string = 'https://openrouter.ai/api/v1'
): Promise<ModelInfo[]> {
  return invoke<ModelInfo[]>('fetch_models', {
    apiKey,
    baseUrl,
  });
}

export async function chatAboutFile(
  path: string,
  sizeBytes: number,
  isDir: boolean,
  history: { role: string; content: string }[],
  userMessage: string,
  apiKey: string,
  baseUrl: string,
  model: string,
  useLocal: boolean,
  tavilyKey: string = '',
): Promise<string> {
  return invoke<string>('chat_about_file', {
    path, sizeBytes, isDir, history, userMessage, apiKey, baseUrl, model, useLocal, tavilyKey,
  });
}

export async function cancelScan(): Promise<void> {
  return invoke('cancel_scan');
}

export async function fetchEnvKey(): Promise<{ has_env_key: boolean; source: string | null }> {
  return invoke('get_env_key');
}

export async function initLocalModel(): Promise<LocalModelStatus> {
  return invoke<LocalModelStatus>('init_local_model');
}

export async function openInExplorer(path: string): Promise<void> {
  return invoke('open_in_explorer', { path });
}

export interface DeleteResult {
  succeeded: string[];
  failed: { path: string; error: string }[];
}

export async function deleteToRecycleBin(paths: string[]): Promise<DeleteResult> {
  return invoke<DeleteResult>('delete_to_recycle_bin', { paths });
}

export async function getLocalModelStatus(): Promise<LocalModelStatus> {
  return invoke<LocalModelStatus>('get_local_model_status');
}
