# Requirements Document

## Introduction

The Multi-Agent Advisory AI System is an advanced portfolio management platform that leverages specialized AI agents to provide tax-optimized, real-time portfolio adjustments. The system uses AWS serverless infrastructure (Bedrock, AgentCore, DynamoDB, Lambda, Step Functions, S3, OpenSearch Serverless) and LangGraph orchestration to coordinate multiple specialized agents that analyze portfolios, optimize tax strategies, and execute rebalancing operations with human-in-the-loop approval.

The system implements a "Glass Box" compliance architecture across four pillars: (1) Compliance-as-Code — 13 FINRA/NIST/PCI DSS rules enforced inline via a standalone Python library; (2) OpenTelemetry tracing — 11 instrumented stages per request via AWS Distro for OpenTelemetry and W3C TraceContext; (3) LLM-as-a-Judge — autonomous second-line-of-defence review of every compliance violation via Claude 3.5 Sonnet on Amazon Bedrock; (4) Human-in-the-Loop — structural trade approval enforced via AWS Step Functions WaitForTaskToken before any execution proceeds.

## Glossary

- **System**: The Multi-Agent Advisory AI System
- **Supervisor_Agent**: LangGraph-based coordinator that receives user prompts, decomposes queries, routes tasks, and aggregates results
- **Portfolio_Analyzer_Agent**: Specialized agent that ingests portfolio holdings, analyzes performance, risk exposure, and diversification
- **Tax_Optimizer_Agent**: Specialized agent that identifies tax-loss harvesting opportunities and suggests optimized trades
- **Rebalancing_Agent**: Specialized agent that calculates necessary trades to achieve target allocation
- **User**: Portfolio owner or financial advisor using the system
- **Portfolio**: Collection of investment holdings with associated cost basis and allocation targets
- **Drift**: Deviation of current portfolio allocation from target allocation
- **Tax_Loss_Harvesting**: Strategy of selling securities at a loss to offset capital gains tax liability
- **Target_Allocation**: Desired distribution of assets across investment categories
- **MCP_Tool**: Model Context Protocol tool that connects agents to data sources and backend services
- **Agent_State**: Persistent memory and context maintained for each agent session
- **Workflow**: Sequence of agent interactions orchestrated by LangGraph to complete a user request
- **Compliance_Engine**: The compliance-as-a-code Python library that encodes FINRA AI framework, NIST, and PCI DSS policies as executable verification functions
- **Compliance_Violation**: A detected breach of a policy rule, classified by severity (critical, high, medium, low) and routed for human investigation when above configured thresholds
- **LLM_Judge**: A second-line-of-defense LLM invoked to evaluate agent decisions, outputs, and compliance logs for quality and policy adherence
- **OTEL_Trace**: An OpenTelemetry distributed trace span capturing a unit of work across the agentic workflow, exported via AWS Distro for OpenTelemetry (ADOT)
- **Groundedness**: The degree to which an LLM output is factually supported by the retrieved context (RAG sources) rather than hallucinated
- **Relevance**: The degree to which an LLM output directly addresses the user's query and the agent's assigned task
- **RAG**: Retrieval-Augmented Generation — the pattern of enriching LLM prompts with documents retrieved from OpenSearch before model invocation
- **AgentCore_Memory**: Amazon Bedrock AgentCore managed memory store providing short-term session memory (keyed by session_id) and long-term cross-session memory (keyed by user_id) for all agents
- **AgentCore_Identity**: Amazon Bedrock AgentCore managed identity service that vends short-lived OAuth 2.0 tokens to agents for external tool and API access, enforcing per-agent-type scope restrictions
- **AgentCore_Gateway**: Amazon Bedrock AgentCore managed MCP server that hosts MCP tools as managed endpoints, replacing direct Lambda-to-Lambda tool invocation

## Requirements

### Requirement 1: Supervisor Agent Orchestration

**User Story:** As a user, I want my portfolio management requests to be intelligently routed to specialized agents, so that I receive comprehensive and accurate advice.

