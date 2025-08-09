"""
Base Agent class cho tất cả các LLM agents trong hệ thống MCTS
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from backend.core.llm_client import LLMClient, LLMMessage, LLMResponse, PromptLoader
from backend.config import MCTSConfig

logger = logging.getLogger(__name__)

@dataclass
class AgentInput:
    """Input data cho agent"""
    data: Any
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    iteration: int = 1

@dataclass 
class AgentOutput:
    """Output data từ agent"""
    content: str
    success: bool
    agent_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    iteration: int = 1
    error: Optional[str] = None

class BaseAgent(ABC):
    """
    Abstract base class cho tất cả LLM agents
    """
    
    def __init__(self, 
                 agent_type: str,
                 config: MCTSConfig,
                 llm_client: LLMClient):
        self.agent_type = agent_type
        self.config = config
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
        
        # Load system prompt
        self.system_prompt = self.prompt_loader.get_system_prompt(agent_type)
        if not self.system_prompt:
            logger.warning(f"No system prompt loaded for agent type: {agent_type}")
        
        # Conversation history
        self.conversation_history: List[LLMMessage] = []
        
        # Performance tracking
        self.call_count = 0
        self.total_tokens = 0
        self.success_rate = 0.0
        
    @abstractmethod
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """
        Main processing method - must be implemented by subclasses
        """
        pass
    
    async def _make_llm_call(self, 
                           user_message: str,
                           temperature: Optional[float] = None,
                           max_tokens: Optional[int] = None,
                           use_conversation_history: bool = True) -> LLMResponse:
        """
        Protected method để thực hiện LLM call với error handling
        """
        try:
            self.call_count += 1
            
            if use_conversation_history and self.conversation_history:
                # Continue existing conversation
                response = await self.llm_client.continue_conversation(
                    conversation_history=self.conversation_history,
                    new_message=user_message,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                # Start new conversation
                response = await self.llm_client.single_prompt(
                    prompt=user_message,
                    system_message=self.system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                # Initialize conversation history
                if use_conversation_history:
                    self.conversation_history = [
                        LLMMessage(role="system", content=self.system_prompt),
                        LLMMessage(role="user", content=user_message)
                    ]
            
            # Update conversation history if successful
            if response.success and use_conversation_history:
                self.conversation_history.append(
                    LLMMessage(role="assistant", content=response.content)
                )
            
            # Update metrics
            if response.usage:
                self.total_tokens += response.usage.get("total_tokens", 0)
            
            # Update success rate
            successes = sum(1 for i in range(self.call_count) if i == self.call_count - 1 and response.success)
            self.success_rate = successes / self.call_count if self.call_count > 0 else 0
            
            return response
            
        except Exception as e:
            logger.error(f"Error in LLM call for {self.agent_type}: {str(e)}")
            return LLMResponse(
                content="",
                usage={},
                model=self.config.llm.model,
                success=False,
                error=str(e)
            )
    
    def reset_conversation(self):
        """Reset conversation history"""
        self.conversation_history = []
        logger.info(f"Reset conversation history for {self.agent_type}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Lấy performance metrics của agent"""
        return {
            "agent_type": self.agent_type,
            "call_count": self.call_count,
            "total_tokens": self.total_tokens,
            "success_rate": self.success_rate,
            "avg_tokens_per_call": self.total_tokens / max(self.call_count, 1)
        }
    
    def _create_agent_output(self, 
                           content: str,
                           success: bool,
                           agent_input: AgentInput,
                           error: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> AgentOutput:
        """Helper method để tạo AgentOutput"""
        
        output_metadata = {
            "agent_metrics": self.get_metrics(),
            "input_metadata": agent_input.metadata
        }
        
        if metadata:
            output_metadata.update(metadata)
        
        return AgentOutput(
            content=content,
            success=success,
            agent_type=self.agent_type,
            metadata=output_metadata,
            iteration=agent_input.iteration,
            error=error
        )
    
    async def validate_input(self, agent_input: AgentInput) -> bool:
        """
        Validate input data - can be overridden by subclasses
        """
        if not isinstance(agent_input, AgentInput):
            logger.error(f"Invalid input type for {self.agent_type}")
            return False
        
        if not agent_input.data:
            logger.error(f"Empty data for {self.agent_type}")
            return False
            
        return True
    
    def _format_input_for_llm(self, agent_input: AgentInput) -> str:
        """
        Format input data for LLM - should be overridden by subclasses
        """
        return str(agent_input.data)
    
    async def post_process_output(self, 
                                llm_response: LLMResponse,
                                agent_input: AgentInput) -> str:
        """
        Post-process LLM output - can be overridden by subclasses
        """
        return llm_response.content
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(type={self.agent_type}, calls={self.call_count})"
    
    def __repr__(self) -> str:
        return self.__str__()

class AgentOrchestrator:
    """
    Orchestrator để quản lý multiple agents
    """
    
    def __init__(self, config: MCTSConfig):
        self.config = config
        self.agents: Dict[str, BaseAgent] = {}
        self.llm_client: Optional[LLMClient] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.llm_client = LLMClient(self.config.llm)
        await self.llm_client.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.llm_client:
            await self.llm_client.close_session()
    
    def register_agent(self, agent: BaseAgent):
        """Đăng ký agent với orchestrator"""
        self.agents[agent.agent_type] = agent
        logger.info(f"Registered agent: {agent.agent_type}")
    
    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """Lấy agent theo type"""
        return self.agents.get(agent_type)
    
    async def run_agent(self, 
                       agent_type: str, 
                       agent_input: AgentInput) -> AgentOutput:
        """Chạy một agent cụ thể"""
        agent = self.get_agent(agent_type)
        if not agent:
            error_msg = f"Agent not found: {agent_type}"
            logger.error(error_msg)
            return AgentOutput(
                content="",
                success=False,
                agent_type=agent_type,
                error=error_msg,
                iteration=agent_input.iteration
            )
        
        return await agent.process(agent_input)
    
    async def run_agents_parallel(self, 
                                agent_inputs: Dict[str, AgentInput]) -> Dict[str, AgentOutput]:
        """Chạy multiple agents parallel"""
        tasks = []
        agent_types = []
        
        for agent_type, agent_input in agent_inputs.items():
            task = self.run_agent(agent_type, agent_input)
            tasks.append(task)
            agent_types.append(agent_type)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for i, result in enumerate(results):
            agent_type = agent_types[i]
            if isinstance(result, Exception):
                logger.error(f"Error running agent {agent_type}: {str(result)}")
                output[agent_type] = AgentOutput(
                    content="",
                    success=False,
                    agent_type=agent_type,
                    error=str(result),
                    iteration=agent_inputs[agent_type].iteration
                )
            else:
                output[agent_type] = result
        
        return output
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Lấy metrics của tất cả agents"""
        return {
            agent_type: agent.get_metrics() 
            for agent_type, agent in self.agents.items()
        }
    
    def reset_all_conversations(self):
        """Reset conversation history cho tất cả agents"""
        for agent in self.agents.values():
            agent.reset_conversation()
        logger.info("Reset all agent conversations")

# Utility functions
def create_agent_input(data: Any, 
                      context: Optional[Dict[str, Any]] = None,
                      metadata: Optional[Dict[str, Any]] = None,
                      iteration: int = 1) -> AgentInput:
    """Helper function để tạo AgentInput"""
    return AgentInput(
        data=data,
        context=context or {},
        metadata=metadata or {},
        iteration=iteration
    )
