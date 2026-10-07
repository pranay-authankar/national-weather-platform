import type { FC } from 'react';
import { Server } from 'lucide-react';

export const Header: FC = () => {
  return (
    <header className="app-header">
      <div className="header-titles">
        <h1 className="header-app-name">National Weather Intelligence Platform</h1>
        <p className="header-app-sub">Disaster Management & Weather Analytics</p>
      </div>

      <div className="header-actions">
        <div className="api-status-badge neutral" title="Backend health check has not been initiated">
          <Server size={14} className="status-icon" aria-hidden="true" />
          <span className="status-dot"></span>
          <span className="status-text">API status: Not checked</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
