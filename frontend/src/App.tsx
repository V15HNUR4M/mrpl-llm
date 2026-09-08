import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { GenerationProvider } from './context/GenerationContext';
import { AppShell } from './layouts/AppShell';
import { Login } from './pages/Login';
import { ChatWorkspace } from './pages/ChatWorkspace';
import { Documents } from './pages/Documents';
import { Observability } from './pages/Observability';
import { Evaluation } from './pages/Evaluation';
import { Agents } from './pages/Agents';
import { Users } from './pages/Users';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: 'var(--color-surface-sunken)' }}>
        <div className="spinner dark"></div>
      </div>
    );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  return <>{children}</>;
};

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: 'var(--color-surface-sunken)' }}>
        <div className="spinner dark"></div>
      </div>
    );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (user.role !== 'ADMIN') {
    return <Navigate to="/" replace />;
  }
  
  return <>{children}</>;
};

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <GenerationProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            
            <Route path="/" element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }>
              <Route index element={<ChatWorkspace />} />
              <Route path="documents" element={<Documents />} />
              <Route path="observability" element={<Observability />} />
              <Route path="evaluation" element={<Evaluation />} />
              <Route path="agents" element={<Agents />} />
              <Route path="users" element={
                <AdminRoute>
                  <Users />
                </AdminRoute>
              } />
            </Route>
          </Routes>
        </GenerationProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
