import { useState } from 'react';
import AppShell from './components/layout/AppShell';
import type { NavigationTab } from './components/layout/Sidebar';
import DashboardPage from './pages/DashboardPage';
import MapPage from './pages/MapPage';
import AnalyticsPage from './pages/AnalyticsPage';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('dashboard');

  return (
    <AppShell activeTab={activeTab} onSelectTab={setActiveTab}>
      {activeTab === 'dashboard' && <DashboardPage />}

      {activeTab === 'map' && <MapPage />}

      {activeTab === 'analytics' && <AnalyticsPage />}

      {activeTab === 'reports' && (
        <div className="module-placeholder">
          <div className="page-header">
            <h2 className="page-title">Citizen Weather Reports</h2>
            <p className="page-subtitle">
              Public crowdsourced incident submissions and localized ground observations.
            </p>
          </div>
          <div className="placeholder-box">
            <p className="placeholder-text">Citizen reporting interface scheduled for upcoming module task.</p>
          </div>
        </div>
      )}

      {activeTab === 'verification' && (
        <div className="module-placeholder">
          <div className="page-header">
            <h2 className="page-title">Event Verification & Audit</h2>
            <p className="page-subtitle">
              Operational quality queue for unverified events, confidence scoring, and duplicate cross-checks.
            </p>
          </div>
          <div className="placeholder-box">
            <p className="placeholder-text">Verification queue scheduled for upcoming module task.</p>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default App;
