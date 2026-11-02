import React, { useEffect, useState } from 'react';

interface CountUpProps {
  to: number;
  from?: number;
  duration?: number; // in seconds
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}

export const CountUp: React.FC<CountUpProps> = ({
  to,
  from = 0,
  duration = 1.2,
  decimals = 0,
  prefix = '',
  suffix = '',
  className = '',
}) => {
  const [current, setCurrent] = useState(from);

  useEffect(() => {
    let startTime: number | null = null;
    let animationFrameId: number;

    const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3);

    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / (duration * 1000), 1);
      const eased = easeOutCubic(progress);
      const nextValue = from + (to - from) * eased;
      setCurrent(nextValue);

      if (progress < 1) {
        animationFrameId = requestAnimationFrame(step);
      }
    };

    animationFrameId = requestAnimationFrame(step);

    return () => cancelAnimationFrame(animationFrameId);
  }, [to, from, duration]);

  const formatted = decimals > 0 ? current.toFixed(decimals) : Math.round(current).toLocaleString();

  return (
    <span className={`font-mono tabular-nums ${className}`}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
};

export default CountUp;
