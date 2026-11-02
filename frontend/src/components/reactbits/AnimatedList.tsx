import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';

interface AnimatedListProps {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}

export const AnimatedList: React.FC<AnimatedListProps> = ({
  children,
  className = '',
  delay = 0.05,
}) => {
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <AnimatePresence initial={false}>
        {React.Children.map(children, (child, index) => {
          if (!child) return null;
          return (
            <motion.div
              key={(child as any).key || index}
              initial={{ opacity: 0, y: -12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, height: 0, scale: 0.95 }}
              transition={{
                duration: 0.25,
                delay: index * delay,
                ease: [0.22, 1, 0.36, 1],
              }}
              layout
            >
              {child}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
};

export default AnimatedList;
