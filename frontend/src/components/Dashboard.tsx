import { motion, useMotionValue, animate } from 'framer-motion';
import { useEffect, useState } from 'react';
import { HardDrive, Search, Zap } from 'lucide-react';
import { DriveRing } from './DriveRing';
import type { DriveInfo, ScanConfig } from '../types';

interface Props {
  driveInfo: DriveInfo | null;
  onStartScan: (config: ScanConfig) => void;
  scanning: boolean;
  scanConfig: ScanConfig;
  onConfigChange: (c: ScanConfig) => void;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`;
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  return `${(bytes / 1e3).toFixed(0)} KB`;
}

/** Animates a number from 0 to `target`, re-animating when target changes. */
function CountUpValue({ target, format }: { target: number; format: (n: number) => string }) {
  const mv = useMotionValue(0);
  const [display, setDisplay] = useState(format(0));

  useEffect(() => {
    const ctrl = animate(mv, target, {
      duration: 1.6,
      ease: [0.34, 1.56, 0.64, 1],
      onUpdate: (v) => setDisplay(format(Math.round(v))),
    });
    return ctrl.stop;
  }, [target]);

  return <span>{display}</span>;
}

export function Dashboard({ driveInfo, onStartScan, scanning, scanConfig, onConfigChange }: Props) {
  const usedPercent = driveInfo
    ? Math.round((driveInfo.used / driveInfo.total) * 100)
    : 0;

  const stats = [
    {
      label: '总容量',
      value: driveInfo?.total ?? 0,
      color: 'var(--text-primary)',
    },
    {
      label: '已使用',
      value: driveInfo?.used ?? 0,
      color: 'var(--accent-cyan)',
    },
    {
      label: '可用空间',
      value: driveInfo?.free ?? 0,
      color: 'var(--green)',
    },
  ];

  return (
    <div style={{ padding: '40px 48px', display: 'flex', flexDirection: 'column', gap: 40 }}>
      {/* Header — animated title */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{ display: 'flex', alignItems: 'center', gap: 14 }}
      >
        {/* Logo with pulse ring */}
        <div style={{ position: 'relative', display: 'inline-flex', flexShrink: 0 }}>
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20, delay: 0.1 }}
            style={{
              width: 48, height: 48, borderRadius: 14,
              background: 'var(--accent-gradient)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 28px rgba(0,212,255,0.4)',
              position: 'relative', zIndex: 1,
            }}
          >
            <HardDrive size={22} color="white" />
          </motion.div>
          <div className="pulse-ring" style={{ borderRadius: 14 }} />
        </div>
        <div>
          <motion.h1
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15, duration: 0.4 }}
            style={{
              fontSize: 26, fontWeight: 800,
              background: 'var(--accent-gradient-vivid)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              lineHeight: 1.1,
            }}
          >
            C盘守护者
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.25 }}
            style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}
          >
            C Drive Guardian — 让你的C盘重获新生
          </motion.p>
        </div>
      </motion.div>

      {/* Drive Overview Card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        style={{
          background: 'var(--glass)',
          border: '1px solid var(--glass-border-glow)',
          borderRadius: 'var(--radius-xl)',
          backdropFilter: 'blur(24px)',
          padding: '32px',
          display: 'flex',
          alignItems: 'center',
          gap: 48,
          boxShadow: '0 2px 32px rgba(0,212,255,0.05), inset 0 1px 0 rgba(255,255,255,0.06)',
        }}
      >
        {/* Ring */}
        <DriveRing usedPercent={driveInfo ? usedPercent : 0} size={160} />

        {/* Stats */}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
            {stats.map(({ label, value, color }, i) => (
              <motion.div
                key={label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + i * 0.07, duration: 0.4 }}
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '16px 20px',
                }}
              >
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {label}
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>
                  {driveInfo
                    ? <CountUpValue target={value} format={formatBytes} />
                    : '—'
                  }
                </div>
              </motion.div>
            ))}
          </div>

          {/* Drive path + animated usage bar */}
          <div style={{ marginTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>C:\</span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
                {driveInfo
                  ? <CountUpValue target={usedPercent} format={(n) => `${n}% 已满`} />
                  : '—'
                }
              </span>
            </div>
            <div style={{
              height: 6, borderRadius: 3,
              background: 'rgba(255,255,255,0.06)',
              overflow: 'hidden',
            }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${usedPercent}%` }}
                transition={{ duration: 1.4, delay: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
                style={{
                  height: '100%',
                  background: usedPercent > 85
                    ? 'linear-gradient(90deg, #ff9800, #ff1744)'
                    : usedPercent > 60
                    ? 'linear-gradient(90deg, #ffd600, #ff9800)'
                    : 'var(--accent-gradient)',
                  borderRadius: 3,
                }}
              />
            </div>
          </div>
        </div>
      </motion.div>

      {/* Scan Config + Start */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2 }}
        style={{
          background: 'var(--glass)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius-xl)',
          backdropFilter: 'blur(24px)',
          padding: '28px 32px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
          <Zap size={16} color="var(--accent-cyan)" />
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>扫描设置</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 24 }}>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              扫描路径
            </label>
            <input
              value={scanConfig.root}
              onChange={(e) => onConfigChange({ ...scanConfig, root: e.target.value })}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              最小大小 (MB)
            </label>
            <input
              type="number"
              value={scanConfig.min_size_mb}
              onChange={(e) => onConfigChange({ ...scanConfig, min_size_mb: Number(e.target.value) })}
              style={inputStyle}
              min={1}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              扫描深度
            </label>
            <input
              type="number"
              value={scanConfig.max_depth}
              onChange={(e) => onConfigChange({ ...scanConfig, max_depth: Number(e.target.value) })}
              style={inputStyle}
              min={1}
              max={6}
            />
          </div>
        </div>

        <motion.button
          onClick={() => onStartScan(scanConfig)}
          disabled={scanning}
          className={scanning ? undefined : 'btn-scan-idle'}
          whileHover={scanning ? {} : { scale: 1.02, boxShadow: '0 0 40px rgba(0,212,255,0.55)' }}
          whileTap={scanning ? {} : { scale: 0.97 }}
          style={{
            width: '100%',
            padding: '15px',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            background: scanning ? 'rgba(255,255,255,0.06)' : 'var(--accent-gradient)',
            color: scanning ? 'var(--text-muted)' : 'white',
            fontSize: 15,
            fontWeight: 700,
            cursor: scanning ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            letterSpacing: '0.02em',
          }}
        >
          {scanning ? (
            <>
              <ScanningDots />
              正在扫描中...
            </>
          ) : (
            <>
              <Search size={16} />
              开始扫描
            </>
          )}
        </motion.button>
      </motion.div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'Inter, sans-serif',
  transition: 'border-color 0.15s',
};

function ScanningDots() {
  return (
    <span style={{ display: 'flex', gap: 3 }}>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--accent-cyan)', display: 'inline-block' }}
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </span>
  );
}
