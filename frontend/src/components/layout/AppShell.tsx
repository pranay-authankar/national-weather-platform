import type { FC, ReactNode } from 'react';
import Sidebar, { type NavigationTab } from './Sidebar';
import Header from './Header';

interface AppShellProps {
  activeTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
  children: ReactNode;
}

export const AppShell: FC<AppShellProps> = ({ activeTab, onSelectTab, children }) => {
  return (
    <div className="app-shell">
      <Sidebar activeTab={activeTab} onSelectTab={onSelectTab} />
      <div className="app-shell-body">
        <Header />
        <main className="app-content-area" role="main">
          {children}
        </main>
      </div>
    </div>
  );
};

export default AppShell;
