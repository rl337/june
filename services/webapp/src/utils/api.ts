import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_GATEWAY_URL || 'http://localhost:8000';

// Get auth token from localStorage (checks both regular user and admin)
const getAuthToken = (): string | null => {
  // Check admin token first (takes precedence)
  const admin = localStorage.getItem('june_admin');
  if (admin) {
    const adminData = JSON.parse(admin);
    return adminData.token;
  }
  
  // Fallback to regular user token
  const user = localStorage.getItem('june_user');
  if (user) {
    const userData = JSON.parse(user);
    return userData.token;
  }
  
  return null;
};

// Create axios instance with auth header
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// User Management API
export const userAPI = {
  // List users with pagination, search, and filtering
  listUsers: async (params?: {
    page?: number;
    page_size?: number;
    search?: string;
    status?: 'active' | 'blocked' | 'admin';
  }) => {
    const response = await api.get('/admin/users', { params });
    return response.data;
  },

  // Get user statistics
  getStats: async () => {
    const response = await api.get('/admin/users/stats');
    return response.data;
  },

  // Get user details
  getUser: async (userId: string) => {
    const response = await api.get(`/admin/users/${userId}`);
    return response.data;
  },

  // Create user
  createUser: async (data: { user_id: string; metadata?: any }) => {
    const response = await api.post('/admin/users', data);
    return response.data;
  },

  // Update user
  updateUser: async (userId: string, data: { status: string; reason?: string }) => {
    const response = await api.put(`/admin/users/${userId}`, data);
    return response.data;
  },

  // Delete user
  deleteUser: async (userId: string) => {
    const response = await api.delete(`/admin/users/${userId}`);
    return response.data;
  },
};

// Conversation Management API
export const conversationAPI = {
  // List conversations with pagination, search, and filtering
  listConversations: async (params?: {
    page?: number;
    page_size?: number;
    user_id?: string;
    search?: string;
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/conversations', { params });
    return response.data;
  },

  // Get conversation statistics
  getStats: async () => {
    const response = await api.get('/admin/conversations/stats');
    return response.data;
  },

  // Get conversation details
  getConversation: async (conversationId: string) => {
    const response = await api.get(`/admin/conversations/${conversationId}`);
    return response.data;
  },

  // Search conversations
  searchConversations: async (params: {
    q: string;
    page?: number;
    page_size?: number;
    user_id?: string;
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/conversations/search', { params });
    return response.data;
  },

  // Delete conversation
  deleteConversation: async (conversationId: string) => {
    const response = await api.delete(`/admin/conversations/${conversationId}`);
    return response.data;
  },

  // Export conversation (using existing endpoint)
  exportConversation: async (
    userId: string,
    chatId: string,
    format: 'json' | 'txt' | 'csv' = 'json',
    startDate?: string,
    endDate?: string
  ) => {
    const params: any = { format };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get(`/conversations/${userId}/${chatId}/export`, { 
      params,
      responseType: 'blob' // Handle binary response
    });
    return response.data;
  },
};

// Bot Management API
export const botAPI = {
  // Get bot configuration
  getConfig: async () => {
    const response = await api.get('/admin/bot/config');
    return response.data;
  },

  // Update bot configuration
  updateConfig: async (data: {
    bot_token?: string;
    webhook_url?: string;
    max_file_size_mb?: number;
    max_duration_seconds?: number;
    is_active?: boolean;
  }) => {
    const response = await api.put('/admin/bot/config', data);
    return response.data;
  },

  // Get bot status
  getStatus: async () => {
    const response = await api.get('/admin/bot/status');
    return response.data;
  },

  // Get bot statistics
  getStats: async () => {
    const response = await api.get('/admin/bot/stats');
    return response.data;
  },

  // List bot commands
  listCommands: async () => {
    const response = await api.get('/admin/bot/commands');
    return response.data;
  },

  // Create bot command
  createCommand: async (data: { command: string; description: string }) => {
    const response = await api.post('/admin/bot/commands', data);
    return response.data;
  },

  // Update bot command
  updateCommand: async (commandId: string, data: { description?: string; is_active?: boolean }) => {
    const response = await api.put(`/admin/bot/commands/${commandId}`, data);
    return response.data;
  },

  // Delete bot command
  deleteCommand: async (commandId: string) => {
    const response = await api.delete(`/admin/bot/commands/${commandId}`);
    return response.data;
  },
};

// System Monitoring API
export const monitoringAPI = {
  // Get health status for all services
  getServices: async () => {
    const response = await api.get('/admin/monitoring/services');
    return response.data;
  },

  // Get metrics for all services
  getMetrics: async () => {
    const response = await api.get('/admin/monitoring/metrics');
    return response.data;
  },

  // Get comprehensive health check
  getHealth: async () => {
    const response = await api.get('/admin/monitoring/health');
    return response.data;
  },
};

// System Configuration API
export const systemConfigAPI = {
  // Get current system configuration
  getConfig: async () => {
    const response = await api.get('/admin/config');
    return response.data;
  },

  // Update system configuration
  updateConfig: async (data: {
    config: any;
    category?: string;
  }) => {
    const response = await api.put('/admin/config', data);
    return response.data;
  },

  // Get configuration history
  getHistory: async (params?: {
    page?: number;
    page_size?: number;
    category?: string;
  }) => {
    const response = await api.get('/admin/config/history', { params });
    return response.data;
  },
};

// Analytics API
export const analyticsAPI = {
  // Get user analytics
  getUserAnalytics: async (params?: {
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/analytics/users', { params });
    return response.data;
  },

  // Get conversation analytics
  getConversationAnalytics: async (params?: {
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/analytics/conversations', { params });
    return response.data;
  },

  // Get bot performance analytics
  getBotAnalytics: async (params?: {
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/analytics/bot', { params });
    return response.data;
  },

  // Get system usage analytics
  getSystemAnalytics: async (params?: {
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/analytics/system', { params });
    return response.data;
  },

  // Export analytics data
  exportAnalytics: async (params: {
    format?: 'json' | 'csv';
    start_date?: string;
    end_date?: string;
  }) => {
    const response = await api.get('/admin/analytics/export', { 
      params,
      responseType: params.format === 'csv' ? 'blob' : 'json'
    });
    return response.data;
  },
};

export default api;
