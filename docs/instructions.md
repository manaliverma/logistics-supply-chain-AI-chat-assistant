## Local ingestion setup

An EC2 instance is not required for development. Docker Desktop on macOS provides
the same SQL Server container locally.

Start the existing container if needed:

```bash
docker start logistics-sql
```

Install the Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Load the dataset into SQL Server:

```bash
MSSQL_PASSWORD='LogisticsDev#2026!' \
  python3 scripts/ingest_legacy_data.py
```

The loader uses `data/raw/dynamic_supply_chain_logistics_dataset.csv` and writes
to `dbo.TBL_SC_FLEET_HIST_RAW`. The local connection settings are:

```text
Server: localhost,1433
Database: master
User: sa
Password: LogisticsDev#2026!
```

In the VS Code **SQL Server (mssql)** extension, enable **Trust server
certificate** and set **Encrypt** to **Optional** for this local Docker
connection. Then run:

```sql
SELECT COUNT(*) AS total_rows
FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

For cloud practice later, the same container can be deployed to an Ubuntu EC2
instance with a persistent Docker volume and a restricted security-group rule
for port 1433.

## Pinecone API setup

Create a Pinecone account and API key from the Pinecone console. Add the key
only to the local `.env` file:

```env
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=logistics-policy
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
```

Do not commit or share the API key. Validate the connection with:

```bash
conda activate fde_test
python scripts/check_pinecone.py
```

Create the index only after selecting the embedding model. The index dimension
must match the model's output dimension.

### Phase 1: SOP ingestion

The `logistics-policy` index uses the local
`sentence-transformers/all-MiniLM-L6-v2` model, which produces 384-dimensional
vectors. The SOP is stored in the `sop` namespace.

After adding the Pinecone key to `.env`, run:

```bash
conda activate fde_test
python scripts/ingest_sop_pinecone.py
```

The script reads
`data/policy/Cold_Chain_Incident_SOP_v2.md`, splits it into chunks, creates
embeddings locally, and upserts the chunks to Pinecone. It is safe to rerun;
the same vector IDs are replaced. Embeddings and Pinecone writes are batched
using `PINECONE_BATCH_SIZE` (default: 16). A SHA-256 manifest in the ignored
`data/cache/` directory skips unchanged documents, and stale vectors are
deleted when a changed document has fewer chunks.
Embedding, stale-vector deletion, and Pinecone batch upserts retry up to
`PINECONE_MAX_RETRIES` times with exponential backoff controlled by
`PINECONE_RETRY_BACKOFF_SECONDS`. After the final failed attempt, the original
error is raised and the manifest is not updated.

Search the ingested SOP through LangChain's `PineconeVectorStore`:

```bash
conda activate fde_test
python scripts/search_sop.py \
  "What should we do when port congestion is above the critical threshold?"
```

The search script uses the same
`sentence-transformers/all-MiniLM-L6-v2` model and the `sop` namespace.

### Document extraction cache

Before embedding mixed input files, extract them into hash-addressed JSON:

```bash
conda activate fde_test
python scripts/cache_documents.py --input data/input --output data/cache
```

Supported formats are `.txt`, `.md`, `.csv`, `.xls`, `.xlsx`, and `.pdf`.
Each JSON file is named with the source file's SHA-256 hash and contains the
normalized text, source metadata, and structured spreadsheet/PDF metadata.
If a source file has not changed, its existing hash JSON is reused. Cached
documents are local generated artifacts and are ignored by Git.

The parser uses a common `DocumentParser` interface with specialized
implementations for text, CSV, spreadsheets, and PDFs. It validates empty
documents, reports unsupported extensions, tries common text encodings, and
reports scanned PDFs that have no extractable text.
Empty or invalid JSON cache files are removed automatically before processing,
and empty chunks are never sent for embedding.

Create sample logistics documents in every supported format:

```bash
python scripts/create_sample_documents.py
python scripts/cache_documents.py --input data/input --output data/cache
```

### Synthetic operational enrichment

The source CSV does not contain product, weather, road-closure, temperature
exposure, or depot-capacity fields. Generate a local, deterministic
Amazon-like US logistics dataset for learning:

```bash
conda activate fde_test
python scripts/enrich_logistics_dataset.py
```

The output is:

```text
data/processed/amazon_like_logistics_dataset.csv
```

This is synthetic training data, not Amazon data. It adds shipment IDs,
fulfillment centers, product categories, product-specific temperature limits,
weather conditions, ambient temperature, road closures, exposure duration,
reefer power availability, depot capacity, and a synthetic-data notice.

### Deterministic routing engine

Evaluate enriched shipments against the SOP rules before adding an AI model:

```bash
conda activate fde_test
python scripts/routing_engine.py
```

The engine handles product-specific temperature breaches, exposure limits,
reefer power failures, port congestion, road closures, weather disruptions,
depot capacity, and high-risk delays. It returns severity, actions, reasons,
escalation owners, and the next update interval. It only evaluates fields
present in the dataset and does not invent missing operational inputs.

## System architecture

The intended application flow is:

```text
User question
    ↓