#### Acceptance Criteria

1. WHEN a user submits a portfolio management request, THE Supervisor_Agent SHALL decompose the request into subtasks
2. THE Supervisor_Agent SHALL route each subtask to the appropriate specialized agent
3. WHEN all specialized agents complete their tasks, THE Supervisor_Agent SHALL aggregate the results into a unified response
4. THE Supervisor_Agent SHALL use LangGraph to manage state flow between agents
5. IF a subtask fails, THEN THE Supervisor_Agent SHALL retry the subtask up to 3 times before returning an error to the user

### Requirement 2: Portfolio Analysis

**User Story:** As a Portfolio Advisor (user), I want customer's portfolio to be analyzed for performance and risk, so that I can understand my investment position.

#### Acceptance Criteria

1. WHEN the Portfolio_Analyzer_Agent receives a portfolio analysis request, THE Portfolio_Analyzer_Agent SHALL retrieve current holdings from DynamoDB
2. THE Portfolio_Analyzer_Agent SHALL calculate portfolio performance metrics including total return and risk exposure
3. THE Portfolio_Analyzer_Agent SHALL identify allocation drift from target allocation
4. THE Portfolio_Analyzer_Agent SHALL query OpenSearch Serverless for relevant market data and news
5. WHEN analysis is complete, THE Portfolio_Analyzer_Agent SHALL return a structured analysis report to the Supervisor_Agent

### Requirement 3: Tax Loss Harvesting Identification

**User Story:** As a user, I want the system to identify tax-loss harvesting opportunities, so that I can minimize my tax liability.

#### Acceptance Criteria

1. WHEN the Tax_Optimizer_Agent receives portfolio drift data, THE Tax_Optimizer_Agent SHALL retrieve cost basis information from DynamoDB
2. THE Tax_Optimizer_Agent SHALL identify securities with unrealized losses that qualify for tax-loss harvesting
3. THE Tax_Optimizer_Agent SHALL calculate potential tax savings for each identified opportunity
4. THE Tax_Optimizer_Agent SHALL propose a new allocation that maximizes after-tax returns
5. WHEN tax optimization is complete, THE Tax_Optimizer_Agent SHALL return tax-optimized recommendations to the Supervisor_Agent

### Requirement 4: Portfolio Rebalancing Calculation

**User Story:** As a user, I want specific buy/sell/hold orders calculated to rebalance my portfolio, so that I can execute trades efficiently.

#### Acceptance Criteria

1. WHEN the Rebalancing_Agent receives target allocation and current holdings, THE Rebalancing_Agent SHALL calculate the difference between current and target positions
2. THE Rebalancing_Agent SHALL generate specific buy, sell, and hold orders with quantities and ticker symbols
3. THE Rebalancing_Agent SHALL consider transaction costs in rebalancing calculations
4. THE Rebalancing_Agent SHALL ensure rebalancing orders respect user-defined risk tolerances
5. WHEN rebalancing calculation is complete, THE Rebalancing_Agent SHALL return executable trade orders to the Supervisor_Agent

### Requirement 5: Human-in-the-Loop Approval

**User Story:** As a user, I want to review and approve all proposed trades before execution, so that I maintain control over my portfolio.

#### Acceptance Criteria

1. WHEN the Supervisor_Agent completes a rebalancing workflow, THE System SHALL present the proposed trade plan to the user for review
2. THE System SHALL display tax implications, expected costs, and projected outcomes for the proposed trades
3. THE System SHALL wait for explicit user approval before proceeding with trade execution
4. IF the user rejects the plan, THEN THE System SHALL allow the user to provide feedback and request modifications
5. WHEN the user approves the plan, THE System SHALL proceed to trade execution

### Requirement 6: Trade Execution via MCP Tools

**User Story:** As a user, I want approved trades to be executed automatically through secure APIs, so that my portfolio changes are implemented quickly.

#### Acceptance Criteria

