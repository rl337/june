import React, { useState, useEffect } from 'react';
import { Bot, Settings, Activity, Save, Plus, Edit, Trash2, RefreshCw, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { botAPI } from '../../utils/api';

interface BotConfig {
  id?: string;
  bot_token?: string;
  webhook_url?: string;
  max_file_size_mb?: number;
  max_duration_seconds?: number;
  is_active?: boolean;
  last_activity?: string;
  created_at?: string;
  updated_at?: string;
}

interface BotStatus {
  is_online: boolean;
  is_active: boolean;
  health_status: string;
  last_activity?: string;
  last_updated?: string;
}

interface BotStats {
  total_messages: number;
  active_conversations: number;
  total_errors: number;
  error_rate: number;
  daily_statistics: Array<{
    date: string;
    total_messages: number;
    active_conversations: number;
    error_count: number;
  }>;
}

interface BotCommand {
  id: string;
  command: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const BotManagement: React.FC = () => {
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [stats, setStats] = useState<BotStats | null>(null);
  const [commands, setCommands] = useState<BotCommand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'config' | 'status' | 'stats' | 'commands'>('config');
  
  // Form state
  const [formData, setFormData] = useState<Partial<BotConfig>>({});
  const [showCommandForm, setShowCommandForm] = useState(false);
  const [editingCommand, setEditingCommand] = useState<BotCommand | null>(null);
  const [commandForm, setCommandForm] = useState({ command: '', description: '' });

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [configData, statusData, statsData, commandsData] = await Promise.all([
        botAPI.getConfig(),
        botAPI.getStatus(),
        botAPI.getStats(),
        botAPI.listCommands()
      ]);
      
      setConfig(configData);
      setFormData(configData);
      setStatus(statusData);
      setStats(statsData);
      setCommands(commandsData.commands || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load bot data');
      console.error('Error fetching bot data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Refresh status every 30 seconds
    const statusInterval = setInterval(async () => {
      try {
        const statusData = await botAPI.getStatus();
        setStatus(statusData);
      } catch (err) {
        console.error('Error refreshing status:', err);
      }
    }, 30000);
    
    return () => clearInterval(statusInterval);
  }, []);

  const handleSaveConfig = async () => {
    try {
      setSaving(true);
      setError(null);
      const updatedConfig = await botAPI.updateConfig(formData);
      setConfig(updatedConfig);
      setFormData(updatedConfig);
      alert('Bot configuration saved successfully!');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save configuration');
      console.error('Error saving config:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleCreateCommand = async () => {
    try {
      setSaving(true);
      setError(null);
      await botAPI.createCommand(commandForm);
      setCommandForm({ command: '', description: '' });
      setShowCommandForm(false);
      fetchData();
      alert('Command created successfully!');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create command');
      console.error('Error creating command:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateCommand = async (commandId: string, data: { description?: string; is_active?: boolean }) => {
    try {
      setSaving(true);
      setError(null);
      await botAPI.updateCommand(commandId, data);
      setEditingCommand(null);
      fetchData();
      alert('Command updated successfully!');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update command');
      console.error('Error updating command:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCommand = async (commandId: string, commandName: string) => {
    if (!window.confirm(`Are you sure you want to delete command "${commandName}"?`)) {
      return;
    }
    
    try {
      setSaving(true);
      setError(null);
      await botAPI.deleteCommand(commandId);
      fetchData();
      alert('Command deleted successfully!');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete command');
      console.error('Error deleting command:', err);
    } finally {
      setSaving(false);
    }
  };

  const getStatusIcon = () => {
    if (!status) return <AlertCircle className="w-5 h-5 text-gray-400" />;
    if (status.is_online) {
      return <CheckCircle className="w-5 h-5 text-green-500" />;
    }
    return <XCircle className="w-5 h-5 text-red-500" />;
  };

  const getStatusBadge = () => {
    if (!status) return <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">Unknown</span>;
    if (status.is_online) {
      return <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">Online</span>;
    }
    return <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">Offline</span>;
  };

  if (loading && !config) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading bot management...</div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Bot Management</h1>
        <p className="mt-2 text-gray-600">Configure and monitor the Telegram bot</p>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
          {error}
        </div>
      )}

      {/* Status Bar */}
      {status && (
        <div className="mb-6 bg-white rounded-lg shadow p-4 border border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {getStatusIcon()}
              <div>
                <div className="font-semibold text-gray-900">Bot Status</div>
                <div className="text-sm text-gray-600">
                  {getStatusBadge()} • Health: {status.health_status}
                  {status.last_activity && ` • Last activity: ${new Date(status.last_activity).toLocaleString()}`}
                </div>
              </div>
            </div>
            <button
              onClick={fetchData}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="flex space-x-8">
          {[
            { id: 'config', label: 'Configuration', icon: Settings },
            { id: 'status', label: 'Status', icon: Activity },
            { id: 'stats', label: 'Statistics', icon: Bot },
            { id: 'commands', label: 'Commands', icon: Bot },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id as any)}
              className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
                activeTab === id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Configuration Tab */}
      {activeTab === 'config' && (
        <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Bot Configuration</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Bot Token
              </label>
              <input
                type="password"
                value={formData.bot_token || ''}
                onChange={(e) => setFormData({ ...formData, bot_token: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter Telegram bot token"
              />
              <p className="mt-1 text-xs text-gray-500">Leave empty to keep current token</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Webhook URL
              </label>
              <input
                type="url"
                value={formData.webhook_url || ''}
                onChange={(e) => setFormData({ ...formData, webhook_url: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="https://example.com/webhook"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Max File Size (MB)
                </label>
                <input
                  type="number"
                  value={formData.max_file_size_mb || ''}
                  onChange={(e) => setFormData({ ...formData, max_file_size_mb: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="1"
                  max="100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Max Duration (seconds)
                </label>
                <input
                  type="number"
                  value={formData.max_duration_seconds || ''}
                  onChange={(e) => setFormData({ ...formData, max_duration_seconds: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="1"
                  max="300"
                />
              </div>
            </div>

            <div className="flex items-center">
              <input
                type="checkbox"
                id="is_active"
                checked={formData.is_active ?? true}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="is_active" className="ml-2 text-sm font-medium text-gray-700">
                Bot is active
              </label>
            </div>

            <div className="pt-4">
              <button
                onClick={handleSaveConfig}
                disabled={saving}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Status Tab */}
      {activeTab === 'status' && status && (
        <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Bot Status</h2>
          
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-600 mb-1">Status</div>
                <div className="text-lg font-semibold flex items-center gap-2">
                  {getStatusIcon()}
                  {status.is_online ? 'Online' : 'Offline'}
                </div>
              </div>
              
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-600 mb-1">Health</div>
                <div className="text-lg font-semibold capitalize">{status.health_status}</div>
              </div>
              
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-600 mb-1">Active</div>
                <div className="text-lg font-semibold">{status.is_active ? 'Yes' : 'No'}</div>
              </div>
              
              {status.last_activity && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-1">Last Activity</div>
                  <div className="text-lg font-semibold">
                    {new Date(status.last_activity).toLocaleString()}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Statistics Tab */}
      {activeTab === 'stats' && stats && (
        <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Bot Statistics</h2>
          
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="p-4 bg-blue-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Total Messages</div>
              <div className="text-2xl font-bold text-blue-600">{stats.total_messages.toLocaleString()}</div>
            </div>
            
            <div className="p-4 bg-green-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Active Conversations</div>
              <div className="text-2xl font-bold text-green-600">{stats.active_conversations.toLocaleString()}</div>
            </div>
            
            <div className="p-4 bg-red-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Total Errors</div>
              <div className="text-2xl font-bold text-red-600">{stats.total_errors.toLocaleString()}</div>
            </div>
            
            <div className="p-4 bg-yellow-50 rounded-lg">
              <div className="text-sm text-gray-600 mb-1">Error Rate</div>
              <div className="text-2xl font-bold text-yellow-600">{stats.error_rate.toFixed(2)}%</div>
            </div>
          </div>

          {stats.daily_statistics.length > 0 && (
            <div>
              <h3 className="text-md font-semibold text-gray-900 mb-3">Daily Statistics (Last 7 Days)</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Messages</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Conversations</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Errors</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {stats.daily_statistics.map((day, idx) => (
                      <tr key={idx}>
                        <td className="px-4 py-3 text-sm text-gray-900">{new Date(day.date).toLocaleDateString()}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{day.total_messages.toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{day.active_conversations.toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{day.error_count.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Commands Tab */}
      {activeTab === 'commands' && (
        <div className="bg-white rounded-lg shadow p-6 border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Bot Commands</h2>
            <button
              onClick={() => {
                setShowCommandForm(true);
                setEditingCommand(null);
                setCommandForm({ command: '', description: '' });
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Command
            </button>
          </div>

          {showCommandForm && (
            <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
              <h3 className="text-md font-semibold text-gray-900 mb-3">
                {editingCommand ? 'Edit Command' : 'New Command'}
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Command (without /)
                  </label>
                  <input
                    type="text"
                    value={commandForm.command}
                    onChange={(e) => setCommandForm({ ...commandForm, command: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="start"
                    disabled={!!editingCommand}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    value={commandForm.description}
                    onChange={(e) => setCommandForm({ ...commandForm, description: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Start interacting with the bot"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => editingCommand ? handleUpdateCommand(editingCommand.id, { description: commandForm.description }) : handleCreateCommand()}
                    disabled={saving || !commandForm.command || !commandForm.description}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {saving ? 'Saving...' : editingCommand ? 'Update' : 'Create'}
                  </button>
                  <button
                    onClick={() => {
                      setShowCommandForm(false);
                      setEditingCommand(null);
                      setCommandForm({ command: '', description: '' });
                    }}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Command</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {commands.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                      No commands configured
                    </td>
                  </tr>
                ) : (
                  commands.map((cmd) => (
                    <tr key={cmd.id}>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">/{cmd.command}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{cmd.description}</td>
                      <td className="px-4 py-3 text-sm">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          cmd.is_active
                            ? 'bg-green-100 text-green-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {cmd.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleUpdateCommand(cmd.id, { is_active: !cmd.is_active })}
                            className="text-blue-600 hover:text-blue-800"
                            title={cmd.is_active ? 'Deactivate' : 'Activate'}
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDeleteCommand(cmd.id, cmd.command)}
                            className="text-red-600 hover:text-red-800"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default BotManagement;
