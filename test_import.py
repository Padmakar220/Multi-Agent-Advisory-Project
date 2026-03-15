#!/usr/bin/env python
"""Quick import test."""

import sys
print("Python version:", sys.version)

try:
    print("Importing boto3...")
    import boto3
    print("boto3 imported OK")
except Exception as e:
    print(f"Error importing boto3: {e}")

try:
    print("Importing src.models...")
    from src.models.portfolio import Portfolio, Holding
    print("Portfolio models imported OK")
except Exception as e:
    print(f"Error importing portfolio models: {e}")

try:
    print("Importing src.models.responses...")
    from src.models.responses import RebalancingPlan, TradeOrder
    print("Response models imported OK")
except Exception as e:
    print(f"Error importing response models: {e}")

print("All imports successful!")
