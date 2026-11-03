import React, { useEffect, useState } from 'react';
import { AlertOctagon, Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import { StepRecord } from '../types';

interface StepTimelineProps {
  currentStep: number;
  totalSteps?: number;
  onStepChange: (stepIndex: number) => void;
  stepsData: StepRecord[];
  isClosureApplied: boolean;
}

export const StepTimeline: React.FC<StepTimelineProps> = ({
  currentStep,
  totalSteps = 8,
  onStepChange,
  stepsData,
  isClosureApplied,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const activeStepData = stepsData[currentStep];
  const closureIsActive = isClosureApplied;

  useEffect(() => {
    if (!isPlaying || stepsData.length === 0) return;
    const timer = window.setInterval(() => {
      if (currentStep >= totalSteps - 1) setIsPlaying(false);
      else onStepChange(currentStep + 1);
    }, 1800 / playbackSpeed);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackSpeed, totalSteps, currentStep, onStepChange, stepsData.length]);

  if (stepsData.length === 0) {
    return (
      <section className="step-timeline frost-panel" aria-label="Allocation replay status" role="status">
        <div className="step-round-summary">
          <strong>Round-by-round replay unavailable</strong>
          <span>The current run shows its selected engine and applied resource pool. No matching eight-round replay is available for this pool.</span>
        </div>
      </section>
    );
  }

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
          return (
            <button
              key={index}
              className={`step-point ${index === currentStep ? 'current' : index < currentStep ? 'passed' : ''}`}
              onClick={() => onStepChange(index)}
              aria-label={`Round ${index + 1}`}
              aria-current={index === currentStep ? 'step' : undefined}
              title={`Round ${index + 1}`}
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
