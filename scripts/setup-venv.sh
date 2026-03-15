#!/bin/bash
# Setup Python virtual environment and install dependencies

set -e

echo "Setting up Python virtual environment..."

# Try to find Python 3.11, fall back to python3
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD=python3.11
    echo "Using Python 3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "Using Python $PYTHON_VERSION"
    echo "Note: Python 3.11 is recommended for AWS Lambda compatibility"
else
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.9 or higher"
    exit 1
fi

# Create virtual environment
$PYTHON_CMD -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "✓ Virtual environment setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To deactivate, run:"
echo "  deactivate"
