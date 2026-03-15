"""Setup configuration for Multi-Agent Advisory AI System"""

from setuptools import setup, find_packages

setup(
    name="multi-agent-advisory-ai-system",
    version="0.1.0",
    description="AI-powered portfolio management platform with specialized agents",
    author="Your Team",
    author_email="team@example.com",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "boto3>=1.34.34",
        "langgraph>=0.0.26",
        "langchain>=0.1.4",
        "pydantic>=2.5.3",
        "aws-lambda-powertools>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.4",
            "pytest-cov>=4.1.0",
            "hypothesis>=6.98.3",
            "black>=24.1.1",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
            "isort>=5.13.2",
        ],
        "test": [
            "pytest>=7.4.4",
            "pytest-asyncio>=0.23.3",
            "pytest-cov>=4.1.0",
            "hypothesis>=6.98.3",
            "moto>=5.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.11",
    ],
)
