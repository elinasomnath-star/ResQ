import React, { useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Boxes, MapPinned, Navigation, Waves } from 'lucide-react';
import Aurora from '../components/reactbits/Aurora';
import GradientText from '../components/reactbits/GradientText';
import SpotlightCard from '../components/reactbits/SpotlightCard';
import StarBorder from '../components/reactbits/StarBorder';
import '../styles/LandingView.css';

interface LandingViewProps {
  onLaunchConsole: () => void;
}

const events = [
  { date: '2019-08-10', year: '2019', stage: 11.6, descriptor: 'Severe event' },
  { date: '2024-07-31', year: '2024', stage: 9.3, descriptor: 'Severe flood event' },
  { date: '2026-08-03', year: '2026', stage: 8.5, descriptor: 'Danger-level event' },
];

export const LandingView: React.FC<LandingViewProps> = ({ onLaunchConsole }) => {
  const [activeEvent, setActiveEvent] = useState(events[1]);
  const atDanger = activeEvent.stage >= 8.0;
  const atWarning = activeEvent.stage >= 7.0;
  const stageStatus = atDanger ? 'Danger level reached' : atWarning ? 'Warning level reached' : 'Below warning';

  return (
    <main className="landing-shell">
      {/* ── Header: Pushed to extremes like a real webpage ── */}
      <header className="landing-nav">
        <a className="landing-brand" href="#top" aria-label="ResQ home">
          <span className="landing-brand-mark"><Waves size={20} /></span>
          <span>ResQ<span className="landing-brand-dot">/</span></span>
        </a>
        <div className="landing-nav-meta">
          <span className="landing-live-dot" />
          <span>BANTWAL &middot; DAKSHINA KANNADA</span>
        </div>
        <button className="landing-nav-button" onClick={onLaunchConsole}>
          <span>Open response console</span>
          <ArrowUpRight size={15} />
        </button>
      </header>

      {/* ── Hero Section (Content & Layout 100% Intact) ── */}
      <section id="top" className="landing-hero">
        <div className="landing-aurora" aria-hidden="true">
          <Aurora colorStops={['#20D6D0', '#6477FF', '#AA6DFF']} speed={0.25} amplitude={0.5} />
        </div>
        <div className="landing-orb landing-orb-one" />
        <div className="landing-orb landing-orb-two" />
        <div className="landing-copy">
          <p className="landing-eyebrow">
            <span className="landing-eyebrow-icon"><Waves size={13} /></span>
            <span>DISASTER RESPONSE &nbsp;/&nbsp; FIELD DECISION SUPPORT</span>
          </p>
          <h1>When the river rises,<br /><GradientText colors={['#72E5E4', '#8AA2FF', '#C09AFF', '#72E5E4']} animationSpeed={9}>every route matters.</GradientText></h1>
          <p className="landing-intro">Explore how river conditions, a local road network and zone priorities come together in a relief-allocation planning workspace for Bantwal.</p>

          <div className="landing-actions">
            <StarBorder color="#20D6D0" speed="3.2s" onClick={onLaunchConsole} className="landing-launch">
              Explore ResQ <ArrowUpRight size={16} />
            </StarBorder>
            <a className="landing-secondary" href="#how-it-works">See the workflow <ArrowDownRight size={15} /></a>
          </div>

          <div className="landing-stats" aria-label="Project scope">
            <div className="landing-stat"><span className="landing-stat-icon"><MapPinned size={17} /></span><div><strong>16</strong><span>Bantwal grid zones</span></div></div>
            <div className="landing-stat"><span className="landing-stat-icon"><Waves size={17} /></span><div><strong>03</strong><span>documented events</span></div></div>
            <div className="landing-stat"><span className="landing-stat-icon"><Boxes size={17} /></span><div><strong>03</strong><span>allocation engines</span></div></div>
          </div>
        </div>

        <div className="landing-visual">
          <div className="landing-map-shell">
            <div className="landing-map-frame">
              <img src="/data/bantwal_hero_map.svg" alt="Bantwal flood planning map showing Netravati River, relief shelter and response routes" />
              <span className="landing-map-pulse shelter-pulse" aria-hidden="true">
                <i className="pulse-ring-1" />
                <i className="pulse-ring-2" />
                <b className="pulse-core" />
              </span>
            </div>
          </div>

          <SpotlightCard className="landing-route-card" spotlightColor="rgba(113, 144, 255, .28)">
            <div className="floating-card-heading"><span className="floating-card-icon route-icon"><Navigation size={15} /></span><span><small>NETWORK VIEW</small><strong>Road access, zone by zone</strong></span></div>
            <div className="route-mini-graphic"><span className="route-node" /><i /><i /><i /><span className="route-target"><MapPinned size={12} /></span></div>
            <div className="floating-card-foot"><span>779 clipped road features</span><span>16 grid zones</span></div>
          </SpotlightCard>

          <SpotlightCard className="landing-gauge-card" spotlightColor="rgba(42, 216, 205, .26)">
            <div className="floating-card-heading"><span className="floating-card-icon gauge-icon"><Waves size={15} /></span><span><small>EVENT GAUGE PEAK</small><strong>Netravati at Bantwal</strong></span></div>
            <div className="event-selector" role="group" aria-label="Choose documented event">
              {events.map((event) => <button key={event.date} className={activeEvent.date === event.date ? 'active' : ''} onClick={() => setActiveEvent(event)}>{event.year}</button>)}
            </div>
            <div className="gauge-summary"><div><strong>{activeEvent.stage.toFixed(1)}<small>m</small></strong><span>{activeEvent.descriptor}</span></div><div className={`gauge-status-pill ${atDanger ? 'danger' : atWarning ? 'warning' : ''}`}><i />{stageStatus}</div></div>
            <div className="gauge-scale"><span>Warning 7.0 m</span><span>Danger 8.0 m</span></div>
            <div className="gauge-bar"><i style={{ width: `${Math.min(100, activeEvent.stage / 12 * 100)}%` }} /><b className="warning-mark" style={{ left: '58.3%' }} /><b className="danger-mark" style={{ left: '66.6%' }} /></div>
          </SpotlightCard>
        </div>
      </section>

      {/* ── Bottom Section: Modern cards with edge-to-edge footer ── */}
      <section id="how-it-works" className="landing-bottom">
        <div className="landing-bottom-heading">
          <div>
            <span>THE RESQ WORKSPACE</span>
            <h2>From local context to a response plan.</h2>
          </div>
          <div className="landing-live-badge">
            <span className="badge-glow-dot" />
            <span>Interactive field simulation</span>
          </div>
        </div>

        <div className="landing-pillars">
          <article className="pillar-card pillar-teal">
            <span className="pillar-tag">01 / SITUATION</span>
            <h3>Read the conditions</h3>
            <p>Review sourced gauge stages, rainfall context and the candidate Sentinel-1 change signal across Bantwal.</p>
          </article>
          <article className="pillar-card pillar-violet">
            <span className="pillar-tag">02 / PRIORITY</span>
            <h3>Compare the zones</h3>
            <p>Explore modeled severity and WorldPop estimates across the 16 Bantwal planning grid zones.</p>
          </article>
          <article className="pillar-card pillar-blue">
            <span className="pillar-tag">03 / RESPONSE</span>
            <h3>Trace a delivery plan</h3>
            <p>Compare allocation approaches, inspect delivery routes and block mapped Bantwal roads to see live rerouting.</p>
          </article>
        </div>
      </section>

      {/* ── Footer: Pushed to extremes like a real webpage ── */}
      <footer className="landing-footer">
        <div className="footer-left">
          <span className="footer-brand font-heading font-bold text-white">ResQ</span>
          <span className="footer-sub">&middot; Bantwal Disaster Response Planning Workspace</span>
        </div>
        <div className="footer-right">
          <span>Documented event replays &middot; Assumed inventory &middot; Planning support, not live dispatch</span>
        </div>
      </footer>
    </main>
  );
};

export default LandingView;
