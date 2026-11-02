import React from 'react';
import { X, ShieldAlert, Database, Layers, ExternalLink, Cpu, AlertTriangle } from 'lucide-react';

interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AboutModal: React.FC<AboutModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-md">
      <div className="glass-panel-elevated w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden rounded-2xl border border-white/10 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-400/10 text-cyan-400 border border-cyan-400/20">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-heading text-slate-100 flex items-center gap-2">
                About ResQ & Analytical Boundaries
              </h2>
              <p className="text-xs text-slate-400">
                Data sources, methodological constraints, and operational limitations
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content body */}
        <div className="p-6 overflow-y-auto space-y-6 text-sm text-slate-300">
          {/* Demo-level Authentication Banner */}
          <div className="p-4 rounded-xl bg-violet-500/10 border border-violet-500/30 flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-violet-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-violet-200 flex items-center gap-2">
                <span>Demo-level authentication. Not production security.</span>
                <span className="badge-assumed">DEMO ONLY</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                This deployment includes demo-level role-based access control (<code>viewer</code> and <code>operator</code>) for presentation and verification purposes. It does <strong className="text-slate-300">not</strong> implement production security: user registration/management, password resets, tamper-proof audit logging, multi-factor authentication (MFA), or hardware security module (HSM) termination are omitted.
              </p>
            </div>
          </div>

          {/* Core Non-Negotiable Honesty Guidelines */}
          <div>
            <h3 className="text-base font-semibold text-slate-100 mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              Honesty & Analytical Disclaimers
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                <span className="text-xs font-mono text-cyan-400 uppercase tracking-wider">Candidate VH-Change Signal</span>
                <p className="text-xs text-slate-400">
                  Sentinel-1 SAR backscatter change is designated as a <em>candidate signal</em>, not verified flood extent. False positives from saturated soil, agriculture, and surface roughness can occur.
                </p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                <span className="text-xs font-mono text-cyan-400 uppercase tracking-wider">Modeled Relative Priority</span>
                <p className="text-xs text-slate-400">
                  Zone severity represents modeled comparative urgency across analytical grid cells, not absolute municipal risk or official evacuation directives.
                </p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                <span className="text-xs font-mono text-violet-400 uppercase tracking-wider">Assumed Inventory Stocks</span>
                <p className="text-xs text-slate-400">
                  All relief supply quantities are derived from configured or synthetic scenarios. No live municipal warehouse integration is active.
                </p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                <span className="text-xs font-mono text-amber-400 uppercase tracking-wider">Mapped Bantwal Road Blockages</span>
                <p className="text-xs text-slate-400">
                  Scenarios block verified road segments in the Bantwal OSM map and recalculate routes through the ResQ API. They are planning simulations, not live traffic or checkpoint feeds.
                </p>
              </div>
            </div>
          </div>

          {/* Data Sources */}
          <div>
            <h3 className="text-base font-semibold text-slate-100 mb-3 flex items-center gap-2">
              <Database className="w-4 h-4 text-cyan-400" />
              Primary Data Sources
            </h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                <div>
                  <div className="font-medium text-slate-200">Copernicus Sentinel-1 SAR</div>
                  <div className="text-xs text-slate-400">C-band Synthetic Aperture Radar GRD/RTC backscatter for candidate VH change detection</div>
                </div>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-400/10 text-cyan-400 border border-cyan-400/20">ESA / STAC</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                <div>
                  <div className="font-medium text-slate-200">CHIRPS Daily Precipitation</div>
                  <div className="text-xs text-slate-400">0.05° resolution quasi-global rainfall estimates aggregated per zone over 7-day windows</div>
                </div>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-400/10 text-cyan-400 border border-cyan-400/20">UCSB CHG</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                <div>
                  <div className="font-medium text-slate-200">WorldPop Global2 R2025A (2025 Constrained)</div>
                  <div className="text-xs text-slate-400">1 km building-constrained population raster pixel sums per analytical cell</div>
                </div>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-400/10 text-cyan-400 border border-cyan-400/20">WorldPop</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                <div>
                  <div className="font-medium text-slate-200">OpenStreetMap & CWC Hydrology</div>
                  <div className="text-xs text-slate-400">Bantwal taluk boundary, highway network, relief shelters; CWC Bantwal danger mark (9.0 m)</div>
                </div>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-400/10 text-cyan-400 border border-cyan-400/20">OSM / CWC</span>
              </div>
            </div>
          </div>

          {/* Implemented vs Planned Status Table */}
          <div>
            <h3 className="text-base font-semibold text-slate-100 mb-3 flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              Architecture: Implemented vs. Planned
            </h3>
            <div className="overflow-x-auto rounded-lg border border-white/10">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-white/[0.03] border-b border-white/10 text-slate-400">
                    <th className="p-2.5 font-medium">Subsystem</th>
                    <th className="p-2.5 font-medium">Scope</th>
                    <th className="p-2.5 font-medium">Status</th>
                    <th className="p-2.5 font-medium">Operational Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Ingestion</td>
                    <td className="p-2.5 text-slate-400">Sentinel-1, CHIRPS, WorldPop, OSM</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Implemented</span></td>
                    <td className="p-2.5 text-slate-400">Cached pipeline dependencies with deterministic raster extraction</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Processing</td>
                    <td className="p-2.5 text-slate-400">16-cell grid, SAR, HAND, Severity</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Implemented</span></td>
                    <td className="p-2.5 text-slate-400">Module 5 multi-criteria severity with raster point sampling fallback</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Decision Engines</td>
                    <td className="p-2.5 text-slate-400">OR-Tools MILP, LinUCB, Proportional</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Implemented</span></td>
                    <td className="p-2.5 text-slate-400">Module 6, Module 8 multi-step disruptions & Module 9 shortage transfers</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Serving & API</td>
                    <td className="p-2.5 text-slate-400">FastAPI & SQLite Run Store</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Implemented</span></td>
                    <td className="p-2.5 text-slate-400">REST endpoints, lock-protected run persistence, GeoJSON exports</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Web interface</td>
                    <td className="p-2.5 text-slate-400">React + Vite + Deck.gl / MapLibre</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Implemented</span></td>
                    <td className="p-2.5 text-slate-400">Full command console, swipe comparison, step timeline & offline mode</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Authentication</td>
                    <td className="p-2.5 text-slate-400">Demo RBAC (viewer / operator)</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20">Demo-Level</span></td>
                    <td className="p-2.5 text-slate-400">JWT & salted client hash. No production user auth or MFA</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium text-slate-200">Live Dispatch</td>
                    <td className="p-2.5 text-slate-400">Municipal fleet telematics & GPS</td>
                    <td className="p-2.5"><span className="px-2 py-0.5 rounded bg-slate-500/10 text-slate-400 border border-slate-500/20">Planned</span></td>
                    <td className="p-2.5 text-slate-400">Vehicle tracking, driver mobile app, dynamic live inventory sync</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* React Bits Attribution */}
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                React Bits Component Integration
              </h3>
              <a
                href="https://reactbits.dev"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] font-mono text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/25 transition-colors"
              >
                <span>reactbits.dev</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <p className="text-xs text-slate-400 mb-3">
              Modern interactive and motion components tailored and integrated throughout ResQ:
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">Aurora</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-400">Canvas</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Landing ambient mesh</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">GradientText</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-purple-500/10 text-purple-400">Typography</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Hero animated headline</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">SpotlightCard</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-blue-500/10 text-blue-400">Cursor</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Bento card radial glows</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">StarBorder</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400">Button</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Rotating pulse aura</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">Dock</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-400">Toolbar</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Map layer dock bar</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">CountUp</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400">Easing</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Inventory metric ticks</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">AnimatedList</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-rose-500/10 text-rose-400">Feed</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Escalation modal stream</p>
              </div>
              <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 hover:border-cyan-500/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-cyan-300">Stepper</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-teal-500/10 text-teal-400">Workflow</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Guided scenario walkthrough</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-white/10 bg-white/[0.02]">
          <span className="text-xs text-slate-500 font-mono">
            ResQ · Bantwal Taluk Replay Environment
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-slate-200 text-xs font-medium transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
};
