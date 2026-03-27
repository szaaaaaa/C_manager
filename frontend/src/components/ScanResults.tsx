import { motion } from 'framer-motion';
import { useState, useMemo } from 'react';
import {
  Folder, File, FileText, Image, Archive, Video, Music,
  AlertTriangle, Square, FolderOpen, Check, ClipboardCopy, Minus, Trash2, Loader2,
} from 'lucide-react';
import { SafetyBadge } from './SafetyBadge';
import { openInExplorer, deleteToRecycleBin } from '../api';
import type { ScanItem, ScanProgress, FileCategory } from '../types';

// ── Extension → Category mapping ──

const EXT_MAP: Record<string, FileCategory> = {};
const addExts = (cat: FileCategory, exts: string[]) => exts.forEach(e => { EXT_MAP[e] = cat; });
addExts('文档', ['doc','docx','pdf','xls','xlsx','ppt','pptx','txt','csv','md','rtf','odt']);
addExts('图片', ['jpg','jpeg','png','gif','bmp','svg','webp','ico','tiff','tif','psd','raw']);
addExts('压缩包', ['zip','rar','7z','tar','gz','bz2','xz','zst','cab','iso','wim']);
addExts('视频', ['mp4','avi','mkv','mov','wmv','flv','webm','m4v','ts','vob']);
addExts('音频', ['mp3','wav','flac','aac','ogg','wma','m4a','opus']);

function getCategory(item: ScanItem): FileCategory {
  if (item.is_dir) return '其他';
  const ext = item.name.split('.').pop()?.toLowerCase() ?? '';
  return EXT_MAP[ext] ?? '其他';
}

function getCategoryIcon(cat: FileCategory) {
  switch (cat) {
    case '文档': return <FileText size={14} />;
    case '图片': return <Image size={14} />;
    case '压缩包': return <Archive size={14} />;
    case '视频': return <Video size={14} />;
    case '音频': return <Music size={14} />;
    default: return <File size={14} />;
  }
}

function getFileIcon(item: ScanItem) {
  if (item.is_dir) return <Folder size={14} color="var(--accent-cyan)" />;
  return getCategoryIcon(getCategory(item));
}

function formatTotalSize(bytes: number): string {
  if (bytes >= 1024 ** 4) return (bytes / 1024 ** 4).toFixed(1) + ' TB';
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(1) + ' GB';
  if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + ' MB';
  return (bytes / 1024).toFixed(1) + ' KB';
}

// ── Categories ──

const CATEGORIES: FileCategory[] = ['全部', '文档', '图片', '压缩包', '视频', '音频', '其他'];

// ── Props ──

interface Props {
  items: ScanItem[];
  progress: ScanProgress | null;
  onItemClick: (item: ScanItem) => void;
  selectedPath: string | null;
  onStopScan?: () => void;
  onItemsDeleted?: (deletedPaths: string[]) => void;
}

