import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Dashboard } from './components/Dashboard';
import { ScanResults } from './components/ScanResults';
import { ExplanationBubble } from './components/ExplanationBubble';
import { Sidebar } from './components/Sidebar';
import {
  cancelScan,
  classifyFiles,
  checkAdmin,
  prepareExplanation,
  fetchDriveInfo,
  getScanResults,
  relaunchAsAdmin,
  scanDrive,
} from './api';
import type {
  AppSettings,
  FileClassification,
  DriveInfo,
  EvidencePacket,
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
};

const DEFAULT_CONFIG: ScanConfig = {
  root: 'C:\\',
  min_size_mb: 10,
  engine: 'mft_dual',
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
  const [activeScanConfig, setActiveScanConfig] = useState<ScanConfig>(DEFAULT_CONFIG);
  const [scanning, setScanning] = useState(false);
  const scanRunningRef = useRef(false);
  const [scanRun, setScanRun] = useState(0);
  const [progress, setProgress] = useState<ScanProgress | null>(null);
  const [results, setResults] = useState<ScanItem[]>([]);
  const [classifications, setClassifications] = useState<Record<string, FileClassification>>({});
  const [classificationError, setClassificationError] = useState<string | null>(null);
  const classifiedResults = useMemo(() => results.map(item => ({ ...item, classification: classifications[item.path] })), [results, classifications]);
  useEffect(() => {
    if (classificationError) return;
    const batch = results.filter(item => !classifications[item.path]).slice(0, 1000);
    if (!batch.length) return;
    let active = true;
    classifyFiles(batch).then(values => {
      if (!active) return;
      if (values.length !== batch.length) throw new Error('分类结果数量不一致');
      setClassifications(previous => ({ ...previous, ...Object.fromEntries(batch.map((item, i) => [item.path, values[i]])) }));
    }).catch(error => { if (active) setClassificationError(String(error)); });
    return () => { active = false; };
  }, [results, classifications, classificationError]);
  const [selectedItem, setSelectedItem] = useState<ScanItem | null>(null);
  const [preview, setPreview] = useState<EvidencePacket | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const explainRequestRef = useRef(0);
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
    setResults(prev => [...prev, ...batch]);
  }, []);

  const handleStartScan = useCallback(async (config: ScanConfig) => {
    if (scanRunningRef.current) return;
    scanRunningRef.current = true;
    setActiveScanConfig(config);
    setScanRun(run => run + 1);
    setScanning(true);
    setBackendError(null);
    explainRequestRef.current += 1;
    setExplainLoading(false);
    setResults([]);
    setClassifications({});
    setClassificationError(null);
    fileBatchRef.current = [];
    setSelectedItem(null);
    setPreview(null);
    setExplainError(null);
    setProgress({ status: 'running', engine: config.engine, entries_scanned: 0, files_matched: 0,
      issues: [], excluded_links: [], elapsed_ms: 0, error: null });
    setView('results');

    try {
      const completion = await scanDrive(config.root, config.min_size_mb, (msg) => {
        if (msg.type === 'progress') {
          setProgress(p => p ? {
            ...p,
            entries_scanned: msg.entries_scanned,
            files_matched: msg.files_matched,
          } : p);
        } else if (msg.type === 'verification') {
          setProgress(p => p ? { ...p, verification: msg.verification } : p);
        } else if (msg.type === 'files') {
          fileBatchRef.current.push(...msg.files);
          if (!flushTimerRef.current) {
            flushTimerRef.current = setTimeout(flushFileBatch, 500);
          }
        }
      }, config.engine);
      // Flush any remaining files
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      if (!completion.stream_verified) {
        // Reload the complete retained result if a batch is missing, repeated or undelivered.
        const restored: ScanItem[] = [];
        while (restored.length < completion.summary.files_matched) {
          const page = await getScanResults(completion.scan_id, restored.length);
          if (page.length === 0) throw new Error('扫描结果核对失败：后端结果不完整');
          restored.push(...page);
        }
        if (restored.length !== completion.summary.files_matched
            || new Set(restored.map(item => item.path)).size !== restored.length) {
          throw new Error('扫描结果核对失败：数量不一致或路径重复');
        }
        fileBatchRef.current = [];
        setResults(restored);
      } else {
        flushFileBatch();
      }
      setProgress({ ...completion.summary, error: completion.transport_error });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setBackendError(`扫描失败: ${msg}`);
      // Flush remaining on error too
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      flushFileBatch();
      setProgress(prev => prev ? { ...prev, status: 'failed', error: msg } : null);
    } finally {
      setResults(prev => [...prev].sort((a, b) => b.size - a.size || a.path.localeCompare(b.path)));
      scanRunningRef.current = false;
      setScanning(false);
    }
  }, [flushFileBatch]);

  const handleStopScan = useCallback(() => {
    cancelScan().catch(e => setBackendError(`无法停止扫描: ${String(e)}`));
  }, []);

  const handleItemClick = useCallback(async (item: ScanItem) => {
    const requestId = ++explainRequestRef.current;
    setExplainLoading(false);
    if (selectedItem?.path === item.path) {
      setSelectedItem(null);
      setPreview(null);
      setExplainError(null);
      return;
    }

    setSelectedItem(item);
    setPreview(null);
    setExplainError(null);

    setExplainLoading(true);
    try {
      const packet = await prepareExplanation(item.path);
      if (requestId === explainRequestRef.current) setPreview(packet);
    } catch (e: unknown) {
      if (requestId === explainRequestRef.current) setExplainError(e instanceof Error ? e.message : String(e));
    } finally {
      if (requestId === explainRequestRef.current) setExplainLoading(false);
    }
  }, [selectedItem]);

  const handleCloseExplanation = useCallback(() => {
    explainRequestRef.current += 1;
    setExplainLoading(false);
    setSelectedItem(null);
    setPreview(null);
    setExplainError(null);
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', position: 'relative', zIndex: 1 }}>
      <Sidebar
        onLocalModelChange={handleCloseExplanation}
        currentView={view}
        onViewChange={setView}
        hasResults={progress !== null || scanning}
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
                  key={scanRun}
                  config={activeScanConfig}
                  items={classifiedResults}
                  classificationError={classificationError}
                  progress={progress}
                  onItemClick={handleItemClick}
                  selectedPath={selectedItem?.path ?? null}
                  onStopScan={scanning ? handleStopScan : undefined}
                  onItemsDeleted={(paths) => {
                    setResults(prev => prev.filter(r => !paths.includes(r.path)));
                    if (selectedItem && paths.includes(selectedItem.path)) {
                      handleCloseExplanation();
                    }
                  }}
                />
                <ExplanationBubble
                  item={selectedItem ? { ...selectedItem, classification: classifications[selectedItem.path] } : null}
                  key={selectedItem?.path ?? "closed"}
                  preview={preview}
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
          扫描会遍历所选目录的全部层级，并报告无法读取的位置。
          <br />
          <strong style={{ color: 'var(--accent-cyan)' }}>管理员权限</strong>可能扩大可访问范围；实际覆盖情况以扫描报告为准。
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
