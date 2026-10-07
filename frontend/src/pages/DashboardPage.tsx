import type { FC } from 'react';
import { Database, ShieldAlert, Layers } from 'lucide-react';

export const DashboardPage: FC = () => {
  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h2 className="page-title">National Weather Dashboard</h2>
        <p className="page-subtitle">
          Real-time monitoring of verified and unverified extreme weather events across India using official meteorological sources and community observations.
        </p>
      </div>

      <div className="empty-state-card">
        <div className="empty-state-icon-box">
          <Database size={36} className="empty-state-icon" aria-hidden="true" />
        </div>
        <h3 className="empty-state-title">No weather data loaded yet</h3>
        <p className="empty-state-desc">
          Connect to the backend API to view current events and analytics.
        </p>
        <div className="empty-state-meta">
          <div className="meta-item">
            <ShieldAlert size={16} className="meta-icon" aria-hidden="true" />
            <span>Supported Sources: IMD, IMD RSS, Open-Meteo, Data.gov.in, Citizen Reports</span>
          </div>
          <div className="meta-item">
            <Layers size={16} className="meta-icon" aria-hidden="true" />
            <span>Data Ingestion: Only live, authentic weather observations are processed</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
