import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, List, Settings, HardDrive, Key } from 'lucide-react';
import type { AppSettings } from '../types';

type View = 'dashboard' | 'results';

interface Props {
  currentView: View;
  onViewChange: (v: View) => void;
  hasResults: boolean;
  settings: AppSettings;
  onSettingsChange: (s: AppSettings) => void;
  showSettings: boolean;
  onToggleSettings: () => void;
}

export function Sidebar({
  currentView,
  onViewChange,
  hasResults,
  settings,
  onSettingsChange,
  showSettings,
  onToggleSettings,
}: Props) {
  return (
    <div style={{
      width: 220,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      background: 'rgba(255,255,255,0.015)',
      borderRight: '1px solid var(--border)',
      height: '100%',
    }}>
      {/* Logo area */}
      <div style={{ padding: '24px 20px 20px' }}>
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{ display: 'flex', alignItems: 'center', gap: 10 }}
        >
          {/* Logo icon with hover glow */}
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
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>v1.0 · MVP</div>
          </div>
        </motion.div>
      </div>

      {/* Divider */}
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
          badge={hasResults ? undefined : undefined}
          onClick={() => hasResults && onViewChange('results')}
        />
      </nav>

      {/* Settings toggle */}
      <div style={{ padding: '0 12px 8px' }}>
        <NavItem
          icon={<Settings size={16} />}
          label="API 设置"
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
            style={{
              borderTop: '1px solid var(--border)',
              overflow: 'hidden',
            }}
          >
            <div style={{ padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <Key size={13} color="var(--accent-cyan)" />
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  LLM 配置
                </span>
              </div>
              <SettingField
                label="API Key"
                value={settings.apiKey}
                type="password"
                placeholder="sk-..."
                onChange={(v) => onSettingsChange({ ...settings, apiKey: v })}
              />
              <SettingField
                label="Base URL"
                value={settings.baseUrl}
                placeholder="https://openrouter.ai/api/v1"
                onChange={(v) => onSettingsChange({ ...settings, baseUrl: v })}
              />
              <SettingField
                label="模型"
                value={settings.model}
                placeholder="anthropic/claude-haiku-4-5"
                onChange={(v) => onSettingsChange({ ...settings, model: v })}
              />
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8, lineHeight: 1.5 }}>
                支持 OpenRouter / OpenAI 兼容接口
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bottom hint */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        fontSize: 10,
        color: 'var(--text-muted)',
        lineHeight: 1.6,
      }}>
        🛡️ 只读扫描，不执行任何删除操作
      </div>
    </div>
  );
}

function NavItem({
  icon, label, active, disabled, onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  disabled?: boolean;
  badge?: string;
  onClick: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { x: 3 }}
      whileTap={disabled ? {} : { scale: 0.97 }}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '9px 12px',
        borderRadius: 'var(--radius-sm)',
        background: active ? 'rgba(0,212,255,0.1)' : 'transparent',
        border: active ? '1px solid rgba(0,212,255,0.2)' : '1px solid transparent',
        color: active ? 'var(--accent-cyan)' : disabled ? 'var(--text-muted)' : 'var(--text-secondary)',
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        cursor: disabled ? 'not-allowed' : 'pointer',
        textAlign: 'left',
        marginBottom: 2,
        transition: 'background 0.15s, color 0.15s, border-color 0.15s',
        boxShadow: active ? '0 0 12px rgba(0,212,255,0.1)' : 'none',
      }}
    >
      {icon}
      {label}
    </motion.button>
  );
}

function SettingField({
  label, value, type = 'text', placeholder, onChange,
}: {
  label: string;
  value: string;
  type?: string;
  placeholder?: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: 10, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
        {label}
      </label>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: '7px 9px',
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          color: 'var(--text-primary)',
          fontSize: 11,
          outline: 'none',
          fontFamily: 'Inter, sans-serif',
        }}
      />
    </div>
  );
}
