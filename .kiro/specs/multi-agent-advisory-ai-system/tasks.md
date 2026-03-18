# Implementation Plan: Multi-Agent Advisory AI System

## Overview

This implementation plan breaks down the Multi-Agent Advisory AI System into sequential, actionable tasks. The system is a serverless, AI-powered portfolio management platform built on AWS with a supervisor-agent architecture using LangGraph, AWS Bedrock (Claude 3.5 Sonnet), DynamoDB, OpenSearch Serverless, Step Functions, and Lambda.

The implementation follows a bottom-up approach: infrastructure → data layer → MCP tools → agents → orchestration → API → monitoring → testing. Each task builds on previous work to ensure incremental validation and integration.

## Tasks

- [x] 1. Set up project structure and development environment
  - Create directory structure for Lambda functions, infrastructure code, tests, and configuration
  - Set up Python 3.11 virtual environment with dependencies (boto3, langgraph, hypothesis, pytest)
  - Configure AWS CLI and credentials for development
  - Create requirements.txt with all necessary packages
  - Set up .gitignore for Python and AWS artifacts
  - _Requirements: All (foundational)_

- [x] 2. Implement infrastructure as code for networking and security
  - [x] 2.1 Create VPC stack with public and private subnets
    - Define VPC with CIDR block, subnets across 2 AZs, NAT gateways, route tables
    - Create security groups for Lambda functions with egress to AWS services
    - Configure VPC endpoints for DynamoDB, S3, Bedrock, CloudWatch Logs
    - _Requirements: 13.3_

  - [x] 2.2 Create IAM roles and policies
    - Define AgentExecutionRole with permissions for Bedrock, DynamoDB, OpenSearch, CloudWatch
    - Create StepFunctionsExecutionRole with Lambda invocation permissions
    - Implement least-privilege policies with resource-level permissions
    - Add condition keys for user data isolation (dynamodb:LeadingKeys)
    - _Requirements: 13.1, 13.2, 13.5_

  - [x] 2.3 Create KMS customer-managed keys for encryption
    - Create KMS key for DynamoDB table encryption
    - Define key policy allowing DynamoDB service access
    - Enable automatic key rotation
    - _Requirements: 8.5, 13.3_

  - [x] 2.4 Create Cognito User Pool for authentication
    - Configure user pool with password policy (12+ chars, complexity requirements)
    - Enable optional MFA and email verification
    - Set up account recovery mechanisms
    - _Requirements: 13.1_

- [x] 3. Implement data layer infrastructure
  - [x] 3.1 Create DynamoDB tables with CloudFormation/CDK
    - Create Portfolios table (user_id HASH, portfolio_id RANGE) with KMS encryption and streams
    - Create Transactions table (user_id HASH, timestamp RANGE) with PortfolioIndex GSI
    - Create AgentSessions table (session_id HASH) with UserIndex GSI and TTL
    - Create MarketDataCache table (data_key HASH) with TTL
    - Configure PAY_PER_REQUEST billing mode for all tables
    - _Requirements: 8.1, 8.2, 8.5_

  - [x] 3.2 Write property test for DynamoDB schema conformance
    - **Property 31: Portfolio Storage Schema Conformance**
    - **Property 32: Transaction Storage Schema Conformance**
    - **Validates: Requirements 8.1, 8.2**

  - [x] 3.3 Create OpenSearch Serverless collection
    - Create "market-intelligence" collection with VECTORSEARCH type
    - Define index mapping with knn_vector field (1536 dimensions, HNSW algorithm)
    - Configure data access policies for agent IAM roles
    - _Requirements: 9.1_

  - [x] 3.4 Write property test for vector embedding presence
    - **Property 36: Vector Embedding Presence**
    - **Validates: Requirements 9.1**

  - [x] 3.5 Create S3 buckets for document storage
    - Create bucket for portfolio reports with SSE-KMS encryption
    - Configure bucket policies for agent access
    - Enable versioning and lifecycle policies
    - _Requirements: 8.5_

- [x] 4. Implement core data models and utilities
  - [x] 4.1 Create Python data model classes
    - Implement Portfolio, Holding, Transaction, AgentState classes with type hints
    - Implement request/response classes (SupervisorRequest, AnalysisReport, TaxOptimizationPlan, RebalancingPlan)
    - Add validation methods and schema conformance checks
    - Implement serialization/deserialization for DynamoDB
    - _Requirements: 2.5, 3.5, 4.5_

  - [x] 4.2 Write unit tests for data models
    - Test serialization/deserialization round-trip
    - Test validation logic for edge cases (empty portfolios, negative values)
    - Test schema conformance
    - _Requirements: 2.5, 3.5, 4.5_

  - [x] 4.3 Implement error handling framework
    - Create error classification functions (is_transient, is_permanent, is_critical)
    - Implement ErrorResponse class with user-friendly messages and recovery suggestions
    - Create error logging utilities with structured logging format
    - Implement CircuitBreaker class for external service calls
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 4.4 Write property test for error categorization
    - **Property 59: Error Categorization and Retry Logic**
    - **Validates: Requirements 14.3**

  - [x] 4.5 Create CloudWatch logging utilities
    - Implement structured logging with JSON format (timestamp, level, service, user_id, trace_id)
    - Create log level helpers (debug, info, warn, error, critical)
    - Add context managers for trace ID propagation
    - _Requirements: 13.4, 14.1_

- [x] 5. Implement MCP tools for agent-service connectivity
  - [x] 5.1 Create GetPortfolioTool for DynamoDB portfolio retrieval
    - Implement execute method to query Portfolios table by user_id and portfolio_id
    - Add error handling for missing portfolios and DynamoDB errors
    - Return Portfolio object with all holdings and metadata
    - _Requirements: 2.1, 8.1_

  - [x] 5.2 Write property test for portfolio data retrieval
    - **Property 5: Agent Data Retrieval Success**
    - **Property 33: Portfolio Data Retrieval Performance**
    - **Validates: Requirements 2.1, 8.3**

  - [x] 5.3 Create GetCostBasisTool for tax basis information
    - Implement execute method to retrieve cost basis data from DynamoDB
    - Query Portfolios table for specific ticker holdings with purchase dates
    - Return CostBasisInfo with cost per share and purchase date
    - _Requirements: 3.1, 8.4_

  - [x] 5.4 Write property test for cost basis data completeness
    - **Property 34: Cost Basis Data Completeness**
    - **Validates: Requirements 8.4**

  - [x] 5.5 Create QueryMarketDataTool for OpenSearch vector search
    - Implement execute method to perform knn vector search on OpenSearch
    - Generate query embeddings using Bedrock Titan Embeddings model
    - Return ranked market data results with similarity scores
    - Implement caching with MarketDataCache table (5-minute TTL)
    - _Requirements: 2.4, 9.1, 9.2, 9.3_

  - [x] 5.6 Write property tests for market data operations
    - **Property 37: Vector Search Execution**
    - **Property 38: Market Data Cache TTL**
    - **Property 40: Cached Data Fallback with Notification**
    - **Validates: Requirements 9.2, 9.3, 9.5**

  - [x] 5.7 Create ManageAgentStateTool for session persistence
    - Implement save_state method to persist agent state to AgentSessions table
    - Implement load_state method to retrieve session state by session_id
    - Add TTL calculation (24 hours from last update)
    - _Requirements: 7.1, 7.3, 7.5_

  - [x] 5.8 Write property test for state round-trip persistence
    - **Property 28: Agent State Round-Trip Persistence**
    - **Validates: Requirements 7.1, 7.3, 7.5**

  - [x] 5.9 Create ExecuteTradeTool for brokerage API integration
    - Implement execute method to invoke trade-executor Lambda function
    - Pass TradeOrder with all required fields (action, ticker, quantity, order_type)
    - Return TradeConfirmation with execution details
    - Add circuit breaker for brokerage API failures
    - _Requirements: 6.1, 6.2_

