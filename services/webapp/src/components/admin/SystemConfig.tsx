import React, { useState, useEffect } from 'react';
import { Settings, Save, History, Download, Upload, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react';
import { systemConfigAPI } from '../../utils/api';

interface SystemConfig {
  model_settings?: {
    default_model?: string;
    temperature?: number;
    max_tokens?: number;
    context_length?: number;
    enable_streaming?: boolean;
  };
  service_settings?: {
    gateway_url?: string;
    inference_api_url?: string;
    stt_service_url?: string;
    tts_service_url?: string;
    telegram_bot_url?: string;
  };
  security_settings?: {
    jwt_secret?: string;
    jwt_expiration_hours?: number;
    enable_rate_limiting?: boolean;
    max_requests_per_minute?: number;
    require_https?: boolean;
  };
  feature_flags?: {
    enable_voice_messages?: boolean;
    enable_rag?: boolean;
    enable_ab_testing?: boolean;
    enable_cost_tracking?: boolean;
    enable_analytics?: boolean;
  };
}

interface ConfigHistoryItem {
  id: string;
  config_data: SystemConfig;
  category?: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

const SystemConfig: React.FC = () => {
  const [config, setConfig] = useState<SystemConfig>({});
  const [history, setHistory] = useState<ConfigHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'config' | 'history'>('config');
  const [activeCategory, setActiveCategory] = useState<string>('model_settings');
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotalPages, setHistoryTotalPages] = useState(1);
  const [formData, setFormData] = useState<SystemConfig>({});

  const categories = [
    { id: 'model_settings', name: 'Model Settings', icon: '🤖' },
    { id: 'service_settings', name: 'Service Settings', icon: '🔗' },
    { id: 'security_settings', name: 'Security Settings', icon: '🔒' },
    { id: 'feature_flags', name: 'Feature Flags', icon: '🚩' },
  ];

  const fetchConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await systemConfigAPI.getConfig();
      setConfig(data);
      setFormData(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load system configuration');
      console.error('Error fetching config:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async (page: number = 1) => {
    try {
      const data = await systemConfigAPI.getHistory({ page, page_size: 20 });
      setHistory(data.history || []);
      setHistoryTotalPages(data.total_pages || 1);
    } catch (err: any) {
      console.error('Error fetching history:', err);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory(historyPage);
    }
  }, [activeTab, historyPage]);

  const handleSave = async (category?: string) => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const configToSave = category 
        ? { [category]: formData[category as keyof SystemConfig] }
        : formData;

      await systemConfigAPI.updateConfig({
        config: configToSave,
        category: category || undefined,
      });

      setSuccess('Configuration updated successfully');
      await fetchConfig();
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update configuration');
      console.error('Error updating config:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleExport = () => {
    const dataStr = JSON.stringify(config, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `system-config-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const importedConfig = JSON.parse(text);
      
      // Validate imported config
      if (typeof importedConfig !== 'object' || importedConfig === null) {
        throw new Error('Invalid configuration format');
      }

      setFormData(importedConfig);
      setSuccess('Configuration imported. Click Save to apply.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(`Failed to import configuration: ${err.message}`);
    }
    
    // Reset file input
    event.target.value = '';
  };

  const updateFormField = (category: string, field: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [category]: {
        ...(prev[category as keyof SystemConfig] as any),
        [field]: value,
      },
    }));
  };

  if (loading && !config) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-8 h-8 text-gray-400 animate-spin" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">System Configuration</h1>
        <p className="mt-2 text-gray-600">Manage system settings and configuration</p>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-600" />
          <span className="text-red-800">{error}</span>
        </div>
      )}

      {success && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-600" />
          <span className="text-green-800">{success}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="flex gap-4">
          <button
            onClick={() => setActiveTab('config')}
            className={`py-2 px-4 border-b-2 font-medium text-sm ${
              activeTab === 'config'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Settings className="w-4 h-4 inline mr-2" />
            Configuration
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`py-2 px-4 border-b-2 font-medium text-sm ${
              activeTab === 'history'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <History className="w-4 h-4 inline mr-2" />
            History
          </button>
        </nav>
      </div>

      {/* Configuration Tab */}
      {activeTab === 'config' && (
        <div className="space-y-6">
          {/* Export/Import Actions */}
          <div className="flex justify-end gap-2">
            <label className="px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer flex items-center gap-2">
              <Upload className="w-4 h-4" />
              Import
              <input
                type="file"
                accept=".json"
                onChange={handleImport}
                className="hidden"
              />
            </label>
            <button
              onClick={handleExport}
              className="px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
            >
              <Download className="w-4 h-4" />
              Export
            </button>
          </div>

          {/* Category Tabs */}
          <div className="bg-white rounded-lg shadow border border-gray-200">
            <div className="border-b border-gray-200">
              <nav className="flex gap-1 p-2">
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setActiveCategory(cat.id)}
                    className={`px-4 py-2 rounded-md text-sm font-medium ${
                      activeCategory === cat.id
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <span className="mr-2">{cat.icon}</span>
                    {cat.name}
                  </button>
                ))}
              </nav>
            </div>

            <div className="p-6">
              {/* Model Settings */}
              {activeCategory === 'model_settings' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Default Model
                    </label>
                    <input
                      type="text"
                      value={(formData.model_settings?.default_model || '') as string}
                      onChange={(e) => updateFormField('model_settings', 'default_model', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Temperature (0-2)
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={formData.model_settings?.temperature || 0.7}
                      onChange={(e) => updateFormField('model_settings', 'temperature', parseFloat(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Max Tokens
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="100000"
                      value={formData.model_settings?.max_tokens || 2048}
                      onChange={(e) => updateFormField('model_settings', 'max_tokens', parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Context Length
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="100000"
                      value={formData.model_settings?.context_length || 8192}
                      onChange={(e) => updateFormField('model_settings', 'context_length', parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="enable_streaming"
                      checked={formData.model_settings?.enable_streaming || false}
                      onChange={(e) => updateFormField('model_settings', 'enable_streaming', e.target.checked)}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <label htmlFor="enable_streaming" className="ml-2 text-sm text-gray-700">
                      Enable Streaming
                    </label>
                  </div>
                </div>
              )}

              {/* Service Settings */}
              {activeCategory === 'service_settings' && (
                <div className="space-y-4">
                  {Object.entries(formData.service_settings || {}).map(([key, value]) => (
                    <div key={key}>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </label>
                      <input
                        type="text"
                        value={(value as string) || ''}
                        onChange={(e) => updateFormField('service_settings', key, e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Security Settings */}
              {activeCategory === 'security_settings' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      JWT Expiration (hours)
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="8760"
                      value={formData.security_settings?.jwt_expiration_hours || 24}
                      onChange={(e) => updateFormField('security_settings', 'jwt_expiration_hours', parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Max Requests Per Minute
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      value={formData.security_settings?.max_requests_per_minute || 60}
                      onChange={(e) => updateFormField('security_settings', 'max_requests_per_minute', parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="enable_rate_limiting"
                      checked={formData.security_settings?.enable_rate_limiting || false}
                      onChange={(e) => updateFormField('security_settings', 'enable_rate_limiting', e.target.checked)}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <label htmlFor="enable_rate_limiting" className="ml-2 text-sm text-gray-700">
                      Enable Rate Limiting
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="require_https"
                      checked={formData.security_settings?.require_https || false}
                      onChange={(e) => updateFormField('security_settings', 'require_https', e.target.checked)}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <label htmlFor="require_https" className="ml-2 text-sm text-gray-700">
                      Require HTTPS
                    </label>
                  </div>
                </div>
              )}

              {/* Feature Flags */}
              {activeCategory === 'feature_flags' && (
                <div className="space-y-4">
                  {Object.entries(formData.feature_flags || {}).map(([key, value]) => (
                    <div key={key} className="flex items-center">
                      <input
                        type="checkbox"
                        id={key}
                        checked={(value as boolean) || false}
                        onChange={(e) => updateFormField('feature_flags', key, e.target.checked)}
                        className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                      />
                      <label htmlFor={key} className="ml-2 text-sm text-gray-700">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </label>
                    </div>
                  ))}
                </div>
              )}

              {/* Save Button */}
              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => handleSave(activeCategory)}
                  disabled={saving}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      Save {categories.find(c => c.id === activeCategory)?.name}
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="bg-white rounded-lg shadow border border-gray-200">
          <div className="p-6">
            <div className="space-y-4">
              {history.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  No configuration history found.
                </div>
              ) : (
                <>
                  {history.map((item) => (
                    <div
                      key={item.id}
                      className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <div className="font-medium text-gray-900">
                            {item.category || 'All Categories'}
                          </div>
                          <div className="text-sm text-gray-500">
                            Updated by {item.updated_by} on{' '}
                            {new Date(item.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                      <div className="mt-2 text-sm text-gray-600">
                        <pre className="bg-gray-50 p-2 rounded text-xs overflow-x-auto">
                          {JSON.stringify(item.config_data, null, 2)}
                        </pre>
                      </div>
                    </div>
                  ))}
                  
                  {/* Pagination */}
                  {historyTotalPages > 1 && (
                    <div className="flex justify-center gap-2 mt-6">
                      <button
                        onClick={() => setHistoryPage(p => Math.max(1, p - 1))}
                        disabled={historyPage === 1}
                        className="px-4 py-2 border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Previous
                      </button>
                      <span className="px-4 py-2 text-gray-700">
                        Page {historyPage} of {historyTotalPages}
                      </span>
                      <button
                        onClick={() => setHistoryPage(p => Math.min(historyTotalPages, p + 1))}
                        disabled={historyPage === historyTotalPages}
                        className="px-4 py-2 border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Next
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SystemConfig;
