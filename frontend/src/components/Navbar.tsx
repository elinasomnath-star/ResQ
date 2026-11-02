import React from 'react';
import {
  Waves,
  Shield,
  Layers,
  BarChart3,
  AlertTriangle,
  Info,
  LogOut,
  Settings,
} from 'lucide-react';
import { User } from '../types';

interface NavbarProps {
  user: User | null;
  onLogout: () => void;
  onToggleRole?: () => void;
  onNavigateHome?: () => void;
  offlineMode: boolean;
  onToggleOffline: () => void;
  onOpenCompare: () => void;
  onOpenEscalations: () => void;
  onOpenAbout: () => void;
  onOpenScenarios?: () => void;
  onOpenInventory?: () => void;
  onOpenOverride?: () => void;
  alertCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  user,
  onLogout,
  onToggleRole,
  onNavigateHome,
  offlineMode,
  onToggleOffline,
  onOpenCompare,
  onOpenEscalations,
  onOpenAbout,
  onOpenScenarios,
  onOpenInventory,
  onOpenOverride,
  alertCount,
}) => {
  const isOperator = user?.role === 'operator';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-white/[0.08] bg-[#04070D]/90 backdrop-blur-2xl">
      <div className="flex items-center justify-between gap-3 w-full px-5 lg:px-8 h-14">
        {/* Brand */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onNavigateHome}
            title="Return to Story Overview"
            className="flex items-center gap-2.5 group cursor-pointer focus:outline-none text-left"
          >
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-400 via-sky-400 to-indigo-500 flex items-center justify-center shadow-[0_0_20px_rgba(34,211,238,0.45)] border border-cyan-200/50 group-hover:shadow-[0_0_26px_rgba(34,211,238,0.7)] group-hover:scale-105 transition-all flex-shrink-0">
              <Waves className="w-4 h-4 text-ink-950 stroke-[2.5]" />
            </div>
            <div className="flex flex-col leading-none gap-0.5">
              <span className="font-heading text-[16px] font-black tracking-tight text-white drop-shadow-[0_0_12px_rgba(255,255,255,0.45)] group-hover:text-cyan-100 group-hover:drop-shadow-[0_0_18px_rgba(34,211,238,0.65)] transition-all">
                ResQ
              </span>
              <span className="text-[10.5px] font-mono font-bold tracking-wider text-cyan-300 drop-shadow-[0_0_8px_rgba(34,211,238,0.75)] group-hover:text-cyan-200 transition-colors">
                Bantwal
              </span>
            </div>
          </button>

          <div className="hidden lg:flex items-center gap-2 border-l border-white/[0.12] pl-3">
            <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-violet-950/60 text-violet-300 border border-violet-400/40 font-bold tracking-widest shadow-[0_0_12px_rgba(167,139,250,0.2)]">
              ASSUMED INVENTORY
            </span>
          </div>
        </div>

        {/* Center Navigation */}
        <div className="flex items-center gap-1.5">
          {/* Scenarios */}
          {onOpenScenarios && (
            <button
              onClick={onOpenScenarios}
              className="flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1.5 rounded-lg border border-purple-500/30 bg-purple-500/[0.08] text-purple-300 hover:bg-purple-500/15 hover:border-purple-400/50 transition-all"
              title="Open benchmark scenario deck"
            >
              <Layers className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Scenarios</span>
            </button>
          )}

          {/* Shelters */}
          {onOpenInventory && (
            <button
              onClick={onOpenInventory}
              className="flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1.5 rounded-lg border border-amber-500/30 bg-amber-500/[0.08] text-amber-300 hover:bg-amber-500/15 hover:border-amber-400/50 transition-all"
              title="Inspect and edit shelter inventory"
            >
              <Shield className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Shelters</span>
            </button>
          )}

          {/* Admin Override */}
          {isOperator && onOpenOverride && (
            <button
              onClick={onOpenOverride}
              className="flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1.5 rounded-lg border border-amber-400/50 bg-amber-400/10 text-amber-200 hover:bg-amber-400/20 transition-all"
              title="Manual allocation override"
            >
              <Settings className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Override</span>
            </button>
          )}

          {/* Compare */}
          <button
            onClick={onOpenCompare}
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-text-secondary hover:text-text-primary hover:border-white/15 hover:bg-white/[0.06] transition-all"
            title="Compare allocation engines"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Compare</span>
          </button>

          {/* Alerts */}
          <button
            onClick={onOpenEscalations}
            className="relative flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-text-secondary hover:text-text-primary hover:border-white/15 hover:bg-white/[0.06] transition-all"
            title="Shortage alerts"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-accent-alert" />
            <span className="hidden sm:inline">Alerts</span>
            {alertCount > 0 && (
              <span className="flex items-center justify-center w-4 h-4 text-[9px] font-bold rounded-full bg-accent-alert text-white">
                {alertCount}
              </span>
            )}
          </button>

          {/* About */}
          <button
            onClick={onOpenAbout}
            className="flex items-center p-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-text-secondary hover:text-text-primary hover:border-white/15 transition-all"
            title="Data sources & limitations"
          >
            <Info className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Right side: status + user */}
        <div className="flex items-center gap-2">
          {/* Online/Offline toggle */}
          <button
            onClick={onToggleOffline}
            title="Toggle online / offline mode"
            className={`text-[10px] font-mono px-2.5 py-1 rounded-full border transition-all cursor-pointer flex items-center gap-1.5 font-semibold tracking-wider ${
              offlineMode
                ? 'border-amber-500/35 bg-amber-500/10 text-amber-300 hover:bg-amber-500/18'
                : 'border-emerald-500/35 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/18'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${offlineMode ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'}`} />
            {offlineMode ? 'OFFLINE' : 'ONLINE'}
          </button>

          {/* Role switcher */}
          {user && (
            <button
              onClick={onToggleRole}
              className={`flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all cursor-pointer ${
                user.role === 'operator'
                  ? 'border-accent-indigo/50 bg-accent-indigo/15 text-accent-indigo hover:bg-accent-indigo/25 shadow-[0_0_12px_rgba(99,102,241,0.2)]'
                  : 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20'
              }`}
              title="Click to switch role"
            >
              <Shield className="w-3 h-3" />
              <span className="capitalize">{user.role}</span>
              <span className="text-[9px] opacity-60 underline ml-0.5 font-normal">(switch)</span>
            </button>
          )}

          {/* Logout */}
          <button
            onClick={onLogout}
            aria-label="Sign out"
            className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-accent-alert transition-colors p-1.5 rounded-lg hover:bg-white/[0.04]"
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