- [x] 6. Checkpoint - Verify MCP tools and data layer
  - Ensure all MCP tools can connect to DynamoDB, OpenSearch, and S3
  - Run unit tests for data models and MCP tools
  - Verify IAM permissions allow tool operations
  - Ask the user if questions arise

- [x] 7. Implement Portfolio Analyzer Agent
  - [x] 7.1 Create Lambda function structure for Portfolio Analyzer
    - Create lambda/portfolio-analyzer directory with handler.py
    - Implement lambda_handler entry point accepting AnalysisRequest
    - Set up Bedrock client for Claude 3.5 Sonnet model invocation
    - Configure environment variables (BEDROCK_MODEL_ID, table names, endpoints)
    - _Requirements: 2.1, 12.1, 12.2_

  - [x] 7.2 Implement portfolio data retrieval logic
    - Use GetPortfolioTool to fetch current holdings from DynamoDB
    - Parse holdings into structured format for analysis
    - Handle missing portfolio errors gracefully
    - _Requirements: 2.1_

  - [x] 7.3 Implement performance metrics calculation
    - Calculate total return, annualized return, Sharpe ratio, max drawdown
    - Calculate portfolio volatility, beta, VaR (95%)
    - Compute concentration risk by asset class and individual holdings
    - _Requirements: 2.2_

  - [x] 7.4 Write property test for performance metrics completeness
    - **Property 6: Performance Metrics Completeness**
    - **Validates: Requirements 2.2**

  - [x] 7.5 Implement allocation drift calculation
    - Compare current allocation percentages to target allocation
    - Calculate absolute drift for each asset class
    - Determine if rebalancing is needed based on drift threshold
    - _Requirements: 2.3_

  - [x] 7.6 Write property test for allocation drift accuracy
    - **Property 7: Allocation Drift Calculation Accuracy**
    - **Validates: Requirements 2.3**

  - [x] 7.7 Implement market context retrieval
    - Use QueryMarketDataTool to search OpenSearch for relevant news and data
    - Generate query based on portfolio holdings (tickers, sectors)
    - Extract market insights from search results
    - _Requirements: 2.4, 9.2_

  - [x] 7.8 Write property test for market data query execution
    - **Property 8: Market Data Query Execution**
    - **Validates: Requirements 2.4**

  - [x] 7.9 Implement Bedrock integration for analysis generation
    - Construct prompt with portfolio data, metrics, and market context
    - Invoke Bedrock Claude 3.5 Sonnet model with structured prompt
    - Parse model response and extract recommendations
    - Implement retry logic for invalid responses (up to 2 retries)
    - _Requirements: 12.2, 12.3, 12.4, 12.5_

  - [x] 7.10 Write property tests for Bedrock integration
    - **Property 50: Foundation Model Invocation**
    - **Property 51: Model Prompt Context Completeness**
    - **Property 52: Model Response Validation**
    - **Property 53: Invalid Response Retry**
    - **Validates: Requirements 12.2, 12.3, 12.4, 12.5**

  - [x] 7.11 Assemble and return AnalysisReport
    - Create AnalysisReport object with all metrics, drift, and recommendations
    - Validate report conforms to schema
    - Return structured response to caller
    - _Requirements: 2.5_

  - [x] 7.12 Write property test for analysis report schema conformance
    - **Property 9: Analysis Report Schema Conformance**
    - **Validates: Requirements 2.5**

  - [x] 7.13 Implement error handling for Portfolio Analyzer
    - Add try-catch blocks for DynamoDB, OpenSearch, and Bedrock errors
    - Classify errors as transient or permanent
    - Log errors with structured format
    - Return user-friendly error responses
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 7.14 Write unit tests for Portfolio Analyzer
    - Test with mocked DynamoDB, OpenSearch, and Bedrock clients
    - Test edge cases (empty portfolio, single holding, missing market data)
    - Test error conditions (DynamoDB unavailable, Bedrock throttling)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 8. Implement Tax Optimizer Agent
  - [x] 8.1 Create Lambda function structure for Tax Optimizer
    - Create lambda/tax-optimizer directory with handler.py
    - Implement lambda_handler entry point accepting TaxOptimizationRequest
    - Set up Bedrock client and DynamoDB client
    - Configure environment variables
    - _Requirements: 3.1, 12.1, 12.2_

  - [x] 8.2 Implement cost basis retrieval logic
    - Use GetCostBasisTool to fetch cost basis for all holdings
    - Retrieve current market prices for comparison
    - Calculate unrealized gains/losses for each position
    - _Requirements: 3.1, 3.2_

  - [x] 8.3 Write property test for unrealized loss identification
    - **Property 10: Unrealized Loss Identification Accuracy**
    - **Validates: Requirements 3.2**

  - [x] 8.4 Implement tax-loss harvesting opportunity identification
    - Identify securities with unrealized losses (current value < cost basis)
    - Calculate potential tax savings (loss * tax rate)
    - Find replacement securities to maintain allocation (avoid wash sales)
    - Check wash sale rules (30-day window)
    - _Requirements: 3.2, 3.3_

  - [x] 8.5 Write property test for tax savings calculation
    - **Property 11: Tax Savings Calculation Validity**
    - **Validates: Requirements 3.3**

  - [x] 8.6 Implement Bedrock integration for tax optimization
    - Construct prompt with portfolio, cost basis, and tax context
    - Invoke Bedrock to generate tax-optimized allocation recommendations
    - Parse response for tax-optimized trades
    - Validate after-tax return projections
    - _Requirements: 3.4, 12.2, 12.3, 12.4_

  - [x] 8.7 Write property test for after-tax return optimization
    - **Property 12: After-Tax Return Optimization**
    - **Validates: Requirements 3.4**

  - [x] 8.8 Assemble and return TaxOptimizationPlan
    - Create TaxOptimizationPlan with opportunities, savings, and recommended trades
    - Include wash sale warnings if applicable
    - Validate plan conforms to schema
    - _Requirements: 3.5_

  - [x] 8.9 Write property test for tax optimization plan schema conformance
    - **Property 13: Tax Optimization Plan Schema Conformance**
    - **Validates: Requirements 3.5**

  - [x] 8.10 Implement error handling for Tax Optimizer
    - Add error handling for DynamoDB and Bedrock errors
    - Log errors with structured format
    - Return user-friendly error responses
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 8.11 Write unit tests for Tax Optimizer
    - Test with mocked dependencies
    - Test edge cases (no losses, all losses, wash sale scenarios)
    - Test error conditions
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 9. Implement Rebalancing Agent
  - [x] 9.1 Create Lambda function structure for Rebalancing Agent
    - Create lambda/rebalancing-agent directory with handler.py
    - Implement lambda_handler entry point accepting RebalancingRequest
    - Set up Bedrock client and DynamoDB client
    - Configure environment variables
    - _Requirements: 4.1, 12.1, 12.2_

  - [x] 9.2 Implement allocation delta calculation
    - Calculate difference between current and target allocation for each asset class
    - Convert percentage deltas to dollar amounts based on portfolio value
    - Determine which securities to buy/sell to achieve target
    - _Requirements: 4.1_

  - [x] 9.3 Write property test for allocation delta accuracy
    - **Property 14: Allocation Delta Calculation Accuracy**
    - **Validates: Requirements 4.1**

  - [x] 9.4 Implement trade order generation
    - Generate specific buy/sell orders with tickers, quantities, and order types
    - Calculate estimated prices using current market data
    - Minimize number of trades while achieving target allocation
    - _Requirements: 4.2_

  - [x] 9.5 Write property test for trade order completeness
    - **Property 15: Trade Order Completeness**
    - **Validates: Requirements 4.2**

  - [x] 9.6 Implement transaction cost calculation
    - Calculate commission costs for each trade
    - Estimate slippage based on order size and liquidity
    - Sum total expected costs
    - _Requirements: 4.3_

  - [x] 9.7 Write property test for transaction cost inclusion
    - **Property 16: Transaction Cost Inclusion**
    - **Validates: Requirements 4.3**

  - [x] 9.8 Implement risk tolerance constraint checking
    - Validate trades respect user-defined risk constraints
    - Exclude high-risk securities for conservative portfolios
    - Check against excluded securities list
    - Ensure min trade size requirements are met
    - _Requirements: 4.4_

  - [x] 9.9 Write property test for risk tolerance constraints
    - **Property 17: Risk Tolerance Constraint Satisfaction**
    - **Validates: Requirements 4.4**

  - [x] 9.10 Implement Bedrock integration for rebalancing optimization
    - Construct prompt with portfolio, target allocation, and constraints
    - Invoke Bedrock to optimize trade selection and minimize costs
    - Parse response for optimized trade orders
    - _Requirements: 12.2, 12.3, 12.4_

  - [x] 9.11 Assemble and return RebalancingPlan
    - Create RebalancingPlan with trade orders, costs, and projected allocation
    - Include risk impact analysis
    - Validate plan conforms to schema
    - _Requirements: 4.5_

  - [x] 9.12 Write property test for rebalancing plan schema conformance
    - **Property 18: Rebalancing Plan Schema Conformance**
    - **Validates: Requirements 4.5**

  - [x] 9.13 Implement error handling for Rebalancing Agent
    - Add error handling for DynamoDB and Bedrock errors
    - Log errors with structured format
    - Return user-friendly error responses
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 9.14 Write unit tests for Rebalancing Agent
    - Test with mocked dependencies
    - Test edge cases (already balanced, extreme drift, small portfolio)
    - Test constraint violations
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 10. Checkpoint - Verify all specialized agents
  - Test each agent Lambda function independently with sample inputs
  - Verify Bedrock integration and response parsing
  - Ensure all property tests pass for agents
  - Ask the user if questions arise

