import { motion, AnimatePresence } from 'framer-motion';
import { useEffect, useState } from 'react';
import { LayoutDashboard, List, Settings, HardDrive, Key, ChevronDown, Check, Loader2 } from 'lucide-react';
import { fetchModels, fetchEnvKey } from '../api';
import type { AppSettings, ModelInfo } from '../types';

type View = 'dashboard' | 'results';

interface Props {
  currentView: View;
  onViewChange: (v: View) => void;
  hasResults: boolean;
  settings: AppSettings;
  onSettingsChange: (s: AppSettings) => void;
  showSettings: boolean;
  onToggleSettings: () => void;
  onSaveSettings: () => void;
  settingsDirty: boolean;
}

export function Sidebar({
  currentView,
  onViewChange,
  hasResults,
  settings,
  onSettingsChange,
  showSettings,
  onToggleSettings,
  onSaveSettings,
  settingsDirty,
}: Props) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [envKeyInfo, setEnvKeyInfo] = useState<{ has_env_key: boolean; source: string | null }>({ has_env_key: false, source: null });
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [modelFilter, setModelFilter] = useState('');
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    fetchEnvKey().then(setEnvKeyInfo).catch(() => {});
  }, []);

  const handleFetchModels = async () => {
    const key = settings.useEnvKey ? '' : settings.apiKey;
    if (!key && !envKeyInfo.has_env_key) return;
    setModelsLoading(true);
    setModelsError(null);
    try {
      const result = await fetchModels(key, settings.baseUrl);
      setModels(result);
    } catch (e: unknown) {
      setModelsError(e instanceof Error ? e.message : 'Failed to fetch models');
    } finally {
      setModelsLoading(false);
    }
  };

  const handleSave = () => {
    onSaveSettings();
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 1500);
  };

  const filteredModels = models.filter(
    (m) =>
      m.id.toLowerCase().includes(modelFilter.toLowerCase()) ||
      m.name.toLowerCase().includes(modelFilter.toLowerCase())
  );

  return (
    <div style={{
      width: 260,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      background: 'rgba(255,255,255,0.015)',
      borderRight: '1px solid var(--border)',
      height: '100%',
    }}>
      {/* Logo */}
      <div style={{ padding: '24px 20px 20px' }}>
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{ display: 'flex', alignItems: 'center', gap: 10 }}
        >
          <motion.div
            whileHover={{ boxShadow: '0 0 24px rgba(0,212,255,0.5)', scale: 1.05 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            style={{
              width: 34, height: 34, borderRadius: 10,
              background: 'var(--accent-gradient)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 14px rgba(0,212,255,0.25)',
              flexShrink: 0,
            }}
          >
            <HardDrive size={16} color="white" />
          </motion.div>
          <div>
            <div style={{
              fontSize: 13, fontWeight: 800,
              background: 'var(--accent-gradient)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              lineHeight: 1.2,
            }}>
              C盘守护者
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>v1.0</div>
          </div>
        </motion.div>
      </div>

      <div style={{ margin: '0 16px 12px', height: 1, background: 'var(--border)' }} />

      {/* Nav */}
      <nav style={{ padding: '0 12px', flex: 1 }}>
        <NavItem
          icon={<LayoutDashboard size={16} />}
          label="概览"
          active={currentView === 'dashboard'}
          onClick={() => onViewChange('dashboard')}
        />
        <NavItem
          icon={<List size={16} />}
          label="扫描结果"
          active={currentView === 'results'}
          disabled={!hasResults}
          onClick={() => hasResults && onViewChange('results')}
        />
      </nav>

      {/* Settings toggle */}
      <div style={{ padding: '0 12px 8px' }}>
        <NavItem
          icon={<Settings size={16} />}
          label="设置"
          active={showSettings}
          onClick={onToggleSettings}
        />
      </div>

      {/* Settings panel */}
      <AnimatePresence>
        {showSettings && (
          <motion.div
            key="settings"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            style={{ borderTop: '1px solid var(--border)', overflow: 'hidden' }}
          >
            <div style={{ padding: '16px', maxHeight: 'calc(100vh - 340px)', overflowY: 'auto' }}>
              {/* API Key */}
              <SectionLabel icon={<Key size={13} />} label="API Key" />

              {envKeyInfo.has_env_key && (
                <motion.button
                  onClick={() => onSettingsChange({ ...settings, useEnvKey: !settings.useEnvKey, apiKey: '' })}
                  whileHover={{ scale: 1.01 }}
                  style={{
                    width: '100%', padding: '8px 10px', borderRadius: 8,
                    border: settings.useEnvKey ? '1px solid rgba(0,212,255,0.4)' : '1px solid var(--border)',
                    background: settings.useEnvKey ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.03)',
                    color: 'var(--text-secondary)', fontSize: 11, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, textAlign: 'left',
                  }}
                >
                  <div style={{
                    width: 16, height: 16, borderRadius: 4,
                    border: settings.useEnvKey ? '1px solid var(--accent-cyan)' : '1px solid var(--text-muted)',
                    background: settings.useEnvKey ? 'var(--accent-cyan)' : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    {settings.useEnvKey && <Check size={10} color="white" />}
                  </div>
                  <div>
                    <div style={{ fontSize: 11 }}>使用环境变量</div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>
                      {envKeyInfo.source} 已设置
                    </div>
                  </div>
                </motion.button>
              )}

              {!settings.useEnvKey && (
                <SettingField
                  label=""
                  value={settings.apiKey}
                  type="password"
                  placeholder="sk-or-..."
                  onChange={(v) => onSettingsChange({ ...settings, apiKey: v })}
                />
              )}

              {/* Base URL */}
              <SettingField
                label="Base URL"
                value={settings.baseUrl}
                placeholder="https://openrouter.ai/api/v1"
                onChange={(v) => onSettingsChange({ ...settings, baseUrl: v })}
              />

              {/* Model selector */}
              <div style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 10, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  模型
                </label>
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={() => {
                      if (models.length === 0 && !modelsLoading) handleFetchModels();
                      setShowModelDropdown(!showModelDropdown);
                    }}
                    style={{
                      width: '100%', padding: '7px 9px',
                      background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)',
                      borderRadius: 6, color: 'var(--text-primary)', fontSize: 11,
                      cursor: 'pointer', display: 'flex', alignItems: 'center',
                      justifyContent: 'space-between', textAlign: 'left', fontFamily: 'Inter, sans-serif',
                    }}
                  >
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 }}>
                      {settings.model || 'Select model...'}
                    </span>
                    {modelsLoading ? (
                      <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                        <Loader2 size={12} color="var(--text-muted)" />
                      </motion.div>
                    ) : (
                      <ChevronDown size={12} color="var(--text-muted)" />
                    )}
                  </button>

                  <AnimatePresence>
                    {showModelDropdown && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.15 }}
                        style={{
                          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4,
                          background: 'rgba(16, 16, 32, 0.98)', border: '1px solid rgba(0,212,255,0.2)',
                          borderRadius: 8, boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                          zIndex: 200, maxHeight: 280, display: 'flex', flexDirection: 'column', overflow: 'hidden',
                        }}
                      >
                        <div style={{ padding: '8px 8px 4px' }}>
                          <input
                            type="text"
                            value={modelFilter}
                            onChange={(e) => setModelFilter(e.target.value)}
                            placeholder="搜索模型..."
                            autoFocus
                            style={{
                              width: '100%', padding: '6px 8px',
                              background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border)',
                              borderRadius: 5, color: 'var(--text-primary)', fontSize: 11,
                              outline: 'none', fontFamily: 'Inter, sans-serif',
                            }}
                          />
                        </div>
                        <div style={{ overflowY: 'auto', padding: '4px' }}>
                          {modelsLoading && (
                            <div style={{ padding: '12px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
                              正在加载模型列表...
                            </div>
                          )}
                          {modelsError && (
                            <div style={{ padding: '12px', fontSize: 11, color: 'rgba(255,100,100,0.9)', textAlign: 'center' }}>
                              {modelsError}
                            </div>
                          )}
                          {!modelsLoading && !modelsError && filteredModels.length === 0 && models.length > 0 && (
                            <div style={{ padding: '12px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
                              无匹配模型
                            </div>
                          )}
                          {!modelsLoading && models.length === 0 && !modelsError && (
                            <button
                              onClick={handleFetchModels}
                              style={{
                                width: '100%', padding: '10px', fontSize: 11,
                                color: 'var(--accent-cyan)', background: 'none',
                                border: 'none', cursor: 'pointer', textAlign: 'center',
                              }}
                            >
                              点击加载模型列表
                            </button>
                          )}
                          {filteredModels.map((m) => (
                            <button
                              key={m.id}
                              onClick={() => {
                                onSettingsChange({ ...settings, model: m.id });
                                setShowModelDropdown(false);
                                setModelFilter('');
                              }}
                              style={{
                                width: '100%', padding: '7px 8px',
                                background: settings.model === m.id ? 'rgba(0,212,255,0.1)' : 'transparent',
                                border: 'none', borderRadius: 5,
                                color: settings.model === m.id ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                                fontSize: 10, cursor: 'pointer', textAlign: 'left',
                                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4,
                              }}
                              onMouseEnter={(e) => { (e.target as HTMLElement).style.background = 'rgba(255,255,255,0.05)'; }}
                              onMouseLeave={(e) => { (e.target as HTMLElement).style.background = settings.model === m.id ? 'rgba(0,212,255,0.1)' : 'transparent'; }}
                            >
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                                {m.name || m.id}
                              </span>
                              {settings.model === m.id && <Check size={10} />}
                            </button>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                <input
                  type="text"
                  value={settings.model}
                  placeholder="或手动输入模型ID"
                  onChange={(e) => onSettingsChange({ ...settings, model: e.target.value })}
                  style={{
                    width: '100%', padding: '5px 9px',
                    background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)',
                    borderRadius: 5, color: 'var(--text-muted)', fontSize: 10,
                    outline: 'none', fontFamily: 'Inter, sans-serif', marginTop: 4,
                  }}
                />
              </div>

              {/* Save Button */}
              <motion.button
                onClick={handleSave}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                style={{
                  width: '100%', padding: '9px 12px', borderRadius: 8, border: 'none',
                  background: savedFlash ? 'rgba(0,200,100,0.3)' : settingsDirty ? 'var(--accent-gradient)' : 'rgba(255,255,255,0.08)',
                  color: savedFlash ? 'rgba(0,255,150,1)' : settingsDirty ? 'white' : 'var(--text-muted)',
                  fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  transition: 'background 0.3s, color 0.3s',
                }}
              >
                {savedFlash ? (<><Check size={14} />已保存</>) : '保存配置'}
              </motion.button>

              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 10, lineHeight: 1.5 }}>
                支持 OpenRouter / OpenAI 兼容接口。环境变量 OPENROUTER_API_KEY 或 OPENAI_API_KEY 可自动识别。
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div style={{
        padding: '12px 16px', borderTop: '1px solid var(--border)',
        fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.6,
      }}>
        只读扫描，不执行任何删除操作
      </div>
    </div>
  );
}

function SectionLabel({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
      <span style={{ color: 'var(--accent-cyan)', display: 'flex' }}>{icon}</span>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </span>
    </div>
  );
}

function NavItem({ icon, label, active, disabled, onClick }: {
  icon: React.ReactNode; label: string; active: boolean; disabled?: boolean; onClick: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { x: 3 }}
      whileTap={disabled ? {} : { scale: 0.97 }}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
        padding: '9px 12px', borderRadius: 'var(--radius-sm)',
        background: active ? 'rgba(0,212,255,0.1)' : 'transparent',
        border: active ? '1px solid rgba(0,212,255,0.2)' : '1px solid transparent',
        color: active ? 'var(--accent-cyan)' : disabled ? 'var(--text-muted)' : 'var(--text-secondary)',
        fontSize: 13, fontWeight: active ? 600 : 400,
        cursor: disabled ? 'not-allowed' : 'pointer', textAlign: 'left', marginBottom: 2,
        transition: 'background 0.15s, color 0.15s, border-color 0.15s',
        boxShadow: active ? '0 0 12px rgba(0,212,255,0.1)' : 'none',
      }}
    >
      {icon}
      {label}
    </motion.button>
  );
}

function SettingField({ label, value, type = 'text', placeholder, onChange }: {
  label: string; value: string; type?: string; placeholder?: string; onChange: (v: string) => void;
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      {label && (
        <label style={{ fontSize: 10, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
          {label}
        </label>
      )}
      <input
        type={type} value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%', padding: '7px 9px',
          background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)',
          borderRadius: 6, color: 'var(--text-primary)', fontSize: 11,
          outline: 'none', fontFamily: 'Inter, sans-serif',
        }}
      />
    </div>
  );
}
