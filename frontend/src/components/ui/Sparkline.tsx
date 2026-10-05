import React from 'react';

export interface SparklineProps {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  color = '#FF7A00',
  height = 36,
  width = 120,
}) => {
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((val, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const fillPoints = `${points} ${width},${height} 0,${height}`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={`sparkline-grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <polygon
        points={fillPoints}
        fill={`url(#sparkline-grad-${color.replace('#', '')})`}
      />
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
};
