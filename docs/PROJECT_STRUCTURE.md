# Project Structure

This document describes the organization of the Multi-Agent Advisory AI System codebase.

## Directory Layout

```
multi-agent-advisory-ai-system/
│
├── .kiro/                          # Kiro specifications
│   └── specs/
│       └── multi-agent-advisory-ai-system/
│           ├── requirements.md     # System requirements
│           ├── design.md           # Technical design
│           └── tasks.md            # Implementation tasks
│
├── lambda/                         # AWS Lambda functions
│   ├── supervisor-agent/           # LangGraph-based orchestrator
│   ├── portfolio-analyzer/         # Portfolio analysis agent
│   ├── tax-optimizer/              # Tax optimization agent
│   ├── rebalancing-agent/          # Rebalancing calculation agent
│   ├── trade-executor/             # Trade execution handler
│   ├── approval-handler/           # Human-in-the-loop approval
│   ├── portfolio-updater/          # Portfolio state updater
│   └── market-data-ingestion/      # Market data pipeline
│
├── src/                            # Shared Python modules
│   ├── models/                     # Data models and schemas
│   │   ├── __init__.py
│   │   ├── portfolio.py            # Portfolio, Holding classes
│   │   ├── transaction.py          # Transaction models
│   │   ├── agent_state.py          # Agent state models
│   │   └── requests_responses.py   # Request/response models
│   │
│   ├── mcp_tools/                  # Model Context Protocol tools
│   │   ├── __init__.py
│   │   ├── get_portfolio.py        # Portfolio retrieval tool
│   │   ├── get_cost_basis.py       # Cost basis retrieval tool
│   │   ├── query_market_data.py    # Market data query tool
│   │   ├── manage_agent_state.py   # Agent state management tool
│   │   └── execute_trade.py        # Trade execution tool
│   │
│   ├── utils/                      # Utility functions
│   │   ├── __init__.py
│   │   ├── logging.py              # Structured logging utilities
│   │   ├── metrics.py              # CloudWatch metrics helpers
│   │   └── config.py               # Configuration management
│   │
│   └── error_handling/             # Error handling framework
│       ├── __init__.py
│       ├── errors.py               # Error classes
│       ├── handlers.py             # Error handlers
│       └── circuit_breaker.py      # Circuit breaker pattern
│
├── tests/                          # Test suites
│   ├── unit/                       # Unit tests
│   │   ├── __init__.py
│   │   ├── test_supervisor_agent.py
│   │   ├── test_portfolio_analyzer.py
│   │   ├── test_tax_optimizer.py
│   │   ├── test_rebalancing_agent.py
│   │   ├── test_mcp_tools.py
│   │   └── test_error_handling.py
│   │
│   ├── property/                   # Property-based tests
│   │   ├── __init__.py
│   │   ├── test_properties_supervisor.py
│   │   ├── test_properties_portfolio.py
│   │   ├── test_properties_tax.py
│   │   ├── test_properties_rebalancing.py
│   │   └── ...
│   │
│   ├── integration/                # Integration tests
│   │   ├── __init__.py
│   │   ├── test_end_to_end_rebalancing.py
│   │   ├── test_tax_optimization_workflow.py
│   │   └── test_human_approval_flow.py
│   │
│   └── performance/                # Performance tests
│       ├── __init__.py
│       ├── test_agent_response_time.py
│       └── test_concurrent_requests.py
│
├── infrastructure/                 # Infrastructure as Code
│   ├── README.md
│   ├── network-stack.yaml          # VPC, subnets, security groups
│   ├── data-stack.yaml             # DynamoDB, OpenSearch, S3
│   ├── compute-stack.yaml          # Lambda functions
│   ├── ai-stack.yaml               # Bedrock configuration
│   ├── api-stack.yaml              # API Gateway, Cognito
│   └── monitoring-stack.yaml       # CloudWatch, SNS
│
├── config/                         # Configuration files
│   ├── dev.yaml                    # Development environment
│   ├── staging.yaml                # Staging environment
│   └── prod.yaml                   # Production environment
│
├── docs/                           # Documentation
│   ├── SETUP.md                    # Setup guide
│   ├── AWS_SETUP.md                # AWS-specific setup
│   └── PROJECT_STRUCTURE.md        # This file
│
├── scripts/                        # Utility scripts
│   ├── setup-venv.sh               # Virtual environment setup (Unix)
│   ├── setup-venv.bat              # Virtual environment setup (Windows)
│   ├── verify-setup.sh             # Verify project setup
│   ├── format.sh                   # Code formatting
│   ├── lint.sh                     # Code quality checks
│   └── run-tests.sh                # Run test suite
│
├── .gitignore                      # Git ignore patterns
├── .flake8                         # Flake8 configuration
├── pytest.ini                      # Pytest configuration
├── pyproject.toml                  # Python project configuration
├── requirements.txt                # Python dependencies
├── setup.py                        # Package setup
├── Makefile                        # Make commands
├── CONTRIBUTING.md                 # Contribution guidelines
└── README.md                       # Project overview
```

