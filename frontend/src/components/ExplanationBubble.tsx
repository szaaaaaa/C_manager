import { motion, AnimatePresence } from 'framer-motion';
import { useEffect, useState, useRef } from 'react';
import { X, Sparkles, Bot } from 'lucide-react';
import { SafetyBadge } from './SafetyBadge';
import type { ExplainResponse, ScanItem } from '../types';

interface Props {
  item: ScanItem | null;
  explanation: ExplainResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

export function ExplanationBubble({ item, explanation, loading, error, onClose }: Props) {
  const visible = item !== null;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key={item?.path}
          initial={{ opacity: 0, x: 60, scale: 0.94 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: 60, scale: 0.94 }}
          transition={{ type: 'spring', stiffness: 340, damping: 28 }}
          style={{
            position: 'absolute',
            right: 0,
            top: 0,
            bottom: 0,
            width: 350,
            background: 'rgba(8, 8, 20, 0.88)',
            backdropFilter: 'blur(32px)',
            borderLeft: '1px solid rgba(0, 212, 255, 0.18)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 100,
            overflow: 'hidden',
            boxShadow: '-8px 0 48px rgba(0, 0, 0, 0.5), -1px 0 0 rgba(0, 212, 255, 0.1)',
          }}
        >
          {/* Top glow accent strip */}
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            height: 2,
            background: 'var(--accent-gradient-vivid)',
            opacity: 0.9,
          }} />

          {/* Left arrow pointer — visually connects bubble to the row */}
          <motion.div
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.18, duration: 0.3 }}
            style={{
              position: 'absolute',
              left: -9,
              top: '50%',
              transform: 'translateY(-50%)',
              width: 0,
              height: 0,
              borderTop: '9px solid transparent',
              borderBottom: '9px solid transparent',
              borderRight: '9px solid rgba(0, 212, 255, 0.25)',
              filter: 'drop-shadow(-2px 0 6px rgba(0,212,255,0.2))',
            }}
          />

          {/* Header */}
          <div style={{
            padding: '22px 20px 16px',
            borderBottom: '1px solid rgba(255,255,255,0.07)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
          }}>
            <motion.div
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', stiffness: 450, damping: 20, delay: 0.08 }}
              style={{
                width: 34, height: 34, borderRadius: 10,
                background: 'linear-gradient(135deg, rgba(0,212,255,0.2), rgba(0,102,255,0.2))',
                border: '1px solid rgba(0,212,255,0.35)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
                marginTop: 1,
                boxShadow: '0 0 16px rgba(0,212,255,0.15)',
              }}
            >
              <Bot size={16} color="var(--accent-cyan)" />
            </motion.div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.12, duration: 0.3 }}
                style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 3 }}
              >
                AI 文件解读
              </motion.div>
              <div style={{
                fontSize: 11, color: 'var(--text-muted)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {item?.name}
              </div>
            </div>
            <motion.button
              onClick={onClose}
              whileHover={{ scale: 1.15, color: 'var(--text-primary)' }}
              whileTap={{ scale: 0.9 }}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--text-muted)', padding: 4, borderRadius: 6,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <X size={16} />
            </motion.button>
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
            {/* File info card */}
            {item && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.14, duration: 0.35 }}
                style={{
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: 'var(--radius-md)',
                  padding: '14px',
                  marginBottom: 18,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>文件大小</span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-cyan)', fontVariantNumeric: 'tabular-nums' }}>
                    {item.size_human}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>安全评级</span>
                  <SafetyBadge safety={item.safety} size="sm" />
                </div>
                <div style={{
                  fontSize: 10, color: 'var(--text-muted)', marginTop: 4,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {item.path}
                </div>
              </motion.div>
            )}

            {/* Explanation content */}
            {loading && <LoadingSkeleton />}
            {error && !loading && <ErrorState error={error} />}
            {explanation && !loading && (
              <TypewriterText text={explanation.explanation} />
            )}

            {!loading && !error && !explanation && (
              <div style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                gap: 10, padding: '24px 0', color: 'var(--text-muted)',
              }}>
                <Sparkles size={24} style={{ opacity: 0.4 }} />
                <span style={{ fontSize: 13 }}>正在请求AI分析...</span>
              </div>
            )}
          </div>

          {/* Disclaimer */}
          <div style={{
            padding: '12px 20px',
            borderTop: '1px solid rgba(255,255,255,0.05)',
            fontSize: 10,
            color: 'var(--text-muted)',
            lineHeight: 1.5,
          }}>
            ⚠️ AI建议仅供参考。删除前请确认，本工具只提供建议，不会执行任何删除操作。
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function LoadingSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <motion.div
          style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--accent-gradient)' }}
          animate={{ rotate: 360 }}
          transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
        />
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>正在分析中...</span>
      </div>
      {[100, 85, 100, 60, 90].map((w, i) => (
        <motion.div
          key={i}
          className="shimmer"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1 - i * 0.07, x: 0 }}
          transition={{ delay: i * 0.06, duration: 0.3 }}
          style={{ height: 14, width: `${w}%`, borderRadius: 4 }}
        />
      ))}
    </div>
  );
}

function ErrorState({ error }: { error: string }) {
  const isNoKey = error.toLowerCase().includes('api') || error.toLowerCase().includes('401') || error.toLowerCase().includes('403') || error === 'no api key';
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      style={{
        background: 'rgba(255,68,68,0.08)',
        border: '1px solid rgba(255,68,68,0.2)',
        borderRadius: 'var(--radius-md)',
        padding: '16px',
        fontSize: 13,
        color: 'rgba(255,140,140,0.9)',
        lineHeight: 1.6,
      }}
    >
      {isNoKey ? (
        <>
          <strong>需要API Key</strong>
          <br />
          请在侧边栏设置中填入API Key（支持OpenRouter / OpenAI）才能使用AI分析功能。
        </>
      ) : (
        <>
          <strong>分析失败</strong>
          <br />
          {error}
        </>
      )}
    </motion.div>
  );
}

function TypewriterText({ text }: { text: string }) {
  const [displayed, setDisplayed] = useState('');
  const idx = useRef(0);

  useEffect(() => {
    idx.current = 0;
    setDisplayed('');
    const iv = setInterval(() => {
      idx.current += 1;
      setDisplayed(text.slice(0, idx.current));
      if (idx.current >= text.length) clearInterval(iv);
    }, 16);
    return () => clearInterval(iv);
  }, [text]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      style={{
        fontSize: 14,
        color: 'var(--text-primary)',
        lineHeight: 1.8,
        whiteSpace: 'pre-wrap',
      }}
    >
      {displayed}
      {displayed.length < text.length && (
        <motion.span
          style={{
            display: 'inline-block', width: 2, height: '1em',
            background: 'var(--accent-cyan)', marginLeft: 2,
            verticalAlign: 'text-bottom',
          }}
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.5, repeat: Infinity }}
        />
      )}
    </motion.div>
  );
}
