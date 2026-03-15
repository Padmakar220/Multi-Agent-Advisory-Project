# Contributing to Multi-Agent Advisory AI System

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Set up the development environment: `./scripts/setup-venv.sh`
4. Create a feature branch: `git checkout -b feature/your-feature-name`

## Code Standards

### Python Style Guide

- Follow PEP 8 style guide
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use descriptive variable and function names

### Code Formatting

Before committing, run:

```bash
# Format code
./scripts/format.sh

# Check code quality
./scripts/lint.sh
```

### Testing Requirements

- Write unit tests for all new functions
- Write property-based tests for core logic
- Maintain 80%+ code coverage
- All tests must pass before merging

```bash
# Run tests
./scripts/run-tests.sh

# Run specific test category
pytest tests/unit/
pytest tests/property/
```

## Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Example:**
```
feat(portfolio-analyzer): add risk metrics calculation

Implement calculation of portfolio volatility, beta, and VaR.
Includes unit tests and property-based tests.

Closes #123
```

## Pull Request Process

1. **Update Documentation**
   - Update README.md if needed
   - Add docstrings to new functions
   - Update relevant documentation in docs/

2. **Run Tests**
   - Ensure all tests pass
   - Add new tests for new functionality
   - Verify code coverage remains above 80%

3. **Code Review**
   - Request review from at least one maintainer
   - Address all review comments
   - Ensure CI/CD pipeline passes

4. **Merge Requirements**
   - All tests passing
   - Code review approved
   - No merge conflicts
   - Documentation updated

## Project Structure

```
.
├── lambda/              # Lambda function implementations
├── src/                 # Shared Python modules
│   ├── models/          # Data models
│   ├── mcp_tools/       # MCP tool implementations
│   ├── utils/           # Utility functions
│   └── error_handling/  # Error handling framework
├── tests/               # Test suites
├── infrastructure/      # CloudFormation/CDK templates
├── config/              # Environment configurations
├── docs/                # Documentation
└── scripts/             # Utility scripts
```

## Adding New Features

### Adding a New Agent

1. Create directory: `lambda/new-agent/`
2. Implement handler: `lambda/new-agent/handler.py`
3. Add tests: `tests/unit/test_new_agent.py`
4. Update infrastructure: `infrastructure/compute-stack.yaml`
5. Document in README.md

### Adding a New MCP Tool

1. Create tool: `src/mcp_tools/new_tool.py`
2. Add tests: `tests/unit/test_new_tool.py`
3. Register in tool registry
4. Document usage

### Adding Property-Based Tests

1. Identify the property to test
2. Create test file: `tests/property/test_properties_<category>.py`
3. Use Hypothesis for test generation
4. Reference design document property number
5. Set max_examples=100

Example:
```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100)
@given(portfolio=st.builds(Portfolio))
def test_property_X(portfolio):
    """
    Feature: multi-agent-advisory-ai-system
    Property X: Description of property
    """
    # Test implementation
    pass
```

## Code Review Checklist

- [ ] Code follows style guide
- [ ] All tests pass
- [ ] Code coverage maintained/improved
- [ ] Documentation updated
- [ ] No hardcoded credentials or secrets
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Type hints included
- [ ] Docstrings added

## Reporting Issues

### Bug Reports

Include:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (Python version, AWS region, etc.)
- Error messages and stack traces

### Feature Requests

Include:
- Description of the feature
- Use case and motivation
- Proposed implementation (if any)
- Potential impact on existing functionality

## Questions?

- Check the [documentation](docs/)
- Review existing issues and pull requests
- Contact the maintainers

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