LangGraph orchestration
    ├── Input validation
    ├── Pinecone SOP retrieval
    ├── Read-only SQL Server query
    ├── Deterministic routing engine
    ├── Missing-data and conflict check
    ├── AI explanation
    ├── Human approval gate
    └── Audited response
```

The deterministic routing engine is authoritative for operational thresholds.
The AI model explains the result, summarizes evidence, and asks for missing
inputs; it must not override the SOP or invent operational facts.

## Security, governance, and guardrails

This project uses synthetic learning data. The SOP is labeled **Internal
Operations Only**. Do not upload real customer, employee, shipment, medical,
payment, or other sensitive production data to external models or Pinecone
without organizational approval.

### Secrets and access

- Keep database passwords, Pinecone keys, and model keys only in `.env`.
- Never commit or print `.env`, credentials, or full API keys.
- Rotate any credential that appears in chat, logs, screenshots, or commits.
- Keep `.env` ignored by Git and use separate development and production
  credentials.
- Bind local SQL Server to `127.0.0.1:1433`; do not expose it publicly.
- Use a read-only SQL credential for agent queries.
- Restrict Pinecone keys to the required project and permissions.

### Data handling and auditability

Minimize metadata stored in Pinecone and avoid unnecessary personal data.
Define retention and deletion rules for cached JSON, vectors, logs, and
database records. Audited events should include:

```text
request_id
timestamp
user_or_session
retrieved_document_ids
query_template
result_summary
routing_rules_triggered
model_response
human_approval
```

Do not record passwords, API keys, or complete sensitive shipment records in
logs.

### Agent guardrails

The agent must:

- Retrieve approved SOP content from the configured Pinecone namespace.
- Use only allowlisted tools.
- Permit only parameterized `SELECT` queries.
- Reject `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, and arbitrary SQL.
- Separate observed facts, SOP rules, assumptions, and recommendations.
- Cite the SOP section and shipment fields used.
- State when required operational input is missing.
- Escalate uncertain or conflicting conditions to the Area Manager.
- Require human approval before rerouting, disposing of cargo, releasing holds,
  or contacting customers.

The model must not independently override rules such as:

```text
PRT_CNG_LVL > 7.0
IOT_TEMP_VAL_C > product maximum
RISK_CLS_TXT = 'High Risk' AND DELAY_PROB_DEC > 0.65
```

Expected AI output should be structured as:

```json
{
  "status": "critical",
  "facts": [],
  "policy_basis": [],
  "required_actions": [],
  "missing_information": [],
  "human_approval_required": true,
  "confidence": "high"
}
```

If a required field is unavailable, the response must say that a decision
cannot be determined rather than assuming a route, weather condition, depot
capacity, or product limit.

## Phase 2: Data security

Phase 2 creates a read-only SQL Server login and exposes only a curated view.
The raw legacy and enriched tables are denied to the agent login.

The setup script is:

```text
scripts/setup_security_and_view.sql
```

Apply it locally with the admin connection:

```bash
conda activate fde_test
python scripts/apply_security_setup.py
```

The password is read from the ignored `.env` variable
`AGENT_FDE_RO_PASSWORD`; it is not stored in the SQL script.

Create a new VS Code SQL Server connection:

