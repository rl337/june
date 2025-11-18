# Monitoring and Alerting for Integration Test Service

This guide explains how to set up monitoring and alerting for the June integration test service using Prometheus and Grafana.

## Overview

The integration test service exposes Prometheus metrics at `/metrics` endpoint and can be monitored via:
- **Prometheus** - Metrics collection and alerting
- **Grafana** - Visualization and dashboards
- **Alertmanager** - Alert routing and notifications

## Metrics Exposed

The integration test service exposes the following metrics:

### Test Run Metrics

- `integration_test_runs_total` - Counter of test runs by status and test_path
  - Labels: `status` (completed, failed, cancelled), `test_path`
- `integration_test_run_duration_seconds` - Histogram of test run durations
  - Labels: `status`, `test_path`
- `integration_test_runs_active` - Gauge of currently active (running or pending) test runs

### Service Metrics

- `service_health{service="integration-test"}` - Service health status (1 = healthy, 0 = unhealthy)
- `http_requests_total` - HTTP request counter
  - Labels: `method`, `endpoint`, `status_code`
- `http_request_duration_seconds` - HTTP request duration histogram
  - Labels: `method`, `endpoint`, `status_code`

## Prometheus Configuration

### Scrape Configuration

Add the integration test service to Prometheus scrape configs in `config/prometheus.yml`:

```yaml
- job_name: 'integration-test'
  static_configs:
    - targets: ['integration-test:8082']
      labels:
        service: 'integration-test'
        component: 'testing'
        tier: 'infrastructure'
  metrics_path: '/metrics'
  scrape_interval: 15s
```

**Note:** The service name in docker-compose.yml is `integration-test`, so Prometheus should scrape `integration-test:8082` when running in Docker Compose.

### Alert Rules

Alert rules are defined in `config/prometheus-alerts.yml`. The integration test service has the following alerts:

1. **IntegrationTestServiceDown** - Service is down
   - Severity: warning
   - Condition: `up{job="integration-test"} == 0` for 1 minute

2. **IntegrationTestFailures** - Test failures detected
   - Severity: warning
   - Condition: Failed test runs > 0 per second for 5 minutes

3. **IntegrationTestHighFailureRate** - High failure rate
   - Severity: critical
   - Condition: >50% of tests failing for 10 minutes

4. **IntegrationTestLongDuration** - Tests taking too long
   - Severity: warning
   - Condition: p95 duration > 30 minutes for 5 minutes

5. **IntegrationTestServiceUnhealthy** - Service health check failing
   - Severity: warning
   - Condition: `service_health{service="integration-test"} == 0` for 2 minutes

### Loading Alert Rules

To load alert rules in Prometheus:

1. **If Prometheus is in home_infra:**
   - Copy `config/prometheus-alerts.yml` to your Prometheus configuration directory
   - Update Prometheus config to include the alert rules file
   - Reload Prometheus configuration

2. **If using local Prometheus:**
   - Ensure `prometheus-alerts.yml` is in the Prometheus config directory
   - Prometheus config should reference it: `rule_files: ["prometheus-alerts.yml"]`

## Grafana Dashboard

### Importing the Dashboard

1. **Access Grafana:**
   - Navigate to Grafana (typically `http://localhost:3000` or via home_infra)

2. **Import Dashboard:**
   - Go to Dashboards → Import
   - Upload `config/grafana/integration-test-dashboard.json`
   - Or paste the JSON content
   - Select Prometheus datasource
   - Click "Import"

3. **Dashboard Panels:**
   - **Active Test Runs** - Current number of running/pending tests
   - **Test Success Rate** - Percentage of successful test runs
   - **Service Health** - Integration test service health status
   - **Test Runs by Status** - Time series of completed/failed/cancelled tests
   - **Test Run Duration (p95)** - 95th percentile test duration
   - **Test Failure Rate** - Percentage of failed tests over time

### Dashboard Features

