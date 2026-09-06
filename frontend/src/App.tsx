import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { AppShell } from './layouts/AppShell';
import { Login } from './pages/Login';
import { ChatWorkspace } from './pages/ChatWorkspace';
import { Documents } from './pages/Documents';
import { Observability } from './pages/Observability';
import { Evaluation } from './pages/Evaluation';

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

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
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
            <Route path="agents" element={
              <div style={{ padding: 48, textAlign: 'center', color: 'var(--color-text-muted)' }}>
                <h2>Agents Management</h2>
                <p>Status indicators and configuration coming in a later track.</p>
              </div>
            } />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