- [x] 11. Implement Supervisor Agent with LangGraph
  - [x] 11.1 Create Lambda function structure for Supervisor Agent
    - Create lambda/supervisor-agent directory with handler.py
    - Install langgraph library and dependencies
    - Implement lambda_handler entry point accepting SupervisorRequest
    - Configure environment variables for agent Lambda ARNs
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 11.2 Define LangGraph state schema
    - Create AgentState class with all required fields (user_id, session_id, subtasks, results, retry_counts)
    - Implement state serialization for persistence
    - Add state validation methods
    - _Requirements: 1.1, 7.2_

  - [x] 11.3 Implement request decomposition logic
    - Parse SupervisorRequest and extract intent (analyze, rebalance, tax_optimize)
    - Break down complex requests into subtasks for specialized agents
    - Assign subtask types (analysis, tax, rebalancing)
    - _Requirements: 1.1_

  - [x] 11.4 Write property test for request decomposition completeness
    - **Property 1: Request Decomposition Completeness**
    - **Validates: Requirements 1.1**

  - [x] 11.5 Implement subtask routing logic
    - Route analysis subtasks to Portfolio Analyzer Lambda
    - Route tax subtasks to Tax Optimizer Lambda
    - Route rebalancing subtasks to Rebalancing Agent Lambda
    - Use boto3 Lambda client to invoke agent functions
    - _Requirements: 1.2_

  - [x] 11.6 Write property test for subtask routing correctness
    - **Property 2: Subtask Routing Correctness**
    - **Validates: Requirements 1.2**

  - [x] 11.7 Implement result aggregation logic
    - Collect results from all completed subtasks
    - Merge results into unified response structure
    - Ensure data consistency across results (no conflicting recommendations)
    - _Requirements: 1.3_

  - [x] 11.8 Write property test for result aggregation completeness
    - **Property 3: Result Aggregation Completeness**
    - **Validates: Requirements 1.3**

  - [x] 11.9 Implement retry logic for failed subtasks
    - Track retry count per subtask in state
    - Retry failed subtasks with exponential backoff (2s, 4s, 8s)
    - Stop after 3 retry attempts and return error
    - _Requirements: 1.5_

  - [x] 11.10 Write property test for subtask retry exhaustion
    - **Property 4: Subtask Retry Exhaustion**
    - **Validates: Requirements 1.5**

  - [x] 11.11 Define LangGraph state machine nodes
    - Create ReceiveRequest node to parse incoming requests
    - Create DecomposeTask node to break down requests
    - Create RouteToAgents node to invoke specialized agents
    - Create CheckCompletion node to verify all subtasks done
    - Create AggregateResults node to merge agent outputs
    - Create HumanApproval node to wait for user approval
    - Create ExecuteTrades node to invoke trade execution
    - Create UpdatePortfolio node to persist changes
    - Create RetryTask node for failure handling
    - Create ErrorNotification node for permanent failures
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 11.12 Define LangGraph state machine edges and transitions
    - Connect nodes according to workflow diagram in design
    - Add conditional edges for approval status (approved, rejected, cancelled)
    - Add conditional edges for retry logic (retry < 3, retry >= 3)
    - Add conditional edges for task completion (all complete, more tasks)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 11.13 Implement agent state persistence
    - Use ManageAgentStateTool to save state after each transition
    - Restore state on Lambda invocation for session continuity
    - Include conversation history and user preferences in state
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 11.14 Write property test for session context maintenance
    - **Property 29: Session Context Maintenance**
    - **Validates: Requirements 7.2**

  - [x] 11.15 Implement error handling for Supervisor Agent
    - Handle agent invocation failures with retry logic
    - Handle state persistence failures
    - Log all errors with trace IDs
    - Return structured error responses
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 11.16 Write unit tests for Supervisor Agent
    - Test with mocked agent Lambda invocations
    - Test state transitions and edge conditions
    - Test retry logic and error handling
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 12. Implement human-in-the-loop approval workflow
  - [x] 12.1 Create approval handler Lambda function
    - Create lambda/approval-handler directory with handler.py
    - Implement handler to present trade plans to users
    - Generate approval payload with trade details, tax implications, costs
    - Store pending approval in DynamoDB with task token
    - _Requirements: 5.1, 5.2_

  - [x] 12.2 Write property tests for approval workflow
    - **Property 19: Trade Plan Presentation Requirement**
    - **Property 20: Trade Plan Information Completeness**
    - **Property 21: Approval Prerequisite for Execution**
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 12.3 Create approval response handler
    - Implement endpoint to receive user approval/rejection
    - Resume Step Functions workflow with task token
    - Pass approval status to Supervisor Agent
    - _Requirements: 5.3, 5.4, 5.5_

  - [x] 12.4 Write property tests for approval triggers
    - **Property 22: Rejection Feedback Acceptance**
    - **Property 23: Approval Triggers Execution**
    - **Validates: Requirements 5.4, 5.5**

  - [x] 12.5 Write unit tests for approval workflow
    - Test approval payload generation
    - Test approval/rejection handling
    - Test timeout scenarios (24-hour limit)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 13. Implement trade execution system
  - [x] 13.1 Create trade executor Lambda function
    - Create lambda/trade-executor directory with handler.py
    - Implement handler accepting TradeOrder objects
    - Integrate with brokerage API (mock for development)
    - Return TradeConfirmation with execution details
    - _Requirements: 6.1, 6.2_

  - [x] 13.2 Write property test for MCP tool invocation on approval
    - **Property 24: MCP Tool Invocation on Approval**
    - **Validates: Requirements 6.1**

  - [x] 13.3 Implement transaction recording
    - Write completed trades to Transactions table in DynamoDB
    - Include all required fields (timestamp, execution price, ticker, quantity, action)
    - Add transaction_id and execution_status
    - _Requirements: 6.3_

  - [x] 13.4 Write property test for transaction recording completeness
    - **Property 25: Transaction Recording Completeness**
    - **Validates: Requirements 6.3**

  - [x] 13.5 Implement trade failure handling
    - Log trade failures to CloudWatch with error details
    - Send user notification via SNS with failure reason
    - Record failed transaction in DynamoDB with error status
    - _Requirements: 6.4, 14.1_

  - [x] 13.6 Write property test for trade failure logging
    - **Property 26: Trade Failure Logging and Notification**
    - **Validates: Requirements 6.4, 14.1**

  - [x] 13.7 Create portfolio updater Lambda function
    - Create lambda/portfolio-updater directory with handler.py
    - Update portfolio holdings in DynamoDB after successful trades
    - Increment quantities for buys, decrement for sells
    - Recalculate total portfolio value
    - _Requirements: 6.5_

  - [x] 13.8 Write property test for portfolio update consistency
    - **Property 27: Portfolio Update Consistency**
    - **Validates: Requirements 6.5**

  - [x] 13.9 Implement circuit breaker for brokerage API
    - Add CircuitBreaker wrapper around brokerage API calls
    - Configure failure threshold (5 failures) and timeout (60 seconds)
    - Transition to OPEN state on repeated failures
    - _Requirements: 6.2, 14.3_

  - [x] 13.10 Write unit tests for trade execution
    - Test successful trade execution flow
    - Test trade failure scenarios
    - Test portfolio update logic
    - Test circuit breaker behavior
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 14. Checkpoint - Verify end-to-end workflow
  - Test complete workflow from request to trade execution
  - Verify state persistence across Lambda invocations
  - Ensure approval workflow functions correctly
  - Validate portfolio updates after trades
  - Ask the user if questions arise

