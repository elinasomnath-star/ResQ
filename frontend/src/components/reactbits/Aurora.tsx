import React, { useEffect, useRef } from 'react';

interface AuroraProps {
  colorStops?: string[];
  amplitude?: number;
  speed?: number;
  className?: string;
  children?: React.ReactNode;
}

export const Aurora: React.FC<AuroraProps> = ({
  colorStops = ['#22D3EE', '#818CF8', '#A78BFA'], // water-cyan, indigo, violet
  amplitude = 1.0,
  speed = 0.8,
  className = '',
  children,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let t = 0;

    const resize = () => {
      canvas.width = canvas.parentElement?.clientWidth || window.innerWidth;
      canvas.height = canvas.parentElement?.clientHeight || window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const render = () => {
      t += 0.005 * speed;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Create base deep ink background
      const baseGradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
      baseGradient.addColorStop(0, '#060A12');
      baseGradient.addColorStop(1, '#0C1424');
      ctx.fillStyle = baseGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Render 3 flowing soft aurora waves
      const waves = [
        { color: colorStops[0] || '#22D3EE', alpha: 0.18, offset: 0, freq: 0.002 },
        { color: colorStops[1] || '#818CF8', alpha: 0.14, offset: 2.1, freq: 0.0025 },
        { color: colorStops[2] || '#A78BFA', alpha: 0.12, offset: 4.2, freq: 0.0018 },
      ];

      waves.forEach((w) => {
        ctx.save();
        ctx.filter = 'blur(48px)';
        ctx.beginPath();
        ctx.moveTo(0, canvas.height);

        for (let x = 0; x <= canvas.width; x += 15) {
          const y =
            canvas.height * 0.45 +
            Math.sin(x * w.freq + t + w.offset) * 80 * amplitude +
            Math.cos(x * w.freq * 0.7 - t * 0.8) * 50 * amplitude;
          ctx.lineTo(x, y);
        }

        ctx.lineTo(canvas.width, canvas.height);
        ctx.closePath();

        ctx.fillStyle = w.color;
        ctx.globalAlpha = w.alpha;
        ctx.fill();
        ctx.restore();
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resize);
    };
  }, [colorStops, amplitude, speed]);

  return (
    <div className={`relative overflow-hidden ${className}`}>
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none w-full h-full"
      />
      <div className="relative z-10 w-full h-full">{children}</div>
    </div>
  );
};

export default Aurora;
