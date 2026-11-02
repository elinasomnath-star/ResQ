import React, { useState, useEffect } from 'react';
import { LandingView } from './views/LandingView';
import { LoginView } from './views/LoginView';
import { ConsoleView } from './views/ConsoleView';
import { User } from './types';
import { api } from './services/api';

export function App() {
  // Check if URL requests direct console
  const getInitialView = (): 'landing' | 'login' | 'console' => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('view') === 'console' || window.location.hash === '#console') {
        return 'console';
      }
      if (params.get('view') === 'login' || window.location.hash === '#login') {
        return 'login';
      }
    }
    return 'landing';
  };

  const [activeView, setActiveView] = useState<'landing' | 'login' | 'console'>(getInitialView);
  const [user, setUser] = useState<User | null>(null);
  const [offlineMode, setOfflineMode] = useState<boolean>(false);
  const [sessionExpiredMsg, setSessionExpiredMsg] = useState<string | null>(null);

  // Check existing session on mount & probe backend health
  useEffect(() => {
    let isMounted = true;
    const checkSession = async () => {
      try {
        const isHealthy = await api.checkBackendHealth();
        api.setOfflineMode(!isHealthy);
        setOfflineMode(!isHealthy);
        const currentUser = await api.getMe();
        if (isMounted && currentUser) {
          setUser(currentUser);
        }
      } catch {
        // Session not yet established
      }
    };
    checkSession();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleToggleOffline = () => {
    const nextVal = !offlineMode;
    setOfflineMode(nextVal);
    api.setOfflineMode(nextVal);
  };

  const handleToggleRole = () => {
    const nextRole = user?.role === 'operator' ? 'viewer' : 'operator';
    const nextUser: User = { username: nextRole, role: nextRole };
    setUser(nextUser);
    sessionStorage.setItem('resq_user', JSON.stringify(nextUser));
  };

  const handleLoginSuccess = (authenticatedUser: User) => {
    setUser(authenticatedUser);
    setSessionExpiredMsg(null);
    setActiveView('console');
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      // Ignore
    } finally {
      setUser({ username: 'viewer', role: 'viewer' });
      setActiveView('login');
    }
  };

  const handleLaunchConsole = () => {
    setActiveView('login');
  };

  return (
    <div className="min-h-screen w-full bg-ink-950 text-text-primary selection:bg-accent-cyan/30 selection:text-accent-cyan">
      {sessionExpiredMsg && activeView === 'login' && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl bg-accent-alert/20 border border-accent-alert/40 text-accent-alert text-xs font-mono font-medium shadow-2xl backdrop-blur-md">
          {sessionExpiredMsg}
        </div>
      )}

      {activeView === 'landing' && (
        <LandingView onLaunchConsole={handleLaunchConsole} />
      )}

      {activeView === 'login' && (
        <LoginView onLoginSuccess={handleLoginSuccess} />
      )}

      {activeView === 'console' && (
        <ConsoleView
          user={user}
          onLogout={handleLogout}
          onToggleRole={handleToggleRole}
          onNavigateHome={() => setActiveView('landing')}
          offlineMode={offlineMode}
          onToggleOffline={handleToggleOffline}
        />
      )}
    </div>
  );
}

export default App;
