"""Root conftest.py - ensures test-results directory exists before any test run."""
import os

# Create test-results directory for JUnit XML output
os.makedirs("test-results", exist_ok=True)
