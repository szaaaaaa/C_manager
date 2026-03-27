interface Props {
  safety: 'red' | 'yellow' | 'green';
  size?: 'sm' | 'md';
}

const CONFIG = {
  red: { emoji: '🔴', label: '别删', bg: 'var(--red-bg)', color: 'var(--red)', border: 'rgba(255,68,68,0.25)' },
  yellow: { emoji: '🟡', label: '看看再删', bg: 'var(--yellow-bg)', color: 'var(--yellow)', border: 'rgba(255,214,0,0.25)' },
  green: { emoji: '🟢', label: '放心删', bg: 'var(--green-bg)', color: 'var(--green)', border: 'rgba(0,230,118,0.25)' },
};

export function SafetyBadge({ safety, size = 'md' }: Props) {
  const cfg = CONFIG[safety];
  const small = size === 'sm';
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: small ? 3 : 5,
      padding: small ? '2px 7px' : '4px 10px',
      borderRadius: 100,
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      color: cfg.color,
      fontSize: small ? 10 : 11,
      fontWeight: 600,
      whiteSpace: 'nowrap',
      letterSpacing: '0.02em',
    }}>
      <span style={{ fontSize: small ? 8 : 10 }}>{cfg.emoji}</span>
      {cfg.label}
    </span>
  );
}
