# Makefile for Multi-Agent Advisory AI System

.PHONY: help setup install test lint format clean deploy

help:
	@echo "Multi-Agent Advisory AI System - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup      - Set up Python virtual environment"
	@echo "  make install    - Install dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make test       - Run all tests"
	@echo "  make test-unit  - Run unit tests only"
	@echo "  make test-prop  - Run property-based tests only"
	@echo "  make lint       - Run code quality checks"
	@echo "  make format     - Format code automatically"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-dev - Deploy to development environment"
	@echo "  make deploy-staging - Deploy to staging environment"
	@echo "  make deploy-prod - Deploy to production environment"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean      - Remove build artifacts and cache"

setup:
	@echo "Setting up virtual environment..."
	./scripts/setup-venv.sh

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt

test:
	@echo "Running all tests..."
	./scripts/run-tests.sh

test-unit:
	@echo "Running unit tests..."
	pytest tests/unit/ \
		--cov=src --cov=lambda \
		--cov-report=term-missing --cov-report=html:htmlcov \
		--cov-fail-under=80 \
		--junitxml=test-results/unit-tests.xml \
		-v

test-prop:
	@echo "Running property-based tests..."
	pytest tests/property/ \
		--hypothesis-show-statistics \
		--junitxml=test-results/property-tests.xml \
		-v

test-integration:
	@echo "Running integration tests..."
	pytest tests/integration/ \
		--timeout=120 \
		--junitxml=test-results/integration-tests.xml \
		-v

test-coverage:
	@echo "Running all tests with combined coverage..."
	pytest tests/unit/ tests/property/ \
		--cov=src --cov=lambda \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml \
		--cov-fail-under=80

lint:
	@echo "Running code quality checks..."
	./scripts/lint.sh

format:
	@echo "Formatting code..."
	./scripts/format.sh

clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".hypothesis" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ htmlcov/ .coverage

deploy-dev:
	@echo "Deploying to development environment..."
	@echo "Not yet implemented - infrastructure code needed"

deploy-staging:
	@echo "Deploying to staging environment..."
	@echo "Not yet implemented - infrastructure code needed"

deploy-prod:
	@echo "Deploying to production environment..."
	@echo "Not yet implemented - infrastructure code needed"