- [x] 15. Implement Step Functions workflow orchestration
  - [x] 15.1 Create Step Functions state machine definition
    - Define workflow states according to design (InitializeSupervisor, AnalyzePortfolio, OptimizeTaxes, etc.)
    - Configure Lambda function ARNs for each state
    - Add retry policies with exponential backoff (2s, 4s, 8s, max 3 attempts)
    - Add timeout configurations (300s for agent tasks, 86400s for approval)
    - _Requirements: 10.1, 10.2_

  - [x] 15.2 Write property test for workflow step retry
    - **Property 41: Workflow Step Retry with Exponential Backoff**
    - **Validates: Requirements 10.2**

  - [x] 15.3 Implement WaitForApproval state with task token
    - Configure lambda:invoke.waitForTaskToken integration
    - Pass task token to approval handler
    - Set 24-hour timeout for user response
    - _Requirements: 5.1, 10.4_

  - [x] 15.4 Add Choice state for approval status routing
    - Route to ExecuteTrades on "approved" status
    - Route to HandleRejection on "rejected" status
    - Route to WorkflowCancelled on "cancelled" status
    - _Requirements: 5.3, 5.4, 5.5_

  - [x] 15.5 Implement Map state for parallel trade execution
    - Configure Map state to iterate over trade_orders array
    - Execute each trade in parallel with ExecuteSingleTrade Lambda
    - Add error handling with Catch clause for trade failures
    - _Requirements: 6.1, 6.2_

  - [x] 15.6 Add error handling and notification states
    - Create TradeFailure state to handle individual trade errors
    - Create ErrorNotification state for permanent failures
    - Configure SNS topic for critical error alerts
    - _Requirements: 10.5, 14.4_

  - [x] 15.7 Write property tests for workflow behavior
    - **Property 42: Workflow State Persistence**
    - **Property 43: Long-Running Workflow Notification**
    - **Property 44: Permanent Failure Logging and Notification**
    - **Validates: Requirements 10.3, 10.4, 10.5**

  - [x] 15.8 Deploy Step Functions state machine
    - Create CloudFormation/CDK stack for state machine
    - Configure IAM role with Lambda invocation permissions
    - Enable CloudWatch Logs for execution history
    - _Requirements: 10.1, 10.3_

  - [x] 15.9 Write integration test for complete workflow
    - Test end-to-end rebalancing workflow
    - Test approval and rejection flows
    - Test error handling and retries
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 16. Implement API Gateway and authentication
  - [x] 16.1 Create API Gateway REST API
    - Define API resources and methods (POST /rebalance, POST /analyze, POST /optimize-tax)
    - Configure request/response models with JSON schemas
    - Enable CORS for web client access
    - _Requirements: 1.1_

  - [x] 16.2 Integrate Cognito authorizer
    - Attach Cognito User Pool authorizer to API methods
    - Configure authorization scopes and token validation
    - Add IAM authorization for service-to-service calls
    - _Requirements: 13.1_

  - [x] 16.3 Write property test for request authentication
    - **Property 54: Request Authentication**
    - **Validates: Requirements 13.1**

  - [x] 16.4 Create API Gateway integration with Step Functions
    - Configure StartExecution integration for workflow initiation
    - Pass request body to Step Functions as input
    - Return execution ARN to client for status tracking
    - _Requirements: 10.1_

  - [x] 16.5 Implement API for approval responses
    - Create POST /approval endpoint to receive user decisions
    - Validate approval payload and extract task token
    - Send task success/failure to Step Functions
    - _Requirements: 5.3, 5.4_

  - [x] 16.6 Add request validation and throttling
    - Configure request validators for required fields
    - Set up usage plans with rate limiting (100 req/sec per user)
    - Add API keys for external integrations
    - _Requirements: 13.1_

  - [x] 16.7 Write integration tests for API Gateway
    - Test authentication with valid/invalid tokens
    - Test workflow initiation via API
    - Test approval submission
    - Test rate limiting behavior
    - _Requirements: 13.1_

