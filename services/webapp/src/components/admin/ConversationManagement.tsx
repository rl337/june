import React, { useState, useEffect } from 'react';
import { MessageSquare, Search, Download, Trash2, Eye, Calendar, User, Filter, X } from 'lucide-react';
import { conversationAPI } from '../../utils/api';
import { useNavigate } from 'react-router-dom';

interface Message {
  id: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  created_at: string;
  metadata?: any;
}

interface Conversation {
  id: string;
  user_id: string;
  session_id: string;
  created_at: string;
  updated_at: string;
  metadata?: any;
  message_count: number;
  first_message_at?: string;
  last_message_at?: string;
}

interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface ConversationStats {
  total_conversations: number;
  active_conversations: number;
  total_messages: number;
  average_length: number;
}

const ConversationManagement: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [search, setSearch] = useState('');
  const [userFilter, setUserFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [stats, setStats] = useState<ConversationStats | null>(null);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [conversationDetail, setConversationDetail] = useState<any>(null);
  const [showDetail, setShowDetail] = useState(false);
  const navigate = useNavigate();

  const fetchConversations = async () => {
    try {
      setLoading(true);
      setError(null);
      const params: any = {
        page,
        page_size: pageSize,
      };
      if (search) params.search = search;
      if (userFilter) params.user_id = userFilter;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;

      const data: ConversationListResponse = await conversationAPI.listConversations(params);
      setConversations(data.conversations);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load conversations');
      console.error('Error fetching conversations:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const data = await conversationAPI.getStats();
      setStats(data);
    } catch (err: any) {
      console.error('Error fetching stats:', err);
    }
  };

  const fetchConversationDetail = async (conversationId: string) => {
    try {
      const data = await conversationAPI.getConversation(conversationId);
      setConversationDetail(data);
      setShowDetail(true);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to load conversation details');
      console.error('Error fetching conversation detail:', err);
    }
  };

  useEffect(() => {
    fetchConversations();
    fetchStats();
  }, [page, search, userFilter, startDate, endDate]);

  const handleDelete = async (conversationId: string) => {
    if (!window.confirm('Are you sure you want to delete this conversation? This action cannot be undone.')) {
      return;
    }

    try {
      await conversationAPI.deleteConversation(conversationId);
      fetchConversations(); // Refresh list
      fetchStats(); // Refresh stats
      if (selectedConversation?.id === conversationId) {
        setSelectedConversation(null);
        setShowDetail(false);
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete conversation');
      console.error('Error deleting conversation:', err);
    }
  };

  const handleExport = async (conversation: Conversation, format: 'json' | 'txt' | 'csv' = 'json') => {
    try {
      const blob = await conversationAPI.exportConversation(
        conversation.user_id,
        conversation.session_id,
        format,
        startDate || undefined,
        endDate || undefined
      );
      
      // Create download link from blob
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `conversation_${conversation.user_id}_${conversation.session_id}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      // Try to extract error message from blob response if possible
      let errorMessage = 'Failed to export conversation';
      if (err.response?.data) {
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          errorMessage = json.detail || errorMessage;
        } catch {
          errorMessage = err.response?.data?.detail || errorMessage;
        }
      }
      alert(errorMessage);
      console.error('Error exporting conversation:', err);
    }
  };

  const clearFilters = () => {
    setSearch('');
    setUserFilter('');
    setStartDate('');
    setEndDate('');
    setPage(1);
  };

  const getRoleBadge = (role: string) => {
    const baseClasses = "px-2 py-1 rounded-full text-xs font-medium";
    switch (role) {
      case 'user':
        return `${baseClasses} bg-blue-100 text-blue-800`;
      case 'assistant':
        return `${baseClasses} bg-green-100 text-green-800`;
      case 'system':
        return `${baseClasses} bg-gray-100 text-gray-800`;
      case 'tool':
        return `${baseClasses} bg-purple-100 text-purple-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  if (showDetail && conversationDetail) {
    return (
      <div className="p-6">
        <div className="mb-6 flex justify-between items-center">
          <div>
            <button
              onClick={() => {
                setShowDetail(false);
                setConversationDetail(null);
                setSelectedConversation(null);
              }}
              className="text-blue-600 hover:text-blue-800 mb-2 flex items-center gap-2"
            >
              ← Back to Conversations
            </button>
            <h1 className="text-2xl font-bold text-gray-900">Conversation Details</h1>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleExport(selectedConversation!, 'json')}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Download className="w-4 h-4" />
              Export JSON
            </button>
            <button
              onClick={() => handleDelete(conversationDetail.id)}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div>
              <label className="text-sm font-medium text-gray-500">Conversation ID</label>
              <p className="text-sm text-gray-900 font-mono">{conversationDetail.id}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">User ID</label>
              <p className="text-sm text-gray-900">{conversationDetail.user_id}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Session ID</label>
              <p className="text-sm text-gray-900 font-mono">{conversationDetail.session_id}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Message Count</label>
              <p className="text-sm text-gray-900">{conversationDetail.message_count}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Created At</label>
              <p className="text-sm text-gray-900">{new Date(conversationDetail.created_at).toLocaleString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-500">Last Updated</label>
              <p className="text-sm text-gray-900">{new Date(conversationDetail.updated_at).toLocaleString()}</p>
            </div>
          </div>

          <h2 className="text-lg font-semibold text-gray-900 mb-4">Messages</h2>
          <div className="space-y-4 max-h-96 overflow-y-auto">
            {conversationDetail.messages && conversationDetail.messages.length > 0 ? (
              conversationDetail.messages.map((message: Message) => (
                <div key={message.id} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex justify-between items-start mb-2">
                    <span className={getRoleBadge(message.role)}>{message.role}</span>
                    <span className="text-xs text-gray-500">
                      {new Date(message.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-900 whitespace-pre-wrap">{message.content}</p>
                  {message.metadata && Object.keys(message.metadata).length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs text-gray-500 cursor-pointer">Metadata</summary>
                      <pre className="text-xs text-gray-600 mt-1 p-2 bg-gray-50 rounded">
                        {JSON.stringify(message.metadata, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))
            ) : (
              <p className="text-gray-500 text-center py-8">No messages in this conversation</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Conversation Management</h1>
        <p className="mt-2 text-gray-600">View and manage all conversations</p>
      </div>

      {/* Statistics */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow p-4 border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Total Conversations</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_conversations}</p>
              </div>
              <MessageSquare className="w-8 h-8 text-blue-500" />
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Active (7 days)</p>
                <p className="text-2xl font-bold text-gray-900">{stats.active_conversations}</p>
              </div>
              <MessageSquare className="w-8 h-8 text-green-500" />
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Total Messages</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_messages}</p>
              </div>
              <MessageSquare className="w-8 h-8 text-purple-500" />
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Avg Length</p>
                <p className="text-2xl font-bold text-gray-900">{stats.average_length}</p>
              </div>
              <MessageSquare className="w-8 h-8 text-orange-500" />
            </div>
          </div>
        </div>
      )}

      {/* Search and Filters */}
      <div className="mb-6 bg-white rounded-lg shadow p-4 border border-gray-200">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="relative">
            <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Filter by User ID..."
              value={userFilter}
              onChange={(e) => {
                setUserFilter(e.target.value);
                setPage(1);
              }}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="date"
              placeholder="Start Date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="date"
              placeholder="End Date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>
        {(search || userFilter || startDate || endDate) && (
          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={clearFilters}
              className="flex items-center gap-2 px-3 py-1 text-sm text-gray-600 hover:text-gray-800"
            >
              <X className="w-4 h-4" />
              Clear Filters
            </button>
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}

      {/* Conversations Table */}
      {loading ? (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-2 text-gray-600">Loading conversations...</p>
        </div>
      ) : conversations.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <MessageSquare className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600">No conversations found</p>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Conversation ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    User ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Messages
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Updated
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {conversations.map((conversation) => (
                  <tr key={conversation.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-sm font-mono text-gray-900">{conversation.id.substring(0, 8)}...</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-sm text-gray-900">{conversation.user_id}</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {conversation.message_count}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(conversation.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(conversation.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => {
                            setSelectedConversation(conversation);
                            fetchConversationDetail(conversation.id);
                          }}
                          className="text-blue-600 hover:text-blue-900"
                          title="View Details"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleExport(conversation, 'json')}
                          className="text-green-600 hover:text-green-900"
                          title="Export"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(conversation.id)}
                          className="text-red-600 hover:text-red-900"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex justify-between items-center">
              <div className="text-sm text-gray-700">
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} conversations
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  Previous
                </button>
                <span className="px-4 py-2 text-sm text-gray-700">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-4 py-2 border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ConversationManagement;