1. WHEN the user approves a trade plan, THE System SHALL invoke the trade execution MCP_Tool with the approved orders
2. THE System SHALL execute trades through AWS Lambda functions that interface with brokerage APIs
3. WHEN each trade completes, THE System SHALL record the transaction in DynamoDB with timestamp and execution price
4. IF a trade fails, THEN THE System SHALL log the error and notify the user with failure details
5. WHEN all trades complete, THE System SHALL update the portfolio holdings in DynamoDB

### Requirement 7: Agent State Persistence

**User Story:** As a user, I want the system to remember my preferences and context across sessions, so that I receive personalized advice.

#### Acceptance Criteria

1. WHEN an agent session begins, THE System SHALL retrieve Agent_State from Bedrock AgentCore Runtime
2. WHILE an agent is processing a request, THE System SHALL maintain session context including user preferences and conversation history
3. WHEN an agent session ends, THE System SHALL persist Agent_State to Bedrock AgentCore Runtime
4. THE System SHALL isolate Agent_State between different users using IAM-based access control
5. WHEN a user returns for a new session, THE System SHALL restore Agent_State from the previous session

### Requirement 8: Portfolio Data Storage and Retrieval

**User Story:** As a user, I want my portfolio data to be securely stored and quickly accessible, so that agents can provide real-time analysis.

#### Acceptance Criteria

1. THE System SHALL store portfolio holdings in DynamoDB with user_id as partition key
2. THE System SHALL store transaction history in DynamoDB with composite key of user_id and timestamp
3. WHEN an agent requests portfolio data, THE System SHALL retrieve the data from DynamoDB within 100 milliseconds
4. THE System SHALL store cost basis information for each security position in DynamoDB
5. THE System SHALL encrypt all portfolio data at rest using AWS KMS

### Requirement 9: Market Data Integration

**User Story:** As a user, I want agents to access current market data and news, so that recommendations are based on up-to-date information.

#### Acceptance Criteria

1. THE System SHALL index market data and regulatory documents in OpenSearch Serverless using vector embeddings
2. WHEN an agent needs market context, THE System SHALL perform vector search on OpenSearch Serverless to retrieve relevant information
3. THE System SHALL cache frequently accessed market data in DynamoDB with TTL of 5 minutes
4. THE System SHALL refresh market data from external sources at least every 15 minutes during market hours
5. WHEN market data is unavailable, THE System SHALL use the most recent cached data and notify the user of the data age

### Requirement 10: Workflow Orchestration with Step Functions

**User Story:** As a system administrator, I want long-running workflows to be managed reliably with automatic retries, so that the system is resilient to transient failures.

#### Acceptance Criteria

1. THE System SHALL use AWS Step Functions to orchestrate high-level workflows including portfolio rebalancing and tax optimization
2. WHEN a workflow step fails, THE System SHALL automatically retry the step with exponential backoff up to 3 times
3. THE System SHALL maintain workflow state in Step Functions for audit and debugging purposes
4. WHEN a workflow exceeds 15 minutes, THE System SHALL send a progress notification to the user
5. IF a workflow fails after all retries, THEN THE System SHALL log the failure details and notify the user with error information

### Requirement 11: Agent Scaling and Resource Management

**User Story:** As a system administrator, I want agents to scale automatically based on demand, so that the system handles varying workloads efficiently.

#### Acceptance Criteria

1. THE System SHALL use Bedrock AgentCore Runtime to scale agents from zero based on incoming requests
2. WHEN request volume increases, THE System SHALL provision additional agent instances within 30 seconds
3. WHEN request volume decreases, THE System SHALL scale down agent instances after 5 minutes of idle time
4. THE System SHALL limit concurrent agent instances to 100 per agent type to control costs
5. WHEN agent capacity is reached, THE System SHALL queue additional requests and notify users of expected wait time

### Requirement 12: Foundation Model Integration

**User Story:** As a user, I want agents to use advanced AI models for reasoning and analysis, so that I receive high-quality investment advice.

#### Acceptance Criteria

