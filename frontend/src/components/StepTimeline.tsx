import React, { useEffect, useState } from 'react';
import { AlertOctagon, Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import type { StepRecord } from '../types';

interface StepTimelineProps {
  currentStep: number;
  totalSteps?: number;
  onStepChange: (stepIndex: number) => void;
  stepsData: StepRecord[];
  isClosureApplied: boolean;
  processProgress?: number | null;
  processZoneCount?: number;
  processMinCoveragePct?: number;
  processUnmetDemandPct?: number;
  processPaused?: boolean;
  processSpeed?: number;
  onProcessPause?: () => void;
  onProcessSpeedChange?: (speed: number) => void;
  onProcessStepChange?: (zoneCount: number) => void;
}

export const StepTimeline: React.FC<StepTimelineProps> = ({
  currentStep,
  totalSteps = 8,
  onStepChange,
  stepsData,
  isClosureApplied,
  processProgress = null,
  processZoneCount = 16,
  processMinCoveragePct = 0,
  processUnmetDemandPct = 0,
  processPaused = false,
  processSpeed = 1,
  onProcessPause,
  onProcessSpeedChange,
  onProcessStepChange,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const liveProcess = processProgress != null;
  const activeStepData = stepsData[currentStep];
  const revealedZones = Math.min(processProgress ?? 0, processZoneCount || 16);
  const totalZones = processZoneCount || 16;
  const processStage = liveProcess
    ? Math.min(totalSteps - 1, Math.floor((revealedZones * totalSteps) / totalZones))
    : currentStep;
  const displayStep = liveProcess ? processStage : currentStep;

  useEffect(() => {
    if (liveProcess || !isPlaying || stepsData.length === 0) return;
    const timer = window.setInterval(() => {
      if (currentStep >= totalSteps - 1) setIsPlaying(false);
      else onStepChange(currentStep + 1);
    }, 1800 / playbackSpeed);
    return () => window.clearInterval(timer);
  }, [liveProcess, isPlaying, playbackSpeed, totalSteps, currentStep, onStepChange, stepsData.length]);

  if (stepsData.length === 0 && !liveProcess) {
    return (
      <section className="step-timeline frost-panel" aria-label="Allocation replay status" role="status">
        <div className="step-round-summary">
          <strong>Round-by-round replay unavailable</strong>
          <span>The current run shows its selected engine and applied resource pool. No matching eight-round replay is available for this pool.</span>
        </div>
      </section>
    );
  }

  const handlePrevious = () => liveProcess
    ? onProcessStepChange?.(Math.max(0, revealedZones - Math.max(1, Math.round(totalZones / totalSteps))))
    : onStepChange(Math.max(0, currentStep - 1));
  const handleNext = () => liveProcess
    ? onProcessStepChange?.(Math.min(totalZones, revealedZones + Math.max(1, Math.round(totalZones / totalSteps))))
    : onStepChange(Math.min(totalSteps - 1, currentStep + 1));
  const handleStageSelect = (index: number) => liveProcess
    ? onProcessStepChange?.(Math.min(totalZones, Math.round(((index + 1) / totalSteps) * totalZones)))
    : onStepChange(index);

  return (
    <section className="step-timeline frost-panel" aria-label="Eight-round allocation timeline">
      <div className="step-timeline-toolbar">
        {/* Playback controls */}
        <div className="step-playback">
          <button onClick={handlePrevious}
            disabled={liveProcess ? revealedZones === 0 : currentStep === 0}
            aria-label="Previous Step" title="Previous round">
            <SkipBack size={13} />
          </button>
          <button className="step-play"
            onClick={() => liveProcess ? onProcessPause?.() : setIsPlaying((value) => !value)}
            aria-label={liveProcess ? (processPaused ? 'Resume allocation' : 'Pause allocation') : (isPlaying ? 'Pause' : 'Play')}
            title={liveProcess ? (processPaused ? 'Resume allocation' : 'Pause allocation') : undefined}>
            {liveProcess ? (processPaused ? <Play size={13} fill="currentColor" /> : <Pause size={13} />) : isPlaying ? <Pause size={13} /> : <Play size={13} fill="currentColor" />}
          </button>
          <button onClick={handleNext}
            disabled={liveProcess ? revealedZones >= totalZones : currentStep >= totalSteps - 1}
            aria-label="Next Step" title="Next round">
            <SkipForward size={13} />
          </button>
          <div className="step-speed" aria-label="Playback speed">
            {[0.5, 1, 2].map((speed) => (
              <button key={speed}
                aria-pressed={liveProcess ? processSpeed === speed : playbackSpeed === speed}
                onClick={() => liveProcess ? onProcessSpeedChange?.(speed) : setPlaybackSpeed(speed)}>
                {speed}x
              </button>
            ))}
          </div>
        </div>

        {/* Round summary & Metrics with separated cards */}
        <div className="step-round-summary">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <strong>{liveProcess ? `ROUND ${displayStep + 1} OF ${totalSteps}` : `ROUND ${currentStep + 1} OF ${totalSteps}`}</strong>
              <span className="w-1 h-1 rounded-full bg-accent-cyan" />
              <span>Dynamic allocation replay</span>
            </div>
          </div>
          {(activeStepData || liveProcess) && (
            <div className="step-metrics">
              <span className="step-metric-pill">
                <small>Fairness floor</small>
                <b>{(liveProcess ? processMinCoveragePct : Number(activeStepData?.min_zone_coverage_pct ?? 0)).toFixed(1)}%</b>
              </span>
              <span className="step-metric-pill">
                <small>Unmet demand</small>
                <b className="text-amber-300">{(liveProcess ? processUnmetDemandPct : Number(activeStepData?.unmet_demand_pct ?? 0)).toFixed(1)}%</b>
              </span>
            </div>
          )}
        </div>

        {/* Closure actions */}
        <div className="step-closure-actions">
          {isClosureApplied && <span className="closure-pill"><AlertOctagon size={12} /> Closure active</span>}
        </div>
      </div>

      {/* Step scrubber dots — line cuts directly through circle centers */}
      <div className="step-scrubber" role="group" aria-label="Select allocation round">
        <div className="step-track" />
        <div className="step-progress" style={{ transform: `scaleX(${displayStep / Math.max(1, totalSteps - 1)})` }} />
        {Array.from({ length: totalSteps }, (_, index) => (
          <button key={index}
            className={`step-point ${index === displayStep ? 'current' : index < displayStep ? 'passed' : ''}`}
            onClick={() => handleStageSelect(index)}
            aria-label={`Round ${index + 1}`}
            aria-current={index === displayStep ? 'step' : undefined}
            title={`Round ${index + 1}`}>
            <span>{index + 1}</span>
          </button>
        ))}
      </div>
    </section>
  );
};

export default StepTimeline;
