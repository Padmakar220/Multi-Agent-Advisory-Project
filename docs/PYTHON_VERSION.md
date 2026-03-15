# Python Version Requirements

## Recommended Version

The Multi-Agent Advisory AI System is designed for **Python 3.11** as specified in the AWS Lambda runtime requirements.

## Compatibility

The codebase should work with Python 3.9+ for local development, but deployment to AWS Lambda requires Python 3.11.

## Current System

Your system has: **Python 3.9.6**

## Options

### Option 1: Install Python 3.11 (Recommended for Production)

**macOS (using Homebrew):**
```bash
brew install python@3.11
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv
```

**Windows:**
Download from [python.org](https://www.python.org/downloads/)

### Option 2: Use Python 3.9 for Local Development

You can use Python 3.9 for local development and testing. The setup scripts have been updated to support Python 3.9+.

**Note:** When deploying to AWS Lambda, you must use Python 3.11 runtime.

## Verification

Check your Python version:
```bash
python3 --version
```

For Python 3.11 specifically:
```bash
python3.11 --version
```

## Virtual Environment Setup

The setup scripts will automatically detect and use the best available Python version:

```bash
./scripts/setup-venv.sh
```

This will create a virtual environment with your system's Python version.

## AWS Lambda Deployment

When deploying to AWS Lambda, ensure you specify Python 3.11 runtime:

```yaml
Runtime: python3.11
```

The Lambda functions will run with Python 3.11 regardless of your local development version.
