import React, { useState } from 'react';
import { X, PlayCircle } from 'lucide-react';
import type { EngineType } from '../types';
import { Stepper, StepItem } from './reactbits/Stepper';

interface GuidedDemoModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectEvent?: (date: string) => void;
  onSelectEngine?: (engine: EngineType) => void;
  onToggleCompare?: () => void;
  onToggleEscalations?: () => void;
}

const DEMO_STEPS: StepItem[] = [
  {
    id: 'intro',
    title: '1. Replay Context & Hydrological Danger',
    description:
      'ResQ replays three documented flood events (2019, 2024, 2026) in Bantwal Taluk. The left rail visualizes river water levels against the official CWC 9.0 m danger mark. Notice all inventory is tagged with the violet ASSUMED chip.',
  },
  {
    id: 'grid-severity',
    title: '2. 16 Analytical Grid Cells & Modeled Severity',
    description:
      'The taluk is divided into exactly 16 analytical grid cells. Cell fills reflect modeled relative priority (teal #2DD4BF to yellow #FDE047 to coral #FB7185). Population figures are WorldPop modeled estimates.',
  },
  {
    id: 'sar-signal',
    title: '3. Candidate VH-Change Signal (SAR)',
    description:
      'Toggle the SAR candidate layer in the bottom dock. Sentinel-1 RTC backscatter change indicates candidate VH signals rather than verified ground flood extents, respecting operational honesty standards.',
  },
  {
    id: 'inventory-thresholds',
    title: '4. Assumed Inventory & Critical Thresholds',
    description:
      'The top right panel displays assumed capsule meters for Food, Water, and Medical kits. When stock-to-unmet-demand drops below the 20% critical threshold, the meter pulses with an alert state.',
  },
  {
    id: 'timeline-closures',
    title: '5. Timeline & Bantwal Road Blockage Scenarios',
    description:
      'Use the Scenario Deck to block one of the mapped Bantwal road segments. The ResQ API recalculates routes across the local network and the map highlights the blocked segment.',
  },
  {
    id: 'route-morphing',
    title: '6. Route Morphing & Candidate Fallbacks',
    description:
      'Normal routes flow in glowing cyan particles. Detours recompute dynamically. If an unverified fallback route is evaluated, it is rendered as a dotted violet arc clearly labeled "unverified".',
  },
  {
    id: 'engine-comparison',
    title: '7. Multi-Engine Allocation Comparison',
    description:
      'Open the Compare drawer to view side-by-side performance between OR-Tools MILP (#60A5FA), LinUCB (#FB923C), and Proportional (#4ADE80) baselines across minimum-zone coverage and unmet demand.',
  },
  {
    id: 'escalations-rbac',
    title: '8. Shortage Escalations & Role Controls',
    description:
      'Review Module 9 shortage triggers and donor-to-recipient reallocation arcs. Note that administrative override and closure triggers are restricted to the operator role, while viewers have read-only replay access.',
  },
];

export const GuidedDemoModal: React.FC<GuidedDemoModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-24 right-6 z-40 w-96 max-w-[calc(100vw-3rem)]">
      <div className="relative">
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 z-50 p-1.5 rounded-full bg-ink-950 border border-white/20 text-slate-400 hover:text-white hover:bg-white/10 transition-colors shadow-lg"
          title="Close Presenter Mode"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-2 px-1">
          <PlayCircle className="w-4 h-4 text-accent-cyan" />
          <span className="text-xs font-mono font-medium text-slate-300">
            Interactive Presenter Walkthrough
          </span>
        </div>

        <Stepper
          steps={DEMO_STEPS}
          currentStep={currentStepIndex}
          onStepChange={setCurrentStepIndex}
          onComplete={onClose}
          className="shadow-2xl border-accent-cyan/30 bg-ink-950/95"
        />
      </div>
    </div>
  );
};
