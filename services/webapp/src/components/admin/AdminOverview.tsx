import React, { useState, useEffect } from 'react';
import { Users, MessageSquare, Bot, Activity, TrendingUp, Clock } from 'lucide-react';
import { userAPI } from '../../utils/api';

interface OverviewStats {
  totalUsers: number;
  activeUsers: number;
  totalConversations: number;
  activeConversations: number;
  totalMessages: number;
  botStatus: 'online' | 'offline';
  systemHealth: 'healthy' | 'degraded' | 'down';
}

const AdminOverview: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        setError(null);
        
        // Fetch user statistics
        const userStats = await userAPI.getStats();
        
        // Set stats from API response
        // Note: total_conversations, active_conversations, and total_messages
        // will be available when conversation management APIs are implemented
        setStats({
          totalUsers: userStats.total_users || 0,
          activeUsers: userStats.active_users || 0,
          totalConversations: userStats.total_conversations || 0, // TODO: Fetch from conversations API
          activeConversations: userStats.active_conversations || 0, // TODO: Fetch from conversations API
          totalMessages: userStats.total_messages || 0, // TODO: Fetch from messages API
          botStatus: 'online', // TODO: Fetch from bot status API
          systemHealth: 'healthy', // TODO: Fetch from monitoring API
        });
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load statistics');
        console.error('Error fetching overview stats:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p className="ml-3 text-gray-600">Loading overview...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
        {error}
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total Users',
      value: stats?.totalUsers || 0,
      icon: <Users className="w-6 h-6" />,
      color: 'blue',
      change: '+12%',
    },
    {
      title: 'Active Users',
      value: stats?.activeUsers || 0,
      icon: <Activity className="w-6 h-6" />,
      color: 'green',
      change: '+5%',
    },
    {
      title: 'Total Conversations',
      value: stats?.totalConversations || 0,
      icon: <MessageSquare className="w-6 h-6" />,
      color: 'purple',
      change: '+8%',
    },
    {
      title: 'Active Conversations',
      value: stats?.activeConversations || 0,
      icon: <Clock className="w-6 h-6" />,
      color: 'orange',
      change: '+3%',
    },
    {
      title: 'Total Messages',
      value: stats?.totalMessages || 0,
      icon: <MessageSquare className="w-6 h-6" />,
      color: 'indigo',
      change: '+15%',
    },
    {
      title: 'Bot Status',
      value: stats?.botStatus === 'online' ? 'Online' : 'Offline',
      icon: <Bot className="w-6 h-6" />,
      color: stats?.botStatus === 'online' ? 'green' : 'red',
      change: null,
    },
  ];

  const getColorClasses = (color: string) => {
    const colors: Record<string, { bg: string; text: string; icon: string }> = {
      blue: { bg: 'bg-blue-50', text: 'text-blue-600', icon: 'text-blue-600' },
      green: { bg: 'bg-green-50', text: 'text-green-600', icon: 'text-green-600' },
      purple: { bg: 'bg-purple-50', text: 'text-purple-600', icon: 'text-purple-600' },
      orange: { bg: 'bg-orange-50', text: 'text-orange-600', icon: 'text-orange-600' },
      indigo: { bg: 'bg-indigo-50', text: 'text-indigo-600', icon: 'text-indigo-600' },
      red: { bg: 'bg-red-50', text: 'text-red-600', icon: 'text-red-600' },
    };
    return colors[color] || colors.blue;
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Admin Dashboard</h1>
        <p className="mt-2 text-gray-600">Overview of system metrics and key statistics</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {statCards.map((card, index) => {
          const colors = getColorClasses(card.color);
          return (
            <div
              key={index}
              className="bg-white rounded-lg shadow p-6 border border-gray-200"
            >
              <div className="flex items-center justify-between mb-4">
                <div className={`p-3 rounded-lg ${colors.bg}`}>
                  <div className={colors.icon}>{card.icon}</div>
                </div>
                {card.change && (
                  <div className="flex items-center text-sm text-green-600">
                    <TrendingUp className="w-4 h-4 mr-1" />
                    {card.change}
                  </div>
                )}
              </div>
              <div className="text-2xl font-bold text-gray-900 mb-1">{card.value.toLocaleString()}</div>
              <div className="text-sm text-gray-600">{card.title}</div>
            </div>
          );
        })}
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <a
            href="/admin/users/new"
            className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="font-medium text-gray-900">Create User</div>
            <div className="text-sm text-gray-600 mt-1">Add a new user to the system</div>
          </a>
          <a
            href="/admin/bot"
            className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="font-medium text-gray-900">Bot Configuration</div>
            <div className="text-sm text-gray-600 mt-1">Manage bot settings</div>
          </a>
          <a
            href="/admin/conversations"
            className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="font-medium text-gray-900">View Conversations</div>
            <div className="text-sm text-gray-600 mt-1">Browse all conversations</div>
          </a>
          <a
            href="/admin/monitoring"
            className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="font-medium text-gray-900">System Health</div>
            <div className="text-sm text-gray-600 mt-1">Check service status</div>
          </a>
        </div>
      </div>
    </div>
  );
};

export default AdminOverview;
