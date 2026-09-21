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
