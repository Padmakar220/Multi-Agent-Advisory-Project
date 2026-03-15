# Multi-Agent Advisory AI System

An advanced portfolio management platform leveraging specialized AI agents to provide tax-optimized, real-time portfolio adjustments using AWS serverless infrastructure.

## Architecture Overview

The system employs a supervisor-agent architecture where a LangGraph-based Supervisor Agent orchestrates three specialized agents:
- **Portfolio Analyzer Agent**: Analyzes performance, risk exposure, and diversification
- **Tax Optimizer Agent**: Identifies tax-loss harvesting opportunities
- **Rebalancing Agent**: Calculates necessary trades to achieve target allocation

## Technology Stack

- **Foundation Model**: Amazon Bedrock (Claude 3.5 Sonnet)
- **Agent Orchestration**: LangGraph
- **Compute**: AWS Lambda (Python 3.11)
- **Workflow**: AWS Step Functions
- **Data Storage**: Amazon DynamoDB
- **Vector Search**: Amazon OpenSearch Serverless
- **Authentication**: Amazon Cognito
- **API**: Amazon API Gateway

## Project Structure

```
.
├── lambda/                      # Lambda function code
│   ├── supervisor-agent/        # Supervisor agent with LangGraph
│   ├── portfolio-analyzer/      # Portfolio analysis agent
│   ├── tax-optimizer/           # Tax optimization agent
│   ├── rebalancing-agent/       # Rebalancing calculation agent
│   ├── trade-executor/          # Trade execution handler
│   ├── approval-handler/        # Human-in-the-loop approval
│   ├── portfolio-updater/       # Portfolio state updater
│   └── market-data-ingestion/   # Market data pipeline
├── infrastructure/              # Infrastructure as Code
│   ├── network-stack.yaml       # VPC, subnets, security groups
│   ├── data-stack.yaml          # DynamoDB, OpenSearch, S3
│   ├── compute-stack.yaml       # Lambda functions
│   ├── ai-stack.yaml            # Bedrock configuration
│   ├── api-stack.yaml           # API Gateway, Cognito
│   └── monitoring-stack.yaml    # CloudWatch, SNS
├── src/                         # Shared Python modules
│   ├── models/                  # Data models and schemas
│   ├── mcp_tools/               # Model Context Protocol tools
│   ├── utils/                   # Utility functions
│   └── error_handling/          # Error handling framework
├── tests/                       # Test suites
│   ├── unit/                    # Unit tests
│   ├── property/                # Property-based tests
│   ├── integration/             # Integration tests
│   └── performance/             # Performance tests
├── config/                      # Configuration files
│   ├── dev.yaml                 # Development environment
│   ├── staging.yaml             # Staging environment
│   └── prod.yaml                # Production environment
├── docs/                        # Documentation
├── scripts/                     # Deployment and utility scripts
└── requirements.txt             # Python dependencies
```

## Setup Instructions

### Prerequisites

- Python 3.11 or higher
- AWS CLI configured with appropriate credentials
- AWS account with permissions for Bedrock, Lambda, DynamoDB, etc.

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd multi-agent-advisory-ai-system
   ```

2. **Create and activate virtual environment**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure AWS credentials**
   ```bash
   aws configure
   ```

5. **Run tests**
   ```bash
   pytest tests/
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run property-based tests
pytest tests/property/

# Run with coverage
pytest --cov=src --cov=lambda tests/
```

### Code Quality

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8 .

# Type checking
mypy src/ lambda/
```

## Deployment

Deployment instructions will be added as infrastructure code is implemented.

## Documentation

- [Requirements Document](.kiro/specs/multi-agent-advisory-ai-system/requirements.md)
- [Technical Design](.kiro/specs/multi-agent-advisory-ai-system/design.md)
- [Implementation Tasks](.kiro/specs/multi-agent-advisory-ai-system/tasks.md)

## License

[Add license information]

## Support

[Add support contact information]
