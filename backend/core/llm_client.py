"""
LLM Client cho hệ thống MCTS
Xử lý tất cả các kết nối và giao tiếp với LLM API
"""

import json
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from backend.config import LLMConfig

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LLMResponse:
    """Cấu trúc response từ LLM API"""
    content: str
    usage: Dict[str, int]
    model: str
    success: bool
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class LLMMessage:
    """Cấu trúc message cho LLM"""
    role: str  # "system", "user", "assistant"
    content: str

class LLMClient:
    """
    Client để giao tiếp với LLM API
    Hỗ trợ cả sync và async calls
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}"
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_session()
        
    async def start_session(self):
        """Khởi tạo aiohttp session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=timeout
            )
            
    async def close_session(self):
        """Đóng aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _build_payload(self, 
                      messages: List[LLMMessage], 
                      temperature: Optional[float] = None,
                      max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Xây dựng payload cho API request"""
        
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": msg.role, "content": msg.content} 
                for msg in messages
            ],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens
        }
        
        return payload
    
    async def chat_completion(self, 
                            messages: List[LLMMessage],
                            temperature: Optional[float] = None,
                            max_tokens: Optional[int] = None,
                            retries: int = 3) -> LLMResponse:
        """
        Thực hiện chat completion với retry logic
        """
        if not self.session:
            await self.start_session()
            
        payload = self._build_payload(messages, temperature, max_tokens)
        
        for attempt in range(retries + 1):
            try:
                logger.info(f"Gửi request đến LLM (attempt {attempt + 1}/{retries + 1})")
                
                async with self.session.post(self.config.url, json=payload) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        return self._parse_success_response(response_data)
                    else:
                        error_msg = f"API Error {response.status}: {response_data}"
                        logger.error(error_msg)
                        
                        if attempt == retries:  # Last attempt
                            return LLMResponse(
                                content="",
                                usage={},
                                model=self.config.model,
                                success=False,
                                error=error_msg
                            )
                        
                        # Wait before retry
                        await asyncio.sleep(2 ** attempt)
                        
            except asyncio.TimeoutError:
                error_msg = f"Timeout sau {self.config.timeout}s"
                logger.error(error_msg)
                
                if attempt == retries:
                    return LLMResponse(
                        content="",
                        usage={},
                        model=self.config.model,
                        success=False,
                        error=error_msg
                    )
                    
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(error_msg)
                
                if attempt == retries:
                    return LLMResponse(
                        content="",
                        usage={},
                        model=self.config.model,
                        success=False,
                        error=error_msg
                    )
                    
                await asyncio.sleep(2 ** attempt)
        
        # Shouldn't reach here, but just in case
        return LLMResponse(
            content="",
            usage={},
            model=self.config.model,
            success=False,
            error="Max retries exceeded"
        )
    
    def _parse_success_response(self, response_data: Dict[str, Any]) -> LLMResponse:
        """Parse thành công response từ API"""
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise ValueError("No choices in response")
                
            content = choices[0].get("message", {}).get("content", "")
            usage = response_data.get("usage", {})
            model = response_data.get("model", self.config.model)
            
            return LLMResponse(
                content=content,
                usage=usage,
                model=model,
                success=True,
                metadata=response_data
            )
            
        except Exception as e:
            error_msg = f"Failed to parse response: {str(e)}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                usage={},
                model=self.config.model,
                success=False,
                error=error_msg
            )
    
    async def single_prompt(self, 
                          prompt: str,
                          system_message: Optional[str] = None,
                          temperature: Optional[float] = None,
                          max_tokens: Optional[int] = None) -> LLMResponse:
        """
        Convenience method cho single prompt
        """
        messages = []
        
        if system_message:
            messages.append(LLMMessage(role="system", content=system_message))
            
        messages.append(LLMMessage(role="user", content=prompt))
        
        return await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    async def continue_conversation(self,
                                  conversation_history: List[LLMMessage],
                                  new_message: str,
                                  temperature: Optional[float] = None,
                                  max_tokens: Optional[int] = None) -> LLMResponse:
        """
        Tiếp tục cuộc hội thoại với lịch sử
        """
        messages = conversation_history.copy()
        messages.append(LLMMessage(role="user", content=new_message))
        
        return await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

