import { useState } from 'react';
import AppShell from './components/layout/AppShell';
import type { NavigationTab } from './components/layout/Sidebar';
import DashboardPage from './pages/DashboardPage';
import MapPage from './pages/MapPage';
import AnalyticsPage from './pages/AnalyticsPage';
import ReportsPage from './pages/ReportsPage';
import VerificationPage from './pages/VerificationPage';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('dashboard');

  return (
    <AppShell activeTab={activeTab} onSelectTab={setActiveTab}>
      {activeTab === 'dashboard' && <DashboardPage />}

      {activeTab === 'map' && <MapPage />}

      {activeTab === 'analytics' && <AnalyticsPage />}

      {activeTab === 'reports' && <ReportsPage />}

      {activeTab === 'verification' && <VerificationPage />}
    </AppShell>
  );
}

export default App;
