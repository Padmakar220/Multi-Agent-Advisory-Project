#!/bin/bash
# Format code automatically

set -e

# Activate virtual environment if not already activated
if [ -z "$VIRTUAL_ENV" ]; then
    source venv/bin/activate
fi

echo "Formatting code..."
echo ""

# Format with black
echo "=== Running black ==="
black src/ lambda/ tests/

echo ""

# Sort imports with isort
echo "=== Running isort ==="
isort src/ lambda/ tests/

echo ""
echo "✓ Code formatting complete!"
