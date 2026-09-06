import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { MessageSquare, Database, Bot, LogOut, Activity } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import styles from './AppShell.module.css';

export const AppShell: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className={styles.appContainer}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2>MRPL AI</h2>
        </div>
        
        <nav className={styles.nav}>
          <NavLink 
            to="/" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
            end
          >
            <MessageSquare className={styles.navIcon} />
            Chat
          </NavLink>
          <NavLink 
            to="/documents" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <Database className={styles.navIcon} />
            Documents
          </NavLink>
          <NavLink 
            to="/observability" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <Activity className={styles.navIcon} />
            Observability
          </NavLink>
          <NavLink 
            to="/agents" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <Bot className={styles.navIcon} />
            Agents
          </NavLink>
        </nav>
        
        <div className={styles.sidebarFooter}>
          <div className={styles.userInfo}>
            <span className={styles.userName}>{user?.email?.split('@')[0] || 'User'}</span>
            <span className={styles.userRole}>{user?.role || 'Engineer'}</span>
          </div>
          <button className={styles.logoutBtn} onClick={handleLogout} title="Log out">
            <LogOut size={18} />
          </button>
        </div>
      </aside>
      
      <main className={styles.mainContent}>
        <Outlet />
      </main>
    </div>
  );
};
