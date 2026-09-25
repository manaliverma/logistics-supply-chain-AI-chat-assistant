# Local Grafana monitoring

Grafana OSS is free to self-host. Grafana Cloud also has a limited free tier,
but cloud quotas and retention limits apply. This local stack uses Grafana OSS
and Prometheus.

Start the exporter from the repository root:

```bash
conda run --no-capture-output -n fde_test \
  python ops/monitoring/metrics_exporter.py
```

Start Prometheus and Grafana in another terminal:

```bash
docker compose -f ops/monitoring/docker-compose.yml up -d
```

The Compose configuration provisions the Prometheus data source and three
Grafana alert rules automatically:

- p95 request latency above 10 seconds for 5 minutes
- any model quota failure
- any audit-write failure

After changing provisioning files, recreate the Grafana container:

```bash
docker compose -f ops/monitoring/docker-compose.yml up -d --force-recreate grafana
```

Open:

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Metrics exporter: http://localhost:9108/metrics

Grafana login:

```text
username: admin
password: admin
```

In Grafana, add a Prometheus data source with URL:

```text
http://prometheus:9090
```

Import `logistics-agent-dashboard.json`. The dashboard includes request
success/failure, p50/p90/p95 request latency, dependency latency, model quota
and dependency failures, incidents, and approval requests.

View active rules in Grafana under **Alerting → Alert rules**. Provisioned rules
evaluate Prometheus data; they do not send email or Slack until a contact
point and notification policy are configured.

The exporter reads the local development SQLite metrics store. Production
should replace it with a durable metrics backend or emit metrics directly
from the application to Prometheus/OpenTelemetry/CloudWatch. Do not expose
the exporter publicly; place it behind private networking and authentication.
