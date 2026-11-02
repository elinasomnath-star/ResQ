import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Check } from 'lucide-react';

export interface StepItem {
  id: string;
  title: string;
  description: string;
  actionText?: string;
  targetFocus?: string;
}

interface StepperProps {
  steps: StepItem[];
  currentStep: number;
  onStepChange: (stepIndex: number) => void;
  onComplete?: () => void;
  className?: string;
}

export const Stepper: React.FC<StepperProps> = ({
  steps,
  currentStep,
  onStepChange,
  onComplete,
  className = '',
}) => {
  // Arrow key navigation for presenter
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        if (currentStep < steps.length - 1) {
          onStepChange(currentStep + 1);
        } else if (onComplete) {
          onComplete();
        }
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        if (currentStep > 0) {
          onStepChange(currentStep - 1);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStep, steps.length, onStepChange, onComplete]);

  const activeStep = steps[currentStep] || steps[0];

  return (
    <div className={`rounded-xl border border-white/10 bg-ink-900/90 p-4 backdrop-blur-xl shadow-2xl ${className}`}>
      {/* Step Indicators */}
      <div className="flex items-center justify-between gap-1 mb-3">
        {steps.map((step, idx) => {
          const isDone = idx < currentStep;
          const isCurrent = idx === currentStep;
          return (
            <button
              key={step.id}
              onClick={() => onStepChange(idx)}
              className="flex-1 flex flex-col items-center group focus:outline-none"
            >
              <div
                className={`h-1.5 w-full rounded-full transition-all duration-300 ${
                  isDone
                    ? 'bg-accent-cyan'
                    : isCurrent
                    ? 'bg-gradient-to-r from-accent-cyan to-accent-indigo shadow-[0_0_8px_rgba(34,211,238,0.5)]'
                    : 'bg-white/10 group-hover:bg-white/20'
                }`}
              />
            </button>
          );
        })}
      </div>

      {/* Step Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeStep.id}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.2 }}
          className="space-y-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono tracking-wider text-accent-cyan uppercase">
              Step {currentStep + 1} of {steps.length} &middot; Presenter Mode
            </span>
            <span className="text-[10px] text-text-muted font-mono">Use &larr; &rarr; keys</span>
          </div>
          <h4 className="font-heading text-sm font-semibold text-text-primary">
            {activeStep.title}
          </h4>
          <p className="text-xs text-text-secondary leading-relaxed">
            {activeStep.description}
          </p>
        </motion.div>
      </AnimatePresence>

      {/* Navigation Controls */}
      <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-white/10">
        <button
          onClick={() => currentStep > 0 && onStepChange(currentStep - 1)}
          disabled={currentStep === 0}
          className="flex items-center gap-1 text-xs font-medium text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:pointer-events-none transition-colors px-2 py-1 rounded"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Prev
        </button>

        <button
          onClick={() => {
            if (currentStep < steps.length - 1) {
              onStepChange(currentStep + 1);
            } else if (onComplete) {
              onComplete();
            }
          }}
          className="flex items-center gap-1 text-xs font-medium bg-accent-cyan/20 border border-accent-cyan/40 hover:bg-accent-cyan/30 text-accent-cyan transition-colors px-3 py-1 rounded-md shadow-sm"
        >
          {currentStep === steps.length - 1 ? (
            <>
              Finish <Check className="w-3.5 h-3.5" />
            </>
          ) : (
            <>
              Next <ChevronRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default Stepper;
