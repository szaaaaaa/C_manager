import { invoke, Channel } from '@tauri-apps/api/core';
import type { DriveInfo, ExplainResponse, LocalModelStatus, ModelInfo } from './types';

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
  | { type: 'progress'; entries_scanned: number; files_matched: number }
  | { type: 'file'; path: string; name: string; size: number; size_human: string; is_dir: boolean; children_count: number; safety: string };

export async function scanDrive(
  root: string,
  minSizeMb: number,
  maxDepth: number,
  onMessage: (msg: ScanMessage) => void,
): Promise<void> {
  const channel = new Channel<ScanMessage>();
  channel.onmessage = onMessage;
  return invoke<void>('scan_drive', {
    root,
    minSizeMb,
    maxDepth,
    onEvent: channel,
  });
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
