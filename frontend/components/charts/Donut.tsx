import React from "react";

interface DonutSegment {
  value: number;
  color: string;
  label?: string;
}

interface DonutProps {
  segments: DonutSegment[];
  size?: number;
}

export function Donut({ segments, size = 72 }: DonutProps) {
  const r = 28, cx = 36, cy = 36;
  const circ = 2 * Math.PI * r;
  const total = segments.reduce((a, s) => a + s.value, 0);
  let offset = 0;

  return (
    <svg width={size} height={size} viewBox="0 0 72 72">
      <circle
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth="10"
      />
      {segments.map((s, i) => {
        const dash = (s.value / total) * circ;
        const gap = circ - dash;
        const el = (
          <circle
            key={i}
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={s.color}
            strokeWidth="10"
            strokeDasharray={`${dash} ${gap}`}
            strokeDashoffset={-offset}
            transform="rotate(-90 36 36)"
            strokeLinecap="butt"
          />
        );
        offset += dash;
        return el;
      })}
    </svg>
  );
}
