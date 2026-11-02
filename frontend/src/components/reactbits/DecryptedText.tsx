import React, { useEffect, useState } from 'react';

interface DecryptedTextProps {
  text: string;
  speed?: number;
  maxIterations?: number;
  characters?: string;
  className?: string;
  parentClassName?: string;
  encryptedClassName?: string;
  animateOn?: 'view' | 'hover';
}

export const DecryptedText: React.FC<DecryptedTextProps> = ({
  text,
  speed = 40,
  maxIterations = 10,
  characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?',
  className = '',
  encryptedClassName = 'text-accent-cyan opacity-80',
}) => {
  const [displayText, setDisplayText] = useState(text);
  const [isDecrypting, setIsDecrypting] = useState(false);

  const startDecryption = () => {
    if (isDecrypting) return;
    setIsDecrypting(true);

    let iteration = 0;
    const interval = setInterval(() => {
      setDisplayText(() =>
        text
          .split('')
          .map((char, index) => {
            if (char === ' ') return ' ';
            if (index < iteration) {
              return text[index];
            }
            return characters[Math.floor(Math.random() * characters.length)];
          })
          .join('')
      );

      if (iteration >= text.length) {
        clearInterval(interval);
        setIsDecrypting(false);
      }
      iteration += 1 / (maxIterations / 2);
    }, speed);
  };

  useEffect(() => {
    startDecryption();
  }, [text]);

  return (
    <span
      onMouseEnter={startDecryption}
      className={`font-mono cursor-default inline-block tracking-wider ${className} ${
        isDecrypting ? encryptedClassName : ''
      }`}
    >
      {displayText}
    </span>
  );
};

export default DecryptedText;
