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