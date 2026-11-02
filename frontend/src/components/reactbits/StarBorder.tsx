import React from 'react';

interface StarBorderProps {
  as?: React.ElementType;
  className?: string;
  color?: string;
  speed?: string;
  children?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit' | 'reset';
}

export const StarBorder: React.FC<StarBorderProps> = ({
  as: Component = 'button',
  className = '',
  color = '#20D6D0',
  speed = '3s',
  children,
  onClick,
  disabled = false,
  type = 'button',
}) => {
  return (
    <Component
      type={Component === 'button' ? type : undefined}
      onClick={onClick}
      disabled={disabled}
      className={`relative inline-block overflow-hidden rounded-2xl p-[2.5px] font-medium transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-accent-cyan/50 disabled:opacity-50 disabled:pointer-events-none group ${className}`}
    >
      {/* Outer Bloom Rotating Pulse (Bigger, glowing aura) */}
      <span
        style={{
          animationDuration: speed,
          background: `conic-gradient(from 0deg, transparent 0deg 240deg, rgba(99, 102, 241, 0.75) 290deg, #20D6D0 340deg, ${color} 360deg)`,
        }}
        className="absolute inset-[-150%] animate-[spin_3s_linear_infinite] blur-md opacity-90 group-hover:opacity-100 pointer-events-none"
      />
      {/* Sharp Rotating Border Pulse */}
      <span
        style={{
          animationDuration: speed,
          background: `conic-gradient(from 0deg, transparent 0deg 250deg, rgba(120, 140, 255, 0.9) 300deg, #20D6D0 345deg, #ffffff 360deg)`,
        }}
        className="absolute inset-[-100%] animate-[spin_3s_linear_infinite] opacity-95 group-hover:opacity-100 pointer-events-none"
      />
      {/* Inner surface */}
      <span className="relative flex items-center justify-center gap-2 rounded-[13px] bg-ink-900/90 px-6 py-3 text-sm font-semibold text-text-primary transition-all duration-300 group-hover:bg-ink-850 backdrop-blur-md">
        {children}
      </span>
    </Component>
  );
};

export default StarBorder;
