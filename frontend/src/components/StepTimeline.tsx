import React, { useEffect, useState } from 'react';
import { AlertOctagon, Pause, Play, SkipBack, SkipForward, Zap } from 'lucide-react';
import { StepRecord } from '../types';

interface StepTimelineProps {
  currentStep: number;
  totalSteps?: number;
  onStepChange: (stepIndex: number) => void;
  closureStep?: number;
  stepsData: StepRecord[];
  isClosureApplied: boolean;
  onTriggerClosure?: () => void;
  canTriggerClosure?: boolean;
}

export const StepTimeline: React.FC<StepTimelineProps> = ({
  currentStep,
  totalSteps = 8,
  onStepChange,
  closureStep = 1,
  stepsData,
  isClosureApplied,
  onTriggerClosure,
  canTriggerClosure = false,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const activeStepData = stepsData[currentStep];
  const closureIsActive = isClosureApplied && currentStep >= closureStep;

  useEffect(() => {
    if (!isPlaying) return;
    const timer = window.setInterval(() => {
      if (currentStep >= totalSteps - 1) setIsPlaying(false);
      else onStepChange(currentStep + 1);
    }, 1800 / playbackSpeed);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackSpeed, totalSteps, currentStep, onStepChange]);

  return (
    <section className="step-timeline frost-panel" aria-label="Eight-round allocation timeline">
      <div className="step-timeline-toolbar">
        {/* Playback controls */}
        <div className="step-playback">
          <button
            onClick={() => onStepChange(Math.max(0, currentStep - 1))}
            disabled={currentStep === 0}
            aria-label="Previous Step"
            title="Previous round"
          >
            <SkipBack size={13} />
          </button>
          <button
            className="step-play"
            onClick={() => setIsPlaying((v) => !v)}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause size={13} /> : <Play size={13} fill="currentColor" />}
          </button>
          <button
            onClick={() => onStepChange(Math.min(totalSteps - 1, currentStep + 1))}
            disabled={currentStep === totalSteps - 1}
            aria-label="Next Step"
            title="Next round"
          >
            <SkipForward size={13} />
          </button>
          <div className="step-speed" aria-label="Playback speed">
            {[0.5, 1, 2].map((speed) => (
              <button
                key={speed}
                aria-pressed={playbackSpeed === speed}
                onClick={() => setPlaybackSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>

        {/* Round summary & Metrics with separated cards */}
        <div className="step-round-summary">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <strong>ROUND {currentStep + 1} OF {totalSteps}</strong>
              <span className="w-1 h-1 rounded-full bg-accent-cyan" />
              <span>Dynamic allocation replay</span>
            </div>
          </div>
          {activeStepData && (
            <div className="step-metrics">
              <span className="step-metric-pill">
                <small>Fairness floor</small>
                <b>{activeStepData.min_zone_coverage_pct.toFixed(1)}%</b>
              </span>
              <span className="step-metric-pill">
                <small>Unmet demand</small>
                <b className="text-amber-300">{(activeStepData.unmet_demand_pct ?? 0).toFixed(1)}%</b>
              </span>
            </div>
          )}
        </div>

        {/* Closure actions */}
        <div className="step-closure-actions">
          {closureIsActive && (
            <span className="closure-pill">
              <AlertOctagon size={12} /> Closure active
            </span>
          )}
          {onTriggerClosure && (
            <button
              className={`closure-action ${isClosureApplied ? 'applied' : ''}`}
              onClick={onTriggerClosure}
              disabled={!canTriggerClosure || isClosureApplied}
              aria-label={isClosureApplied ? 'Closure Applied' : 'Apply Verified Closure'}
              title={
                canTriggerClosure
                  ? isClosureApplied
                    ? 'Verified closure already applied'
                    : 'Apply the first verified closure and recalculate routes'
                  : 'Operator role required'
              }
            >
              <Zap size={12} />
              {isClosureApplied ? 'Closure applied' : 'Apply closure'}
            </button>
          )}
        </div>
      </div>

      {/* Step scrubber dots — line cuts directly through circle centers */}
      <div className="step-scrubber" role="group" aria-label="Select allocation round">
        <div className="step-track" />
        <div
          className="step-progress"
          style={{ transform: `scaleX(${currentStep / Math.max(1, totalSteps - 1)})` }}
        />
        {Array.from({ length: totalSteps }, (_, index) => {
          const closurePoint = index === closureStep;
          return (
            <button
              key={index}
              className={`step-point ${index === currentStep ? 'current' : index < currentStep ? 'passed' : ''} ${closurePoint ? 'closure-point' : ''}`}
              onClick={() => onStepChange(index)}
              aria-label={`Round ${index + 1}${closurePoint ? ', closure step' : ''}`}
              aria-current={index === currentStep ? 'step' : undefined}
              title={closurePoint ? 'Verified road closure step' : `Round ${index + 1}`}
            >
              <span>{index + 1}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
};

export default StepTimeline;
