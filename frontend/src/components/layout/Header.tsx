import { useState, useEffect, type FC } from 'react';
import { Server } from 'lucide-react';
import { getHealth } from '../../services/healthApi';

type HealthStatus = 'checking' | 'online' | 'offline';

export const Header: FC = () => {
  const [status, setStatus] = useState<HealthStatus>('checking');

  useEffect(() => {
    let isMounted = true;

    getHealth()
      .then((response) => {
        if (!isMounted) return;
        if (response?.status === 'ok') {
          setStatus('online');
        } else {
          setStatus('offline');
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setStatus('offline');
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const getStatusBadgeProps = () => {
    switch (status) {
      case 'online':
        return {
          className: 'api-status-badge online',
          text: 'API status: Online',
          title: 'Backend API is online',
        };
      case 'offline':
        return {
          className: 'api-status-badge offline',
          text: 'API status: Offline',
          title: 'Backend API is unavailable',
        };
      case 'checking':
      default:
        return {
          className: 'api-status-badge checking',
          text: 'API status: Checking...',
          title: 'Checking backend API health',
        };
    }
  };

  const badge = getStatusBadgeProps();

  return (
    <header className="app-header">
      <div className="header-titles">
        <h1 className="header-app-name">National Weather Intelligence Platform</h1>
        <p className="header-app-sub">Disaster Management & Weather Analytics</p>
      </div>

      <div className="header-actions">
        <div className={badge.className} title={badge.title}>
          <Server size={14} className="status-icon" aria-hidden="true" />
          <span className="status-dot"></span>
          <span className="status-text">{badge.text}</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
