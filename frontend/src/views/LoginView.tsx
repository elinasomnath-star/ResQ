import React, { useState } from 'react';
import { AlertCircle, ArrowRight, Eye, EyeOff, KeyRound, LockKeyhole, Shield, User as UserIcon, Waves } from 'lucide-react';
import { api } from '../services/api';
import type { User } from '../types';
import '../styles/LoginView.css';

interface LoginViewProps {
  onLoginSuccess: (user: User) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('operator');
  const [password, setPassword] = useState('operator2026');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      onLoginSuccess(await api.login(username, password));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Sign in failed. Check the demo credentials.');
    } finally {
      setLoading(false);
    }
  };

  const selectRole = (role: 'viewer' | 'operator') => {
    setUsername(role);
    setPassword(`${role}2026`);
    setError(null);
  };

  return (
    <main className="auth-page">
      {/* ── Background Mesh & Ambient Glow Orbs ── */}
      <div className="auth-ambient-orb auth-orb-1" aria-hidden="true" />
      <div className="auth-ambient-orb auth-orb-2" aria-hidden="true" />

      {/* ── Topbar (Full Extreme Width) ── */}
      <header className="auth-topbar">
        <a className="auth-brand" href="#auth" aria-label="ResQ home">
          <span className="auth-brand-mark"><Waves size={19} /></span>
          <span>ResQ<span className="auth-brand-slash">/</span></span>
        </a>
        <div className="auth-topline">
          <span className="auth-live-indicator" />
          <span>BANTWAL &middot; DISASTER RESPONSE CONSOLE</span>
        </div>
      </header>

      {/* ── Animated Flood Waves Band ── */}
      <div className="auth-flood-band" aria-hidden="true">
        <div className="auth-flood-glow" />
        <svg viewBox="0 0 1440 250" preserveAspectRatio="none">
          <path className="auth-wave auth-wave-back" d="M0,95 C200,25 370,170 590,92 C800,16 970,135 1160,77 C1280,40 1370,48 1440,65 L1440,250 L0,250 Z" />
          <path className="auth-wave auth-wave-front" d="M0,145 C210,80 370,205 620,130 C820,70 1010,172 1190,120 C1300,88 1380,110 1440,98 L1440,250 L0,250 Z" />
        </svg>
        <span className="auth-flood-caption">LOCAL CONTEXT &middot; RAPID FIELD ALLOCATION</span>
      </div>

      {/* ── Main Auth Card ── */}
      <div id="auth" className="auth-main">
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-card-kicker">
            <span className="kicker-icon"><LockKeyhole size={13} /></span>
            <span>SECURE WORKSPACE ACCESS</span>
          </div>

          <h1 id="auth-title">Sign in to ResQ</h1>
          <p className="auth-subtitle">Select a demo role or enter credentials to open the Bantwal response console.</p>

          {/* Interactive Role Switcher */}
          <div className="auth-role-switch" role="group" aria-label="Choose demo role">
            <button
              type="button"
              onClick={() => selectRole('viewer')}
              aria-pressed={username === 'viewer'}
              className={`role-btn ${username === 'viewer' ? 'active' : ''}`}
            >
              <span className="role-icon viewer-icon"><Eye size={16} /></span>
              <span className="role-text">
                <strong>Viewer</strong>
                <small>Read-only simulation replay</small>
              </span>
            </button>
            <button
              type="button"
              onClick={() => selectRole('operator')}
              aria-pressed={username === 'operator'}
              className={`role-btn ${username === 'operator' ? 'active' : ''}`}
            >
              <span className="role-icon operator-icon"><Shield size={16} /></span>
              <span className="role-text">
                <strong>Operator</strong>
                <small>Full allocation controls</small>
              </span>
            </button>
          </div>

          {error && (
            <div className="auth-error" role="alert">
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="auth-field">
              <label htmlFor="auth-username">Username</label>
              <div className="auth-input-wrapper">
                <span className="input-icon"><UserIcon size={15} /></span>
                <input
                  id="auth-username"
                  type="text"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  placeholder="e.g. operator"
                  required
                />
              </div>
            </div>

            <div className="auth-field">
              <label htmlFor="auth-password">Password</label>
              <div className="auth-input-wrapper">
                <span className="input-icon"><KeyRound size={15} /></span>
                <input
                  id="auth-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  placeholder="Enter password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="password-toggle-btn"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading} className="auth-submit">
              <span>{loading ? 'Authenticating…' : 'Enter Command Console'}</span>
              <ArrowRight size={16} />
            </button>
          </form>

          {/* Quick Demo Credentials Footer */}
          <div className="auth-demo-hint">
            <span>Demo:</span>
            <button type="button" onClick={() => selectRole('operator')} className="demo-chip">
              operator / operator2026
            </button>
            <button type="button" onClick={() => selectRole('viewer')} className="demo-chip">
              viewer / viewer2026
            </button>
          </div>
        </section>
      </div>

      {/* ── Footer (Pushed to Extremes) ── */}
      <footer className="auth-footer">
        <span className="footer-left-meta">ResQ &middot; Bantwal Taluk, Karnataka &middot; Field Decision Support</span>
        <span className="footer-right-meta">Documented Event Replays &middot; Assumed Inventory Prototype</span>
      </footer>
    </main>
  );
};

export default LoginView;
