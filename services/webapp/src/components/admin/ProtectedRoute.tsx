import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../hooks/AuthContext';
import AdminLoginForm from '../AdminLoginForm';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ 
  children, 
  requireAdmin = false 
}) => {
  const { isAuthenticated, isAdmin } = useAuth();

  if (!isAuthenticated) {
    if (requireAdmin) {
      return <AdminLoginForm />;
    }
    return <Navigate to="/" replace />;
  }

  if (requireAdmin && !isAdmin) {
    return <AdminLoginForm />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
