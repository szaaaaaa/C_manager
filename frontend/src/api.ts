import { invoke } from '@tauri-apps/api/core';
import type { DriveInfo, ExplainResponse, ModelInfo, ScanItem } from './types';

export async function fetchDriveInfo(drive = 'C:\\'): Promise<DriveInfo> {
  return invoke<DriveInfo>('get_drive_info', { drive });
}

export async function scanDrive(
  root: string,
  minSizeMb: number,
  maxDepth: number
): Promise<ScanItem[]> {
  return invoke<ScanItem[]>('scan_drive', { root, minSizeMb, maxDepth });
}

export async function explainItem(
  path: string,
  sizeBytes: number,
  isDir: boolean,
  apiKey: string,
  baseUrl: string,
  model: string
): Promise<ExplainResponse> {
  return invoke<ExplainResponse>('explain_item', {
    path,
    sizeBytes,
    isDir,
    apiKey,
    baseUrl,
    model,
  });
}

export async function fetchModels(
  apiKey: string,
  baseUrl: string = 'https://openrouter.ai/api/v1'
): Promise<ModelInfo[]> {
  return invoke<ModelInfo[]>('fetch_models', { apiKey, baseUrl });
}

export async function fetchEnvKey(): Promise<{ has_env_key: boolean; source: string | null }> {
  return invoke('get_env_key');
}