class PromptLoader:
    """
    Utility class để load và quản lý prompts từ files
    """
    
    def __init__(self, prompts_dir: str = "backend/prompts"):
        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}
    
    def load_prompt(self, filename: str) -> str:
        """Load prompt từ file với caching"""
        if filename in self._cache:
            return self._cache[filename]
            
        try:
            filepath = f"{self.prompts_dir}/{filename}"
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                self._cache[filename] = content
                return content
                
        except FileNotFoundError:
            logger.error(f"Prompt file not found: {filepath}")
            return ""
        except Exception as e:
            logger.error(f"Error loading prompt {filename}: {str(e)}")
            return ""
    
    def get_system_prompt(self, agent_type: str) -> str:
        """Lấy system prompt cho loại agent cụ thể"""
        filename_map = {
            "primary": "primary_llm.txt",
            "critical_thinking": "critical_thinking_llm.txt", 
            "adversarial": "adversarial_expert_llm.txt",
            "synthesis": "synthesis_assessment_llm.txt"
        }
        
        filename = filename_map.get(agent_type, "")
        if not filename:
            logger.error(f"Unknown agent type: {agent_type}")
            return ""
            
        return self.load_prompt(filename)
    
    def clear_cache(self):
        """Xóa cache prompts"""
        self._cache.clear()

# Convenience functions
async def quick_llm_call(prompt: str, 
                        config: LLMConfig,
                        system_message: Optional[str] = None,
                        temperature: float = 0.7) -> LLMResponse:
    """
    Quick function để gọi LLM với minimal setup
    """
    async with LLMClient(config) as client:
        return await client.single_prompt(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature
        )

def create_message(role: str, content: str) -> LLMMessage:
    """Helper function để tạo LLMMessage"""
    return LLMMessage(role=role, content=content)

def create_conversation(system_prompt: str, 
                       user_messages: List[str],
                       assistant_messages: List[str] = None) -> List[LLMMessage]:
    """
    Helper function để tạo conversation history
    """
    messages = [LLMMessage(role="system", content=system_prompt)]
    
    assistant_messages = assistant_messages or []
    
    # Interleave user và assistant messages
    for i, user_msg in enumerate(user_messages):
        messages.append(LLMMessage(role="user", content=user_msg))
        
        if i < len(assistant_messages):
            messages.append(LLMMessage(role="assistant", content=assistant_messages[i]))
    
    return messages

# Test function
async def test_llm_connection(config: LLMConfig) -> bool:
    """
    Test connection đến LLM API
    """
    try:
        logger.info("Testing LLM connection...")
        
        test_prompt = "Xin chào! Bạn có thể trả lời bằng tiếng Việt không?"
        
        response = await quick_llm_call(
            prompt=test_prompt,
            config=config,
            temperature=0.1
        )
        
        if response.success:
            logger.info(f"✅ LLM connection successful: {response.content[:100]}...")
            return True
        else:
            logger.error(f"❌ LLM connection failed: {response.error}")
            return False
            
    except Exception as e:
        logger.error(f"❌ LLM connection test error: {str(e)}")
        return False

if __name__ == "__main__":
    # Example usage
    from backend.config import DEFAULT_CONFIG
    
    async def main():
        # Test connection
        success = await test_llm_connection(DEFAULT_CONFIG.llm)
        
        if success:
            # Test prompt loading
            loader = PromptLoader()
            primary_prompt = loader.get_system_prompt("primary")
            print(f"Loaded prompt length: {len(primary_prompt)} characters")
            
            # Test conversation
            async with LLMClient(DEFAULT_CONFIG.llm) as client:
                response = await client.single_prompt(
                    "Hãy giải thích ngắn gọn vai trò của bạn trong hệ thống MCTS",
                    system_message=primary_prompt[:1000],  # Truncate for test
                    temperature=0.5
                )
                
                if response.success:
                    print(f"Response: {response.content[:200]}...")
                else:
                    print(f"Error: {response.error}")
    
    asyncio.run(main())
