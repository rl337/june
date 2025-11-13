import React, { useState, useEffect } from 'react';
import { Activity, Server, AlertCircle, CheckCircle, XCircle, Clock, TrendingUp, AlertTriangle, RefreshCw } from 'lucide-react';
import { monitoringAPI } from '../../utils/api';

interface ServiceHealth {
  service: string;
  status: 'healthy' | 'unhealthy' | 'unreachable' | 'error';
  response_time_ms?: number;
  details?: any;
  last_check: string;
  error?: string;
}

interface ServiceMetrics {
  service: string;
  metrics: {
    cpu_usage_percent?: string;
    memory_usage_bytes?: string;
    request_rate_per_second?: string;
    error_rate_per_second?: string;
  };
  timestamp: string;
}

interface MonitoringData {
  services: ServiceHealth[];
  summary: {
    total: number;
    healthy: number;
    unhealthy: number;
    unreachable: number;
    timestamp: string;
  };
}

const SystemMonitoring: React.FC = () => {
  const [monitoringData, setMonitoringData] = useState<MonitoringData | null>(null);
  const [metrics, setMetrics] = useState<ServiceMetrics[]>([]);
  const [overallHealth, setOverallHealth] = useState<string>('unknown');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState<NodeJS.Timeout | null>(null);

  const fetchMonitoringData = async () => {
    try {
      setError(null);
      const healthData = await monitoringAPI.getHealth();
      setOverallHealth(healthData.overall_status || 'unknown');
      setMonitoringData(healthData.services);
      setMetrics(healthData.metrics?.services || []);
      setLoading(false);
    } catch (err: any) {
      console.error('Failed to fetch monitoring data:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to fetch monitoring data');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMonitoringData();

    // Set up auto-refresh if enabled
    if (autoRefresh) {
      const interval = setInterval(fetchMonitoringData, 15000); // Refresh every 15 seconds
      setRefreshInterval(interval);
      return () => {
        if (interval) clearInterval(interval);
      };
    } else {
      if (refreshInterval) {
        clearInterval(refreshInterval);
        setRefreshInterval(null);
      }
    }
  }, [autoRefresh]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'unhealthy':
        return <XCircle className="w-5 h-5 text-red-500" />;
      case 'unreachable':
        return <AlertCircle className="w-5 h-5 text-yellow-500" />;
      case 'error':
        return <AlertTriangle className="w-5 h-5 text-orange-500" />;
      default:
        return <Activity className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'unhealthy':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'unreachable':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'error':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const formatBytes = (bytes: string | undefined): string => {
    if (!bytes) return 'N/A';
    const numBytes = parseFloat(bytes);
    if (isNaN(numBytes)) return 'N/A';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    if (numBytes === 0) return '0 B';
    const i = Math.floor(Math.log(numBytes) / Math.log(1024));
    return `${(numBytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
  };

  const formatNumber = (value: string | undefined, decimals: number = 2): string => {
    if (!value) return 'N/A';
    const num = parseFloat(value);
    if (isNaN(num)) return 'N/A';
    return num.toFixed(decimals);
  };

  const getServiceMetrics = (serviceName: string): ServiceMetrics | undefined => {
    return metrics.find(m => m.service === serviceName);
  };

  if (loading && !monitoringData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Activity className="w-8 h-8 text-gray-400 mx-auto mb-2 animate-spin" />
          <p className="text-gray-600">Loading monitoring data...</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Monitoring</h1>
          <p className="mt-2 text-gray-600">Monitor service health and system metrics</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-300"
            />
            Auto-refresh
          </label>
          <button
            onClick={fetchMonitoringData}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-center gap-2 text-red-800">
            <AlertCircle className="w-5 h-5" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Overall Health Status */}
      {monitoringData && (
        <div className="mb-6">
          <div className={`p-6 rounded-lg border-2 ${getStatusColor(overallHealth)}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {getStatusIcon(overallHealth)}
                <div>
                  <h2 className="text-xl font-semibold">Overall System Status</h2>
                  <p className="text-sm opacity-80">
                    {monitoringData.summary.healthy} healthy, {monitoringData.summary.unhealthy} unhealthy, {monitoringData.summary.unreachable} unreachable
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm opacity-80">Last updated</p>
                <p className="text-sm font-medium">
                  {new Date(monitoringData.summary.timestamp).toLocaleTimeString()}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Services Grid */}
      {monitoringData && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {monitoringData.services.map((service) => {
            const serviceMetrics = getServiceMetrics(service.service);
            return (
              <div
                key={service.service}
                className="bg-white rounded-lg shadow border border-gray-200 p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Server className="w-5 h-5 text-gray-600" />
                    <h3 className="text-lg font-semibold text-gray-900 capitalize">
                      {service.service.replace('-', ' ')}
                    </h3>
                  </div>
                  {getStatusIcon(service.status)}
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-600">Status</span>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(service.status)}`}>
                      {service.status}
                    </span>
                  </div>

                  {service.response_time_ms !== null && service.response_time_ms !== undefined && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Response Time</span>
                      <span className="text-gray-900 font-medium">{service.response_time_ms.toFixed(2)} ms</span>
                    </div>
                  )}

                  {serviceMetrics && (
                    <>
                      {serviceMetrics.metrics.cpu_usage_percent && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">CPU Usage</span>
                          <span className="text-gray-900 font-medium">
                            {formatNumber(serviceMetrics.metrics.cpu_usage_percent)}%
                          </span>
                        </div>
                      )}

                      {serviceMetrics.metrics.memory_usage_bytes && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">Memory Usage</span>
                          <span className="text-gray-900 font-medium">
                            {formatBytes(serviceMetrics.metrics.memory_usage_bytes)}
                          </span>
                        </div>
                      )}

                      {serviceMetrics.metrics.request_rate_per_second && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">Request Rate</span>
                          <span className="text-gray-900 font-medium">
                            {formatNumber(serviceMetrics.metrics.request_rate_per_second)} req/s
                          </span>
                        </div>
                      )}

                      {serviceMetrics.metrics.error_rate_per_second && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">Error Rate</span>
                          <span className="text-red-600 font-medium">
                            {formatNumber(serviceMetrics.metrics.error_rate_per_second)} err/s
                          </span>
                        </div>
                      )}
                    </>
                  )}

                  {service.error && (
                    <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-800">
                      {service.error}
                    </div>
                  )}

                  <div className="flex items-center gap-1 text-xs text-gray-500 pt-2 border-t">
                    <Clock className="w-3 h-3" />
                    <span>Last check: {new Date(service.last_check).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Metrics Summary */}
      {metrics.length > 0 && (
        <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            System Metrics
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((serviceMetric) => (
              <div key={serviceMetric.service} className="border border-gray-200 rounded p-4">
                <h3 className="text-sm font-medium text-gray-700 mb-2 capitalize">
                  {serviceMetric.service.replace('-', ' ')}
                </h3>
                <div className="space-y-1 text-xs">
                  {serviceMetric.metrics.cpu_usage_percent && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">CPU:</span>
                      <span className="font-medium">{formatNumber(serviceMetric.metrics.cpu_usage_percent)}%</span>
                    </div>
                  )}
                  {serviceMetric.metrics.memory_usage_bytes && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Memory:</span>
                      <span className="font-medium">{formatBytes(serviceMetric.metrics.memory_usage_bytes)}</span>
                    </div>
                  )}
                  {serviceMetric.metrics.request_rate_per_second && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Requests:</span>
                      <span className="font-medium">{formatNumber(serviceMetric.metrics.request_rate_per_second)}/s</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Integration Links */}
      <div className="mt-6 bg-white rounded-lg shadow border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Monitoring Integrations</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href={`${process.env.REACT_APP_PROMETHEUS_URL || 'http://localhost:9090'}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <Activity className="w-5 h-5 text-orange-500" />
            <div>
              <p className="font-medium text-gray-900">Prometheus</p>
              <p className="text-sm text-gray-600">View detailed metrics</p>
            </div>
          </a>
          <a
            href={`${process.env.REACT_APP_GRAFANA_URL || 'http://localhost:3000'}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <TrendingUp className="w-5 h-5 text-blue-500" />
            <div>
              <p className="font-medium text-gray-900">Grafana</p>
              <p className="text-sm text-gray-600">View dashboards</p>
            </div>
          </a>
          <a
            href={`${process.env.REACT_APP_LOKI_URL || 'http://localhost:3100'}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <AlertCircle className="w-5 h-5 text-purple-500" />
            <div>
              <p className="font-medium text-gray-900">Loki</p>
              <p className="text-sm text-gray-600">View service logs</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  );
};

export default SystemMonitoring;