```text
Profile name: agent-fde-ro
Connection group: <Default>
Input type: Parameters
Server: localhost
Port: 1433
Trust server certificate: On
Authentication: SQL Login
Username: USR_FDE_RO
Password: value of AGENT_FDE_RO_PASSWORD in local .env
Save password: On
Database: master
Encrypt: Optional
```

Test the allowed view:

```sql
SELECT TOP 5 *
FROM FDE_VIEWS.VW_ACTIVE_FLEET;
```

Test that direct raw-table access is denied:

```sql
SELECT TOP 5 *
FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

The first query should succeed. The second should fail with a permission
error. The AI agent must use the curated view and never receive admin
credentials.

## Implementation phases

The project is built in phases so that operational correctness and governance
are established before production deployment.

### Phase 0: Local foundation — completed

- Create the Python 3.12 `fde_test` environment.
- Run SQL Server locally in Docker.
- Load synthetic logistics telemetry.
- Keep secrets in `.env` and generated files in ignored directories.
- Establish repeatable scripts and standard-library unit tests.

### Phase 1: Evidence ingestion — completed

- Parse TXT, Markdown, CSV, spreadsheet, and PDF sources.
- Cache extracted documents by content hash.
- Chunk and embed approved SOP documents locally.
- Store SOP vectors in Pinecone namespace `sop`.
- Support incremental ingestion, retries, manifests, and stale-vector cleanup.

### Phase 2: Data security — completed

- Create the read-only `USR_FDE_RO` SQL login.
- Expose only `FDE_VIEWS.VW_ACTIVE_FLEET`.
- Deny agent access to raw and enriched tables.
- Use parameterized queries and never pass administrator credentials to the
  agent.

### Phase 3: Deterministic operational decisions — completed

- Evaluate product-specific temperature and exposure limits.
- Evaluate reefer power, port congestion, road closures, weather disruption,
  depot capacity, and high-risk delay conditions.
- Return severity, reasons, actions, escalation owners, and update intervals.
- Keep deterministic routing authoritative; the LLM explains but does not
  override the result.

### Phase 4: Governed agent tools — completed

- Register allowlisted tools for telemetry, SOP retrieval, weather, routes,
  routing decisions, incidents, approvals, health checks, and audit events.
- Return structured external API errors without leaking credentials or URLs.
- Require human approval before rerouting, disposal, hold release, or customer
  contact.
- Reject secret-like fields from audit payloads.

### Phase 5: LangGraph orchestration — completed

- Use `create_agent` with the external governed system prompt.
- Preserve request IDs as LangGraph thread IDs.
- Use checkpointed conversations with `InMemorySaver` for local learning.
- Support non-interactive, interactive, and streamed requests.
- Keep telemetry-first, SOP-backed, deterministic decision flow in the prompt.

### Phase 6: Audit logging and traceability — completed

- Store sanitized append-only development audit events.
- Correlate lifecycle, tool, incident, approval, and final-response events by
  request ID.
- Record request start, completion, failure, cache status, tool activity, and
  response duration.
- Provide `scripts/view_agent_log.py` and the Streamlit Audit Log view.
- Do not store raw prompts, credentials, API keys, or full sensitive records
  by default.

### Phase 7: Streamlit operator UI — current

- Provide a multi-user dispatch console.
- Assign each browser session a separate user ID and thread ID.
- Cache the graph/model once per Streamlit process with `st.cache_resource`.
- Cache the local embedding/vector store and SQL engine per process.
- Use a local fast path for greetings without loading the agent.
- Fall back to uncached graph construction if resource caching fails.
- Show safe tool traces and audit timelines without exposing secrets.

Known local behavior:

- The first operational request may be slower while Gemini, embeddings, and
  Pinecone initialize.
- `torchvision` is not required because the application uses text embeddings.
- Streamlit's file watcher is disabled to avoid optional Transformers vision
  import warnings.
- Current checkpoint state is process-local and is not durable across restarts.

### Phase 8: Reliability and performance hardening — in progress

- Add explicit provider quota and timeout handling with user-safe messages.
- Measure tool and model latency from audit events.
- Add bounded timeouts and controlled retry policies for external providers.
- Add startup health checks and optional process warm-up.
- Add integration tests for SQL Server, Pinecone, weather, routing, and the
  configured LLM provider.
- Add forecast-aware logic for questions such as “what may be affected in the
  next hour”; distinguish current observations from forecasts.

The observability layer now classifies failures as recoverable dependency,
invalid configuration, missing secret, model quota, or database permission
failures. It records request success/failure, provider and model latency,
cache initialization, SQL, Pinecone, weather, routing, incident, approval,
request latency percentiles, and audit-write metrics in the local development
operations store. Use `latency_percentiles("request_latency_ms")` for p50/p95.
Alert evaluation is available through `src.observability.evaluate_alerts`;
production should export these metrics to CloudWatch, Prometheus, or
OpenTelemetry and route alerts to the operations team.

### Grafana and CloudWatch dashboarding

Grafana OSS is free to self-host. Grafana Cloud provides a limited free tier,
but its storage, active-series, retention, and alerting limits depend on the
current plan. The repository includes a local Prometheus/Grafana stack:

```text
ops/monitoring/
    metrics_exporter.py
    prometheus.yml
    docker-compose.yml
    logistics-agent-dashboard.json
