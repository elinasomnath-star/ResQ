import React, { useRef } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';

interface DockProps {
  children: React.ReactNode;
  className?: string;
}

export const Dock: React.FC<DockProps> = ({ children, className = '' }) => {
  const mouseX = useMotionValue(Infinity);

  return (
    <motion.div
      onMouseMove={(e) => mouseX.set(e.pageX)}
      onMouseLeave={() => mouseX.set(Infinity)}
      className={`flex items-center gap-2 rounded-2xl border border-white/10 bg-ink-900/80 px-3 py-2 shadow-2xl backdrop-blur-xl ${className}`}
    >
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(child, { mouseX } as any);
        }
        return child;
      })}
    </motion.div>
  );
};

interface DockItemProps {
  children: React.ReactNode;
  mouseX?: any;
  onClick?: () => void;
  isActive?: boolean;
  label?: string;
  className?: string;
}

export const DockItem: React.FC<DockItemProps> = ({
  children,
  mouseX,
  onClick,
  isActive = false,
  label = '',
  className = '',
}) => {
  const ref = useRef<HTMLButtonElement | null>(null);
  const fallbackMouseX = useMotionValue(Infinity);
  const resolvedMouseX = mouseX ?? fallbackMouseX;

  const distance = useTransform(resolvedMouseX, (val: number) => {
    const bounds = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
    return val - bounds.x - bounds.width / 2;
  });

  const widthSync = useTransform(distance, [-120, 0, 120], [42, 58, 42]);
  const width = useSpring(widthSync, { mass: 0.1, stiffness: 180, damping: 14 });

  return (
    <div className="group relative flex flex-col items-center">
      {label && (
        <span className="pointer-events-none absolute -top-8 scale-0 rounded bg-ink-800 border border-white/10 px-2 py-0.5 text-[11px] font-medium text-text-primary opacity-0 shadow-lg transition-all duration-150 group-hover:scale-100 group-hover:opacity-100 whitespace-nowrap z-50">
          {label}
        </span>
      )}
      <motion.button
        ref={ref}
        style={{ width, height: width }}
        onClick={onClick}
        className={`flex items-center justify-center rounded-xl border transition-colors ${
          isActive
            ? 'border-accent-cyan/60 bg-accent-cyan/20 text-accent-cyan shadow-[0_0_12px_rgba(34,211,238,0.3)]'
            : 'border-white/10 bg-white/[0.04] text-text-secondary hover:border-white/20 hover:bg-white/[0.08] hover:text-text-primary'
        } ${className}`}
      >
        {children}
      </motion.button>
    </div>
  );
};

export default Dock;
