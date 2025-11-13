import React, { useState } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/AuthContext';
import {
  Users,
  Bot,
  MessageSquare,
  Settings,
  BarChart3,
  Activity,
  Home,
  Menu,
  X,
  LogOut,
  ChevronRight
} from 'lucide-react';

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { path: '/admin', label: 'Overview', icon: <Home className="w-5 h-5" /> },
  { path: '/admin/users', label: 'Users', icon: <Users className="w-5 h-5" /> },
  { path: '/admin/bot', label: 'Bot', icon: <Bot className="w-5 h-5" /> },
  { path: '/admin/conversations', label: 'Conversations', icon: <MessageSquare className="w-5 h-5" /> },
  { path: '/admin/config', label: 'Configuration', icon: <Settings className="w-5 h-5" /> },
  { path: '/admin/analytics', label: 'Analytics', icon: <BarChart3 className="w-5 h-5" /> },
  { path: '/admin/monitoring', label: 'Monitoring', icon: <Activity className="w-5 h-5" /> },
];

// Breadcrumb component
function Breadcrumbs() {
  const location = useLocation();
  const pathSegments = location.pathname.split('/').filter(Boolean);
  
  // Skip 'admin' segment
  const segments = pathSegments.slice(1);
  
  // Don't show breadcrumbs on home page
  if (segments.length === 0 || location.pathname === '/admin') {
    return null;
  }

  const breadcrumbMap: Record<string, string> = {
    'users': 'Users',
    'bot': 'Bot',
    'conversations': 'Conversations',
    'config': 'Configuration',
    'analytics': 'Analytics',
    'monitoring': 'Monitoring',
  };

  return (
    <nav className="flex items-center space-x-2 text-sm text-gray-600 mb-4">
      <Link to="/admin" className="hover:text-gray-900">Admin</Link>
      {segments.map((segment, index) => {
        const isLast = index === segments.length - 1;
        const label = breadcrumbMap[segment] || segment;
        const path = '/' + pathSegments.slice(0, index + 2).join('/');
        
        return (
          <React.Fragment key={segment}>
            <ChevronRight className="w-4 h-4" />
            {isLast ? (
              <span className="text-gray-900 font-medium">{label}</span>
            ) : (
              <Link to={path} className="hover:text-gray-900">
                {label}
              </Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}

// Navigation link component
function NavLink({ item }: { item: NavItem }) {
  const location = useLocation();
  const isActive = location.pathname === item.path || 
    (item.path !== '/admin' && location.pathname.startsWith(item.path));

  return (
    <Link
      to={item.path}
      className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
        isActive
          ? 'bg-gray-800 text-white'
          : 'text-gray-300 hover:bg-gray-800 hover:text-white'
      }`}
    >
      {item.icon}
      <span>{item.label}</span>
    </Link>
  );
}

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/admin/login');
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-full w-64 bg-gray-900 text-white z-50 transform transition-transform duration-300 ease-in-out ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Sidebar header */}
          <div className="p-6 border-b border-gray-800">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold">June Admin</h1>
              <button
                onClick={() => setSidebarOpen(false)}
                className="lg:hidden text-gray-400 hover:text-white"
              >
                <X className="w-6 h-6" />
              </button>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
            {navItems.map((item) => (
              <NavLink key={item.path} item={item} />
            ))}
          </nav>

          {/* Sidebar footer */}
          <div className="p-6 border-t border-gray-800">
            <div className="text-sm text-gray-400 mb-2">Logged in as</div>
            <div className="text-white font-medium mb-4">{user?.username}</div>
            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Logout
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:ml-64">
        {/* Top header */}
        <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-30">
          <div className="px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="lg:hidden text-gray-600 hover:text-gray-900"
                >
                  <Menu className="w-6 h-6" />
                </button>
                <div className="hidden sm:block">
                  <Breadcrumbs />
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="hidden sm:flex items-center gap-2 text-sm text-gray-600">
                  <span className="font-medium">{user?.username}</span>
                </div>
                <button
                  onClick={handleLogout}
                  className="lg:hidden flex items-center gap-2 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="hidden sm:inline">Logout</span>
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
