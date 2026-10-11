import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { explainItem, openInExplorer } from '../api';
import { EvidenceDetails, ExplanationResult } from './ExplanationResult';
import type { AppSettings, EvidencePacket, ExplainResponse, ScanItem } from '../types';

interface Props {
  item: ScanItem | null;
  preview: EvidencePacket | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  settings: AppSettings;
}

export function ExplanationBubble({ item, preview, loading, error, onClose, settings }: Props) {
  const [result, setResult] = useState<ExplainResponse | null>(null);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [online, setOnline] = useState(false);
  const request = useRef(0);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!item) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const nodes = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), a[href], summary');
        if (!nodes?.length) { event.preventDefault(); return; }
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => { request.current += 1; document.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [item, onClose]);

  const analyze = async (allowSearch: boolean, followup = false) => {
    if (!item || !preview || working) return;
    const id = ++request.current;
    setWorking(true); setFailure(null);
    const local = settings.modelSource === 'local';
    try {
      const response = await explainItem(item.path, preview.fingerprint, allowSearch,
        local ? '' : settings.useEnvKey ? '' : settings.apiKey,
        local ? '' : settings.baseUrl, local ? '' : settings.model, local,
        allowSearch ? settings.tavilyKey : '', followup ? question : null);
      if (id !== request.current) return;
      setResult(response); setOnline(allowSearch); setQuestion('');
    } catch (e) {
      if (id === request.current) { setFailure(String(e)); setResult(null); }
    } finally { if (id === request.current) setWorking(false); }
  };

  if (!item) return null;
  return <div style={{ position: 'fixed', inset: 0, zIndex: 201, background: 'rgba(0,0,0,.65)', display: 'grid', placeItems: 'center' }} onClick={onClose}>
    <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="explanation-title" onClick={e => e.stopPropagation()}
      style={{ width: 600, maxWidth: 'calc(100vw - 48px)', maxHeight: 'calc(100vh - 64px)', overflowY: 'auto', background: '#121228', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 18, padding: 24, lineHeight: 1.7, fontSize: 13 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 12 }}>
        <div style={{ minWidth: 0 }}><h2 id="explanation-title" style={{ fontSize: 18, margin: 0, overflowWrap: 'anywhere' }}>{item.name}</h2>
          <div>{preview?.size_human ?? item.size_human} · 文件释义</div></div>
        <button aria-label="关闭文件释义" onClick={onClose}><X size={18} /></button>
      </header>
      <p style={{ overflowWrap: 'anywhere', color: 'var(--text-muted)' }}>{item.path}</p>
      {loading && <p role="status">正在检查本机线索，尚未联网…</p>}
      {(error || failure) && <p role="alert" style={{ color: '#ffaaaa' }}>{error || failure}</p>}
      {preview && <>
        <p>仅检查文件与附近配置，尚未确认使用状态、备份或可恢复性。</p>
        <p>拟发送的搜索词：<strong>{preview.query ?? '没有不含私人信息的查询词；仅支持本机分析'}</strong></p>
        {settings.modelSource === 'api' && <p>当前使用云端模型：生成时会向所配置的模型服务发送完整路径、已列出的本机线索及问题。</p>}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button disabled={working} onClick={() => analyze(false)}>用本机线索生成解释</button>
          <button disabled={working || !preview.query || !settings.tavilyKey} onClick={() => analyze(true)}>使用上述查询联网分析</button>
          <button onClick={() => openInExplorer(item.path).catch(e => setFailure(String(e)))}>打开所在位置</button>
        </div>
        {!settings.tavilyKey && <p>未配置搜索API Key，联网分析未启用。</p>}
        {working && <p role="status">正在整理证据并生成解释；关闭窗口可忽略本次结果。</p>}
        {result ? <ExplanationResult result={result} /> : <EvidenceDetails packet={preview} />}
        {result && <form onSubmit={e => { e.preventDefault(); if (question.trim()) analyze(online, true); }} style={{ marginTop: 18 }}>
          <label htmlFor="file-question">针对当前文件继续提问（会重新核对证据，更新四项说明）</label>
          <input id="file-question" value={question} maxLength={1000} disabled={working} onChange={e => setQuestion(e.target.value)} style={{ display: 'block', width: '100%', margin: '8px 0' }} />
          <button disabled={working || !question.trim()}>更新解释</button>
        </form>}
      </>}
      <footer style={{ marginTop: 20, color: 'var(--text-muted)' }}>解释不等于删除授权。本面板只读，不执行删除、迁移或命令。</footer>
    </div>
  </div>;
}
