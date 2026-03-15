# Developer Guide

## Project Structure

```
.
├── lambda/                    # Lambda function handlers
│   ├── supervisor-agent/      # LangGraph orchestrator
│   ├── portfolio-analyzer/    # Portfolio analysis agent
│   ├── tax-optimizer/         # Tax-loss harvesting agent
│   ├── rebalancing-agent/     # Portfolio rebalancing agent
│   ├── approval-handler/      # Human-in-the-loop approval
│   ├── trade-executor/        # Brokerage trade execution
│   ├── compliance-screening/  # Input compliance screening
│   ├── llm-judge/             # LLM-based violation review
│   └── market-data-ingestion/ # OpenSearch data ingestion
├── src/
│   ├── compliance/            # Compliance-as-a-Code library
│   │   ├── engine.py          # ComplianceEngine
│   │   ├── models.py          # ComplianceViolation, ComplianceResult
│   │   ├── registry.py        # PolicyRegistry
│   │   └── rules/             # FINRA, NIST, PCI DSS rule functions
│   ├── error_handling/        # Error classification, circuit breaker
│   ├── mcp_tools/             # MCP tool implementations
│   ├── models/                # Data models (Portfolio, TradeOrder, etc.)
│   ├── security/              # Encryption utilities
│   └── utils/                 # Shared utilities (tracing, RAG enricher)
├── infrastructure/            # CloudFormation stacks
├── tests/
│   ├── property/              # Hypothesis property-based tests
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── smoke/                 # Post-deployment smoke tests
├── scripts/                   # Deployment and packaging scripts
└── docs/                      # Documentation
```

---

## Adding a New Agent

1. Create `lambda/{agent-name}/handler.py` with a `lambda_handler` entry point
2. Add the agent to `infrastructure/compute-stack.yaml` as a new Lambda function
3. Add the agent ARN as an environment variable in `supervisor-agent`
4. Register the agent in `SupervisorAgent._route_to_agents()` in `lambda/supervisor-agent/handler.py`
5. Add RAGEnricher integration: `self.rag_enricher = RAGEnricher()` in `__init__`, call `enrich()` before prompt construction
6. Write property tests in `tests/property/test_{agent}_properties.py`
7. Write unit tests in `tests/unit/test_{agent}.py`

---

## Adding a New Compliance Rule

1. Add a pure function to the appropriate rules file in `src/compliance/rules/`
   - Function signature: `def check_rule(text: str, metadata: dict) -> Optional[ComplianceViolation]`
   - No AWS dependencies allowed
2. Register the rule in `src/compliance/engine.py` `_register_default_rules()`
3. Add test cases to `tests/unit/test_compliance_rules.py`
4. Update `compliance_config.yaml` if threshold changes are needed

---

## Adding a New MCP Tool

1. Create `src/mcp_tools/{tool_name}.py` implementing the tool class
2. Add `execute()` method returning the appropriate data model
3. Add error handling for DynamoDB/OpenSearch/external API errors
4. Write property tests in `tests/property/test_mcp_{tool_name}.py`
5. Integrate into the relevant agent Lambda handler

---

## Testing

### Run unit tests
```bash
pytest tests/unit/ -v --cov=src --cov=lambda --cov-report=term-missing
```

### Run property-based tests
```bash
pytest tests/property/ -v --hypothesis-show-statistics
```

### Run integration tests (requires LocalStack)
```bash
localstack start -d
pytest tests/integration/ -v
```

### Run smoke tests (post-deployment)
```bash
python tests/smoke/test_deployment_smoke.py --env dev
```

### Coverage requirements
- `src/compliance/`: 100% (enforced in CI)
- All other `src/` and `lambda/`: 80%+

---

## Local Development

### Setup
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment variables for local testing
```bash
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
export DYNAMODB_TABLE_PORTFOLIOS=advisory-portfolios
export OPENSEARCH_ENDPOINT=localhost:9200
export COMPLIANCE_VIOLATIONS_TABLE=advisory-compliance-violations
```

### Running a Lambda locally
```bash
python -c "
from lambda.portfolio_analyzer.handler import lambda_handler
result = lambda_handler({'user_id': 'u1', 'portfolio_id': 'p1'}, None)
print(result)
"
```