```

The local monitoring data flow is:

```text
Streamlit/agent process
    ↓ records metrics
data/cache/agent_operations.sqlite3
    ↓ reads and exposes /metrics
ops/monitoring/metrics_exporter.py
    ↓ Prometheus scrapes every 15 seconds
Prometheus
    ↓ Grafana queries Prometheus
Grafana dashboard
```

Start the exporter first:

```bash
conda activate fde_test
python ops/monitoring/metrics_exporter.py
```

Verify it:

```bash
curl http://localhost:9108/health
curl http://localhost:9108/metrics
```

Then start Prometheus and Grafana:

```bash
docker compose -f ops/monitoring/docker-compose.yml up -d
```

Open the local services:

```text
Exporter:  http://localhost:9108/metrics
Prometheus: http://localhost:9090
Grafana:    http://localhost:3000
```

The Docker Compose service is named `prometheus`. Therefore:

- Your Mac browser reaches Grafana at `http://localhost:3000`.
- Grafana's container reaches Prometheus at `http://prometheus:9090`.
- Prometheus reaches the host exporter at
  `http://host.docker.internal:9108/metrics`.

In Grafana, configure the Prometheus data source:

1. Open **Connections → Data sources → Add data source**.
2. Select **Prometheus**.
3. Set the URL to `http://prometheus:9090`.
4. Select **Save & test**.
5. Import `ops/monitoring/logistics-agent-dashboard.json`.
6. Select the Prometheus data source when Grafana asks for it.

The dashboard includes:

- Request count and success/failure rate.
- Request latency p50, p90, and p95.
- SQL, Pinecone, weather, and routing latency.
- Model quota and recoverable dependency/rate-limit failures.
- Incident and approval-request counts.

The dashboard can show `null` when no samples exist for a metric. For example,
the quota panel remains empty until a quota or rate-limit failure is recorded.
That is different from a scrape failure. Diagnose an empty panel in this
order:

```bash
curl http://localhost:9108/metrics
curl http://localhost:9090/-/healthy
curl http://localhost:9090/api/v1/targets
```

The Prometheus target should show `health: "up"`. If it is up but a panel is
empty, query the metric directly in Prometheus, for example:

```text
logistics_request_latency_ms_quantile{quantile="0.5"}
logistics_failure_model_quota_failure_total
logistics_request_count_total
```

The exporter currently reads the local SQLite metrics store for learning.
Prometheus stores scraped samples, while Grafana only visualizes and queries
them:

```text
exporter = translates application metrics
Prometheus = stores time-series samples
Grafana = displays dashboards and alerts
dashboard JSON = defines panels and PromQL queries
```

Stop the local monitoring stack with:

```bash
docker compose -f ops/monitoring/docker-compose.yml down
```

Do not expose the exporter, Prometheus, or Grafana directly to the public
internet. Use authentication, private networking, TLS, and restricted
security groups in any shared environment.

For production, replace the local SQLite exporter path with one of:

- CloudWatch custom metrics and CloudWatch alarms for an AWS-first deployment.
- Amazon Managed Service for Prometheus plus Grafana.
- Grafana Cloud with Prometheus remote write.
- OpenTelemetry Collector exporting to the approved metrics backend.

