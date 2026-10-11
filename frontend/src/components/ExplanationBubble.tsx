import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { explainItem, openInExplorer } from '../api';
import { EvidenceDetails, ExplanationResult, SearchTrace } from './ExplanationResult';
import { ClassificationBadge } from './ClassificationBadge';
import type { SearchStep, AppSettings, EvidencePacket, ExplainResponse, ScanItem } from '../types';

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
  const [steps, setSteps] = useState<SearchStep[]>([]);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [online, setOnline] = useState(false);
  const [editedQuery, setEditedQuery] = useState<string | null>(null);
  const searchQuery = editedQuery ?? preview?.query ?? `${item?.name ?? ''} 文件用途 删除影响`;
  const request = useRef(0);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!item) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const nodes = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href], summary') ?? []).filter(node => node.getClientRects().length > 0);
        if (!nodes?.length) { event.preventDefault(); return; }
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [item, onClose]);

  useEffect(() => () => { request.current += 1; }, [item?.path]);

  const analyze = async (allowSearch: boolean, followup = false) => {
    if (!item || !preview || working) return;
    const id = ++request.current;
    setWorking(true); setFailure(null); setSteps([]); setResult(null);
    const local = settings.modelSource === 'local';
    try {
      const response = await explainItem(item.path, preview.fingerprint, allowSearch,
        local ? '' : settings.useEnvKey ? '' : settings.apiKey,
        local ? '' : settings.baseUrl, local ? '' : settings.model, local,
        followup ? question : null, allowSearch ? searchQuery.trim() : null, step => {
          if (id === request.current) setSteps(previous => [...previous.filter(s => s.round !== step.round), step]);
        });
      if (id !== request.current) return;
      setResult(response); setOnline(allowSearch); setQuestion('');
    } catch (e) {
      if (id === request.current) { setFailure(String(e)); setResult(null); }
    } finally { if (id === request.current) setWorking(false); }
  };

  if (!item) return null;
  return <div style={{ position: 'fixed', inset: 0, zIndex: 201, background: 'rgba(0,0,0,.65)', display: 'grid', placeItems: 'center' }} onClick={onClose}>
    <div className="explanation-panel" ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="explanation-title" onClick={e => e.stopPropagation()}
      style={{ width: 600, maxWidth: 'calc(100vw - 48px)', maxHeight: 'calc(100vh - 64px)', overflowY: 'auto', background: '#121228', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 18, padding: 24, lineHeight: 1.7, fontSize: 13 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 12 }}>
        <div style={{ minWidth: 0 }}><h2 id="explanation-title" style={{ fontSize: 18, margin: 0, overflowWrap: 'anywhere' }}>{item.name}</h2>
          <div>{preview?.size_human ?? item.size_human} · 文件释义</div></div>
        <button className="explanation-close" aria-label="关闭文件释义" onClick={onClose}><X size={18} /></button>
      </header>
      <p style={{ overflowWrap: 'anywhere', color: 'var(--text-muted)' }}>{item.path}</p>
      <p style={{ color: 'var(--text-secondary)', fontSize: 12 }}>用途分类：<ClassificationBadge classification={item.classification} size="sm" /> · 分类不代表可以删除</p>
      {loading && <p role="status">正在检查本机线索，尚未联网…</p>}
      {(error || failure) && <p role="alert" style={{ color: '#ffaaaa' }}>{error || failure}</p>}
      {preview && <>
        {result && <ExplanationResult result={result} />}
        <details open={!result} style={{ marginTop: 14 }}>
        <summary>{result ? '重新分析 / 修改搜索词' : '搜索与分析'}</summary>
        <p>专属多轮检索 · DDGS</p>
        <label htmlFor="file-search-query">初始搜索线索（每行一条，最多两条，可修改）</label>
        <textarea id="file-search-query" rows={3} value={searchQuery} maxLength={300} disabled={working} onChange={e => setEditedQuery(e.target.value)} style={{ display: 'block', width: '100%', margin: '8px 0' }} />
        <p>模型会据此生成查询并根据结果补搜。初始线索请勿包含私人信息；实际查询显示在检索过程里。</p>
        {settings.modelSource === 'api' && <p>当前使用云端模型：生成时会向所配置的模型服务发送完整路径、已列出的本机线索及问题。</p>}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button className="explanation-primary" disabled={working} onClick={() => analyze(false)}>用本机线索生成解释</button>
          <button disabled={working || !searchQuery.trim()} onClick={() => analyze(true)}>使用上述查询联网分析</button>
          <button onClick={() => openInExplorer(item.path).catch(e => setFailure(String(e)))}>打开所在位置</button>
        </div>
        </details>
        {steps.length > 0 && !result && <SearchTrace steps={steps} />}
        {working && <p role="status">正在整理建议…</p>}
        {!result && <EvidenceDetails packet={preview} />}
        {result && <form onSubmit={e => { e.preventDefault(); if (question.trim()) analyze(online, true); }} style={{ marginTop: 18 }}>
          <label htmlFor="file-question">继续问这个文件</label>
          <input placeholder="例如：删除后会影响哪个软件？" id="file-question" value={question} maxLength={1000} disabled={working} onChange={e => setQuestion(e.target.value)} style={{ display: 'block', width: '100%', margin: '8px 0' }} />
          <button className="explanation-primary" disabled={working || !question.trim()}>更新解释</button>
        </form>}
      </>}
      <footer style={{ marginTop: 20, color: 'var(--text-muted)' }}>这里只提供建议，不会改动文件。</footer>
    </div>
  </div>;
}
