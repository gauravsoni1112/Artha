import React from "react";

interface RiskArcProps {
  value?: number; // 0–1
}

export function RiskArc({ value = 0.55 }: RiskArcProps) {
  const W = 120, H = 65;
  const cx = 60, cy = 62, r = 48;
  const angle = Math.PI + value * Math.PI;
  const px = cx + r * Math.cos(angle);
  const py = cy + r * Math.sin(angle);
  const track = `M${cx - r},${cy} A${r},${r} 0 0,1 ${cx + r},${cy}`;
  const fill = `M${cx - r},${cy} A${r},${r} 0 0,1 ${px.toFixed(2)},${py.toFixed(2)}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H }}>
      <path
        d={track}
        fill="none"
        stroke="rgba(255,255,255,0.07)"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <path
        d={fill}
        fill="none"
        stroke="oklch(0.76 0.16 65)"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <circle cx={px.toFixed(2)} cy={py.toFixed(2)} r="5" fill="oklch(0.76 0.16 65)" />
    </svg>
  );
}