export function ScanResults({ items, progress, onItemClick, selectedPath, onStopScan, onItemsDeleted }: Props) {
  const [checkedPaths, setCheckedPaths] = useState<Set<string>>(new Set());
  const [activeCategory, setActiveCategory] = useState<FileCategory>('全部');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteResult, setDeleteResult] = useState<{ succeeded: number; failed: number } | null>(null);

  // Category counts
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { '全部': items.length };
    for (const item of items) {
      const cat = getCategory(item);
      counts[cat] = (counts[cat] ?? 0) + 1;
    }
    return counts;
  }, [items]);

  // Filtered items
  const filteredItems = useMemo(
    () => activeCategory === '全部' ? items : items.filter(i => getCategory(i) === activeCategory),
    [items, activeCategory],
  );

  // Selection helpers
  const allFilteredChecked = filteredItems.length > 0 && filteredItems.every(i => checkedPaths.has(i.path));
  const someFilteredChecked = filteredItems.some(i => checkedPaths.has(i.path));

  const toggleCheck = (path: string) => {
    setCheckedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const toggleAll = () => {
    if (allFilteredChecked) {
      setCheckedPaths(prev => {
        const next = new Set(prev);
        filteredItems.forEach(i => next.delete(i.path));
        return next;
      });
    } else {
      setCheckedPaths(prev => {
        const next = new Set(prev);
        filteredItems.forEach(i => next.add(i.path));
        return next;
      });
    }
  };

  // Checked items stats
  const checkedItems = items.filter(i => checkedPaths.has(i.path));
  const checkedTotalSize = checkedItems.reduce((s, i) => s + i.size, 0);

  const handleOpenSelected = () => {
    checkedItems.forEach(item => openInExplorer(item.path));
  };

  const handleCopyPaths = () => {
    const text = checkedItems
      .map(i => `${i.path}  (${i.size_human})`)
      .join('\n');
    navigator.clipboard.writeText(text);
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteResult(null);
    try {
      const result = await deleteToRecycleBin(checkedItems.map(i => i.path));
      setDeleteResult({ succeeded: result.succeeded.length, failed: result.failed.length });
      if (result.succeeded.length > 0) {
        // Remove deleted items from checked set
        setCheckedPaths(prev => {
          const next = new Set(prev);
          result.succeeded.forEach(p => next.delete(p));
          return next;
        });
        // Notify parent to remove from items list
        onItemsDeleted?.(result.succeeded);
      }
      // Auto-close confirm dialog after short delay
      setTimeout(() => {
        setShowDeleteConfirm(false);
        setDeleteResult(null);
      }, 2000);
    } catch (e) {
      setDeleteResult({ succeeded: 0, failed: checkedItems.length });
    } finally {
      setDeleting(false);
    }
  };

  const maxSize = items[0]?.size ?? 1;

  // ── Empty state ──
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
      {/* ── Summary header ── */}
      <div style={{ padding: '20px 32px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            {checkedPaths.size > 0 ? (
              <>
                <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  已勾选 {checkedPaths.size} 个大文件，共{' '}
                  <span style={{ color: 'var(--accent-cyan)' }}>{formatTotalSize(checkedTotalSize)}</span>
                </h2>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  请继续勾选需要清理的文件
                </p>
              </>
            ) : (
              <>
                <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  {progress?.running ? '正在扫描...' : '扫描结果'}
                </h2>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
                  {progress?.running
                    ? `已扫描 ${(progress.progress || 0).toLocaleString()} 条记录 · 找到 ${items.length} 个大文件`
                    : `找到 ${items.length} 个大文件 · 勾选后可批量操作`
                  }
                </p>
              </>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {progress?.running && (
              <>
                <motion.div
                  style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent-cyan)' }}
                  animate={{ opacity: [0.4, 1, 0.4], scale: [0.9, 1.1, 0.9] }}
                  transition={{ duration: 1.2, repeat: Infinity }}
                />
                {onStopScan && (
                  <motion.button
                    onClick={onStopScan}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5,
                      padding: '5px 12px', borderRadius: 6,
                      background: 'rgba(255,68,68,0.12)',
                      border: '1px solid rgba(255,68,68,0.3)',
                      color: '#ff8888', fontSize: 11, fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <Square size={10} fill="currentColor" />
                    停止
                  </motion.button>
                )}
              </>
            )}

            {checkedPaths.size > 0 && !progress?.running && (
              <>
                <motion.button
                  onClick={handleCopyPaths}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '8px 14px', borderRadius: 8,
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-secondary)', fontSize: 12, fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  <ClipboardCopy size={13} />
                  复制路径
                </motion.button>
                <motion.button
                  onClick={handleOpenSelected}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '8px 16px', borderRadius: 8,
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-secondary)', fontSize: 12, fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  <FolderOpen size={14} />
                  打开位置
                </motion.button>
                <motion.button
                  onClick={() => setShowDeleteConfirm(true)}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '8px 16px', borderRadius: 8,
                    background: 'rgba(255,68,68,0.15)',
                    border: '1px solid rgba(255,68,68,0.3)',
                    color: '#ff8888', fontSize: 12, fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <Trash2 size={14} />
                  移到回收站
                </motion.button>
              </>
            )}
          </div>
        </div>

        {/* ── Category tabs ── */}
        <div style={{
          display: 'flex', gap: 4, marginTop: 16, paddingBottom: 12,
          borderBottom: '1px solid var(--border)',
        }}>
          {CATEGORIES.map(cat => {
            const count = categoryCounts[cat] ?? 0;
            const isActive = activeCategory === cat;
            if (cat !== '全部' && count === 0) return null;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                style={{
                  padding: '6px 14px', borderRadius: 6,
                  background: isActive ? 'rgba(0,212,255,0.1)' : 'transparent',
                  border: isActive ? '1px solid rgba(0,212,255,0.3)' : '1px solid transparent',
                  color: isActive ? 'var(--accent-cyan)' : 'var(--text-muted)',
                  fontSize: 13, fontWeight: isActive ? 600 : 400,
                  cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 5,
                  transition: 'all 0.15s',
                }}
              >
                {cat}
                {count > 0 && (
                  <span style={{
                    fontSize: 10, fontWeight: 600,
                    padding: '1px 6px', borderRadius: 10,
                    background: isActive ? 'rgba(0,212,255,0.2)' : 'rgba(255,255,255,0.06)',
                    color: isActive ? 'var(--accent-cyan)' : 'var(--text-muted)',
                  }}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Column headers ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '36px 36px 1fr 60px 100px 90px 36px',
        gap: 8,
        padding: '10px 32px',
        borderBottom: '1px solid var(--border)',
        fontSize: 11,
        color: 'var(--text-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        alignItems: 'center',
      }}>
        <span
          onClick={toggleAll}
          style={{ cursor: 'pointer', display: 'flex', justifyContent: 'center' }}
        >
          <Checkbox checked={allFilteredChecked} indeterminate={someFilteredChecked && !allFilteredChecked} />
        </span>
        <span />
        <span>名称 / 路径</span>
        <span style={{ textAlign: 'center' }}>磁盘</span>
        <span style={{ textAlign: 'right' }}>大小</span>
        <span style={{ textAlign: 'center' }}>安全</span>
        <span />
      </div>

      {/* ── List ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {filteredItems.map((item, i) => (
          <ResultRow
            key={item.path}
            item={item}
            index={i}
            maxSize={maxSize}
            isSelected={item.path === selectedPath}
            isChecked={checkedPaths.has(item.path)}
            onCheck={() => toggleCheck(item.path)}
            onClick={() => onItemClick(item)}
            onOpenExplorer={() => openInExplorer(item.path)}
            animate={i < 20}
          />
        ))}
      </div>

      {/* ── Delete confirmation dialog ── */}
      {showDeleteConfirm && (
        <>
          <div
            onClick={() => !deleting && setShowDeleteConfirm(false)}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
              zIndex: 300,
            }}
          />
          <div style={{
            position: 'fixed', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            width: 480, maxWidth: 'calc(100vw - 40px)',
            maxHeight: 'calc(100vh - 80px)',
            background: 'rgba(12,12,28,0.97)',
            border: '1px solid rgba(255,68,68,0.2)',
            borderRadius: 16, zIndex: 301,
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          }}>
            {/* Header */}
            <div style={{
              padding: '18px 22px 14px',
              borderBottom: '1px solid rgba(255,255,255,0.06)',
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <Trash2 size={18} color="#ff8888" />
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
                确认移到回收站
              </span>
            </div>

            {/* File list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 22px', maxHeight: 300 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                以下 {checkedItems.length} 个文件将被移到回收站（可恢复），共 {formatTotalSize(checkedTotalSize)}：
              </div>
              {checkedItems.map(item => (
                <div key={item.path} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  fontSize: 12,
                }}>
                  <span style={{
                    color: 'var(--text-secondary)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    flex: 1, minWidth: 0,
                  }}>
                    {item.name}
                  </span>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 12, flexShrink: 0 }}>
                    {item.size_human}
                  </span>
                </div>
              ))}
            </div>

            {/* Result message */}
            {deleteResult && (
              <div style={{
                padding: '10px 22px',
                fontSize: 12,
                color: deleteResult.failed > 0 ? '#ff8888' : '#00c864',
                background: deleteResult.failed > 0 ? 'rgba(255,68,68,0.08)' : 'rgba(0,200,100,0.08)',
              }}>
                {deleteResult.succeeded > 0 && `${deleteResult.succeeded} 个文件已移到回收站`}
                {deleteResult.failed > 0 && `  ${deleteResult.failed} 个失败`}
              </div>
            )}

            {/* Actions */}
            <div style={{
              padding: '14px 22px',
              borderTop: '1px solid rgba(255,255,255,0.06)',
              display: 'flex', gap: 10, justifyContent: 'flex-end',
            }}>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
                style={{
                  padding: '9px 18px', borderRadius: 8,
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  color: 'var(--text-muted)', fontSize: 13, fontWeight: 500,
                  cursor: deleting ? 'not-allowed' : 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting || deleteResult !== null}
                style={{
                  padding: '9px 18px', borderRadius: 8,
                  border: 'none',
                  background: deleting ? 'rgba(255,68,68,0.1)' : 'rgba(255,68,68,0.2)',
                  color: '#ff8888', fontSize: 13, fontWeight: 600,
                  cursor: deleting || deleteResult !== null ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                {deleting && <Loader2 size={14} className="animate-spin" />}
                {deleting ? '正在删除...' : '确认删除'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Checkbox ──

function Checkbox({ checked, indeterminate }: { checked: boolean; indeterminate?: boolean }) {
  return (
    <div style={{
      width: 18, height: 18, borderRadius: 4,
      border: checked || indeterminate ? '1.5px solid var(--accent-cyan)' : '1.5px solid rgba(255,255,255,0.2)',
      background: checked || indeterminate ? 'rgba(0,212,255,0.15)' : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'all 0.15s',
    }}>
      {checked && <Check size={12} color="var(--accent-cyan)" strokeWidth={3} />}
      {indeterminate && !checked && <Minus size={12} color="var(--accent-cyan)" strokeWidth={3} />}
    </div>
  );
}

// ── Row ──

interface RowProps {
  item: ScanItem;
  index: number;
  maxSize: number;
  isSelected: boolean;
  isChecked: boolean;
  onCheck: () => void;
  onClick: () => void;
  onOpenExplorer: () => void;
  animate: boolean;
}

function ResultRow({ item, index, maxSize, isSelected, isChecked, onCheck, onClick, onOpenExplorer, animate }: RowProps) {
  const barWidth = Math.max(3, (item.size / maxSize) * 100);
  const safetyColor = { red: 'var(--red)', yellow: 'var(--yellow)', green: 'var(--green)' }[item.safety];
  const drive = item.path.match(/^([A-Z]):/i)?.[1]?.toUpperCase() ?? '';

  const Wrapper = animate ? motion.div : 'div';
  const animProps = animate ? {
    initial: { opacity: 0, x: -16 },
    animate: { opacity: 1, x: 0 },
    transition: { duration: 0.25, delay: Math.min(index * 0.03, 0.5) },
  } : {};

  return (
    <Wrapper
      {...animProps}
      style={{
        display: 'grid',
        gridTemplateColumns: '36px 36px 1fr 60px 100px 90px 36px',
        gap: 8,
        padding: '10px 32px',
        cursor: 'pointer',
        alignItems: 'center',
        background: isSelected ? 'rgba(0,212,255,0.06)' : isChecked ? 'rgba(0,212,255,0.03)' : 'transparent',
        borderLeft: isSelected ? '2px solid var(--accent-cyan)' : '2px solid transparent',
        transition: 'background 0.15s, border-color 0.15s',
      }}
    >
      {/* Checkbox */}
      <div
        onClick={e => { e.stopPropagation(); onCheck(); }}
        style={{ display: 'flex', justifyContent: 'center', cursor: 'pointer' }}
      >
        <Checkbox checked={isChecked} />
      </div>

      {/* Icon */}
      <div
        onClick={onClick}
        style={{
          width: 28, height: 28, borderRadius: 8,
          background: item.is_dir ? 'rgba(0,212,255,0.12)' : 'rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        {getFileIcon(item)}
      </div>

      {/* Name + path bar */}
      <div onClick={onClick} style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: 500, color: 'var(--text-primary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          marginBottom: 3,
        }}>
          {item.name}
        </div>
        <div style={{ position: 'relative', height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${barWidth}%`,
              background: `linear-gradient(90deg, ${safetyColor}66, ${safetyColor})`,
              borderRadius: 2,
              transition: 'width 0.4s ease-out',
            }}
          />
        </div>
        <div style={{
          fontSize: 10, color: 'var(--text-muted)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          marginTop: 2,
        }}>
          {item.path}
        </div>
      </div>

      {/* Drive */}
      <div onClick={onClick} style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
        {drive} 盘
      </div>

      {/* Size */}
      <div onClick={onClick} style={{ textAlign: 'right' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
          {item.size_human}
        </span>
        {item.is_dir && item.children_count > 0 && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>
            {item.children_count.toLocaleString()} 个文件
          </div>
        )}
      </div>

      {/* Safety badge */}
      <div onClick={onClick} style={{ display: 'flex', justifyContent: 'center' }}>
        <SafetyBadge safety={item.safety} size="sm" />
      </div>

      {/* Open in explorer */}
      <button
        onClick={e => { e.stopPropagation(); onOpenExplorer(); }}
        title="在资源管理器中打开"
        style={{
          width: 28, height: 28, borderRadius: 6,
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.08)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', color: 'var(--text-muted)',
        }}
      >
        <FolderOpen size={13} />
      </button>
    </Wrapper>
  );
}