1. THE System SHALL use Amazon Bedrock with Claude 3.5 Sonnet as the foundation model for all agents
2. WHEN an agent needs to perform reasoning or analysis, THE System SHALL invoke the foundation model through Bedrock API
3. THE System SHALL include relevant portfolio context and market data in model prompts
4. THE System SHALL parse and validate model responses before using them in agent decisions
5. IF the foundation model returns an invalid or incomplete response, THEN THE System SHALL retry the request with clarified prompts up to 2 times

### Requirement 13: Security and Access Control

**User Story:** As a user, I want my portfolio data and agent interactions to be secure, so that my financial information is protected.

#### Acceptance Criteria

1. THE System SHALL authenticate all user requests using AWS IAM or Cognito
2. THE System SHALL authorize agent access to user data based on IAM policies
3. THE System SHALL encrypt all data in transit using TLS 1.3
4. THE System SHALL log all agent actions and data access to CloudWatch for audit purposes
5. THE System SHALL isolate agent sessions between users to prevent data leakage

### Requirement 14: Error Handling and User Notification

**User Story:** As a user, I want to be informed of any errors or issues during portfolio management operations, so that I can take appropriate action.

#### Acceptance Criteria
### Requirement 15: Performance Monitoring and Optimization

**User Story:** As a system administrator, I want to monitor system performance and identify bottlenecks, so that I can optimize the system for better user experience.

#### Acceptance Criteria

1. THE System SHALL emit performance metrics to CloudWatch including agent response times and workflow durations
2. THE System SHALL track the number of requests processed per agent type per hour
3. WHEN agent response time exceeds 5 seconds, THE System SHALL log a performance warning
4. THE System SHALL monitor DynamoDB and OpenSearch query latencies and alert when latency exceeds 200 milliseconds
5. THE System SHALL provide a dashboard showing key performance indicators including success rate, average response time, and error rate

### Requirement 16: Input Compliance Screening

**User Story:** As a compliance officer, I want every user query and prompt to be automatically screened against FINRA AI framework, NIST, and PCI DSS policies before it reaches any agent, so that non-compliant inputs are intercepted and flagged for human review.

#### Acceptance Criteria

1. WHEN a user submits a query or prompt, THE Compliance_Engine SHALL evaluate the input against all active FINRA AI framework, NIST, and PCI DSS policy rules before the request is forwarded to any agent
2. THE Compliance_Engine SHALL assign a severity level (critical, high, medium, low) to each detected Compliance_Violation
3. WHEN a Compliance_Violation severity meets or exceeds the configured threshold, THE System SHALL halt processing and route the input to a human investigation queue with full context (user_id, timestamp, violation type, raw input hash)
4. WHEN a Compliance_Violation severity is below the configured threshold, THE System SHALL log the violation, attach a warning to the request, and allow processing to continue
5. THE System SHALL make violation thresholds configurable per policy domain (FINRA, NIST, PCI DSS) without requiring code changes
6. THE Compliance_Engine SHALL complete input screening within 500 milliseconds so as not to materially increase end-to-end latency

### Requirement 17: LLM Output Quality and Compliance Evaluation

**User Story:** As a compliance officer, I want every LLM-generated output to be evaluated for groundedness, relevance, and compliance before it is returned to the user or passed to the next agent stage, so that hallucinated, off-topic, or policy-violating responses are caught automatically.

#### Acceptance Criteria

1. WHEN an LLM produces an output, THE System SHALL evaluate that output for Groundedness against the RAG context documents used to construct the prompt
2. THE System SHALL evaluate each LLM output for Relevance to the originating user query and agent task
3. THE System SHALL evaluate each LLM output against the Compliance_Engine policy rules (FINRA AI framework, NIST, PCI DSS)
4. WHEN a Groundedness score falls below the configured minimum threshold, THE System SHALL flag the output, log the failure with the supporting context, and route it for human investigation
5. WHEN a Relevance score falls below the configured minimum threshold, THE System SHALL flag the output and log the failure
6. WHEN a Compliance_Violation is detected in an LLM output and its severity meets or exceeds the configured threshold, THE System SHALL suppress the output, log the violation, and route it to the human investigation queue
7. All evaluation scores and violation details SHALL be attached to the OTEL_Trace span for the corresponding LLM invocation

