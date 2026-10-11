import type { ExplainResponse, EvidencePacket } from '../types';

export function EvidenceDetails({ packet }: { packet: EvidencePacket }) {
  return <details style={{ marginTop: 14 }}>
    <summary>查看依据与检查范围（{packet.evidence.length}项）</summary>
    <p>检查时间：{new Date(packet.checked_at * 1000).toLocaleString()}</p>
    {packet.evidence.map(source => <article key={source.id} style={{ marginTop: 12 }}>
      <strong>{source.id} · {source.title}</strong>
      <div>{source.kind === 'web_excerpt' ? '网络搜索片段，适用性待确认' : '本机观察，不等于使用或安全证明'}</div>
      <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{source.content}</p>
      {source.url && <a href={source.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-cyan)', overflowWrap: 'anywhere' }}>{source.url}</a>}
    </article>)}
    {packet.warnings.map((warning, i) => <p key={i}>{warning}</p>)}
  </details>;
}

const labels = { ownership: '它是谁的？', impact: '删了影响什么？', recovery: '能不能找回来？', advice: '怎么处理更合适？' } as const;
const statuses = { supported: '资料支持 · 尚非安全认证', uncertain: '有线索，待确认', unknown: '尚未确认' };

export function ExplanationResult({ result }: { result: ExplainResponse }) {
  return <div>
    <p role="status">{result.search_status}</p>
    {(Object.keys(labels) as (keyof typeof labels)[]).map(key => {
      const section = result.explanation[key];
      return <section key={key} style={{ marginTop: 18 }}>
        <h3 style={{ fontSize: 15, marginBottom: 4 }}>{labels[key]}</h3>
        <small style={{ color: 'var(--text-muted)' }}>{statuses[section.status]}</small>
        <p style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }}>{section.text}</p>
        {!!section.evidence_ids.length && <small>依据：{section.evidence_ids.join('、')}（见下方原文）</small>}
      </section>;
    })}
    <h3 style={{ fontSize: 15, marginTop: 18 }}>还需要确认</h3>
    <ul>{result.explanation.unknowns.map((text, i) => <li key={i}>{text}</li>)}</ul>
    <EvidenceDetails packet={result.packet} />
  </div>;
}