- [x] 17. Implement security controls
  - [x] 17.1 Configure data encryption at rest
    - Verify DynamoDB tables use KMS encryption
    - Verify S3 buckets use SSE-KMS
    - Verify OpenSearch collections use encryption
    - _Requirements: 8.5, 13.3_

  - [x] 17.2 Write property test for data encryption at rest
    - **Property 35: Data Encryption at Rest**
    - **Validates: Requirements 8.5**

  - [x] 17.3 Configure TLS 1.3 for all communications
    - Set minimum TLS version on API Gateway
    - Configure VPC endpoints with TLS
    - Verify Bedrock and DynamoDB clients use TLS 1.3
    - _Requirements: 13.3_

  - [x] 17.4 Write property test for data encryption in transit
    - **Property 56: Data Encryption in Transit**
    - **Validates: Requirements 13.3**

  - [x] 17.5 Implement IAM authorization checks
    - Add authorization logic in Lambda functions to verify user access
    - Check IAM policies before data access operations
    - Enforce user data isolation with condition keys
    - _Requirements: 13.2, 13.5_

  - [x] 17.6 Write property tests for authorization and isolation
    - **Property 30: User Data Isolation**
    - **Property 55: Agent Access Authorization**
    - **Validates: Requirements 13.2, 13.5**

  - [x] 17.7 Implement audit logging for all agent actions
    - Log every data access with timestamp, user_id, agent_type, action_type
    - Use structured logging format with trace IDs
    - Send logs to CloudWatch Logs
    - _Requirements: 13.4_

  - [x] 17.8 Write property test for agent action audit logging
    - **Property 57: Agent Action Audit Logging**
    - **Validates: Requirements 13.4**

  - [x] 17.9 Write unit tests for security controls
    - Test IAM policy enforcement
    - Test user data isolation
    - Test audit log generation
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [x] 18. Implement auto-scaling configuration
  - [x] 18.1 Configure Lambda reserved concurrency
    - Set reserved concurrent executions to 100 for each agent Lambda
    - Configure provisioned concurrency for Supervisor Agent (warm start)
    - _Requirements: 11.4_

  - [x] 18.2 Write property test for concurrent instance limit
    - **Property 48: Concurrent Instance Limit**
    - **Validates: Requirements 11.4**

  - [x] 18.3 Implement request queueing for capacity limits
    - Add SQS queue for requests when Lambda concurrency is exhausted
    - Configure dead-letter queue for failed requests
    - Notify users of expected wait time when queued
    - _Requirements: 11.5_

  - [x] 18.4 Write property test for request queueing
    - **Property 49: Request Queueing at Capacity**
    - **Validates: Requirements 11.5**

  - [x] 18.5 Configure DynamoDB on-demand scaling
    - Verify PAY_PER_REQUEST billing mode is enabled
    - Monitor capacity usage and adjust if needed
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 18.6 Write property tests for scaling behavior
    - **Property 45: Zero-to-Scale Agent Provisioning**
    - **Property 46: Scale-Up Performance**
    - **Property 47: Scale-Down After Idle Period**
    - **Validates: Requirements 11.1, 11.2, 11.3**

  - [x] 18.7 Write performance tests for scaling
    - Test cold start performance (< 30 seconds)
    - Test scale-up under load
    - Test scale-down after idle period
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 19. Implement monitoring and observability
  - [x] 19.1 Create CloudWatch custom metrics
    - Emit AgentResponseTime metric for each agent invocation
    - Emit WorkflowDuration metric for Step Functions executions
    - Emit TradeExecutionSuccess metric for trade outcomes
    - Emit DynamoDBQueryLatency metric for database operations
    - _Requirements: 15.1, 15.2_

  - [x] 19.2 Write property tests for metrics emission
    - **Property 62: Performance Metrics Emission**
    - **Property 63: Request Count Tracking**
    - **Validates: Requirements 15.1, 15.2**

  - [x] 19.3 Create CloudWatch alarms
    - Create HighAgentResponseTime alarm (threshold: 5 seconds, 2 evaluation periods)
    - Create HighDynamoDBLatency alarm (threshold: 200ms, 3 evaluation periods)
    - Create TradeExecutionFailures alarm (threshold: < 5 successes, 1 evaluation period)
    - Configure SNS topics for alarm notifications
    - _Requirements: 15.3, 15.4_

  - [x] 19.4 Write property tests for performance warnings and alerts
    - **Property 64: Slow Response Warning**
    - **Property 65: Query Latency Alerting**
    - **Validates: Requirements 15.3, 15.4**

  - [x] 19.5 Create CloudWatch dashboard
    - Add Lambda performance widget (Duration, Errors, Invocations)
    - Add agent performance widget (AgentResponseTime p99, WorkflowDuration avg)
    - Add log insights widget for recent errors
    - Add DynamoDB metrics widget (read/write capacity, latency)
    - _Requirements: 15.1, 15.2_

  - [x] 19.6 Configure CloudWatch Logs Insights queries
    - Create query for error analysis by service and error type
    - Create query for user activity tracking
    - Create query for trade execution audit trail
    - _Requirements: 13.4, 14.1_

  - [x] 19.7 Set up SNS topics for notifications
    - Create admin-alerts topic for performance warnings
    - Create critical-alerts topic for system failures
    - Subscribe email endpoints for administrators
    - _Requirements: 14.4_

  - [x] 19.8 Write property tests for error notifications
    - **Property 58: User-Facing Error Notification**
    - **Property 60: Critical Error Alerting**
    - **Property 61: Error Recovery Suggestions**
    - **Validates: Requirements 14.2, 14.4, 14.5**

  - [x] 19.9 Write integration tests for monitoring
    - Test metric emission from Lambda functions
    - Test alarm triggering on threshold violations
    - Test SNS notification delivery
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [x] 20. Implement market data ingestion pipeline
  - [x] 20.1 Create market data ingestion Lambda function
    - Create lambda/market-data-ingestion directory with handler.py
    - Implement handler to fetch data from external market data APIs
    - Generate embeddings using Bedrock Titan Embeddings model
    - Index documents in OpenSearch Serverless
    - _Requirements: 9.1, 9.4_

  - [x] 20.2 Configure EventBridge scheduled rule
    - Create rule to trigger ingestion Lambda every 15 minutes during market hours
    - Configure rule with cron expression for market hours (9:30 AM - 4:00 PM ET)
    - _Requirements: 9.4_

  - [x] 20.3 Write property test for market data refresh frequency
    - **Property 39: Market Data Refresh Frequency**
    - **Validates: Requirements 9.4**

  - [x] 20.4 Implement fallback to cached data
    - Add logic to return cached data when live data unavailable
    - Notify users of data age when using cache
    - Log cache usage for monitoring
    - _Requirements: 9.5_

  - [x] 20.5 Write unit tests for market data ingestion
    - Test embedding generation
    - Test OpenSearch indexing
    - Test error handling for API failures
    - _Requirements: 9.1, 9.4, 9.5_

- [x] 21. Checkpoint - Verify complete system integration
  - Test end-to-end workflow with all components
  - Verify monitoring and alerting work correctly
  - Test security controls and data isolation
  - Validate auto-scaling behavior under load
  - Ask the user if questions arise

- [-] 22. Implement comprehensive test suite
  - [x] 22.1 Complete all property-based tests
    - Ensure all 65 correctness properties have corresponding tests
    - Configure Hypothesis with max_examples=100 for each test
    - Run full property test suite and verify all pass
    - _Requirements: All_

  - [x] 22.2 Implement custom Hypothesis strategies
    - Create portfolio_strategy generator for Portfolio objects
    - Create trade_order_strategy generator for TradeOrder objects
    - Create agent_state_strategy generator for AgentState objects
    - Create allocation_strategy generator for target allocations
    - _Requirements: All_

  - [x] 22.3 Complete all unit tests
    - Ensure 80%+ code coverage across all Lambda functions
    - Test all edge cases (empty inputs, boundary values, null handling)
    - Test all error conditions with mocked failures
    - _Requirements: All_

  - [x] 22.4 Implement integration tests
    - Create test_end_to_end_rebalancing_workflow integration test
    - Create test_tax_optimization_workflow integration test
    - Create test_human_approval_flow integration test
    - Create test_trade_execution integration test
    - Use LocalStack for local AWS service testing
    - _Requirements: All_

  - [x] 22.5 Implement performance tests
    - Create test_portfolio_data_retrieval_performance (< 100ms)
    - Create test_agent_response_time (< 5 seconds)
    - Create test_concurrent_requests (100 concurrent users)
    - Measure p95 and p99 latencies
    - _Requirements: 8.3, 15.3_

  - [x] 22.6 Set up test automation in CI/CD
    - Create GitHub Actions workflow for unit tests
    - Create workflow for property-based tests with statistics
    - Create workflow for integration tests with LocalStack
    - Configure test coverage reporting
    - _Requirements: All_

- [x] 23. Create deployment pipeline
  - [x] 23.1 Create CloudFormation/CDK deployment stacks
    - Organize stacks by layer (network, data, compute, ai, api, monitoring)
    - Define stack dependencies and outputs
    - Parameterize for multiple environments (dev, staging, prod)
    - _Requirements: All_

  - [x] 23.2 Package Lambda functions for deployment
    - Create deployment packages with dependencies
    - Configure Lambda layers for shared libraries (boto3, langgraph)
    - Optimize package sizes for faster cold starts
    - _Requirements: All_

  - [x] 23.3 Create deployment scripts
    - Write deploy.sh script to deploy all stacks in order
    - Write rollback.sh script for deployment failures
    - Add validation checks before deployment
    - _Requirements: All_

  - [x] 23.4 Set up CI/CD pipeline
    - Create GitHub Actions workflow for automated deployment
    - Configure deployment to dev environment on push to main
    - Configure deployment to staging on release tags
    - Require manual approval for production deployment
    - _Requirements: All_

  - [x] 23.5 Implement deployment smoke tests
    - Test API Gateway endpoints after deployment
    - Test Lambda function invocations
    - Test DynamoDB table access
    - Test Step Functions workflow execution
    - _Requirements: All_

