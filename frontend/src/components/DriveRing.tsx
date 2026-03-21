import { motion, useMotionValue, useTransform, animate } from 'framer-motion';
import { useEffect } from 'react';

interface Props {
  usedPercent: number; // 0–100
  size?: number;
}

export function DriveRing({ usedPercent, size = 200 }: Props) {
  const progress = useMotionValue(0);
  const strokeDashoffset = useTransform(progress, (v) => {
    const r = (size / 2) * 0.75;
    const circ = 2 * Math.PI * r;
    return circ * (1 - v / 100);
  });

  useEffect(() => {
    const ctrl = animate(progress, usedPercent, { duration: 1.4, ease: [0.34, 1.56, 0.64, 1] });
    return ctrl.stop;
  }, [usedPercent]);

  const r = (size / 2) * 0.75;
  const circ = 2 * Math.PI * r;
  const cx = size / 2;
  const cy = size / 2;
  const strokeW = size * 0.06;

  // Color gradient: green → yellow → red based on usage
  const hue = Math.round(120 - (usedPercent / 100) * 120);
  const color = `hsl(${hue}, 100%, 60%)`;

  return (
    <svg width={size} height={size} style={{ filter: `drop-shadow(0 0 ${size * 0.08}px ${color}60)` }}>
      <defs>
        <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00d4ff" />
          <stop offset="100%" stopColor="#0066ff" />
        </linearGradient>
      </defs>
      {/* Track */}
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.07)"
        strokeWidth={strokeW}
      />
      {/* Progress arc */}
      <motion.circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="url(#ringGrad)"
        strokeWidth={strokeW}
        strokeLinecap="round"
        strokeDasharray={circ}
        style={{ strokeDashoffset }}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      {/* Center text */}
      <text
        x={cx}
        y={cy - size * 0.04}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="white"
        fontSize={size * 0.18}
        fontWeight="700"
        fontFamily="Inter, sans-serif"
      >
        {Math.round(usedPercent)}%
      </text>
      <text
        x={cx}
        y={cy + size * 0.14}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="rgba(255,255,255,0.45)"
        fontSize={size * 0.07}
        fontFamily="Inter, sans-serif"
      >
        已使用
      </text>
    </svg>
  );
}
