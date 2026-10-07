import type { FC } from 'react';
import {
  LayoutDashboard,
  Map,
  BarChart3,
  FileText,
  ShieldCheck,
  Radio,
} from 'lucide-react';

export type NavigationTab = 'dashboard' | 'map' | 'analytics' | 'reports' | 'verification';

interface SidebarProps {
  activeTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
}

interface NavItem {
  id: NavigationTab;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: readonly NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'map', label: 'Live Map', icon: Map },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'reports', label: 'Citizen Reports', icon: FileText },
  { id: 'verification', label: 'Verification', icon: ShieldCheck },
];

export const Sidebar: FC<SidebarProps> = ({ activeTab, onSelectTab }) => {
  return (
    <aside className="app-sidebar" aria-label="Main Navigation">
      <div className="sidebar-brand">
        <div className="brand-icon-box">
          <Radio className="brand-icon" size={20} aria-hidden="true" />
        </div>
        <div className="brand-text">
          <span className="brand-title">NW-BDAP</span>
          <span className="brand-sub">Disaster Cell</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-group-label">Intelligence Modules</div>
        <ul className="nav-list">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <li key={item.id} className="nav-item">
                <button
                  type="button"
                  className={`nav-link ${isActive ? 'active' : ''}`}
                  onClick={() => onSelectTab(item.id)}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon className="nav-icon" size={18} aria-hidden="true" />
                  <span className="nav-label">{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <div className="system-pill">
          <span className="pill-dot"></span>
          <span>PS ID 26069</span>
        </div>
        <div className="system-desc">National Disaster Analytics</div>
      </div>
    </aside>
  );
};

export default Sidebar;
