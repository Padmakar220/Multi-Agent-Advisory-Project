"""Supervisor Agent Lambda function using LangGraph for orchestration."""

import json
import os
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import asdict, dataclass, field

import boto3
from langgraph.graph import StateGraph, END
from langgraph.types import StateSnapshot

from src.models.requests import SupervisorRequest, Subtask, CompletedTask
from src.models.responses import SupervisorResponse, ErrorResponse
from src.models.portfolio import AgentState
from src.utils.rag_enricher import RAGEnricher

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# AWS clients
lambda_client = boto3.client("lambda")
dynamodb = boto3.resource("dynamodb")
cloudwatch = boto3.client("cloudwatch")

# Environment variables
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
DYNAMODB_TABLE_SESSIONS = os.environ.get("DYNAMODB_TABLE_SESSIONS", "AgentSessions")
PORTFOLIO_ANALYZER_ARN = os.environ.get("PORTFOLIO_ANALYZER_ARN")
TAX_OPTIMIZER_ARN = os.environ.get("TAX_OPTIMIZER_ARN")
REBALANCING_AGENT_ARN = os.environ.get("REBALANCING_AGENT_ARN")

# Max retries for subtasks
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 4, 8]


@dataclass
class SupervisorAgentState:
    """LangGraph state for Supervisor Agent orchestration."""
    
    user_id: str
    session_id: str
    original_request: Dict[str, Any]
    subtasks: List[Dict[str, Any]] = field(default_factory=list)
    completed_tasks: List[Dict[str, Any]] = field(default_factory=list)
    pending_tasks: List[Dict[str, Any]] = field(default_factory=list)
    aggregated_results: Dict[str, Any] = field(default_factory=dict)
    retry_counts: Dict[str, int] = field(default_factory=dict)
    approval_status: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for persistence."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "original_request": self.original_request,
            "subtasks": self.subtasks,
            "completed_tasks": self.completed_tasks,
            "pending_tasks": self.pending_tasks,
            "aggregated_results": self.aggregated_results,
            "retry_counts": self.retry_counts,
            "approval_status": self.approval_status,
            "error_details": self.error_details
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SupervisorAgentState":
        """Create state from dictionary."""
        return cls(
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            original_request=data.get("original_request", {}),
            subtasks=data.get("subtasks", []),
            completed_tasks=data.get("completed_tasks", []),
            pending_tasks=data.get("pending_tasks", []),
            aggregated_results=data.get("aggregated_results", {}),
            retry_counts=data.get("retry_counts", {}),
            approval_status=data.get("approval_status"),
            error_details=data.get("error_details")
        )


