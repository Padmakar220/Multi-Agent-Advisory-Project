#!/bin/bash
# Verify project setup is complete

set -e

echo "Verifying Multi-Agent Advisory AI System setup..."
echo ""

# Check Python version
echo "=== Checking Python version ==="
if command -v python3.11 &> /dev/null; then
    PYTHON_VERSION=$(python3.11 --version)
    echo "✓ $PYTHON_VERSION found (recommended)"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ $PYTHON_VERSION found"
    echo "  Note: Python 3.11 is recommended for AWS Lambda compatibility"
else
    echo "✗ Python 3 not found"
    echo "  Please install Python 3.9 or higher"
    exit 1
fi

echo ""

# Check AWS CLI
echo "=== Checking AWS CLI ==="
if command -v aws &> /dev/null; then
    AWS_VERSION=$(aws --version)
    echo "✓ AWS CLI found: $AWS_VERSION"
else
    echo "✗ AWS CLI not found"
    echo "  Install with: pip install awscli"
    exit 1
fi

echo ""

# Check AWS credentials
echo "=== Checking AWS credentials ==="
if aws sts get-caller-identity &> /dev/null; then
    echo "✓ AWS credentials configured"
    aws sts get-caller-identity --query 'Account' --output text | xargs -I {} echo "  Account: {}"
else
    echo "✗ AWS credentials not configured"
    echo "  Run: aws configure"
    exit 1
fi

echo ""

# Check directory structure
echo "=== Checking directory structure ==="
REQUIRED_DIRS=(
    "lambda/supervisor-agent"
    "lambda/portfolio-analyzer"
    "lambda/tax-optimizer"
    "lambda/rebalancing-agent"
    "lambda/trade-executor"
    "lambda/approval-handler"
    "lambda/portfolio-updater"
    "lambda/market-data-ingestion"
    "src/models"
    "src/mcp_tools"
    "src/utils"
    "src/error_handling"
    "tests/unit"
    "tests/property"
    "tests/integration"
    "tests/performance"
    "infrastructure"
    "config"
    "docs"
    "scripts"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "✓ $dir"
    else
        echo "✗ $dir missing"
        exit 1
    fi
done

echo ""

# Check required files
echo "=== Checking required files ==="
REQUIRED_FILES=(
    "requirements.txt"
    "README.md"
    ".gitignore"
    "pytest.ini"
    "pyproject.toml"
    ".flake8"
    "setup.py"
    "Makefile"
    "CONTRIBUTING.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ $file"
    else
        echo "✗ $file missing"
        exit 1
    fi
done

echo ""

# Check virtual environment
echo "=== Checking virtual environment ==="
if [ -d "venv" ]; then
    echo "✓ Virtual environment exists"
    if [ -f "venv/bin/activate" ]; then
        echo "✓ Activation script found"
    else
        echo "✗ Activation script not found"
    fi
else
    echo "⚠ Virtual environment not created yet"
    echo "  Run: ./scripts/setup-venv.sh"
fi

echo ""

# Check if dependencies are installed (if venv exists)
if [ -d "venv" ] && [ -n "$VIRTUAL_ENV" ]; then
    echo "=== Checking installed dependencies ==="
    REQUIRED_PACKAGES=("boto3" "langgraph" "pytest" "hypothesis")
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if python -c "import $package" 2>/dev/null; then
            echo "✓ $package installed"
        else
            echo "✗ $package not installed"
        fi
    done
else
    echo "⚠ Skipping dependency check (virtual environment not activated)"
fi

echo ""
echo "=== Setup Verification Complete ==="
echo ""
echo "Next steps:"
echo "1. Create virtual environment: ./scripts/setup-venv.sh"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Review documentation: docs/SETUP.md"
echo "4. Configure AWS: docs/AWS_SETUP.md"
echo "5. Start implementing tasks from: .kiro/specs/multi-agent-advisory-ai-system/tasks.md"
