import React, { useState, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import LoginForm from './components/LoginForm';
import { useAuth } from './hooks/useAuth';
import { AuthProvider } from './hooks/AuthContext';

function App() {
  return (
    <AuthProvider>
      <div className="App">
        <MainApp />
      </div>
    </AuthProvider>
  );
}

function MainApp() {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <LoginForm />;
  }

  return (
    <div className="h-screen bg-telegram-light">
      <ChatInterface user={user} />
    </div>
  );
}

export default App;




