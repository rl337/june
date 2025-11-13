import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ChatInterface from './components/ChatInterface';
import LoginForm from './components/LoginForm';
import AdminLoginForm from './components/AdminLoginForm';
import { AuthProvider, useAuth } from './hooks/AuthContext';
import AdminLayout from './components/admin/AdminLayout';
import ProtectedRoute from './components/admin/ProtectedRoute';
import ErrorBoundary from './components/admin/ErrorBoundary';

// Admin components
import AdminOverview from './components/admin/AdminOverview';
import UserList from './components/admin/UserList';
import UserDetail from './components/admin/UserDetail';
import UserForm from './components/admin/UserForm';
import BotManagement from './components/admin/BotManagement';
import ConversationManagement from './components/admin/ConversationManagement';
import SystemConfig from './components/admin/SystemConfig';
import AnalyticsDashboard from './components/admin/AnalyticsDashboard';
import SystemMonitoring from './components/admin/SystemMonitoring';

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Router>
          <div className="App">
            <MainApp />
          </div>
        </Router>
      </AuthProvider>
    </ErrorBoundary>
  );
}

function MainApp() {
  const { isAuthenticated, user } = useAuth();

  return (
    <Routes>
      {/* Admin Routes */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute requireAdmin={true}>
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<AdminOverview />} />
        <Route path="users" element={<UserList />} />
        <Route path="users/new" element={<UserForm />} />
        <Route path="users/:userId" element={<UserDetail />} />
        <Route path="users/:userId/edit" element={<UserForm />} />
        <Route path="bot" element={<BotManagement />} />
        <Route path="conversations" element={<ConversationManagement />} />
        <Route path="config" element={<SystemConfig />} />
        <Route path="analytics" element={<AnalyticsDashboard />} />
        <Route path="monitoring" element={<SystemMonitoring />} />
        <Route path="login" element={<AdminLoginForm />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Route>

      {/* Regular Chat Interface - requires authentication */}
      <Route
        path="/"
        element={
          !isAuthenticated ? (
            <LoginForm />
          ) : (
            <div className="h-screen bg-telegram-light">
              <ChatInterface user={user!} />
            </div>
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;