### Requirement 18: End-to-End Distributed Tracing with OpenTelemetry

**User Story:** As a platform engineer, I want every stage of the agentic workflow — including user inputs, LLM invocations, RAG retrievals, agent decisions, MCP tool calls, and workflow transitions — to emit structured OpenTelemetry traces via AWS Distro for OpenTelemetry, so that I have full observability across all layers.

#### Acceptance Criteria

1. THE System SHALL instrument all workflow stages using the AWS Distro for OpenTelemetry (ADOT) Python SDK, creating a root trace span per user request that propagates through all downstream components
2. EACH of the following stages SHALL emit a child OTEL_Trace span with relevant attributes: user input receipt, compliance screening, RAG retrieval, LLM prompt construction, LLM invocation, LLM output evaluation, agent decision, MCP tool invocation, Step Functions state transition, trade execution, and portfolio update
3. OTEL_Trace spans SHALL include the following standard attributes: trace_id, span_id, user_id, session_id, agent_type, stage_name, duration_ms, status (ok/error), and compliance_flags
4. THE System SHALL export traces to AWS X-Ray via the ADOT collector running as a Lambda extension or sidecar
5. WHEN a compliance violation or evaluation failure occurs, THE System SHALL annotate the corresponding OTEL_Trace span with the violation details and set span status to error
6. THE System SHALL propagate trace context (W3C TraceContext headers) across all Lambda-to-Lambda and Lambda-to-Step-Functions invocations so that the full request path is visible as a single trace in X-Ray

### Requirement 19: Unified Observability Data for Second-Line-of-Defense LLM Judge

**User Story:** As a risk manager, I want all observability data — CloudWatch logs, OpenTelemetry traces, CloudTrail audit events, X-Ray traces, and compliance violation records — to be consolidated and made queryable so that an LLM-as-a-Judge system can perform automated second-line-of-defense reviews.

#### Acceptance Criteria

1. THE System SHALL route all CloudWatch log groups, OTEL traces, CloudTrail events, and X-Ray trace summaries to a unified observability store (CloudWatch Logs Insights and S3 with Athena) that the LLM_Judge can query
2. Compliance violation records SHALL be stored in a dedicated DynamoDB table (ComplianceViolations) with attributes: violation_id, timestamp, user_id, session_id, stage, policy_domain, severity, raw_content_hash, investigation_status, and llm_judge_verdict
3. THE LLM_Judge SHALL be invoked automatically for every Compliance_Violation routed to the human investigation queue, producing a structured verdict (confirm_violation, false_positive, escalate) with reasoning
4. THE LLM_Judge verdict and reasoning SHALL be written back to the ComplianceViolations record and emitted as a CloudWatch metric for dashboard visibility
5. THE System SHALL retain compliance-related logs and violation records for a minimum of 7 years to satisfy FINRA record-keeping requirements
6. Access to the unified observability store and ComplianceViolations table SHALL be restricted to authorised compliance and risk roles via IAM policies

### Requirement 20: RAG Context Enrichment for Agent Prompts

**User Story:** As a platform engineer, I want every agent prompt — for both LLM inputs and outputs — to be enriched with relevant context retrieved from the OpenSearch vector store, so that agents reason over current, grounded information rather than relying solely on model weights.

#### Acceptance Criteria

1. BEFORE constructing any LLM prompt, THE System SHALL perform a vector similarity search on the OpenSearch Serverless collection using the agent's current task description and user query as the search query
2. THE System SHALL retrieve the top-k (configurable, default 5) most relevant documents and inject them into the prompt as a structured context block, clearly delimited from the instruction and user input sections
3. THE System SHALL store agent inputs, agent outputs, and LLM responses as indexed documents in OpenSearch so that they are available as RAG context for subsequent agent stages within the same workflow session
4. WHEN no relevant documents are found above the configured similarity threshold, THE System SHALL proceed without RAG context and log a warning indicating low-context generation
5. THE System SHALL record which documents were retrieved for each prompt in the corresponding OTEL_Trace span (document_ids, similarity_scores) to support groundedness evaluation under Requirement 17
6. RAG retrieval latency SHALL not exceed 300 milliseconds at the 95th percentile