## Key Components

### Lambda Functions

Each Lambda function is self-contained with its own handler and dependencies:

- **supervisor-agent**: Orchestrates specialized agents using LangGraph
- **portfolio-analyzer**: Analyzes portfolio performance and risk
- **tax-optimizer**: Identifies tax-loss harvesting opportunities
- **rebalancing-agent**: Calculates rebalancing trades
- **trade-executor**: Executes trades through brokerage APIs
- **approval-handler**: Manages human-in-the-loop approval workflow
- **portfolio-updater**: Updates portfolio state after trades
- **market-data-ingestion**: Ingests and indexes market data

### Shared Modules

#### src/models/
Data models using Pydantic for validation:
- Portfolio, Holding, Transaction
- AgentState for session management
- Request/response models for all agents

#### src/mcp_tools/
Model Context Protocol tool implementations:
- Portfolio data retrieval
- Cost basis information
- Market data queries
- Agent state persistence
- Trade execution

#### src/utils/
Utility functions:
- Structured logging with CloudWatch
- Metrics emission
- Configuration management

#### src/error_handling/
Error handling framework:
- Error classification (transient, permanent, critical)
- Retry logic with exponential backoff
- Circuit breaker pattern

### Tests

#### tests/unit/
Unit tests for individual components with mocked dependencies.

#### tests/property/
Property-based tests using Hypothesis to verify universal properties across all inputs.

#### tests/integration/
End-to-end tests validating complete workflows.

#### tests/performance/
Performance tests measuring latency and throughput.

### Infrastructure

CloudFormation/CDK templates organized by layer:
- Network layer (VPC, subnets, security groups)
- Data layer (DynamoDB, OpenSearch, S3)
- Compute layer (Lambda functions)
- AI layer (Bedrock configuration)
- API layer (API Gateway, Cognito)
- Monitoring layer (CloudWatch, SNS)

### Configuration

Environment-specific configurations:
- **dev.yaml**: Development with debug logging
- **staging.yaml**: Staging with production-like settings
- **prod.yaml**: Production with strict security

## File Naming Conventions

### Python Files
- **handler.py**: Lambda function entry point
- **test_*.py**: Test files
- **models.py**: Data model definitions
- **utils.py**: Utility functions

### Configuration Files
- ***.yaml**: YAML configuration files
- **requirements.txt**: Python dependencies
- **pytest.ini**: Test configuration
- **pyproject.toml**: Python project metadata

### Scripts
- **setup-*.sh**: Setup scripts
- ***.sh**: Bash scripts (Unix/Linux/macOS)
- ***.bat**: Batch scripts (Windows)

## Import Conventions

### Absolute Imports
```python
from src.models.portfolio import Portfolio
from src.mcp_tools.get_portfolio import GetPortfolioTool
from src.utils.logging import setup_logger
```

### Relative Imports (within package)
```python
from .models import Portfolio
from .utils import setup_logger
```

## Code Organization Principles

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **DRY (Don't Repeat Yourself)**: Shared code in src/, not duplicated in Lambda functions
3. **Testability**: All code is testable with clear interfaces
4. **Type Safety**: Type hints throughout for better IDE support and error detection
5. **Documentation**: Docstrings for all public functions and classes

## Adding New Components

### Adding a New Lambda Function
1. Create directory: `lambda/new-function/`
2. Add `handler.py` with `lambda_handler` function
3. Add `requirements.txt` if function-specific dependencies needed
4. Add tests: `tests/unit/test_new_function.py`
5. Update infrastructure: `infrastructure/compute-stack.yaml`

### Adding a New MCP Tool
1. Create file: `src/mcp_tools/new_tool.py`
2. Implement tool class with `execute` method
3. Add tests: `tests/unit/test_new_tool.py`
4. Register in tool registry

### Adding a New Data Model
1. Create file: `src/models/new_model.py`
2. Define Pydantic model with validation
3. Add tests: `tests/unit/test_new_model.py`
4. Export from `src/models/__init__.py`

## Development Workflow

1. **Create feature branch**: `git checkout -b feature/your-feature`
2. **Implement changes**: Follow code organization principles
3. **Write tests**: Unit tests + property tests
4. **Format code**: `make format`
5. **Run tests**: `make test`
6. **Check quality**: `make lint`
7. **Commit changes**: Follow commit message conventions
8. **Create pull request**: Request review

## References

- [Setup Guide](SETUP.md)
- [AWS Setup Guide](AWS_SETUP.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
- [Requirements Document](../.kiro/specs/multi-agent-advisory-ai-system/requirements.md)
- [Technical Design](../.kiro/specs/multi-agent-advisory-ai-system/design.md)
