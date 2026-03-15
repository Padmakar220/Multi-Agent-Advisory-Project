#!/bin/bash
# Run code quality checks

set -e

# Activate virtual environment if not already activated
if [ -z "$VIRTUAL_ENV" ]; then
    source venv/bin/activate
fi

echo "Running code quality checks..."
echo ""

# Format code with black
echo "=== Black (Code Formatting) ==="
black --check src/ lambda/ tests/

echo ""

# Sort imports with isort
echo "=== isort (Import Sorting) ==="
isort --check-only src/ lambda/ tests/

echo ""

# Lint with flake8
echo "=== flake8 (Linting) ==="
flake8 src/ lambda/ tests/

echo ""

# Type checking with mypy
echo "=== mypy (Type Checking) ==="
mypy src/ lambda/

echo ""
echo "✓ All code quality checks passed!"
