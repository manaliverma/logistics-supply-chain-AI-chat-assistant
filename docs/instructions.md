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