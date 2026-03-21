import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Dashboard } from './components/Dashboard';
import { ScanResults } from './components/ScanResults';
import { ExplanationBubble } from './components/ExplanationBubble';
import { Sidebar } from './components/Sidebar';
import {
  explainItem,
  fetchDriveInfo,
  fetchScanResults,
  startScan,
  subscribeScanProgress,
} from './api';
import type {
  AppSettings,
  DriveInfo,
  ExplainResponse,
  ScanConfig,
  ScanItem,
  ScanProgress,
} from './types';

type View = 'dashboard' | 'results';

const STORAGE_KEY = 'c_manager_settings';

const DEFAULT_SETTINGS: AppSettings = {
  aiBackend: 'api',
  apiKey: '',
  useEnvKey: false,
  baseUrl: 'https://openrouter.ai/api/v1',
  model: 'anthropic/claude-haiku-4-5',
};

const DEFAULT_CONFIG: ScanConfig = {
  root: 'C:\\',
  min_size_mb: 50,
  max_depth: 3,
};

function loadSettings(): AppSettings {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch {
    // ignore
  }
  return DEFAULT_SETTINGS;
}

export default function App() {
  const [view, setView] = useState<View>('dashboard');
  const [driveInfo, setDriveInfo] = useState<DriveInfo | null>(null);
  const [scanConfig, setScanConfig] = useState<ScanConfig>(DEFAULT_CONFIG);
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState<ScanProgress | null>(null);
  const [results, setResults] = useState<ScanItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<ScanItem | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [settings, setSettings] = useState<AppSettings>(loadSettings);
  const [savedSettings, setSavedSettings] = useState<AppSettings>(loadSettings);
  const [showSettings, setShowSettings] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  const sseCleanup = useRef<(() => void) | null>(null);

  const settingsDirty = JSON.stringify(settings) !== JSON.stringify(savedSettings);

  // Load drive info on mount
  useEffect(() => {
    fetchDriveInfo('C:\\')
      .then(setDriveInfo)
      .catch(() => setBackendError('无法连接到后端服务 (localhost:8765)。请先启动 Python 后端。'));
  }, []);

  const handleSaveSettings = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    setSavedSettings(settings);
  }, [settings]);

  const handleStartScan = useCallback(async (config: ScanConfig) => {
    if (scanning) return;
    setScanning(true);
    setResults([]);
    setSelectedItem(null);
    setExplanation(null);
    setExplainError(null);
    setProgress({ running: true, progress: 0, current_path: '', result_count: 0, error: null });

    try {
      await startScan(config);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setBackendError(`扫描启动失败: ${msg}`);
      setScanning(false);
      return;
    }

    setView('results');

    // Subscribe to SSE progress
    sseCleanup.current?.();
    sseCleanup.current = subscribeScanProgress(
      (p) => setProgress(p),
      async () => {
        // Scan done — fetch results
        try {
          const r = await fetchScanResults();
          setResults(r.results);
        } catch {
          // ignore
        }
        setScanning(false);
      },
      (err) => {
        setBackendError(`进度流失败: ${err.message}`);
        setScanning(false);
      }
    );
  }, [scanning]);

  const handleItemClick = useCallback(async (item: ScanItem) => {
    if (selectedItem?.path === item.path) {
      setSelectedItem(null);
      setExplanation(null);
      setExplainError(null);
      return;
    }

    setSelectedItem(item);
    setExplanation(null);
    setExplainError(null);

    // Use saved settings for API calls
    const s = savedSettings;

    if (s.aiBackend === 'api' && !s.apiKey && !s.useEnvKey) {
      setExplainError('no api key');
      return;
    }

    setExplainLoading(true);
    try {
      const resp = await explainItem(
        item.path,
        item.size,
        item.is_dir,
        s.useEnvKey ? '' : s.apiKey,
        s.baseUrl,
        s.model,
        s.aiBackend
      );
      setExplanation(resp);
    } catch (e: unknown) {
      setExplainError(e instanceof Error ? e.message : String(e));
    } finally {
      setExplainLoading(false);
    }
  }, [selectedItem, savedSettings]);

  const handleCloseExplanation = useCallback(() => {
    setSelectedItem(null);
    setExplanation(null);
    setExplainError(null);
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', position: 'relative', zIndex: 1 }}>
      {/* Sidebar */}
      <Sidebar
        currentView={view}
        onViewChange={setView}
        hasResults={results.length > 0 || scanning}
        settings={settings}
        onSettingsChange={setSettings}
        showSettings={showSettings}
        onToggleSettings={() => setShowSettings(v => !v)}
        onSaveSettings={handleSaveSettings}
        settingsDirty={settingsDirty}
      />

      {/* Main content area */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {/* Backend error banner */}
        <AnimatePresence>
          {backendError && (
            <motion.div
              initial={{ opacity: 0, y: -40 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -40 }}
              style={{
                background: 'rgba(255,68,68,0.12)',
                borderBottom: '1px solid rgba(255,68,68,0.25)',
                padding: '10px 24px',
                fontSize: 13,
                color: '#ff8888',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              {backendError}
              <button
                onClick={() => setBackendError(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ff8888', fontSize: 16 }}
              >x</button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* View content */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          <AnimatePresence mode="wait">
            {view === 'dashboard' ? (
              <motion.div
                key="dashboard"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                style={{ height: '100%', overflowY: 'auto' }}
              >
                <Dashboard
                  driveInfo={driveInfo}
                  onStartScan={handleStartScan}
                  scanning={scanning}
                  scanConfig={scanConfig}
                  onConfigChange={setScanConfig}
                />
              </motion.div>
            ) : (
              <motion.div
                key="results"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.2 }}
                style={{ height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}
              >
                <ScanResults
                  items={results}
                  progress={progress}
                  onItemClick={handleItemClick}
                  selectedPath={selectedItem?.path ?? null}
                />
                {/* Explanation panel overlays the right side of results */}
                <ExplanationBubble
                  item={selectedItem}
                  explanation={explanation}
                  loading={explainLoading}
                  error={explainError}
                  onClose={handleCloseExplanation}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
