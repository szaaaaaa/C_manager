import type { ReactNode } from 'react';
import type { SearchStep, ExplainResponse, EvidencePacket } from '../types';

export function EvidenceDetails({ packet, children }: { packet: EvidencePacket; children?: ReactNode }) {
  return <details style={{ marginTop: 14 }}>
    <summary>{children ? '查看详细说明与来源' : `查看本机线索（${packet.evidence.length}项）`}</summary>
    {children}
    <p>检查时间：{new Date(packet.checked_at * 1000).toLocaleString()}</p>
    {packet.evidence.map(source => <article key={source.id} style={{ marginTop: 12 }}>
      <strong>{source.id} · {source.title}</strong>
      <div>{source.kind === 'web_document' ? '网页正文' : source.kind === 'web_excerpt' ? '仅搜索摘要（未读取正文）' : '本机观察'}</div>
      <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{source.content}</p>
      {source.url && <a href={source.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-cyan)', overflowWrap: 'anywhere' }}>{source.url}</a>}
    </article>)}
    {packet.warnings.map((warning, i) => <p key={i}>{warning}</p>)}
  </details>;
}

const labels = { advice: '能不能删？', impact: '删了会怎样？', ownership: '有什么用？', recovery: '误删后怎么找回？' } as const;
const decisions = {
  direct_delete: '可直接删除', managed_cleanup: '通过系统或软件清理',
  conditional_delete: '满足条件后可删除', keep: '建议保留', unknown: '暂无法判断',
};
const statuses = { supported: '资料支持', uncertain: '本机适用性未完全确认', unknown: '还不能确定' };

export function ExplanationResult({ result }: { result: ExplainResponse }) {
  return <div>
    {result.search_status.includes('失败') && <p role="alert">{result.search_status}</p>}
    <div aria-label="文件清理建议">
      {(['advice', 'impact', 'ownership'] as const).map(key => <section key={key} style={{ marginTop: 14 }}>
        <h3 style={{ fontSize: 15, margin: '0 0 4px' }}>{labels[key]}</h3>
        {key === 'advice' && <>
          <p style={{ margin: '6px 0', fontWeight: 600, color: 'var(--accent-cyan)' }}>{decisions[result.explanation.decision]}</p>
          {result.explanation.condition && <p style={{ margin: '4px 0', whiteSpace: 'pre-wrap' }}>
            {result.explanation.decision === 'unknown' ? '缺少依据：' : '必要条件：'}{result.explanation.condition}
          </p>}
        </>}
        <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{result.explanation[key].text}</p>
      </section>)}
    </div>
    <EvidenceDetails packet={result.packet}>
      <h4>{labels.recovery}</h4>
      <p>{result.explanation.recovery.text}</p>
      {result.explanation.unknowns.length > 0 && <>
        <h4>还需确认</h4>
        <ul>{result.explanation.unknowns.map((text, i) => <li key={i}>{text}</li>)}</ul>
      </>}
      <p>{result.search_status}</p>
      <SearchTrace steps={result.search_steps ?? []} />
      {(Object.keys(labels) as (keyof typeof labels)[]).map(key => <p key={key}>
        {labels[key]} {statuses[result.explanation[key].status]} · 依据：{result.explanation[key].evidence_ids.join('、') || '暂无'}
      </p>)}
    </EvidenceDetails>
  </div>;
}

export function SearchTrace({ steps }: { steps: SearchStep[] }) {
  if (!steps.length) return null;
  const names: Record<string, string> = { search: '搜索', open_page: '读网页', find_in_page: '页内查找', review_source: '核对来源归属', reject_sources: '排除不匹配来源', finish: '结束检索' };
  const goals = { identity: '核实归属', purpose: '查明用途', impact: '核实删除影响', handling: '确认处理方式' };
  const sources = new Map(steps.flatMap(step => step.sources.map(source => [source.id, source] as const)));
  const linkStyle = { color: 'var(--accent-cyan)', overflowWrap: 'anywhere' as const };
  return <details open style={{ marginTop: 12 }}>
    <summary>检索记录（{steps.length}步）</summary>
    <ol>{steps.map(step => <li key={step.round} style={{ marginBottom: 14, overflowWrap: 'anywhere' }}>
      <strong>{goals[step.goal]} · {names[step.action] ?? step.action}</strong>
      <div>{step.reason}</div>
      {step.action === 'search' && <>
        <div>搜索词：{step.target}</div>
        {step.site && <div>限定站点：{step.site}</div>}
      </>}
      {(step.action === 'open_page' || step.action === 'find_in_page') && <>
        <div>来源 ID：{step.target}</div>
        {step.focus && <div>{step.action === 'find_in_page' ? '页内关键词' : '阅读关注'}：{step.focus}</div>}
      </>}
      {step.action === 'review_source' && <>
        <div>来源编号：{step.target}</div>
        <div>关联判断（模型判断）：{step.focus}</div>
      </>}
      {step.action === 'reject_sources' && <>
        <div>排除编号：{step.target}</div>
        <div>不匹配原因（模型判断）：{step.focus}</div>
      </>}
      <div role="status">执行结果：{step.outcome}</div>
      {step.finding && <div style={{ marginTop: 4 }}>
        依据摘要（模型整理）：{step.finding}
        <div>引用：{step.evidence_ids.length ? step.evidence_ids.map((id, index) => {
          const source = sources.get(id);
          return <span key={id}>{index > 0 && '、'}{source && /^https?:\/\//i.test(source.url)
            ? <a href={source.url} target="_blank" rel="noopener noreferrer" style={linkStyle}>{id}</a>
            : id}</span>;
        }) : '暂无'}</div>
      </div>}
      {step.missing.length > 0 && <div>待确认：{step.missing.join('；')}</div>}
      {step.sources.length > 0 && <ul aria-label="本步来源" style={{ marginTop: 4 }}>
        {step.sources.map(source => <li key={source.id}>
          {source.id} · {/^https?:\/\//i.test(source.url)
            ? <a href={source.url} target="_blank" rel="noopener noreferrer" style={linkStyle}>{source.title || source.url}</a>
            : source.title}
          <span style={{ color: 'var(--text-secondary)' }}> · {source.kind === 'web_document' ? '已读正文' : '搜索摘要'}</span>
        </li>)}
      </ul>}
    </li>)}</ol>
  </details>;
}