Keep metric names stable when migrating so the dashboard queries remain
portable. Production should also add alert rules for high model error rate,
quota exhaustion, SQL/Pinecone failure, audit-write failure, increased p95
latency, repeated critical incidents, missing approval records, and
unauthorized access attempts.

The local Grafana stack provisions three learning-stage alert rules:

```text
logistics-p95-latency
    p95 request latency > 10,000 ms for 5 minutes

logistics-model-quota
    any model quota failure in the evaluation window

logistics-audit-write-failure
    any audit-write failure in the evaluation window
```

These rules are stored in:

```text
ops/monitoring/grafana/provisioning/alerting/logistics-agent-rules.yml
```

They appear in Grafana under **Alerting → Alert rules** after starting or
recreating the Grafana container. Provisioning creates the rules but does not
send notifications. Configure a contact point and notification policy in
Grafana for email, Slack, PagerDuty, or the approved production destination.

CloudWatch is the natural AWS production destination for alarms on quota,
latency, SQL/Pinecone failures, audit failures, critical incidents, missing
approvals, and unauthorized access. Grafana can visualize CloudWatch metrics
through its CloudWatch data source or visualize Prometheus metrics through
Amazon Managed Service for Prometheus.

### CI/CD separation

CI/CD is intentionally separate from application scripts:

```text
.github/workflows/ci.yml
.github/workflows/quality.yml
```

`ci.yml` installs dependencies, compiles Python, and runs unit tests for pull
requests and pushes. Live integration tests are opt-in through the repository
variable `RUN_INTEGRATION_TESTS=true`, because they can access external
services and consume LLM quota. `quality.yml` provides a manually triggered
dependency-review job. Future deployment workflows should build and scan the
container, deploy staging, run health/integration checks, require approval, and
then deploy production.

Current alert policies cover quota exhaustion, database permission failures,
repeated dependency failures, and audit-write failures. Production policies
should additionally alert on high model error rate, p50/p95 latency, repeated
critical incidents, missing approval records, and unauthorized access.

Opt-in live integration checks are separated from unit tests:

```bash
RUN_INTEGRATION_TESTS=1 \
  conda run --no-capture-output -n fde_test \
  python -m unittest discover -s tests/integration -v
```

They cover SQL Server curated-view access, Pinecone retrieval, weather,
routing, audit persistence, and LLM tool calling. Do not run the LLM smoke
test in routine CI because it consumes provider quota.

### Phase 9: Production persistence and deployment — planned

- Replace `InMemorySaver` with a durable shared LangGraph checkpointer.
- Replace the local SQLite operations store with an approved durable audit and
  incident database.
- Use authenticated users and role-based access to dispatch and audit views.
- Use separate development, staging, and production credentials.
- Configure retention, deletion, encryption, monitoring, backups, and alerting.
- Deploy multiple replicas only after thread state and audit writes are shared
  and consistent across replicas.

### Phase 10: Operational acceptance — planned

- Validate least-privilege SQL access.
- Validate incident and approval workflows with operations owners.
- Test provider failures, quota exhaustion, missing telemetry, conflicting
  evidence, and stale data.
- Confirm that every high-risk decision has evidence, deterministic rule
  output, approval state, and an auditable request timeline.
- Obtain formal approval before using real customer, shipment, employee,
  medical, payment, or other sensitive production data.

## Agent tools

`src/agent_tools.py` exposes three deliberately separate tools:

### SOP compliance search

`search_sop_compliance` searches the existing Pinecone SOP index. Pinecone is
the evidence store; it does not itself decide whether an operation is
compliant. The tool is needed so the agent can retrieve the relevant policy
sections for the current question, cite them, and compare them with observed
telemetry and deterministic routing results. This prevents the model from
relying on memory or treating vector similarity as an approval.

### Telemetry query

`query_telemetry` uses the `USR_FDE_RO` SQL login and reads only
`FDE_VIEWS.VW_ACTIVE_FLEET`. It uses a fixed parameterized `SELECT` template,
so the agent cannot submit arbitrary SQL or reach the raw tables.

### Weather lookup