- [x] 24. Implement Compliance-as-a-Code Library (Requirement 21)
  - [x] 24.1 Create src/compliance/ package structure
    - Create src/compliance/__init__.py, models.py, engine.py, registry.py, config.py
    - Create src/compliance/rules/ sub-package with finra.py, nist.py, pci_dss.py
    - Add compliance_config.yaml with per-domain thresholds and enabled/disabled rules
    - _Requirements: 21.1, 21.4_

  - [x] 24.2 Implement ComplianceViolation and ComplianceResult data models
    - Define Severity enum (critical, high, medium, low)
    - Define ComplianceViolation dataclass (policy_domain, rule_id, rule_name, severity, description, remediation_suggestion)
    - Define ComplianceResult dataclass (violations list, is_compliant bool)
    - _Requirements: 21.1_

  - [x] 24.3 Implement FINRA AI framework rules as pure functions
    - Implement FINRA-001: suitability check (detects advice lacking suitability basis)
    - Implement FINRA-002: disclosure requirement (flags missing AI disclosure language)
    - Implement FINRA-003: supervision obligation (detects unsupervised automated recommendations)
    - Implement FINRA-004: no misleading outputs (flags statistically unsupported claims)
    - Each rule is a pure function with no AWS dependencies
    - _Requirements: 21.2, 21.3_

  - [x] 24.4 Implement NIST AI RMF rules as pure functions
    - Implement NIST-001: bias and fairness (detects demographic bias indicators)
    - Implement NIST-002: transparency marker (flags outputs lacking explainability)
    - Implement NIST-003: robustness indicator (detects adversarial/OOD inputs)
    - Implement NIST-004: privacy risk (flags PII exposure risk)
    - Each rule is a pure function with no AWS dependencies
    - _Requirements: 21.2, 21.3_

  - [x] 24.5 Implement PCI DSS rules as pure functions
    - Implement PCI-001: PAN detection (Luhn-validated card number patterns)
    - Implement PCI-002: CVV detection (3-4 digit verification values in context)
    - Implement PCI-003: expiry detection (MM/YY and MM/YYYY patterns)
    - Implement PCI-004: sensitive auth data (flags logging of auth data)
    - Implement PCI-005: data minimisation (flags unnecessary cardholder data retention)
    - Each rule is a pure function with no AWS dependencies
    - _Requirements: 21.2, 21.3_

  - [x] 24.6 Implement PolicyRegistry class
    - Implement register(rule_fn, domain, rule_id) method for runtime rule registration
    - Implement get_rules(domain=None) method to retrieve registered rules
    - Ensure registered rules are applied in subsequent ComplianceEngine.evaluate() calls
    - _Requirements: 21.5_

  - [x] 24.7 Implement ComplianceEngine public API
    - Implement __init__ loading compliance_config.yaml and registering default rules
    - Implement evaluate(text, metadata) → ComplianceResult running all active rules
    - Enforce 500ms latency budget; log warning if exceeded
    - Apply per-domain halt_threshold from config to set is_compliant flag
    - _Requirements: 16.1, 16.6, 21.1_

  - [x] 24.8 Write property tests for compliance library
    - **Property 66: Input Compliance Screening Coverage** — for any (text, metadata), evaluate() returns ComplianceResult
    - **Property 67: Violation Severity Assignment** — for any violation, severity is in {critical, high, medium, low}
    - **Property 69: Config-Driven Threshold Round-Trip** — loading different configs changes engine behavior without code changes
    - **Property 83: PolicyRegistry Runtime Extension** — registered rules are applied to subsequent evaluations
    - **Property 84: Policy Domain Rule Coverage** — inputs matching known triggers return violations for the correct domain
    - Configure Hypothesis with max_examples=100
    - _Requirements: 16.1, 16.2, 16.5, 21.1, 21.4, 21.5_

  - [x] 24.9 Write unit tests for all policy rule functions
    - Test each FINRA, NIST, and PCI DSS rule function in isolation with no AWS mocking
    - Test positive cases (rule triggered) and negative cases (rule not triggered)
    - Test edge cases (empty string, whitespace-only, unicode, very long inputs)
    - Enforce 100% coverage via pytest-cov in CI
    - _Requirements: 21.3, 21.6_

- [x] 25. Implement input compliance screening integration (Requirement 16)
  - [x] 25.1 Integrate ComplianceEngine into the API Gateway / Lambda entry point
    - Invoke ComplianceEngine.evaluate() on every incoming user request before forwarding to Step Functions
    - Enforce 500ms timeout on screening; treat timeout as a medium-severity warning
    - _Requirements: 16.1, 16.6_

  - [x] 25.2 Implement violation routing logic
    - If any violation severity meets or exceeds the domain halt_threshold: write ComplianceViolation record to DynamoDB, enqueue to SQS investigation queue, return halt response to user
    - If all violations are below threshold: attach warning metadata to request, log structured warning, forward to Step Functions
    - _Requirements: 16.3, 16.4_

  - [x] 25.3 Create ComplianceViolations DynamoDB table in data-stack.yaml
    - Define table with violation_id (HASH) and timestamp (RANGE) keys
    - Add InvestigationStatusIndex GSI on investigation_status + timestamp
    - Enable point-in-time recovery and KMS encryption
    - _Requirements: 19.2_

  - [x] 25.4 Write property tests for input screening
    - **Property 68: Threshold-Based Routing** — violations at/above threshold halt; below threshold continue
    - **Property 70: Input Screening Latency** — screening completes within 500ms for any input
    - Configure Hypothesis with max_examples=100
    - _Requirements: 16.3, 16.4, 16.6_

  - [x] 25.5 Write unit tests for compliance screening integration
    - Test halt path with mocked DynamoDB and SQS writes
    - Test continue path with warning attachment
    - Test timeout handling
    - _Requirements: 16.1, 16.3, 16.4, 16.6_

- [x] 26. Implement LLM output evaluation (Requirement 17)
  - [x] 26.1 Create OutputEvaluator class in src/compliance/output_evaluator.py
    - Implement evaluate(llm_output, rag_context, user_query, trace_span) → EvaluatedOutput
    - Compute groundedness score: max cosine similarity between output embedding and RAG doc embeddings
    - Compute relevance score: cosine similarity between output embedding and query embedding
    - Use Bedrock Titan Embeddings for all embedding generation
    - _Requirements: 17.1, 17.2_

  - [x] 26.2 Integrate ComplianceEngine into OutputEvaluator
    - Run ComplianceEngine.evaluate() on the LLM output text
    - Apply output-specific thresholds from compliance_config.yaml
    - _Requirements: 17.3_

  - [x] 26.3 Implement suppression and routing logic
    - If groundedness < groundedness_min_threshold: flag output, log failure with RAG context, route to investigation queue
    - If relevance < relevance_min_threshold: flag output and log failure
    - If compliance violation severity >= threshold: suppress output, log violation, route to investigation queue
    - _Requirements: 17.4, 17.5, 17.6_

  - [x] 26.4 Attach evaluation scores to OTEL trace span
    - Set span attributes: groundedness_score, relevance_score, compliance_flags, is_suppressed
    - Set span status to error if output is suppressed
    - _Requirements: 17.7_

  - [x] 26.5 Write property tests for output evaluation
    - **Property 71: LLM Output Evaluation Completeness** — all three scores produced for any output
    - **Property 72: Below-Threshold Output Actions** — correct action taken per score vs threshold
    - **Property 73: Evaluation Scores Attached to OTEL Span** — span contains all score attributes
    - Configure Hypothesis with max_examples=100
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_

  - [x] 26.6 Write unit tests for OutputEvaluator
    - Test with mocked Bedrock embeddings client
    - Test suppression path, flag-only path, and clean path
    - Test span attribute setting
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_