- **Auto-refresh:** Dashboard refreshes every 30 seconds
- **Time range:** Default view shows last 1 hour
- **Color coding:** 
  - Green = healthy/good
  - Yellow = warning
  - Red = critical/failure

## Alerting Setup

### Prometheus Alertmanager

To receive alerts, configure Alertmanager:

1. **Alertmanager Configuration:**
   ```yaml
   route:
     group_by: ['alertname', 'severity']
     group_wait: 10s
     group_interval: 10s
     repeat_interval: 12h
     receiver: 'default'
     routes:
       - match:
           severity: critical
         receiver: 'critical-alerts'
       - match:
           severity: warning
         receiver: 'warning-alerts'
   
   receivers:
     - name: 'default'
       webhook_configs:
         - url: 'http://your-webhook-url'
     - name: 'critical-alerts'
       email_configs:
         - to: 'admin@example.com'
     - name: 'warning-alerts'
       email_configs:
         - to: 'team@example.com'
   ```

2. **Notification Channels:**
   - Email
   - Slack
   - PagerDuty
   - Webhooks
   - etc.

### Alert Examples

**Test Failure Alert:**
```
Alert: IntegrationTestFailures
Severity: warning
Message: Integration tests are failing. 0.5 failed test runs per second in the last 5 minutes.
```

**High Failure Rate Alert:**
```
Alert: IntegrationTestHighFailureRate
Severity: critical
Message: More than 50% of integration tests are failing for more than 10 minutes.
```

## Monitoring Best Practices

1. **Set up alerts early:** Configure alerts before deploying to production
2. **Use appropriate severities:**
   - `critical` - Immediate action required (service down, high failure rate)
   - `warning` - Attention needed (test failures, long durations)
   - `info` - Informational (low throughput, etc.)
3. **Monitor trends:** Watch for gradual degradation, not just failures
4. **Review dashboards regularly:** Check dashboard at least daily
5. **Correlate with deployments:** Link test failures to code deployments
6. **Set up notifications:** Ensure alerts reach the right people

## Troubleshooting

### Metrics Not Appearing

1. **Check service is running:**
   ```bash
   docker compose ps integration-test
   curl http://localhost:8082/health
   ```

2. **Check metrics endpoint:**
   ```bash
   curl http://localhost:8082/metrics | grep integration_test
   ```

3. **Check Prometheus scrape config:**
   - Verify `integration-test:8082` is in scrape configs
   - Check Prometheus targets page: `http://localhost:9090/targets`
   - Verify target is "UP"

4. **Check network connectivity:**
   - Ensure integration-test service is on `shared-network`
   - Verify Prometheus can reach `integration-test:8082`

### Alerts Not Firing

1. **Check alert rules are loaded:**
   - Go to Prometheus alerts page: `http://localhost:9090/alerts`
   - Verify integration test alerts are listed

2. **Check alert conditions:**
   - Verify alert expressions are correct
   - Test expressions in Prometheus query interface

3. **Check Alertmanager:**
   - Verify Alertmanager is running and configured
   - Check Alertmanager status: `http://localhost:9093`

### Dashboard Not Showing Data

1. **Check datasource:**
   - Verify Prometheus datasource is configured in Grafana
   - Test datasource connection

2. **Check time range:**
   - Ensure time range includes when tests ran
   - Check if metrics exist for the time range

3. **Check queries:**
   - Verify Prometheus queries return data
   - Test queries in Prometheus directly

## Integration with Existing Monitoring

The integration test service integrates with existing monitoring infrastructure:

- **Prometheus** - Metrics are scraped from `/metrics` endpoint
- **Grafana** - Dashboard can be imported and customized
- **Alertmanager** - Alerts are routed through existing alerting setup
- **Jaeger** - Tracing is available (if enabled) via OpenTelemetry

## Related Documentation

- **Testing Guide:** See `docs/guides/TESTING.md` for how to use the integration test service
- **Service Documentation:** See service-specific README files
- **Prometheus Configuration:** See `config/prometheus.yml` and `config/prometheus-alerts.yml`
