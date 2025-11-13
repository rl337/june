import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit, Trash2, UserCheck, UserX, Shield, MessageSquare, Calendar, Clock } from 'lucide-react';
import { userAPI } from '../utils/api';

interface UserDetail {
  user_id: string;
  conversation_count: number;
  message_count: number;
  first_seen: string;
  last_active: string;
  status: 'active' | 'blocked' | 'admin';
  blocked_info?: {
    blocked_by: string;
    reason: string;
    created_at: string;
    updated_at: string;
  };
  admin_info?: {
    created_at: string;
  };
  recent_conversations: Array<{
    id: string;
    session_id: string;
    created_at: string;
    updated_at: string;
    metadata: any;
  }>;
}

const UserDetail: React.FC = () => {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (userId) {
      fetchUser();
    }
  }, [userId]);

  const fetchUser = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await userAPI.getUser(userId!);
      setUser(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load user');
      console.error('Error fetching user:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Are you sure you want to delete user ${userId}? This action cannot be undone.`)) {
      return;
    }

    try {
      await userAPI.deleteUser(userId!);
      navigate('/admin/users');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete user');
      console.error('Error deleting user:', err);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <UserCheck className="w-5 h-5 text-green-500" />;
      case 'blocked':
        return <UserX className="w-5 h-5 text-red-500" />;
      case 'admin':
        return <Shield className="w-5 h-5 text-blue-500" />;
      default:
        return null;
    }
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = "px-3 py-1 rounded-full text-sm font-medium";
    switch (status) {
      case 'active':
        return `${baseClasses} bg-green-100 text-green-800`;
      case 'blocked':
        return `${baseClasses} bg-red-100 text-red-800`;
      case 'admin':
        return `${baseClasses} bg-blue-100 text-blue-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-2 text-gray-600">Loading user details...</p>
        </div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="p-6">
        <div className="mb-4">
          <button
            onClick={() => navigate('/admin/users')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Users
          </button>
        </div>
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error || 'User not found'}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate('/admin/users')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Users
        </button>
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3 mb-2">
              {getStatusIcon(user.status)}
              <h1 className="text-3xl font-bold text-gray-900">{user.user_id}</h1>
              <span className={getStatusBadge(user.status)}>
                {user.status}
              </span>
            </div>
            <p className="text-gray-600">User Details</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => navigate(`/admin/users/${userId}/edit`)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Edit className="w-4 h-4" />
              Edit
            </button>
            <button
              onClick={handleDelete}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>
      </div>

      {/* User Information */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Statistics</h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <MessageSquare className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-600">Conversations</p>
                <p className="text-xl font-semibold text-gray-900">{user.conversation_count}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <MessageSquare className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-600">Messages</p>
                <p className="text-xl font-semibold text-gray-900">{user.message_count}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Timeline</h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-600">First Seen</p>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(user.first_seen).toLocaleString()}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Clock className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-600">Last Active</p>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(user.last_active).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Blocked Info */}
      {user.status === 'blocked' && user.blocked_info && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-red-900 mb-4">Blocked Information</h2>
          <div className="space-y-2">
            <p><span className="font-medium">Blocked by:</span> {user.blocked_info.blocked_by}</p>
            {user.blocked_info.reason && (
              <p><span className="font-medium">Reason:</span> {user.blocked_info.reason}</p>
            )}
            <p><span className="font-medium">Blocked on:</span> {new Date(user.blocked_info.created_at).toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Admin Info */}
      {user.status === 'admin' && user.admin_info && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-blue-900 mb-4">Admin Information</h2>
          <p><span className="font-medium">Admin since:</span> {new Date(user.admin_info.created_at).toLocaleString()}</p>
        </div>
      )}

      {/* Recent Conversations */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Conversations</h2>
        {user.recent_conversations.length === 0 ? (
          <p className="text-gray-600">No conversations found</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Session ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Updated</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {user.recent_conversations.map((conv) => (
                  <tr key={conv.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">{conv.session_id}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(conv.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(conv.updated_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default UserDetail;
