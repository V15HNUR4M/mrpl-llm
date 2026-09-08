import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { MessageSquare, Database, Bot, LogOut, Activity, ShieldCheck, Cpu, Users as UsersIcon } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import styles from './AppShell.module.css';

export const AppShell: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const username = user?.username || user?.email?.split('@')[0] || 'Engineer';
  const initials = username.slice(0, 2).toUpperCase();

  return (
    <div className={styles.appContainer}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <div className={styles.brandBadge}>
            <div className={styles.brandIconWrap}>
              <Cpu size={18} className={styles.brandIcon} />
            </div>
            <div className={styles.brandText}>
              <div className={styles.brandTitle}>MRPL</div>
              <div className={styles.brandSubtitle}>AI WORKBENCH</div>
            </div>
          </div>
          <div className={styles.brandTagline}>Private • On-Premise AI</div>
        </div>
        
        <nav className={styles.nav} aria-label="Main Navigation">
          <div className={styles.navGroupLabel}>WORKSPACE</div>
          <NavLink 
            to="/" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
            end
          >
            <MessageSquare className={styles.navIcon} size={18} />
            <span className={styles.navLabel}>Chat</span>
          </NavLink>
          <NavLink 
            to="/documents" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <Database className={styles.navIcon} size={18} />
            <span className={styles.navLabel}>Documents</span>
          </NavLink>
          
          <div className={styles.navGroupLabel}>OPERATIONS & CONTROL</div>
          <NavLink 
            to="/observability" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <Activity className={styles.navIcon} size={18} />
            <span className={styles.navLabel}>Observability</span>
          </NavLink>
          <NavLink 
            to="/evaluation" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <ShieldCheck className={styles.navIcon} size={18} />
            <span className={styles.navLabel}>Evaluation</span>
          </NavLink>
          <NavLink 
            to="/agents" 
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
          >
            <Bot className={styles.navIcon} size={18} />
            <span className={styles.navLabel}>Agents</span>
          </NavLink>
          {user?.role === 'ADMIN' && (
            <NavLink 
              to="/users" 
              className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
            >
              <UsersIcon className={styles.navIcon} size={18} />
              <span className={styles.navLabel}>User Management</span>
            </NavLink>
          )}
        </nav>

        <div className={styles.systemStatus}>
          <span className={styles.statusDot}></span>
          <span className={styles.statusText}>Sovereign System Online</span>
        </div>
        
        <div className={styles.sidebarFooter}>
          <div className={styles.userCard}>
            <div className={styles.userAvatar}>
              {initials}
            </div>
            <div className={styles.userInfo}>
              <span className={styles.userName}>{username}</span>
              <span className={styles.userRole}>{user?.role || 'ENGINEER'}</span>
            </div>
          </div>
          <button 
            type="button" 
            className={styles.logoutBtn} 
            onClick={handleLogout} 
            title="Log out" 
            aria-label="Log out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      
      <main className={styles.mainContent}>
        <Outlet />
      </main>
    </div>
  );
};

