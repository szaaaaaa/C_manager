import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Dashboard } from './components/Dashboard';
import { ScanResults } from './components/ScanResults';
import { ExplanationBubble } from './components/ExplanationBubble';
import { Sidebar } from './components/Sidebar';
import {
  cancelScan,
  checkAdmin,
  explainItem,
  fetchDriveInfo,
  relaunchAsAdmin,
  scanDrive,
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
  apiKey: '',
  useEnvKey: false,
  baseUrl: 'https://openrouter.ai/api/v1',
  model: 'anthropic/claude-haiku-4-5',
  modelSource: 'local',
  tavilyKey: '',
};

const DEFAULT_CONFIG: ScanConfig = {
  root: 'C:\\',
  min_size_mb: 10,
  max_depth: 3,
};

function loadSettings(): AppSettings {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      // Migrate old 'ollama' setting to 'local'
      if (parsed.modelSource === 'ollama') {
        parsed.modelSource = 'local';
      }
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
  const [initialSettings] = useState(loadSettings);
  const [settings, setSettings] = useState<AppSettings>(initialSettings);
  const [savedSettings, setSavedSettings] = useState<AppSettings>(initialSettings);
  const [showSettings, setShowSettings] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [showAdminPrompt, setShowAdminPrompt] = useState(false);

  const settingsDirty = JSON.stringify(settings) !== JSON.stringify(savedSettings);

  // Load drive info and check admin on mount
  useEffect(() => {
    fetchDriveInfo('C:\\')
      .then(setDriveInfo)
      .catch((e) => setBackendError(`无法获取磁盘信息: ${e}`));
    checkAdmin().then((admin) => {
      setIsAdmin(admin);
      if (!admin) setShowAdminPrompt(true);
    }).catch(() => {});
  }, []);

  const handleSaveSettings = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    setSavedSettings(settings);
  }, [settings]);

  const fileBatchRef = useRef<ScanItem[]>([]);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushFileBatch = useCallback(() => {
    flushTimerRef.current = null;
    const batch = fileBatchRef.current;
    if (batch.length === 0) return;
    fileBatchRef.current = [];
    setResults(prev => {
      const next = [...prev, ...batch];
      next.sort((a, b) => b.size - a.size);
      return next;
    });
  }, []);

  const handleStartScan = useCallback(async (config: ScanConfig) => {
    if (scanning) return;
    setScanning(true);
    setResults([]);
    fileBatchRef.current = [];
    setSelectedItem(null);
    setExplanation(null);
    setExplainError(null);
    setProgress({ running: true, progress: 0, current_path: '正在扫描 MFT...', result_count: 0, error: null });
    setView('results');

    try {
      await scanDrive(config.root, config.min_size_mb, config.max_depth, (msg) => {
        if (msg.type === 'progress') {
          setProgress(p => p ? {
            ...p,
            progress: msg.entries_scanned,
            current_path: `已扫描 ${msg.entries_scanned.toLocaleString()} 条记录`,
            result_count: msg.files_matched,
          } : p);
        } else if (msg.type === 'file') {
          fileBatchRef.current.push(msg as unknown as ScanItem);
          // Flush batch every 200ms to avoid per-file re-render
          if (!flushTimerRef.current) {
            flushTimerRef.current = setTimeout(flushFileBatch, 200);
          }
        }
      });
      // Flush any remaining files
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      flushFileBatch();
      setProgress(prev => prev ? { ...prev, running: false } : null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!msg.includes('cancelled')) {
        setBackendError(`扫描失败: ${msg}`);
      }
      // Flush remaining on error too
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      flushFileBatch();
      setProgress(null);
    } finally {
      setScanning(false);
    }
  }, [scanning, flushFileBatch]);

  const handleStopScan = useCallback(() => {
    cancelScan().catch(() => {});
  }, []);

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

    const s = savedSettings;
    const isLocal = s.modelSource === 'local';

    if (!isLocal && !s.apiKey && !s.useEnvKey) {
      setExplainError('no api key');
      return;
    }

    setExplainLoading(true);
    try {
      const resp = await explainItem(
        item.path,
        item.size,
        item.is_dir,
        isLocal ? '' : (s.useEnvKey ? '' : s.apiKey),
        isLocal ? '' : s.baseUrl,
        isLocal ? '' : s.model,
        isLocal,
        isLocal ? (s.tavilyKey || '') : '',
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

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
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
                  isAdmin={isAdmin}
                  onRequestAdmin={relaunchAsAdmin}
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
                  onStopScan={scanning ? handleStopScan : undefined}
                  onItemsDeleted={(paths) => {
                    setResults(prev => prev.filter(r => !paths.includes(r.path)));
                    if (selectedItem && paths.includes(selectedItem.path)) {
                      setSelectedItem(null);
                      setExplanation(null);
                    }
                  }}
                />
                <ExplanationBubble
                  item={selectedItem}
                  explanation={explanation}
                  loading={explainLoading}
                  error={explainError}
                  onClose={handleCloseExplanation}
                  settings={savedSettings}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Admin elevation prompt on startup */}
      <AnimatePresence>
        {showAdminPrompt && (
          <>
            <motion.div
              key="admin-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowAdminPrompt(false)}
              style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(6px)', zIndex: 300 }}
            />
            <AdminDialog onClose={() => setShowAdminPrompt(false)} onElevate={() => { setShowAdminPrompt(false); relaunchAsAdmin(); }} />
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function AdminDialog({ onClose, onElevate }: { onClose: () => void; onElevate: () => void }) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    setDragging(true);
    dragStart.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [pos]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging) return;
    setPos({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y });
  }, [dragging]);

  const onPointerUp = useCallback(() => setDragging(false), []);

  const dragRef = useRef({ x: 0, y: 0 });
  dragRef.current = dragStart.current;

  return (
    <motion.div
      key="admin-dialog"
      initial={{ opacity: 0, scale: 0.85, y: 30 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.9, y: 20 }}
      transition={{ type: 'spring', stiffness: 400, damping: 26 }}
      style={{
        position: 'fixed',
        top: `calc(50% + ${pos.y}px)`,
        left: `calc(50% + ${pos.x}px)`,
        transform: 'translate(-50%, -50%)',
        width: 400,
        background: 'rgba(12,12,28,0.97)',
        border: '1px solid rgba(0,212,255,0.2)',
        borderRadius: 18,
        zIndex: 301,
        overflow: 'hidden',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(0,212,255,0.06)',
      }}
    >
      {/* Draggable title bar */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={{
          padding: '16px 20px 12px',
          cursor: dragging ? 'grabbing' : 'grab',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 22 }}>🔍</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>扫描权限提示</span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,255,255,0.06)', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', width: 26, height: 26, borderRadius: 6,
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
          }}
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: '20px 24px 24px', textAlign: 'center' }}>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 22 }}>
          你的个人文件无需提权即可完整扫描。
          <br />
          <strong style={{ color: 'var(--accent-cyan)' }}>管理员权限</strong>可额外访问系统保护目录（Windows Installer 缓存、WinSxS 等），这些通常是不可删除的系统文件。
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={onClose}
            style={{
              flex: 1, padding: '11px', borderRadius: 10, border: '1px solid var(--border)',
              background: 'transparent', color: 'var(--text-muted)', fontSize: 13,
              fontWeight: 600, cursor: 'pointer',
            }}
          >
            跳过，继续扫描
          </button>
          <button
            onClick={onElevate}
            style={{
              flex: 1, padding: '11px', borderRadius: 10, border: 'none',
              background: 'var(--accent-gradient)', color: 'white', fontSize: 13,
              fontWeight: 700, cursor: 'pointer',
            }}
          >
            以管理员重启
          </button>
        </div>
      </div>
    </motion.div>
  );
}
