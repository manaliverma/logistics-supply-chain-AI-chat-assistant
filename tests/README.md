# Tests

The test suite uses Python's standard `unittest` framework, so it does not
require a new test dependency or live external services.

Run all tests from the repository root:

```bash
conda activate fde_test
python -m unittest discover -s tests -v
```

The tests cover:

- Deterministic routing thresholds and escalation
- Weather-code mapping
- Weather and OSRM failure responses
- Coordinate and query-limit validation
- Incident, approval, and audit persistence
- Audit secret-field rejection
- LangGraph state initialization and ReAct tool registration

External Pinecone, SQL Server, weather, and routing calls are mocked in unit
tests. Those services should be exercised separately by integration checks
when the local services are intentionally available.

Run the opt-in live integration checks only when all configured dependencies
are intentionally available:

```bash
RUN_INTEGRATION_TESTS=1 \
  conda run --no-capture-output -n fde_test \
  python -m unittest discover -s tests/integration -v
```

The live checks cover the curated SQL view, Pinecone retrieval, weather,
routing, audit persistence, and an LLM tool-calling smoke test. They can incur
provider costs and quota usage; the LLM check should not run in routine CI.

## CI/CD location

Application-independent delivery automation lives under:

```text
.github/workflows/
```

`ci.yml` runs compilation and unit tests on pushes and pull requests. Its live
integration job runs only when the repository variable
`RUN_INTEGRATION_TESTS=true` is intentionally enabled. `quality.yml` is a
manually triggered dependency-review workflow. Monitoring and deployment
assets live under `ops/`, separate from application logic.