`get_weather` is an external-data adapter, separate from Pinecone and SQL.
It uses Open-Meteo by default for local development. Set
`WEATHER_API_BASE_URL` or replace this adapter when selecting the production
weather provider. It returns current conditions plus one day of hourly
temperature, rain, snowfall, wind speed, and wind direction. Weather
responses are observations and must be combined with the SOP and routing
rules; they must not override them. Weather alone must not be converted into
port congestion or road-closure status.

Open-Meteo uses WMO weather codes. The tool adds a readable
`current.weather_code_description` alongside the numeric
`current.weather_code`; for example, `61` means slight rain and `95` means
thunderstorm.

### Free route and transport baseline

`get_route` uses the public OSRM routing API with OpenStreetMap road data.
It provides a baseline driving route, distance, and estimated duration without
an API key. It is useful for route geometry and normal travel estimates, but
it is not a live traffic service and does not guarantee current road-closure
information.

Therefore:

```text
OSRM/OpenStreetMap = baseline route and distance
SQL telemetry      = observed route risk, closures, and congestion fields
Live traffic API   = optional future production integration
```

Do not treat an OSRM duration as current congestion. For production live
traffic, use an approved provider such as a commercial traffic API or a
regional public transport/road authority feed.

Run the tools from the project environment after configuring `.env`:

```bash
conda activate fde_test
python -c "from src.agent_tools import search_sop_compliance, query_telemetry, get_weather; print('agent tools imported')"
```

The additional governance tools are:

- `evaluate_shipment_routing`: applies deterministic routing rules to the
  latest telemetry. The model does not decide thresholds.
- `record_incident`: records a breach without executing an operational action.
- `get_incident_status`: retrieves incident records for a shipment or incident.
- `request_human_approval`: creates a pending approval for controlled actions.
- `health_check_dependencies`: checks SQL Server, Pinecone, and weather access.
- `write_audit_event`: records sanitized evidence, decisions, and approval
  metadata. Events include an event ID, timestamp, actor, and optional
  request ID for correlation. Secret-like fields are rejected recursively.
- `get_audit_events`: retrieves audit events by request ID or event type for
  investigation and trace review.

The current development implementation stores incidents, approvals, and audit
events in the ignored `data/cache/agent_operations.sqlite3` file. Audit events
are append-only from the tool interface and contain sanitized JSON payloads.
Use the request ID as the trace key:

```text
REQ-...  ->  AUD-... incident_detected
         ->  AUD-... approval_requested
         ->  AUD-... final_assessment
```

Production deployment should replace this with an approved durable
incident/audit database that provides authenticated access, retention,
immutability, and monitoring.

The orchestrator automatically writes lifecycle events around each request:

```text
agent_request_started
agent_request_completed
agent_request_failed
```

These events intentionally store metadata such as provider, message counts,
shipment context, and error type, but not the user's raw question, model
response, credentials, or full tool payloads. Inspect the local log without
calling the LLM:

```bash
conda activate fde_test
python scripts/view_agent_log.py --limit 20
python scripts/view_agent_log.py --request-id REQ-... --json
```

### Agent tool flow

```text
User request or scheduled monitor
        |
        v
query_telemetry
        |
        +--> get_weather (only when current weather is relevant)
        |
        +--> search_sop_compliance (retrieve applicable policy evidence)
        |
        v
evaluate_shipment_routing
        |
        +--> normal/elevated: explain and write_audit_event
        |
        +--> critical: record_incident
                    |
                    +--> request_human_approval for reroute, disposal,
                         hold release, or customer contact
                    |
                    +--> get_incident_status for follow-up
```

The agent may detect, explain, record, and request approval. It must not
execute rerouting, disposal, hold release, or customer-contact actions itself.

## LangGraph orchestration

`src/orchestrator.py` builds the stateful ReAct workflow. The LLM is the
reasoner: it chooses which allowlisted tools are needed and in what order.
The LLM does not replace the deterministic routing engine and cannot bypass
the tool boundaries.

The governed system instructions are stored in:

```text
src/prompts/system_prompt.txt
```

Keeping the prompt separate makes the agent policy and required business
response format reviewable without changing graph code. The prompt must use
the registered tool names: `query_telemetry`, `get_weather`, `get_route`, and
`search_sop_compliance`.

