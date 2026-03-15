#!/bin/bash
# Run test suite

set -e

# Activate virtual environment if not already activated
if [ -z "$VIRTUAL_ENV" ]; then
    source venv/bin/activate
fi

echo "Running test suite..."
echo ""

# Run unit tests
echo "=== Unit Tests ==="
pytest tests/unit/ -v

echo ""

# Run property-based tests
echo "=== Property-Based Tests ==="
pytest tests/property/ -v

echo ""

# Run integration tests
echo "=== Integration Tests ==="
pytest tests/integration/ -v

echo ""

# Run with coverage
echo "=== Coverage Report ==="
pytest --cov=src --cov=lambda --cov-report=term-missing --cov-report=html tests/

echo ""
echo "✓ All tests complete!"
echo "Coverage report available at: htmlcov/index.html"
