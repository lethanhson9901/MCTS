"""
Dynamic Processor - Xử lý dynamic input từ user
"""

import asyncio
import logging
import json
import re
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from backend.core.llm_client import LLMClient, LLMMessage, LLMResponse
from backend.core.mcts_orchestrator import MCTSOrchestrator, MCTSSession
from backend.config import MCTSConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

class InputType(Enum):
    """Loại input từ user"""
    QUESTION = "question"
    ANALYSIS_REQUEST = "analysis_request"
    IDEA_REQUEST = "idea_request"
    DATA_TO_ANALYZE = "data_to_analyze"
    FEEDBACK = "feedback"
    GENERAL_CHAT = "general_chat"

@dataclass
class DynamicInput:
    """Dynamic input từ user"""
    content: str
    input_type: InputType
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ProcessedResponse:
    """Response đã xử lý"""
    content: str
    response_type: str
    success: bool
    suggestions: List[str] = field(default_factory=list)
    follow_up_questions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class DynamicProcessor:
    """
    Processor chính để xử lý mọi loại input từ user
    """
    
    def __init__(self, config: MCTSConfig = None):
        self.config = config or DEFAULT_CONFIG
        self.llm_client: Optional[LLMClient] = None
        self.mcts_orchestrator: Optional[MCTSOrchestrator] = None
        
        # Conversation context
        self.conversation_history: List[Dict[str, Any]] = []
        self.current_session: Optional[MCTSSession] = None
        
        # Classification prompts
        self.classifier_prompt = """
Bạn là một AI classifier thông minh. Hãy phân loại input sau của user vào một trong các loại:

1. QUESTION - Câu hỏi tổng quát về startup, business, technology
2. ANALYSIS_REQUEST - Yêu cầu phân tích dữ liệu/thông tin cụ thể  
3. IDEA_REQUEST - Yêu cầu tạo ý tưởng startup/business
4. DATA_TO_ANALYZE - Cung cấp dữ liệu để phân tích
5. FEEDBACK - Feedback về kết quả trước đó
6. GENERAL_CHAT - Trò chuyện thông thường

Input: "{input_text}"

Trả về JSON format:
{{
    "type": "loại_được_phân_loại",
    "confidence": 0.95,
    "reasoning": "lý do phân loại",
    "extracted_intent": "ý định chính của user",
    "key_entities": ["entity1", "entity2"]
}}
"""
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()
    
    async def initialize(self):
        """Khởi tạo components"""
        logger.info("Initializing Dynamic Processor...")
        
        # Initialize LLM client
        self.llm_client = LLMClient(self.config.llm)
        await self.llm_client.start_session()
        
        # Initialize MCTS orchestrator
        self.mcts_orchestrator = MCTSOrchestrator(self.config)
        await self.mcts_orchestrator.initialize()
        
        logger.info("✅ Dynamic Processor initialized successfully")
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.llm_client:
            await self.llm_client.close_session()
        
        if self.mcts_orchestrator:
            await self.mcts_orchestrator.cleanup()
    
    async def process_user_input(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> ProcessedResponse:
        """
        Xử lý input từ user một cách dynamic
        
        Args:
            user_input: Input text từ user
            context: Context bổ sung (optional)
        
        Returns:
            ProcessedResponse với kết quả
        """
        
        try:
            # Step 1: Classify input
            classified_input = await self._classify_input(user_input, context)
            
            # Step 2: Process based on type
            response = await self._process_by_type(classified_input)
            
            # Step 3: Update conversation history
            self._update_conversation_history(user_input, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing user input: {str(e)}")
            return ProcessedResponse(
                content=f"Xin lỗi, đã có lỗi xảy ra: {str(e)}",
                response_type="error",
                success=False,
                suggestions=["Hãy thử lại với input khác", "Kiểm tra kết nối mạng"]
            )
    
    async def _classify_input(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> DynamicInput:
        """Phân loại input của user"""
        
        try:
            # Prepare classifier prompt
            prompt = self.classifier_prompt.format(input_text=user_input)
            
            # Add context if available
            if context:
                prompt += f"\n\nContext bổ sung: {json.dumps(context, ensure_ascii=False)}"
            
            # Call LLM
            response = await self.llm_client.single_prompt(
                prompt=prompt,
                temperature=0.1  # Low temperature for consistent classification
            )
            
            if not response.success:
                # Fallback classification
                return self._fallback_classify(user_input, context)
            
            # Parse JSON response
            try:
                classification = json.loads(response.content)
                input_type = InputType(classification.get("type", "general_chat"))
                
                return DynamicInput(
                    content=user_input,
                    input_type=input_type,
                    context=context or {},
                    metadata={
                        "confidence": classification.get("confidence", 0.5),
                        "reasoning": classification.get("reasoning", ""),
                        "extracted_intent": classification.get("extracted_intent", ""),
                        "key_entities": classification.get("key_entities", [])
                    }
                )
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse classification JSON: {str(e)}")
                return self._fallback_classify(user_input, context)
                
        except Exception as e:
            logger.error(f"Error in input classification: {str(e)}")
            return self._fallback_classify(user_input, context)
    
    def _fallback_classify(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> DynamicInput:
        """Fallback classification sử dụng regex patterns"""
        
        user_lower = user_input.lower()
        
        # Question patterns
        question_patterns = [
            r'\b(tại sao|làm sao|như thế nào|là gì|có phải)\b',
            r'^\s*(có|bạn|ai|gì|ở đâu|khi nào)',
            r'\?'
        ]
        
        # Analysis request patterns
        analysis_patterns = [
            r'\b(phân tích|đánh giá|nghiên cứu|so sánh)\b',
            r'\b(xu hướng|thị trường|dữ liệu|báo cáo)\b',
            r'\b(insight|thống kê|metric)\b'
        ]
        
        # Idea request patterns
        idea_patterns = [
            r'\b(ý tưởng|idea|startup|sáng tạo)\b',
            r'\b(tạo ra|đề xuất|gợi ý|brainstorm)\b',
            r'\b(business|kinh doanh|dự án)\b'
        ]
        
        # Data patterns
        data_patterns = [
            r'\b(đây là dữ liệu|data|thông tin|nội dung)\b',
            r'\b(từ reddit|từ hackernews|từ product hunt)\b',
            r'^\s*[\{\[].*[\}\]]'  # JSON-like structure
        ]
        
        # Determine type
        if any(re.search(pattern, user_lower) for pattern in question_patterns):
            input_type = InputType.QUESTION
        elif any(re.search(pattern, user_lower) for pattern in analysis_patterns):
            input_type = InputType.ANALYSIS_REQUEST
        elif any(re.search(pattern, user_lower) for pattern in idea_patterns):
            input_type = InputType.IDEA_REQUEST
        elif any(re.search(pattern, user_lower) for pattern in data_patterns):
            input_type = InputType.DATA_TO_ANALYZE
        else:
            input_type = InputType.GENERAL_CHAT
        
        return DynamicInput(
            content=user_input,
            input_type=input_type,
            context=context or {},
            metadata={"fallback_classification": True}
        )
    
    async def _process_by_type(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý input dựa trên type đã classify"""
        
        if dynamic_input.input_type == InputType.QUESTION:
            return await self._handle_question(dynamic_input)
        
        elif dynamic_input.input_type == InputType.ANALYSIS_REQUEST:
            return await self._handle_analysis_request(dynamic_input)
        
        elif dynamic_input.input_type == InputType.IDEA_REQUEST:
            return await self._handle_idea_request(dynamic_input)
        
        elif dynamic_input.input_type == InputType.DATA_TO_ANALYZE:
            return await self._handle_data_analysis(dynamic_input)
        
        elif dynamic_input.input_type == InputType.FEEDBACK:
            return await self._handle_feedback(dynamic_input)
        
        else:  # GENERAL_CHAT
            return await self._handle_general_chat(dynamic_input)
    
    async def _handle_question(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý câu hỏi tổng quát"""
        
        system_prompt = """
Bạn là một chuyên gia startup và business strategy. Hãy trả lời câu hỏi của user một cách:
- Chính xác và có căn cứ
- Practical và actionable  
- Cung cấp examples cụ thể
- Đưa ra follow-up questions để hiểu sâu hơn

Trả lời bằng tiếng Việt.
"""
        
        response = await self.llm_client.single_prompt(
            prompt=dynamic_input.content,
            system_message=system_prompt,
            temperature=0.7
        )
        
        if not response.success:
            return ProcessedResponse(
                content="Xin lỗi, tôi không thể trả lời câu hỏi này lúc này.",
                response_type="error",
                success=False
            )
        
        # Extract follow-up questions từ response
        follow_ups = self._extract_follow_up_questions(response.content)
        
        return ProcessedResponse(
            content=response.content,
            response_type="answer",
            success=True,
            follow_up_questions=follow_ups,
            suggestions=[
                "Bạn có muốn tôi phân tích sâu hơn về chủ đề này?",
                "Có vấn đề gì khác bạn muốn hỏi?",
                "Bạn có muốn tôi tạo ý tưởng startup liên quan?"
            ]
        )
    
    async def _handle_analysis_request(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý yêu cầu phân tích"""
        
        # Check if có sufficient data để analyze
        if len(dynamic_input.content) < 100:
            return ProcessedResponse(
                content="""
Để thực hiện phân tích chất lượng, tôi cần thêm thông tin:

1. **Dữ liệu cụ thể**: Cung cấp data sources, links, hoặc nội dung để phân tích
2. **Scope phân tích**: Bạn muốn phân tích aspect nào? (market trends, competitors, user feedback, etc.)
3. **Mục tiêu**: Phân tích này để làm gì? (market research, idea validation, investment decision)

**Ví dụ input tốt:**
- "Phân tích xu hướng AI/ML startup từ dữ liệu Reddit r/MachineLearning trong tháng 12/2024"
- "Đánh giá thị trường SaaS productivity tools dựa trên ProductHunt launches gần đây"
""",
                response_type="request_more_info",
                success=False,
                suggestions=[
                    "Cung cấp links hoặc raw data để phân tích",
                    "Specify lĩnh vực cần phân tích (AI, SaaS, Fintech, etc.)",
                    "Cho biết mục tiêu của phân tích"
                ]
            )
        
        # Create synthetic data source từ user input
        data_sources = [{
            "type": "user_provided",
            "description": "Dữ liệu/yêu cầu phân tích từ user",
            "content": dynamic_input.content,
            "metadata": dynamic_input.metadata
        }]
        
        # Extract focus areas từ input
        focus_areas = self._extract_focus_areas(dynamic_input.content)
        
        # Set timeframe
        timeframe = {
            "start": "2024-01-01",
            "end": datetime.now().strftime("%Y-%m-%d")
        }
        
        try:
            # Run MCTS analysis
            session = await self.mcts_orchestrator.run_full_analysis(
                data_sources=data_sources,
                timeframe=timeframe,
                focus_areas=focus_areas
            )
            
            self.current_session = session
            
            # Format response
            analysis_summary = self._format_analysis_summary(session)
            
            return ProcessedResponse(
                content=analysis_summary,
                response_type="analysis_result",
                success=True,
                suggestions=[
                    "Bạn có muốn tôi tạo ý tưởng startup từ phân tích này?",
                    "Cần tôi phân tích sâu hơn về aspect nào?",
                    "Muốn export kết quả chi tiết không?"
                ],
                metadata={"session_id": session.session_id}
            )
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            return ProcessedResponse(
                content=f"Phân tích gặp lỗi: {str(e)}. Hãy thử với input khác hoặc đơn giản hóa yêu cầu.",
                response_type="error",
                success=False
            )
    
    async def _handle_idea_request(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý yêu cầu tạo ý tưởng"""
        
        # Check if có context để tạo ý tưởng
        if not self.current_session or not self.current_session.analysis_results:
            # Generate ideas directly từ input
            return await self._generate_ideas_from_scratch(dynamic_input)
        
        # Use existing analysis để generate ideas
        return await self._generate_ideas_from_analysis(dynamic_input)
    
    async def _handle_data_analysis(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý dữ liệu cần phân tích"""
        
        # Auto-trigger analysis với provided data
        analysis_input = DynamicInput(
            content=f"Phân tích dữ liệu sau:\n\n{dynamic_input.content}",
            input_type=InputType.ANALYSIS_REQUEST,
            context=dynamic_input.context,
            metadata=dynamic_input.metadata
        )
        
        return await self._handle_analysis_request(analysis_input)
    
    async def _handle_feedback(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý feedback từ user"""
        
        if not self.current_session:
            return ProcessedResponse(
                content="Tôi chưa có kết quả nào để receive feedback. Hãy bắt đầu với một phân tích hoặc yêu cầu ý tưởng.",
                response_type="no_context",
                success=False
            )
        
        # Process feedback và improve
        system_prompt = """
Bạn nhận được feedback từ user về kết quả trước đó. Hãy:
1. Acknowledge feedback
2. Explain cách sẽ cải thiện
3. Đưa ra next steps cụ thể

Trả lời bằng tiếng Việt.
"""
        
        prompt = f"""
Feedback từ user: {dynamic_input.content}

Context: User đã nhận kết quả từ session {self.current_session.session_id}
"""
        
        response = await self.llm_client.single_prompt(
            prompt=prompt,
            system_message=system_prompt,
            temperature=0.6
        )
        
        return ProcessedResponse(
            content=response.content if response.success else "Cảm ơn feedback của bạn. Tôi sẽ cải thiện trong lần tiếp theo.",
            response_type="feedback_acknowledgment",
            success=response.success,
            suggestions=[
                "Muốn tôi re-run analysis với approach khác?",
                "Cần adjust tiêu chí đánh giá?",
                "Có specific aspect nào cần focus hơn?"
            ]
        )
    
    async def _handle_general_chat(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Xử lý general chat"""
        
        system_prompt = """
Bạn là MCTS AI Assistant - chuyên gia về startup analysis và idea generation. 
Hãy trò chuyện thân thiện và hướng dẫn user sử dụng khả năng của bạn.

Capabilities chính:
- Phân tích dữ liệu startup/market trends
- Tạo ý tưởng startup validated
- Đánh giá business ideas
- Market research automation

Trả lời bằng tiếng Việt.
"""
        
        response = await self.llm_client.single_prompt(
            prompt=dynamic_input.content,
            system_message=system_prompt,
            temperature=0.8
        )
        
        return ProcessedResponse(
            content=response.content if response.success else "Xin chào! Tôi có thể giúp bạn phân tích startup trends và tạo ý tưởng business. Bạn cần hỗ trợ gì?",
            response_type="chat",
            success=response.success,
            suggestions=[
                "Hỏi tôi về startup trends",
                "Yêu cầu phân tích market data",
                "Tạo ý tưởng startup mới",
                "Đánh giá business idea của bạn"
            ]
        )
    
    async def _generate_ideas_from_scratch(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Tạo ý tưởng từ scratch (không có analysis trước)"""
        
        system_prompt = """
Bạn là chuyên gia startup consultant. User yêu cầu tạo ý tưởng startup.
Hãy tạo 3-5 ý tưởng chất lượng cao với:

1. Problem definition rõ ràng
2. Solution overview
3. Target market
4. Business model basics
5. Competitive advantage
6. Implementation roadmap sơ bộ

Format response theo structure:

# Ý TƯỞNG STARTUP

## 1. [Tên ý tưởng]
**Problem:** 
**Solution:**
**Target Market:**
**Business Model:**
**Competitive Advantage:**
**Next Steps:**

Trả lời bằng tiếng Việt.
"""
        
        prompt = f"Yêu cầu tạo ý tưởng: {dynamic_input.content}"
        
        response = await self.llm_client.single_prompt(
            prompt=prompt,
            system_message=system_prompt,
            temperature=0.7
        )
        
        return ProcessedResponse(
            content=response.content if response.success else "Không thể tạo ý tưởng lúc này. Hãy thử lại sau.",
            response_type="ideas_generated",
            success=response.success,
            suggestions=[
                "Muốn tôi phân tích chi tiết hơn ý tưởng nào?",
                "Cần validate ý tưởng với market data?",
                "Tạo business plan cho ý tưởng cụ thể?"
            ]
        )
    
    async def _generate_ideas_from_analysis(self, dynamic_input: DynamicInput) -> ProcessedResponse:
        """Tạo ý tưởng dựa trên analysis có sẵn"""
        
        # Use MCTS idea generation
        try:
            # Continue with ideas phase
            self.mcts_orchestrator.session = self.current_session
            await self.mcts_orchestrator._run_ideas_phase()
            
            ideas_summary = self._format_ideas_summary(self.current_session)
            
            return ProcessedResponse(
                content=ideas_summary,
                response_type="validated_ideas",
                success=True,
                suggestions=[
                    "Phân tích deeper vào ý tưởng nào?",
                    "Tạo business plan chi tiết?",
                    "Export full report?"
                ],
                metadata={"session_id": self.current_session.session_id}
            )
            
        except Exception as e:
            logger.error(f"Ideas generation failed: {str(e)}")
            return await self._generate_ideas_from_scratch(dynamic_input)
    
    def _extract_focus_areas(self, content: str) -> List[str]:
        """Extract focus areas từ user input"""
        
        content_lower = content.lower()
        
        # Common focus areas mapping
        focus_mapping = {
            "ai": ["AI/ML", "Artificial Intelligence"],
            "machine learning": ["AI/ML"],
            "ml": ["AI/ML"],
            "saas": ["SaaS", "Software"],
            "fintech": ["Fintech", "Finance"],
            "healthtech": ["HealthTech", "Healthcare"],
            "edtech": ["EdTech", "Education"],
            "ecommerce": ["E-commerce", "Retail"],
            "blockchain": ["Blockchain", "Web3"],
            "iot": ["IoT", "Hardware"],
            "mobile": ["Mobile Apps"],
            "web": ["Web Applications"],
            "productivity": ["Productivity Tools"],
            "marketing": ["Marketing Tools"],
            "hr": ["HR Tech"],
            "real estate": ["PropTech"]
        }
        
        detected_areas = []
        for keyword, areas in focus_mapping.items():
            if keyword in content_lower:
                detected_areas.extend(areas)
        
        # Remove duplicates và return
        return list(set(detected_areas)) if detected_areas else ["General Technology", "Market Analysis"]
    
    def _extract_follow_up_questions(self, content: str) -> List[str]:
        """Extract follow-up questions từ response"""
        
        # Look for questions in response
        question_pattern = r'([^.!?]*\?)'
        questions = re.findall(question_pattern, content)
        
        # Clean và filter
        follow_ups = []
        for q in questions[-3:]:  # Take last 3 questions
            clean_q = q.strip()
            if len(clean_q) > 10 and clean_q not in follow_ups:
                follow_ups.append(clean_q)
        
        return follow_ups
    
    def _format_analysis_summary(self, session: MCTSSession) -> str:
        """Format analysis results for user"""
        
        if not session.analysis_results:
            return "Phân tích chưa hoàn thành."
        
        # Extract key insights từ analysis
        summary = f"""
# 📊 KẾT QUẢ PHÂN TÍCH

**Session ID:** {session.session_id}
**Thời gian:** {session.start_time.strftime('%Y-%m-%d %H:%M')}
**Số vòng lặp:** {session.analysis_iteration}

## Tóm tắt chính

{session.analysis_results[:1000]}{'...' if len(session.analysis_results) > 1000 else ''}

## Chất lượng kết quả

- **Vòng lặp hoàn thành:** {session.analysis_iteration}/{self.config.max_analysis_loops}
- **Status:** {session.current_phase.value}

📄 **Kết quả đầy đủ** đã được lưu và có thể export nếu cần.
"""
        
        return summary
    
    def _format_ideas_summary(self, session: MCTSSession) -> str:
        """Format ideas results for user"""
        
        if not session.ideas_results:
            return "Chưa có ý tưởng được tạo."
        
        summary = f"""
# 💡 Ý TƯỞNG STARTUP ĐÃ VALIDATED

**Session ID:** {session.session_id}
**Dựa trên phân tích:** {session.analysis_iteration} vòng lặp
**Ý tưởng được test:** {session.ideas_iteration} vòng lặp

## Top Ideas

{session.ideas_results[:1500]}{'...' if len(session.ideas_results) > 1500 else ''}

## Validation Summary

- **Analysis Phase:** {session.analysis_iteration} iterations
- **Ideas Phase:** {session.ideas_iteration} iterations  
- **Quality Assurance:** Đã qua Critical Thinking + Adversarial Testing
- **External Validation:** {'✅' if self.config.enable_external_validation else '❌'}

📄 **Full report** với scoring chi tiết có thể được export.
"""
        
        return summary
    
    def _update_conversation_history(self, user_input: str, response: ProcessedResponse):
        """Update conversation history"""
        
        self.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "response": response.__dict__,
            "session_id": self.current_session.session_id if self.current_session else None
        })
        
        # Keep only last 50 conversations
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]
    
    def get_conversation_context(self) -> Dict[str, Any]:
        """Lấy context của conversation hiện tại"""
        
        return {
            "conversation_length": len(self.conversation_history),
            "current_session": self.current_session.session_id if self.current_session else None,
            "last_interactions": self.conversation_history[-5:] if self.conversation_history else [],
            "active_topics": self._extract_active_topics()
        }
    
    def _extract_active_topics(self) -> List[str]:
        """Extract active topics từ conversation history"""
        
        if not self.conversation_history:
            return []
        
        # Simple keyword extraction từ recent conversations
        recent_inputs = [conv["user_input"] for conv in self.conversation_history[-10:]]
        combined_text = " ".join(recent_inputs).lower()
        
        # Common startup/business topics
        topics = {
            "startup": "Startup Strategy",
            "business": "Business Development", 
            "market": "Market Analysis",
            "competitor": "Competitive Analysis",
            "funding": "Funding & Investment",
            "technology": "Technology Trends",
            "product": "Product Development",
            "user": "User Experience"
        }
        
        active = []
        for keyword, topic in topics.items():
            if keyword in combined_text:
                active.append(topic)
        
        return active[:3]  # Return top 3 active topics

# Convenience functions
async def process_user_message(message: str, config: MCTSConfig = None) -> ProcessedResponse:
    """Quick function để process user message"""
    
    async with DynamicProcessor(config) as processor:
        return await processor.process_user_input(message)

async def start_interactive_session(config: MCTSConfig = None):
    """Start interactive session với user"""
    
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    
    console.print(Panel.fit(
        "🧠 MCTS Interactive Session\nNhập 'quit' để thoát",
        title="Dynamic AI Assistant",
        border_style="blue"
    ))
    
    async with DynamicProcessor(config) as processor:
        while True:
            try:
                # Get user input
                user_input = input("\n💬 Bạn: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    console.print("👋 Tạm biệt! Cảm ơn bạn đã sử dụng MCTS.", style="green")
                    break
                
                if not user_input:
                    continue
                
                # Process input
                console.print("\n🤔 Đang xử lý...", style="yellow")
                response = await processor.process_user_input(user_input)
                
                # Display response
                console.print(f"\n🤖 MCTS: {response.content}", style="white")
                
                # Show suggestions if available
                if response.suggestions:
                    console.print("\n💡 Gợi ý:", style="cyan")
                    for i, suggestion in enumerate(response.suggestions, 1):
                        console.print(f"   {i}. {suggestion}", style="dim cyan")
                
                # Show follow-up questions if available
                if response.follow_up_questions:
                    console.print("\n❓ Câu hỏi tiếp theo:", style="magenta")
                    for i, question in enumerate(response.follow_up_questions, 1):
                        console.print(f"   {i}. {question}", style="dim magenta")
                
            except KeyboardInterrupt:
                console.print("\n👋 Tạm biệt!", style="green")
                break
            except Exception as e:
                console.print(f"\n❌ Lỗi: {str(e)}", style="red")

if __name__ == "__main__":
    # Test dynamic processor
    import asyncio
    
    async def test():
        test_inputs = [
            "AI startup trends trong năm 2024?",
            "Tôi có data từ Reddit về SaaS tools, có thể phân tích không?",
            "Tạo ý tưởng startup trong lĩnh vực fintech",
            "Xin chào, bạn có thể làm gì?"
        ]
        
        for test_input in test_inputs:
            print(f"\nInput: {test_input}")
            response = await process_user_message(test_input)
            print(f"Response: {response.content[:200]}...")
            print(f"Type: {response.response_type}")
    
    asyncio.run(test())
