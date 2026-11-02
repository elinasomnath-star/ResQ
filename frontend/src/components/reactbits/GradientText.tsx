import React from 'react';

interface GradientTextProps {
  children: React.ReactNode;
  colors?: string[];
  animationSpeed?: number;
  showBorder?: boolean;
  className?: string;
}

export const GradientText: React.FC<GradientTextProps> = ({
  children,
  colors = ['#22D3EE', '#818CF8', '#A78BFA', '#22D3EE'],
  animationSpeed = 6,
  showBorder = false,
  className = '',
}) => {
  const gradientStyle = {
    backgroundImage: `linear-gradient(to right, ${colors.join(', ')})`,
    backgroundSize: '300% 100%',
    animation: `gradientMove ${animationSpeed}s linear infinite`,
  };

  return (
    <>
      <style>
        {`
          @keyframes gradientMove {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
          }
        `}
      </style>
      <span
        style={gradientStyle}
        className={`inline-block bg-clip-text text-transparent font-bold ${
          showBorder ? 'border border-accent-cyan/30 rounded-lg px-2 py-0.5' : ''
        } ${className}`}
      >
        {children}
      </span>
    </>
  );
};

export default GradientText;