- [x] 27. Implement end-to-end distributed tracing with ADOT (Requirement 18)
  - [x] 27.1 Add ADOT Lambda layer to all agent Lambda functions
    - Attach aws-otel-python-amd64-ver-* Lambda layer to supervisor-agent, portfolio-analyzer, tax-optimizer, rebalancing-agent, trade-executor, and compliance-screening Lambdas
    - Set AWS_LAMBDA_EXEC_WRAPPER, OTEL_PROPAGATORS, and OTEL_PYTHON_ID_GENERATOR environment variables
    - Configure ADOT collector sidecar to export to X-Ray
    - _Requirements: 18.1, 18.4_

  - [x] 27.2 Instrument all workflow stages with child spans
    - Add child spans for all 11 required stages: user_input_receipt, compliance_screening, rag_retrieval, llm_prompt_construction, llm_invocation, llm_output_evaluation, agent_decision, mcp_tool_invocation, step_functions_transition, trade_execution, portfolio_update
    - Set all required span attributes: trace_id, span_id, user_id, session_id, agent_type, stage_name, duration_ms, status, compliance_flags
    - _Requirements: 18.2, 18.3_

  - [x] 27.3 Implement W3C TraceContext propagation
    - Inject traceparent/tracestate headers into all Lambda-to-Lambda invocation payloads
    - Extract and restore trace context at the start of each Lambda handler
    - Inject trace context into Step Functions input payloads
    - _Requirements: 18.6_

  - [x] 27.4 Annotate violation spans with error status
    - When a compliance violation or evaluation failure occurs, set span status to error and add violation details as span attributes
    - _Requirements: 18.5_

  - [x] 27.5 Write property tests for distributed tracing
    - **Property 74: Workflow Stage Span Completeness** — all 11 stage spans present with required attributes for any workflow execution
    - **Property 75: Violation Span Annotation** — violation events set span status to error with violation details
    - **Property 76: W3C TraceContext Propagation** — all cross-component calls include traceparent/tracestate headers
    - Configure Hypothesis with max_examples=100
    - _Requirements: 18.1, 18.2, 18.3, 18.5, 18.6_

  - [x] 27.6 Write integration test for distributed tracing
    - Test that a complete workflow produces a single trace in X-Ray with all expected spans
    - Test that trace context is preserved across Lambda invocations
    - _Requirements: 18.1, 18.6_

- [x] 28. Implement unified observability store and LLM Judge (Requirement 19)
  - [x] 28.1 Configure unified observability data routing
    - Create S3 compliance bucket with 7-year lifecycle policy (90d → STANDARD_IA, 365d → GLACIER, 2555d expiry)
    - Configure CloudWatch Logs subscription filters to export compliance log groups to S3
    - Set up Athena workgroup and database for querying compliance data in S3
    - _Requirements: 19.1, 19.5_

  - [x] 28.2 Implement LLM Judge Lambda function
    - Create lambda/llm-judge/handler.py triggered by DynamoDB Streams on ComplianceViolations table
    - Invoke Bedrock Claude 3.5 Sonnet with violation record and surrounding OTEL/CloudWatch context
    - Parse structured verdict (confirm_violation, false_positive, escalate) with reasoning and confidence
    - Write verdict back to ComplianceViolations record via DynamoDB UpdateItem
    - Emit llm_judge_verdict CloudWatch metric with verdict as dimension
    - _Requirements: 19.3, 19.4_

  - [x] 28.3 Apply IAM access restrictions to ComplianceViolations table
    - Create ComplianceOfficerRole and RiskManagerRole with read access to ComplianceViolations
    - Create LLMJudgeLambdaRole with read/write access to ComplianceViolations
    - Add explicit Deny policy for all other principals on ComplianceViolations table
    - _Requirements: 19.6_

  - [x] 28.4 Write property tests for observability and LLM Judge
    - **Property 77: ComplianceViolations Record Schema** — any routed violation has a record with all required fields
    - **Property 78: LLM Judge Round-Trip** — every queued violation triggers LLM_Judge, produces a valid verdict, verdict written back and emitted as metric
    - Configure Hypothesis with max_examples=100
    - _Requirements: 19.2, 19.3, 19.4_

  - [x] 28.5 Write unit tests for LLM Judge
    - Test verdict parsing for all three verdict types
    - Test DynamoDB write-back with mocked client
    - Test CloudWatch metric emission
    - Test error handling when Bedrock is unavailable
    - _Requirements: 19.3, 19.4_

- [x] 29. Implement RAG context enrichment for agent prompts (Requirement 20)
  - [x] 29.1 Create RAGEnricher class in src/utils/rag_enricher.py
    - Implement enrich(query, session_id, span) → RAGContext performing knn search on OpenSearch
    - Generate query embedding via Bedrock Titan Embeddings
    - Search both market-intelligence and agent-interactions OpenSearch indices
    - Filter results above configurable similarity_threshold (default 0.6)
    - Return top-k (default 5, configurable via RAG_TOP_K env var) documents
    - _Requirements: 20.1, 20.2_

  - [x] 29.2 Create agent-interactions OpenSearch index
    - Add agent-interactions index mapping to data-stack.yaml with knn_vector field (1536 dims), session_id, agent_type, interaction_type, content, timestamp, workflow_id fields
    - _Requirements: 20.3_

  - [x] 29.3 Implement interaction indexing
    - Implement RAGEnricher.index_interaction(content, agent_type, interaction_type, session_id) to index agent inputs, outputs, and LLM responses into agent-interactions index
    - Call index_interaction after each agent input, agent output, and LLM response within a workflow session
    - _Requirements: 20.3_

  - [x] 29.4 Implement no-context fallback
    - When no documents exceed similarity_threshold, proceed without RAG context block
    - Log structured warning with event=rag_no_context, query, session_id, threshold, top_score
    - _Requirements: 20.4_

  - [x] 29.5 Record RAG retrieval in OTEL span
    - Set span attributes: rag_document_ids (list), rag_similarity_scores (list), rag_duration_ms
    - _Requirements: 20.5_

  - [x] 29.6 Integrate RAGEnricher into all agent Lambda functions
    - Call RAGEnricher.enrich() before every LLM prompt construction in portfolio-analyzer, tax-optimizer, rebalancing-agent, and supervisor-agent
    - Inject returned context documents as structured context block in prompt (delimited by --- RETRIEVED CONTEXT --- markers)
    - _Requirements: 20.1, 20.2_

  - [x] 29.7 Write property tests for RAG enrichment
    - **Property 79: RAG Enrichment Before Prompt Construction** — vector search performed and top-k docs injected before any LLM prompt
    - **Property 80: Agent Interaction Indexing Round-Trip** — indexed agent I/O is retrievable as RAG context in same session
    - **Property 81: RAG Span Document Recording** — OTEL span contains document_ids and similarity_scores for every retrieval
    - **Property 82: RAG Retrieval Latency** — retrieval completes within 300ms at p95
    - Configure Hypothesis with max_examples=100
    - _Requirements: 20.1, 20.2, 20.3, 20.5, 20.6_

  - [x] 29.8 Write unit tests for RAGEnricher
    - Test with mocked OpenSearch and Bedrock clients
    - Test top-k selection and similarity threshold filtering
    - Test no-context fallback path and warning log
    - Test prompt context block formatting
    - _Requirements: 20.1, 20.2, 20.3, 20.4_

- [x] 30. Create system documentation
  - [x] 30.1 Write API documentation
    - Document all API endpoints with request/response schemas
    - Provide example requests and responses
    - Document authentication requirements
    - Document error codes and messages
    - _Requirements: All_

  - [x] 30.2 Write deployment documentation
    - Document prerequisites (AWS account, CLI setup, permissions)
    - Document deployment steps for each environment
    - Document configuration parameters
    - Document rollback procedures
    - _Requirements: All_

  - [x] 30.3 Write operational runbook
    - Document monitoring and alerting setup
    - Document common troubleshooting scenarios
    - Document incident response procedures
    - Document backup and recovery procedures
    - _Requirements: All_

  - [x] 30.4 Write developer guide
    - Document project structure and architecture
    - Document how to add new agents, MCP tools, or compliance rules
    - Document testing strategy and how to run tests
    - Document local development setup
    - _Requirements: All_