The graph state contains:

```text
messages    conversation and tool-call history
request_id  trace identifier used for audit correlation
shipment_id optional shipment context
status      graph lifecycle status
```

Run a request after configuring Gemini:

```bash
conda activate fde_test
export LLM_PROVIDER=gemini
python -m src.orchestrator \
  --shipment-id US-FC-00032065 \
  "Is this shipment compliant and what action is required?"
```

Run an interactive checkpointed dispatcher session:

```bash
conda activate fde_test
python -m src.orchestrator interactive --interactive
```

The interactive mode reads one user question at a time, streams agent updates,
and reuses one in-memory thread ID until `exit` or `quit`. The system
instructions are still loaded from `src/prompts/system_prompt.txt` through
`create_agent`; the prompt is not manually duplicated as a second
`SystemMessage`.

The default reasoner is Gemini. Configure it in the ignored `.env` file:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.6-flash
```

OpenAI remains an optional provider:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
```

The ReAct loop follows this pattern:

```text
User request
    ↓
LangGraph state
    ↓
LLM reasoner chooses an allowlisted tool
    ↓
Tool result returns to the reasoner
    ↓
Reasoner may call another tool
    ↓
Final explanation
```

For a compliance question, the expected tool sequence is typically:

```text
query_telemetry
    ↓
search_sop_compliance
    ↓
evaluate_shipment_routing
    ↓
record_incident and request_human_approval, if required
    ↓
write_audit_event
```

`get_weather` and `get_route` are conditional tools. They are used only when
current weather or baseline route information is relevant. The graph does not
automatically create a production continuous-monitoring loop; a scheduler or
event consumer would invoke `run_request` or a dedicated monitoring graph.

### Current checkpointing

The agent currently uses a shared in-memory LangGraph checkpointer:

```python
from langgraph.checkpoint.memory import InMemorySaver
```

The `request_id` is passed as the `thread_id`, so repeated requests with the
same ID can reuse conversation state while the Python process is running.
`InMemorySaver` is intentionally temporary for learning: all state is lost
when the process exits. A durable database-backed checkpointer is required
before deployment across restarts or multiple workers.

### Streamlit UI, model caching, and multi-user behavior

Run the UI with:

```bash
conda activate fde_test
streamlit run src/streamlit_app.py
```

The repository disables Streamlit's file watcher. This avoids noisy optional
`torchvision` import warnings from Streamlit inspecting the `transformers`
package. `torchvision` is not required because this agent uses text embeddings
and does not process images. Restart Streamlit after code changes during local
development; production deployments should keep the watcher disabled.

The UI uses `st.cache_resource` to build and retain one graph/model instance
per Streamlit process. This avoids reloading the model on every Streamlit
rerun. Each browser session receives its own user ID and request/thread ID,
while the shared LangGraph checkpointer keeps conversations isolated by that
thread ID.

Greetings such as `hi`, `hello`, and `good morning` use a local fast path and
do not load Gemini, Pinecone, embeddings, or SQL telemetry. Operational
questions still use the governed graph and may be slower on the first request
because the cached graph and local embedding model must initialize. The
embedding/vector store and SQL engine are cached once per application process,
so later requests avoid repeated initialization. Response duration is recorded
in the Streamlit audit event.

If resource caching fails, the UI records the failure and builds an uncached
graph for that request. If that fallback also fails, the request is surfaced
as unavailable and the UI remains running; credentials and raw prompts are
not written to the audit log.

In production, each application process or replica has its own resource cache.
Use a durable checkpointer and shared audit store for multiple replicas.
Streamlit session state is user-session state, not durable storage, so it
cannot replace a database for users, threads, incidents, or audit records.

## Testing before production

Keep the project testable before adding production integrations:

```bash
conda activate fde_test
python -m unittest discover -s tests -v
```

The unit tests mock external APIs and database calls where appropriate. They
cover routing thresholds, weather and route API failures, input validation,
incident and approval persistence, audit logging, and secret-field rejection.
Live Pinecone, SQL Server, weather, and routing checks should be run separately
as integration checks when those services are intentionally available.
The orchestrator tests mock the LLM/ReAct agent and verify state initialization,
request validation, tool registration, and final-message propagation.