class SupervisorAgent:
    """Supervisor Agent for orchestrating specialized agents using LangGraph."""
    
    def __init__(self):
        """Initialize Supervisor Agent."""
        self.sessions_table = dynamodb.Table(DYNAMODB_TABLE_SESSIONS)
        self.rag_enricher = RAGEnricher()
        self.graph = self._build_state_machine()
    
    def _build_state_machine(self) -> StateGraph:
        """Build LangGraph state machine for agent orchestration."""
        workflow = StateGraph(SupervisorAgentState)
        
        # Add nodes
        workflow.add_node("receive_request", self._receive_request)
        workflow.add_node("decompose_task", self._decompose_task)
        workflow.add_node("route_to_agents", self._route_to_agents)
        workflow.add_node("check_completion", self._check_completion)
        workflow.add_node("aggregate_results", self._aggregate_results)
        workflow.add_node("human_approval", self._human_approval)
        workflow.add_node("execute_trades", self._execute_trades)
        workflow.add_node("update_portfolio", self._update_portfolio)
        workflow.add_node("retry_task", self._retry_task)
        workflow.add_node("error_notification", self._error_notification)
        
        # Set entry point
        workflow.set_entry_point("receive_request")
        
        # Add edges
        workflow.add_edge("receive_request", "decompose_task")
        workflow.add_edge("decompose_task", "route_to_agents")
        
        # Conditional edges from route_to_agents
        workflow.add_conditional_edges(
            "route_to_agents",
            self._should_check_completion,
            {
                "check_completion": "check_completion",
                "retry": "retry_task"
            }
        )
        
        # Conditional edges from check_completion
        workflow.add_conditional_edges(
            "check_completion",
            self._should_aggregate,
            {
                "aggregate": "aggregate_results",
                "route": "route_to_agents"
            }
        )
        
        workflow.add_edge("aggregate_results", "human_approval")
        
        # Conditional edges from human_approval
        workflow.add_conditional_edges(
            "human_approval",
            self._should_execute,
            {
                "execute": "execute_trades",
                "reject": END,
                "cancel": END
            }
        )
        
        workflow.add_edge("execute_trades", "update_portfolio")
        workflow.add_edge("update_portfolio", END)
        
        # Retry task edges
        workflow.add_conditional_edges(
            "retry_task",
            self._should_retry,
            {
                "retry": "route_to_agents",
                "error": "error_notification"
            }
        )
        
        workflow.add_edge("error_notification", END)
        
        return workflow.compile()
    
    def _receive_request(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Receive and validate incoming request."""
        logger.info(f"Receiving request for session {state.session_id}")
        
        # Restore previous state if exists
        try:
            saved_state = self._load_state(state.session_id)
            if saved_state:
                logger.info(f"Restored previous state for session {state.session_id}")
                return saved_state
        except Exception as e:
            logger.warning(f"Could not restore previous state: {e}")
        
        return state
    
    def _decompose_task(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Decompose request into subtasks."""
        logger.info(f"Decomposing request for session {state.session_id}")

        # RAG enrichment before decomposition
        query = f"Advisory request: {state.original_request.get('request_type', 'analyze')}"
        try:
            rag_context = self.rag_enricher.enrich(query, state.session_id)
            if rag_context.has_context:
                state.original_request["rag_context"] = rag_context.format_context_block()
        except Exception as exc:
            logger.warning("RAG enrichment failed in supervisor: %s", exc)

        request_type = state.original_request.get("request_type", "analyze")
        parameters = state.original_request.get("parameters", {})
        
        subtasks = []
        
        # Decompose based on request type
        if request_type == "analyze":
            subtasks.append({
                "subtask_id": str(uuid.uuid4()),
                "subtask_type": "analysis",
                "agent_name": "portfolio_analyzer",
                "parameters": {
                    "user_id": state.user_id,
                    "portfolio_id": parameters.get("portfolio_id"),
                    "analysis_type": parameters.get("analysis_type", "comprehensive"),
                    "time_period": parameters.get("time_period", "1Y")
                },
                "status": "pending",
                "retry_count": 0
            })
        
        elif request_type == "rebalance":
            # Rebalancing requires analysis, tax optimization, and rebalancing
            subtasks.extend([
                {
                    "subtask_id": str(uuid.uuid4()),
                    "subtask_type": "analysis",
                    "agent_name": "portfolio_analyzer",
                    "parameters": {
                        "user_id": state.user_id,
                        "portfolio_id": parameters.get("portfolio_id"),
                        "analysis_type": "drift",
                        "time_period": "1Y"
                    },
                    "status": "pending",
                    "retry_count": 0
                },
                {
                    "subtask_id": str(uuid.uuid4()),
                    "subtask_type": "tax",
                    "agent_name": "tax_optimizer",
                    "parameters": {
                        "user_id": state.user_id,
                        "portfolio_id": parameters.get("portfolio_id"),
                        "tax_year": datetime.utcnow().year
                    },
                    "status": "pending",
                    "retry_count": 0
                },
                {
                    "subtask_id": str(uuid.uuid4()),
                    "subtask_type": "rebalancing",
                    "agent_name": "rebalancing_agent",
                    "parameters": {
                        "user_id": state.user_id,
                        "portfolio_id": parameters.get("portfolio_id"),
                        "target_allocation": parameters.get("target_allocation", {}),
                        "constraints": parameters.get("constraints", {})
                    },
                    "status": "pending",
                    "retry_count": 0
                }
            ])
        
        elif request_type == "tax_optimize":
            subtasks.append({
                "subtask_id": str(uuid.uuid4()),
                "subtask_type": "tax",
                "agent_name": "tax_optimizer",
                "parameters": {
                    "user_id": state.user_id,
                    "portfolio_id": parameters.get("portfolio_id"),
                    "tax_year": datetime.utcnow().year
                },
                "status": "pending",
                "retry_count": 0
            })
        
        state.subtasks = subtasks
        state.pending_tasks = subtasks.copy()
        
        logger.info(f"Decomposed into {len(subtasks)} subtasks")
        return state
    
    def _route_to_agents(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Route subtasks to appropriate specialized agents."""
        logger.info(f"Routing {len(state.pending_tasks)} subtasks to agents")
        
        for subtask in state.pending_tasks:
            if subtask["status"] != "pending":
                continue
            
            try:
                subtask["status"] = "in_progress"
                
                # Invoke appropriate agent Lambda
                agent_name = subtask["agent_name"]
                agent_arn = self._get_agent_arn(agent_name)
                
                if not agent_arn:
                    raise ValueError(f"Unknown agent: {agent_name}")
                
                logger.info(f"Invoking {agent_name} for subtask {subtask['subtask_id']}")
                
                response = lambda_client.invoke(
                    FunctionName=agent_arn,
                    InvocationType="RequestResponse",
                    Payload=json.dumps(subtask["parameters"])
                )
                
                # Parse response
                response_payload = json.loads(response["Payload"].read())
                
                if response.get("FunctionError"):
                    logger.error(f"Agent {agent_name} returned error: {response_payload}")
                    subtask["status"] = "failed"
                    subtask["error"] = response_payload
                else:
                    subtask["status"] = "completed"
                    subtask["result"] = response_payload
                    
                    # Add to completed tasks
                    state.completed_tasks.append({
                        "subtask_id": subtask["subtask_id"],
                        "subtask_type": subtask["subtask_type"],
                        "agent_name": subtask["agent_name"],
                        "result": response_payload,
                        "completed_at": datetime.utcnow().isoformat()
                    })
            
            except Exception as e:
                logger.error(f"Error routing subtask {subtask['subtask_id']}: {e}")
                subtask["status"] = "failed"
                subtask["error"] = str(e)
        
        # Save state
        self._save_state(state)
        
        return state
    
    def _should_check_completion(self, state: SupervisorAgentState) -> str:
        """Determine if we should check completion or retry."""
        # Check if any subtasks failed
        failed_tasks = [t for t in state.pending_tasks if t.get("status") == "failed"]
        
        if failed_tasks:
            return "retry"
        
        return "check_completion"
    
    def _check_completion(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Check if all subtasks are completed."""
        logger.info("Checking task completion")
        
        pending = [t for t in state.pending_tasks if t.get("status") == "pending"]
        in_progress = [t for t in state.pending_tasks if t.get("status") == "in_progress"]
        
        if pending or in_progress:
            logger.info(f"Still have {len(pending)} pending and {len(in_progress)} in-progress tasks")
        
        return state
    
    def _should_aggregate(self, state: SupervisorAgentState) -> str:
        """Determine if we should aggregate or route more tasks."""
        pending = [t for t in state.pending_tasks if t.get("status") == "pending"]
        in_progress = [t for t in state.pending_tasks if t.get("status") == "in_progress"]
        
        if pending or in_progress:
            return "route"
        
        return "aggregate"
    
    def _aggregate_results(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Aggregate results from all completed subtasks."""
        logger.info("Aggregating results from completed tasks")
        
        aggregated = {
            "analysis": None,
            "tax_optimization": None,
            "rebalancing": None
        }
        
        for task in state.completed_tasks:
            if task["subtask_type"] == "analysis":
                aggregated["analysis"] = task["result"]
            elif task["subtask_type"] == "tax":
                aggregated["tax_optimization"] = task["result"]
            elif task["subtask_type"] == "rebalancing":
                aggregated["rebalancing"] = task["result"]
        
        state.aggregated_results = aggregated
        
        # Save state
        self._save_state(state)
        
        return state
    
    def _human_approval(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Wait for human approval of proposed trades."""
        logger.info(f"Waiting for human approval for session {state.session_id}")
        
        # In a real implementation, this would integrate with Step Functions
        # For now, we'll mark as pending approval
        state.approval_status = "pending"
        
        return state
    
    def _should_execute(self, state: SupervisorAgentState) -> str:
        """Determine if we should execute trades based on approval status."""
        if state.approval_status == "approved":
            return "execute"
        elif state.approval_status == "rejected":
            return "reject"
        else:
            return "cancel"
    
    def _execute_trades(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Execute approved trades."""
        logger.info(f"Executing trades for session {state.session_id}")
        
        # This would invoke the trade executor Lambda
        # For now, just mark as executed
        state.approval_status = "executed"
        
        return state
    
    def _update_portfolio(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Update portfolio after trade execution."""
        logger.info(f"Updating portfolio for session {state.session_id}")
        
        # This would update the portfolio in DynamoDB
        # For now, just mark as updated
        
        return state
    
    def _retry_task(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Retry failed subtasks with exponential backoff."""
        logger.info("Retrying failed subtasks")
        
        for subtask in state.pending_tasks:
            if subtask.get("status") == "failed":
                retry_count = subtask.get("retry_count", 0)
                
                if retry_count < MAX_RETRIES:
                    subtask["retry_count"] = retry_count + 1
                    subtask["status"] = "pending"
                    logger.info(f"Retrying subtask {subtask['subtask_id']} (attempt {retry_count + 1})")
                else:
                    logger.error(f"Max retries exceeded for subtask {subtask['subtask_id']}")
        
        return state
    
    def _should_retry(self, state: SupervisorAgentState) -> str:
        """Determine if we should retry or error out."""
        failed_tasks = [t for t in state.pending_tasks if t.get("status") == "failed"]
        
        # Check if any failed tasks can still be retried
        can_retry = any(t.get("retry_count", 0) < MAX_RETRIES for t in failed_tasks)
        
        if can_retry:
            return "retry"
        
        return "error"
    
    def _error_notification(self, state: SupervisorAgentState) -> SupervisorAgentState:
        """Handle permanent failures and notify user."""
        logger.error(f"Permanent failure for session {state.session_id}")
        
        failed_tasks = [t for t in state.pending_tasks if t.get("status") == "failed"]
        
        state.error_details = {
            "error_code": "AGENT_ERROR",
            "error_message": "One or more agent tasks failed after maximum retries",
            "failed_tasks": [
                {
                    "subtask_id": t["subtask_id"],
                    "agent_name": t["agent_name"],
                    "error": t.get("error", "Unknown error")
                }
                for t in failed_tasks
            ]
        }
        
        return state
    
    def _get_agent_arn(self, agent_name: str) -> Optional[str]:
        """Get Lambda ARN for agent."""
        arns = {
            "portfolio_analyzer": PORTFOLIO_ANALYZER_ARN,
            "tax_optimizer": TAX_OPTIMIZER_ARN,
            "rebalancing_agent": REBALANCING_AGENT_ARN
        }
        return arns.get(agent_name)
    
    def _save_state(self, state: SupervisorAgentState) -> None:
        """Save agent state to DynamoDB."""
        try:
            agent_state = AgentState(
                session_id=state.session_id,
                user_id=state.user_id,
                agent_type="supervisor",
                state=state.to_dict()
            )
            
            self.sessions_table.put_item(Item=agent_state.to_dynamodb())
            logger.info(f"Saved state for session {state.session_id}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _load_state(self, session_id: str) -> Optional[SupervisorAgentState]:
        """Load agent state from DynamoDB."""
        try:
            response = self.sessions_table.get_item(Key={"session_id": session_id})
            
            if "Item" in response:
                item = response["Item"]
                state_dict = item.get("state", {})
                return SupervisorAgentState.from_dict(state_dict)
        except Exception as e:
            logger.error(f"Error loading state: {e}")
        
        return None
    
    def process_request(self, request: SupervisorRequest) -> SupervisorResponse:
        """Process a supervisor request through the state machine."""
        logger.info(f"Processing request for session {request.session_id}")
        
        # Create initial state
        state = SupervisorAgentState(
            user_id=request.user_id,
            session_id=request.session_id,
            original_request={
                "request_type": request.request_type,
                "parameters": request.parameters,
                "context": request.context
            }
        )
        
        # Execute state machine
        try:
            final_state = self.graph.invoke(state)
            
            # Build response
            response = SupervisorResponse(
                session_id=final_state.session_id,
                status="success" if not final_state.error_details else "error",
                results=final_state.aggregated_results,
                requires_approval=final_state.approval_status == "pending",
                error_details=final_state.error_details
            )
            
            return response
        
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            
            return SupervisorResponse(
                session_id=request.session_id,
                status="error",
                results={},
                requires_approval=False,
                error_details={
                    "error_code": "SYSTEM_ERROR",
                    "error_message": str(e)
                }
            )


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for Supervisor Agent."""
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Parse request
        user_id = event.get("user_id")
        session_id = event.get("session_id", str(uuid.uuid4()))
        request_type = event.get("request_type", "analyze")
        parameters = event.get("parameters", {})
        context_data = event.get("context", {})
        
        # Create supervisor request
        request = SupervisorRequest(
            user_id=user_id,
            session_id=session_id,
            request_type=request_type,
            parameters=parameters,
            context=context_data
        )
        
        # Process request
        supervisor = SupervisorAgent()
        response = supervisor.process_request(request)
        
        # Return response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "session_id": response.session_id,
                "status": response.status,
                "results": response.results,
                "requires_approval": response.requires_approval,
                "error_details": response.error_details
            })
        }
    
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "error_code": "SYSTEM_ERROR"
            })
        }
