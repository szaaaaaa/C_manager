import type { FileClassification } from '../types';

interface Props {
  classification?: FileClassification;
  size?: 'sm' | 'md';
}

export function ClassificationBadge({ classification, size = 'md' }: Props) {
  const matches = classification?.matches ?? [];
  const label = !classification ? '未分类' : matches[0]?.label ?? '未命中用途规则';
  const title = matches.length ? matches.map(m => `${m.category} / ${m.group} / ${m.label}\n规则 ${m.rule_id}：${m.path_pattern}`).join('\n\n') + '\n仅为用途分类，不代表可以删除。' : '未命中本地用途规则，可继续查看文件释义。';
  return <span title={title} style={{
    display: 'inline-block', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis',
    padding: size === 'sm' ? '3px 8px' : '5px 10px', borderRadius: 8,
    background: matches.length ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.04)',
    border: '1px solid var(--border)', color: matches.length ? 'var(--accent-cyan)' : 'var(--text-secondary)',
    fontSize: size === 'sm' ? 11 : 12, whiteSpace: 'nowrap',
  }}>{label}{matches.length > 1 ? ` +${matches.length - 1}` : ''}</span>;
}