### Requirement 22: Amazon Bedrock AgentCore — Memory and Identity

**User Story:** As a platform engineer, I want agent session memory and per-agent identity managed by Amazon Bedrock AgentCore, so that the system eliminates custom state-persistence code, gains cross-session long-term memory, and delegates secure credential vending to a managed service.

#### Acceptance Criteria

1. WHEN an agent session begins, THE System SHALL retrieve short-term session memory from AgentCore Memory using the session_id as the memory namespace, replacing direct reads from the AgentSessions DynamoDB table
2. WHEN an agent session ends or checkpoints, THE System SHALL persist session context — including conversation history, user preferences, and workflow state — to AgentCore Memory, replacing direct writes to the AgentSessions DynamoDB table
3. THE System SHALL store cross-session long-term memory (user risk profile, historical trade preferences, recurring instructions) in AgentCore Memory under the user_id namespace, retrievable on every new session
4. THE System SHALL isolate AgentCore Memory namespaces between users such that no agent can read or write another user's memory records
5. WHEN an agent requires credentials to call an external tool or brokerage API, THE System SHALL obtain short-lived credentials via AgentCore Identity token exchange rather than embedding static credentials or assuming IAM roles directly in Lambda code
6. AgentCore Identity SHALL enforce per-agent OAuth 2.0 scopes so that each agent type (Supervisor, Portfolio Analyzer, Tax Optimizer, Rebalancing Agent) can only access the external services its role requires
7. THE System SHALL expose existing MCP tools (GetPortfolioTool, GetCostBasisTool, QueryMarketDataTool, ExecuteTradeTool) via AgentCore Gateway as managed MCP endpoints, removing the direct Lambda-to-Lambda invocation pattern for tool calls
8. All AgentCore Memory reads and writes SHALL be recorded in the OTEL_Trace span for the corresponding agent stage (attributes: memory_namespace, memory_operation, duration_ms)

### Requirement 21: Compliance-as-a-Code Library

**User Story:** As a developer, I want a standalone Python library that encodes FINRA AI framework, NIST, and PCI DSS compliance policies as executable, testable functions, so that compliance verification logic is version-controlled, reusable across all system components, and independently testable.

#### Acceptance Criteria

1. THE Compliance_Engine SHALL be implemented as a standalone Python package (`src/compliance/`) with a public API that accepts a payload (text, metadata dict) and returns a `ComplianceResult` containing a list of `ComplianceViolation` objects, each with: policy_domain, rule_id, rule_name, severity, description, and remediation_suggestion
2. THE library SHALL implement policy rules for the following domains:
   - FINRA AI framework: suitability of AI-generated advice, disclosure requirements, supervision obligations, and prohibition on misleading AI outputs
   - NIST AI RMF: bias and fairness checks, transparency and explainability markers, robustness indicators, and privacy risk flags
   - PCI DSS: detection of payment card data (PAN, CVV, expiry) in inputs and outputs, prohibition on logging sensitive authentication data, and data minimisation checks
3. EACH policy rule SHALL be implemented as an independent, pure function that can be unit-tested in isolation without any AWS dependencies
4. THE library SHALL support a configuration file (`compliance_config.yaml`) that defines per-domain severity thresholds, enabled/disabled rules, and custom rule parameters, loadable at runtime without code changes
5. THE library SHALL expose a `PolicyRegistry` class that allows new rules to be registered at runtime, enabling extension without modifying core library code
6. THE Compliance_Engine SHALL achieve 100% unit test coverage for all policy rule functions, verified by the CI pipeline
