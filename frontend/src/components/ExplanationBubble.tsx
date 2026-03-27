import { motion, AnimatePresence } from 'framer-motion';
import { useEffect, useState, useRef } from 'react';
import { X, Send } from 'lucide-react';
import { SafetyBadge } from './SafetyBadge';
import { chatAboutFile } from '../api';
import type { ExplainResponse, ScanItem, AppSettings } from '../types';

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
}

interface Props {
  item: ScanItem | null;
  explanation: ExplainResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  settings: AppSettings;
}

export function ExplanationBubble({ item, explanation, loading, error, onClose, settings }: Props) {
  const visible = item !== null;
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [dragPos, setDragPos] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });

  // Reset chat and position when item changes
  useEffect(() => {
    setChatHistory([]);
    setInputValue('');
    setDragPos({ x: 0, y: 0 });
  }, [item?.path]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, explanation]);

  const handleSend = async () => {
    if (!inputValue.trim() || !item || chatLoading) return;
    const msg = inputValue.trim();
    setInputValue('');

    const history: ChatMsg[] = [];
    if (explanation) {
      history.push({ role: 'assistant', content: explanation.explanation });
    }
    history.push(...chatHistory);

    setChatHistory(prev => [...prev, { role: 'user', content: msg }]);
    setChatLoading(true);

    try {
      const isLocal = settings.modelSource === 'local';

      const reply = await chatAboutFile(
        item.path, item.size, item.is_dir,
        history.map(m => ({ role: m.role, content: m.content })),
        msg,
        isLocal ? '' : (settings.useEnvKey ? '' : settings.apiKey),
        isLocal ? '' : settings.baseUrl,
        isLocal ? '' : settings.model,
        isLocal,
        isLocal ? (settings.tavilyKey || '') : '',
      );
      setChatHistory(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'assistant', content: `错误: ${e}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {visible && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.55)',
              backdropFilter: 'blur(6px)',
              zIndex: 200,
            }}
          />

          {/* Main bubble */}
          <motion.div
            key={item?.path}
            initial={{ opacity: 0, scale: 0.6, y: 50 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.75, y: 30 }}
            transition={{ type: 'spring', stiffness: 350, damping: 25, mass: 0.8 }}
            style={{
              position: 'fixed',
              top: `calc(50% + ${dragPos.y}px)`,
              left: `calc(50% + ${dragPos.x}px)`,
              transform: 'translate(-50%, -50%)',
              width: 460, maxWidth: 'calc(100vw - 60px)',
              maxHeight: 'calc(100vh - 80px)',
              background: 'linear-gradient(145deg, rgba(10,10,30,0.97), rgba(18,18,40,0.97))',
              border: '1px solid rgba(0,212,255,0.15)',
              borderRadius: 22,
              display: 'flex', flexDirection: 'column',
              zIndex: 201,
              overflow: 'hidden',
              boxShadow: '0 30px 90px rgba(0,0,0,0.6), 0 0 80px rgba(0,212,255,0.05)',
            }}
          >
            {/* Gradient top strip */}
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ delay: 0.1, duration: 0.6, ease: 'easeOut' }}
              style={{
                height: 3, transformOrigin: 'left',
                background: 'linear-gradient(90deg, #00d4ff, #7c3aed, #f43f5e)',
              }}
            />

            {/* Header — draggable */}
            <div
              onPointerDown={(e) => {
                setDragging(true);
                dragStart.current = { x: e.clientX - dragPos.x, y: e.clientY - dragPos.y };
                (e.target as HTMLElement).setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => {
                if (!dragging) return;
                setDragPos({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y });
              }}
              onPointerUp={() => setDragging(false)}
              style={{
                padding: '18px 22px 14px',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                cursor: dragging ? 'grabbing' : 'grab',
                userSelect: 'none',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontSize: 15, fontWeight: 700, color: 'var(--text-primary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {item?.name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 6 }}>
                  <span style={{ fontSize: 18, fontWeight: 800, color: 'var(--accent-cyan)', fontVariantNumeric: 'tabular-nums' }}>
                    {item?.size_human}
                  </span>
                  <SafetyBadge safety={item?.safety ?? 'yellow'} size="sm" />
                </div>
              </div>
              <motion.button
                onClick={onClose}
                whileHover={{ scale: 1.15, rotate: 90 }}
                whileTap={{ scale: 0.85 }}
                transition={{ type: 'spring', stiffness: 400, damping: 15 }}
                style={{
                  background: 'rgba(255,255,255,0.06)', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', width: 32, height: 32, borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}
              >
                <X size={15} />
              </motion.button>
            </div>

            {/* Path */}
            <div style={{
              padding: '0 22px', marginTop: 10, marginBottom: 6,
            }}>
              <div style={{
                fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace',
                padding: '6px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: 6,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {item?.path}
              </div>
            </div>

            {/* Scrollable content — analysis + chat */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '14px 22px 10px' }}>
              {/* Analysis */}
              {loading && <LoadingDots />}
              {error && !loading && <ErrorBlock error={error} />}
              {explanation && !loading && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35 }}
                  style={{
                    fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.9,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {explanation.explanation}
                </motion.div>
              )}

              {/* Chat history */}
              {chatHistory.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  style={{
                    marginTop: 12,
                    padding: '10px 14px',
                    borderRadius: 12,
                    fontSize: 13,
                    lineHeight: 1.7,
                    whiteSpace: 'pre-wrap',
                    ...(msg.role === 'user'
                      ? {
                          background: 'rgba(0,212,255,0.1)',
                          border: '1px solid rgba(0,212,255,0.15)',
                          color: 'var(--accent-cyan)',
                          marginLeft: 40,
                        }
                      : {
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.06)',
                          color: 'var(--text-primary)',
                          marginRight: 40,
                        }),
                  }}
                >
                  {msg.content}
                </motion.div>
              ))}

              {chatLoading && (
                <div style={{ marginTop: 12 }}>
                  <LoadingDots />
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Chat input */}
            {explanation && !loading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                style={{
                  padding: '12px 16px',
                  borderTop: '1px solid rgba(255,255,255,0.06)',
                  display: 'flex', gap: 8, alignItems: 'center',
                }}
              >
                <input
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  placeholder="继续追问..."
                  style={{
                    flex: 1, padding: '10px 14px', borderRadius: 10,
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    color: 'var(--text-primary)', fontSize: 13,
                    outline: 'none', fontFamily: 'Inter, sans-serif',
                  }}
                />
                <motion.button
                  onClick={handleSend}
                  whileHover={{ scale: 1.08 }}
                  whileTap={{ scale: 0.92 }}
                  disabled={chatLoading || !inputValue.trim()}
                  style={{
                    width: 38, height: 38, borderRadius: 10, border: 'none',
                    background: inputValue.trim() ? 'var(--accent-gradient)' : 'rgba(255,255,255,0.06)',
                    color: inputValue.trim() ? 'white' : 'var(--text-muted)',
                    cursor: inputValue.trim() ? 'pointer' : 'default',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Send size={15} />
                </motion.button>
              </motion.div>
            )}

            {/* Footer */}
            <div style={{
              padding: '8px 22px 10px', fontSize: 10,
              color: 'var(--text-muted)', textAlign: 'center',
              borderTop: explanation ? 'none' : '1px solid rgba(255,255,255,0.05)',
            }}>
              AI建议仅供参考 · 本工具不会执行任何删除操作
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function LoadingDots() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <motion.div
        style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid transparent', borderTopColor: 'var(--accent-cyan)' }}
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      />
      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>正在分析...</span>
    </div>
  );
}

function ErrorBlock({ error }: { error: string }) {
  const isNoKey = error === 'no api key' || error.includes('401') || error.includes('403');
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      style={{
        background: 'rgba(255,68,68,0.08)',
        border: '1px solid rgba(255,68,68,0.2)',
        borderRadius: 12, padding: '14px',
        fontSize: 13, color: 'rgba(255,140,140,0.9)', lineHeight: 1.6,
      }}
    >
      {isNoKey ? (
        <><strong>需要 API Key</strong><br />请在左侧设置中填入 API Key</>
      ) : (
        <><strong>分析失败</strong><br />{error}</>
      )}
    </motion.div>
  );
}
