import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { fetchMetrics } from './api/client';
import { ModelProvider } from './context/ModelContext';
import { Sidebar } from './components/Sidebar';
import { MobileNavbar } from './components/MobileNavbar';
import { DisputesPage } from './pages/DisputesPage';
import { CaseDetailPage } from './pages/CaseDetailPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { SettingsPage } from './pages/SettingsPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import './App.css';

export default function App() {
  const [pendingCount, setPendingCount] = useState(0);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(() => {
    return localStorage.getItem('raven_sidebar_collapsed') === 'true';
  });

  const refreshMetrics = async () => {
    try {
      const m = await fetchMetrics();
      setPendingCount(m?.pending_review || 0);
    } catch {
      // ignore network glitch
    }
  };

  useEffect(() => {
    refreshMetrics();

    // Re-fetch metrics whenever disputes are investigated, reviewed, or submitted
    window.addEventListener('raven:data-updated', refreshMetrics);
    window.addEventListener('focus', refreshMetrics);

    // Keep sidebar and metrics live with 30-second polling
    const interval = setInterval(refreshMetrics, 30000);

    return () => {
      window.removeEventListener('raven:data-updated', refreshMetrics);
      window.removeEventListener('focus', refreshMetrics);
      clearInterval(interval);
    };
  }, []);

  const handleToggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('raven_sidebar_collapsed', String(next));
      return next;
    });
  };

  return (
    <BrowserRouter>
      <ModelProvider>
        <div className={`app-layout ${isCollapsed ? 'sidebar-collapsed' : ''}`}>
          {/* Mobile Top App Bar (Visible on <= 768px screens) */}
          <MobileNavbar 
            onToggleSidebar={() => setIsMobileNavOpen((prev) => !prev)} 
            pendingCount={pendingCount} 
          />

          {/* Sidebar (Full desktop, slim strip, or mobile drawer) */}
          <Sidebar 
            pendingCount={pendingCount} 
            isOpen={isMobileNavOpen}
            onClose={() => setIsMobileNavOpen(false)}
            isCollapsed={isCollapsed}
            onToggleCollapse={handleToggleCollapse}
          />

          <main className="main-content">
            <Routes>
              <Route path="/" element={<DisputesPage initialMode="queue" />} />
              <Route path="/disputes" element={<DisputesPage initialMode="queue" />} />
              <Route path="/history" element={<DisputesPage initialMode="history" />} />
              <Route path="/cases" element={<DisputesPage initialMode="queue" />} />
              <Route path="/cases/:caseId" element={<CaseDetailPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/integrations" element={<IntegrationsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </div>
      </ModelProvider>
    </BrowserRouter>
  );
}
