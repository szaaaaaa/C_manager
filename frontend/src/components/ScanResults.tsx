import { motion, AnimatePresence } from 'framer-motion';
import { Folder, File, ChevronRight, AlertTriangle } from 'lucide-react';
import { SafetyBadge } from './SafetyBadge';
import type { ScanItem, ScanProgress } from '../types';

interface Props {
  items: ScanItem[];
  progress: ScanProgress | null;
  onItemClick: (item: ScanItem) => void;
  selectedPath: string | null;
}

export function ScanResults({ items, progress, onItemClick, selectedPath }: Props) {
  const maxSize = items[0]?.size ?? 1;

  if (progress?.running && items.length === 0) {
    return <ScanningPlaceholder progress={progress} />;
  }

  if (!progress?.running && items.length === 0) {
    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 12,
        color: 'var(--text-muted)', padding: 48,
      }}>
        <AlertTriangle size={40} style={{ opacity: 0.3 }} />
        <span style={{ fontSize: 15 }}>扫描完成，没有找到大文件</span>
        <span style={{ fontSize: 13 }}>尝试降低最小文件大小阈值</span>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '20px 32px 12px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
            扫描结果
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
            找到 {items.length} 个大文件 · 点击任意项目获取AI分析
          </p>
        </div>
        {progress?.running && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <motion.div
              style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent-cyan)' }}
              animate={{ opacity: [0.4, 1, 0.4], scale: [0.9, 1.1, 0.9] }}
              transition={{ duration: 1.2, repeat: Infinity }}
            />
            <span style={{ fontSize: 12, color: 'var(--accent-cyan)' }}>扫描中 ({progress.result_count})</span>
          </div>
        )}
      </div>

      {/* Column headers */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '40px 1fr 140px 110px 120px',
        gap: 12,
        padding: '10px 32px',
        borderBottom: '1px solid var(--border)',
        fontSize: 11,
        color: 'var(--text-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>
        <span />
        <span>名称 / 路径</span>
        <span style={{ textAlign: 'right' }}>大小</span>
        <span style={{ textAlign: 'center' }}>安全评级</span>
        <span />
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        <AnimatePresence initial={false}>
          {items.map((item, i) => (
            <ResultRow
              key={item.path}
              item={item}
              index={i}
              maxSize={maxSize}
              isSelected={item.path === selectedPath}
              onClick={() => onItemClick(item)}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

interface RowProps {
  item: ScanItem;
  index: number;
  maxSize: number;
  isSelected: boolean;
  onClick: () => void;
}

function ResultRow({ item, index, maxSize, isSelected, onClick }: RowProps) {
  const barWidth = Math.max(3, (item.size / maxSize) * 100);
  const safetyColor = { red: 'var(--red)', yellow: 'var(--yellow)', green: 'var(--green)' }[item.safety];

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.28, delay: Math.min(index * 0.04, 0.6) }}
      onClick={onClick}
      whileHover={isSelected ? {} : { backgroundColor: 'rgba(255,255,255,0.025)' }}
      style={{
        display: 'grid',
        gridTemplateColumns: '40px 1fr 140px 110px 120px',
        gap: 12,
        padding: '10px 32px',
        cursor: 'pointer',
        alignItems: 'center',
        background: isSelected ? 'rgba(0,212,255,0.06)' : 'transparent',
        borderLeft: isSelected ? '2px solid var(--accent-cyan)' : '2px solid transparent',
        transition: 'background 0.15s, border-color 0.15s',
      }}
    >
      {/* Icon */}
      <div style={{
        width: 28, height: 28, borderRadius: 8,
        background: item.is_dir
          ? 'rgba(0,212,255,0.12)'
          : 'rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {item.is_dir
          ? <Folder size={14} color="var(--accent-cyan)" />
          : <File size={14} color="var(--text-muted)" />
        }
      </div>

      {/* Name + path bar */}
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: 500, color: 'var(--text-primary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          marginBottom: 4,
        }}>
          {item.name}
        </div>
        <div style={{ position: 'relative', height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${barWidth}%` }}
            transition={{ duration: 0.7, delay: Math.min(index * 0.04, 0.6) + 0.1, ease: [0.34, 1.56, 0.64, 1] }}
            style={{
              height: '100%',
              background: `linear-gradient(90deg, ${safetyColor}66, ${safetyColor})`,
              borderRadius: 2,
            }}
          />
        </div>
        <div style={{
          fontSize: 11, color: 'var(--text-muted)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          marginTop: 3,
        }}>
          {item.path}
        </div>
      </div>

      {/* Size */}
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
          {item.size_human}
        </span>
        {item.is_dir && item.children_count > 0 && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
            {item.children_count.toLocaleString()} 个文件
          </div>
        )}
      </div>

      {/* Safety badge */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <SafetyBadge safety={item.safety} size="sm" />
      </div>

      {/* Arrow */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
        <motion.div
          animate={{ x: isSelected ? 2 : 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 20 }}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            fontSize: 11, color: 'var(--accent-cyan)', opacity: isSelected ? 1 : 0.4,
            transition: 'opacity 0.15s',
          }}
        >
          <span>AI分析</span>
          <ChevronRight size={12} />
        </motion.div>
      </div>
    </motion.div>
  );
}

function ScanningPlaceholder({ progress }: { progress: ScanProgress }) {
  // Interpolate a fake percentage that climbs asymptotically
  const fakePercent = Math.min(92, Math.round((progress.progress / Math.max(progress.progress + 500, 1000)) * 100));

  return (
    <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>正在扫描...</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
              {progress.progress.toLocaleString()} 个文件
            </span>
            <span style={{
              fontSize: 12, fontWeight: 700, color: 'var(--accent-cyan)',
              fontVariantNumeric: 'tabular-nums',
            }}>
              {fakePercent}%
            </span>
          </div>
        </div>
        <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
          <motion.div
            style={{ height: '100%', background: 'var(--accent-gradient)', borderRadius: 2 }}
            animate={{ width: ['0%', '40%', '70%', '85%', '92%'] }}
            transition={{ duration: 10, ease: 'easeOut', repeat: Infinity, repeatType: 'mirror' }}
          />
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {progress.current_path || '初始化...'}
        </div>
      </div>
      {/* Skeleton rows */}
      {Array.from({ length: 7 }).map((_, i) => (
        <div
          key={i}
          className="shimmer"
          style={{ height: 52, borderRadius: 'var(--radius-md)', opacity: 1 - i * 0.1 }}
        />
      ))}
    </div>
  );
}