- [x] 31. Final validation and handoff
  - [x] 31.1 Run complete test suite
    - Execute all unit tests and verify 80%+ coverage (100% for src/compliance/)
    - Execute all 84 property-based tests and verify pass
    - Execute all integration tests including compliance screening and distributed tracing
    - Execute performance tests and verify latency requirements (screening ≤500ms, RAG ≤300ms p95)
    - _Requirements: All_

  - [x] 31.2 Perform security audit
    - Verify all IAM policies follow least-privilege principle
    - Verify ComplianceViolations table access is restricted to authorised roles
    - Verify data encryption at rest and in transit
    - Verify user data isolation and audit logging is comprehensive
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 19.6_

  - [x] 31.3 Deploy to staging environment
    - Deploy complete system including new compliance, tracing, and RAG stacks to staging
    - Run smoke tests to verify deployment
    - Perform end-to-end testing with realistic data including compliance violation scenarios
    - Monitor system for 24 hours
    - _Requirements: All_

  - [x] 31.4 Conduct load testing
    - Simulate 100 concurrent users
    - Verify auto-scaling behavior
    - Verify compliance screening and RAG enrichment latency under load
    - Verify error rates remain acceptable
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 16.6, 20.6_

  - [x] 31.5 Create production deployment checklist
    - Document pre-deployment verification steps including compliance config validation
    - Document deployment sequence
    - Document post-deployment validation
    - Document rollback criteria and procedures
    - _Requirements: All_

- [x] 32. Migrate agent state persistence to AgentCore Memory (Requirement 22)
  - [x] 32.1 Configure AgentCore Memory namespaces
    - Create session-scoped memory namespace keyed by session_id for short-term context (conversation history, workflow state, user preferences within a session)
    - Create user-scoped memory namespace keyed by user_id for long-term cross-session memory (risk profile, historical trade preferences, recurring instructions)
    - Configure IAM resource policies to enforce namespace isolation between users
    - _Requirements: 22.1, 22.2, 22.3, 22.4_

  - [x] 32.2 Replace ManageAgentStateTool reads with AgentCore Memory reads
    - Update ManageAgentStateTool.load_state() to call AgentCore Memory GET on session_id namespace
    - Fall back to DynamoDB AgentSessions table if AgentCore Memory returns empty (migration compatibility)
    - Remove direct DynamoDB GetItem calls for session state from all agent Lambda handlers
    - _Requirements: 22.1_

  - [x] 32.3 Replace ManageAgentStateTool writes with AgentCore Memory writes
    - Update ManageAgentStateTool.save_state() to call AgentCore Memory PUT on session_id namespace
    - Write long-term fields (risk_profile, trade_preferences) to user_id namespace on session end
    - Remove direct DynamoDB PutItem calls for session state from all agent Lambda handlers
    - _Requirements: 22.2, 22.3_

  - [x] 32.4 Instrument AgentCore Memory calls with OTEL spans
    - Wrap every AgentCore Memory read and write in a child OTEL_Trace span
    - Set span attributes: memory_namespace, memory_operation (read/write), duration_ms, status
    - _Requirements: 22.8_

  - [x] 32.5 Write property tests for AgentCore Memory integration
    - **Property 85: Session Memory Round-Trip** — state written to AgentCore Memory at session end is retrievable at next session start for the same session_id
    - **Property 86: Long-Term Memory Persistence** — user-scoped fields written on session end are present in a new session for the same user_id
    - **Property 87: Memory Namespace Isolation** — agent cannot read memory records belonging to a different user_id
    - Configure Hypothesis with max_examples=100
    - _Requirements: 22.1, 22.2, 22.3, 22.4_

  - [x] 32.6 Write unit tests for AgentCore Memory migration
    - Test load_state() with mocked AgentCore Memory client returning data
    - Test load_state() fallback path when AgentCore Memory returns empty
    - Test save_state() writing to both session and user namespaces
    - Test OTEL span attribute correctness for memory operations
    - _Requirements: 22.1, 22.2, 22.3, 22.8_

- [x] 33. Integrate AgentCore Identity and Gateway (Requirement 22)
  - [x] 33.1 Configure AgentCore Identity per-agent OAuth 2.0 scopes
    - Define scope set for Supervisor Agent: invoke:portfolio-analyzer, invoke:tax-optimizer, invoke:rebalancing-agent
    - Define scope set for Portfolio Analyzer: read:portfolio-data, read:market-data, invoke:bedrock
    - Define scope set for Tax Optimizer: read:portfolio-data, read:cost-basis, invoke:bedrock
    - Define scope set for Rebalancing Agent: read:portfolio-data, invoke:bedrock, invoke:trade-executor
    - _Requirements: 22.6_

  - [x] 33.2 Replace static IAM credential assumption with AgentCore Identity token exchange
    - Update each agent Lambda handler to call AgentCore Identity token exchange at invocation start
    - Use returned short-lived token for all downstream tool and brokerage API calls within that invocation
    - Remove hardcoded IAM role assumption (sts:AssumeRole) from agent Lambda code
    - _Requirements: 22.5_

  - [x] 33.3 Register MCP tools as AgentCore Gateway managed endpoints
    - Register GetPortfolioTool, GetCostBasisTool, QueryMarketDataTool, and ExecuteTradeTool as MCP tool definitions in AgentCore Gateway
    - Update agent Lambda handlers to invoke tools via AgentCore Gateway endpoint rather than direct Lambda invocation
    - Retain existing tool interface contracts (input schema, output schema) unchanged
    - _Requirements: 22.7_

  - [x] 33.4 Write property tests for AgentCore Identity and Gateway
    - **Property 88: Per-Agent Scope Enforcement** — token issued to agent type X does not grant access to scopes defined only for agent type Y
    - **Property 89: Gateway Tool Invocation Round-Trip** — tool call via AgentCore Gateway returns identical result to direct Lambda invocation for any valid input
    - Configure Hypothesis with max_examples=100
    - _Requirements: 22.5, 22.6, 22.7_

  - [x] 33.5 Write unit tests for Identity and Gateway integration
    - Test token exchange with mocked AgentCore Identity client
    - Test scope rejection for out-of-scope tool calls
    - Test Gateway tool invocation with mocked endpoint
    - Test fallback error handling when AgentCore Identity is unavailable
    - _Requirements: 22.5, 22.6, 22.7_

  - [x] 33.6 Update deployment stacks for AgentCore resources
    - Add AgentCore Memory namespace configuration to ai-stack.yaml
    - Add AgentCore Identity scope definitions to ai-stack.yaml
    - Add AgentCore Gateway tool registrations to ai-stack.yaml
    - Update compute-stack.yaml Lambda environment variables to reference AgentCore endpoints
    - _Requirements: 22.1, 22.5, 22.7_

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties (94 total: 84 existing + 5 new for Requirement 22 Memory + 5 new for Requirement 22 Identity/Gateway)
- Unit tests validate specific examples and edge cases; src/compliance/ requires 100% coverage enforced by CI
- Integration tests validate end-to-end workflows including compliance screening and distributed tracing
- Performance tests validate latency and throughput requirements (screening ≤500ms, RAG ≤300ms p95)
- Tasks 32–33 are additive migrations — existing Lambda hosting remains functional during transition; AgentCore Memory includes a DynamoDB fallback in Task 32.2 for zero-downtime migration
- The implementation uses Python 3.11 as specified in the design document
- All AWS services are configured for serverless, auto-scaling operation
- Security is implemented at every layer (network, IAM, encryption, audit logging)
- Monitoring and observability are built-in from the start, extended with ADOT/X-Ray and LLM Judge
