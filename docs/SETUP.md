# Setup Guide

This guide walks you through setting up the Multi-Agent Advisory AI System for local development.

## Prerequisites

### Required Software

1. **Python 3.11 or higher**
   - Download from [python.org](https://www.python.org/downloads/)
   - Verify installation: `python3.11 --version`

2. **AWS CLI**
   - Install: `pip install awscli`
   - Verify installation: `aws --version`

3. **Git**
   - Download from [git-scm.com](https://git-scm.com/)
   - Verify installation: `git --version`

### AWS Account Requirements

1. **AWS Account** with access to:
   - Amazon Bedrock (Claude 3.5 Sonnet model)
   - AWS Lambda
   - Amazon DynamoDB
   - Amazon OpenSearch Serverless
   - AWS Step Functions
   - Amazon API Gateway
   - Amazon Cognito
   - AWS IAM

2. **IAM Permissions** for:
   - Creating and managing Lambda functions
   - Creating and managing DynamoDB tables
   - Creating and managing OpenSearch collections
   - Invoking Bedrock models
   - Creating and managing Step Functions
   - Creating and managing API Gateway APIs
   - Creating and managing Cognito User Pools

## Local Development Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd multi-agent-advisory-ai-system
```

### 2. Set Up Python Virtual Environment

**On macOS/Linux:**
```bash
chmod +x scripts/setup-venv.sh
./scripts/setup-venv.sh
source venv/bin/activate
```

**On Windows:**
```cmd
scripts\setup-venv.bat
venv\Scripts\activate.bat
```

### 3. Configure AWS Credentials

```bash
aws configure
```

Enter your AWS credentials when prompted:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., us-east-1)
- Default output format (json)

### 4. Enable Bedrock Model Access

1. Go to AWS Console → Amazon Bedrock
2. Navigate to "Model access"
3. Request access to "Claude 3.5 Sonnet" model
4. Wait for approval (usually instant)

### 5. Verify Setup

```bash
# Run tests to verify everything is working
pytest tests/

# Check code quality
./scripts/lint.sh
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run specific test category
pytest tests/unit/
pytest tests/property/
pytest tests/integration/

# Run with coverage
pytest --cov=src --cov=lambda tests/
```

### Code Formatting

```bash
# Format code automatically
./scripts/format.sh

# Check code quality
./scripts/lint.sh
```

### Working with Lambda Functions

Each Lambda function is in its own directory under `lambda/`:

```
lambda/
├── supervisor-agent/
│   ├── handler.py          # Lambda entry point
│   ├── requirements.txt    # Function-specific dependencies
│   └── ...
```

### Working with Shared Code

Shared code is in the `src/` directory:

```
src/
├── models/          # Data models (Portfolio, Transaction, etc.)
├── mcp_tools/       # MCP tool implementations
├── utils/           # Utility functions
└── error_handling/  # Error handling framework
```

## Environment Configuration

Configuration files are in the `config/` directory:

- `dev.yaml`: Development environment
- `staging.yaml`: Staging environment
- `prod.yaml`: Production environment

## Troubleshooting

### Python 3.11 Not Found

If you get "python3.11: command not found":
- Install Python 3.11 from python.org
- On macOS with Homebrew: `brew install python@3.11`
- On Ubuntu: `sudo apt install python3.11`

### AWS Credentials Not Configured

If you get AWS credential errors:
- Run `aws configure` to set up credentials
- Verify credentials: `aws sts get-caller-identity`

### Bedrock Model Access Denied

If you get Bedrock access errors:
- Go to AWS Console → Bedrock → Model access
- Request access to Claude 3.5 Sonnet
- Wait for approval

### Import Errors

If you get import errors:
- Ensure virtual environment is activated: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

## Next Steps

- Review the [Requirements Document](.kiro/specs/multi-agent-advisory-ai-system/requirements.md)
- Review the [Technical Design](.kiro/specs/multi-agent-advisory-ai-system/design.md)
- Review the [Implementation Tasks](.kiro/specs/multi-agent-advisory-ai-system/tasks.md)
- Start implementing tasks from the task list

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the documentation in the `docs/` directory
- Contact the development team
