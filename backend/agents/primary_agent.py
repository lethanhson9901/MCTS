"""
Primary LLM Agent - Tác nhân thực thi chính trong hệ thống MCTS
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .base_agent import BaseAgent, AgentInput, AgentOutput
from config import MCTSConfig

logger = logging.getLogger(__name__)

@dataclass
class AnalysisTask:
    """Cấu trúc cho task phân tích"""
    data_sources: List[Dict[str, Any]]
    timeframe: Dict[str, str]  # {"start": "2024-01-01", "end": "2024-01-31"}
    focus_areas: List[str]
    iteration: int = 1

@dataclass
class IdeaGenerationTask:
    """Cấu trúc cho task tạo ý tưởng"""
    analysis_results: str
    feedback_from_ct: Optional[str] = None
    feedback_from_ae: Optional[str] = None
    target_count: int = 5
    iteration: int = 1

class PrimaryAgent(BaseAgent):
    """
    Primary LLM Agent - Tác nhân chính thực hiện phân tích và tạo ý tưởng
    """
    
    def __init__(self, config: MCTSConfig, llm_client):
        super().__init__("primary", config, llm_client)
        self.current_phase = "analysis"  # "analysis" hoặc "idea_generation"
        self.analysis_results = ""
        
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """
        Main processing method cho Primary Agent
        """
        try:
            # Validate input
            if not await self.validate_input(agent_input):
                return self._create_agent_output(
                    content="",
                    success=False,
                    agent_input=agent_input,
                    error="Invalid input"
                )
            
            # Determine task type và process
            if isinstance(agent_input.data, AnalysisTask):
                return await self._process_analysis_task(agent_input)
            elif isinstance(agent_input.data, IdeaGenerationTask):
                return await self._process_idea_generation_task(agent_input)
            else:
                # Fallback: treat as raw data for analysis
                return await self._process_raw_data(agent_input)
                
        except Exception as e:
            logger.error(f"Error in PrimaryAgent.process: {str(e)}")
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=str(e)
            )
    
    async def _process_analysis_task(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý task phân tích dữ liệu"""
        task: AnalysisTask = agent_input.data
        self.current_phase = "analysis"
        
        # Tạo prompt cho phân tích
        analysis_prompt = self._build_analysis_prompt(task, agent_input)
        
        # Gọi LLM với temperature thấp hơn cho phân tích
        llm_response = await self._make_llm_call(
            user_message=analysis_prompt,
            temperature=0.3,  # Thấp hơn để đảm bảo tính chính xác
            use_conversation_history=task.iteration > 1
        )
        
        if not llm_response.success:
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=llm_response.error
            )
        
        # Post-process analysis results
        processed_output = await self.post_process_output(llm_response, agent_input)
        self.analysis_results = processed_output
        
        return self._create_agent_output(
            content=processed_output,
            success=True,
            agent_input=agent_input,
            metadata={
                "phase": "analysis",
                "data_sources_count": len(task.data_sources),
                "focus_areas": task.focus_areas,
                "token_usage": llm_response.usage
            }
        )
    
    async def _process_idea_generation_task(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý task tạo ý tưởng"""
        task: IdeaGenerationTask = agent_input.data
        self.current_phase = "idea_generation"
        
        # Tạo prompt cho việc tạo ý tưởng
        idea_prompt = self._build_idea_generation_prompt(task, agent_input)
        
        # Gọi LLM với temperature cao hơn cho creativity
        llm_response = await self._make_llm_call(
            user_message=idea_prompt,
            temperature=0.8,  # Cao hơn để khuyến khích sáng tạo
            use_conversation_history=task.iteration > 1
        )
        
        if not llm_response.success:
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=llm_response.error
            )
        
        # Post-process idea generation results
        processed_output = await self.post_process_output(llm_response, agent_input)
        
        return self._create_agent_output(
            content=processed_output,
            success=True,
            agent_input=agent_input,
            metadata={
                "phase": "idea_generation",
                "target_count": task.target_count,
                "has_ct_feedback": task.feedback_from_ct is not None,
                "has_ae_feedback": task.feedback_from_ae is not None,
                "token_usage": llm_response.usage
            }
        )
    
    async def _process_raw_data(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý raw data - fallback method"""
        raw_data = agent_input.data
        
        # Convert raw data thành analysis task
        analysis_task = AnalysisTask(
            data_sources=[{"type": "raw", "content": str(raw_data)}],
            timeframe={"start": "unknown", "end": "unknown"},
            focus_areas=["general_analysis"],
            iteration=agent_input.iteration
        )
        
        # Tạo new agent input với analysis task
        new_input = AgentInput(
            data=analysis_task,
            context=agent_input.context,
            metadata=agent_input.metadata,
            iteration=agent_input.iteration
        )
        
        return await self._process_analysis_task(new_input)
    
    def _build_analysis_prompt(self, task: AnalysisTask, agent_input: AgentInput) -> str:
        """Xây dựng prompt cho phân tích"""
        
        # Chuẩn bị thông tin về data sources
        sources_info = []
        for i, source in enumerate(task.data_sources):
            source_type = source.get("type", "unknown")
            source_desc = source.get("description", "Không có mô tả")
            content_preview = str(source.get("content", ""))[:500]  # Preview 500 chars
            
            sources_info.append(f"""
### Nguồn {i+1}: {source_type.upper()}
**Mô tả:** {source_desc}
**Nội dung (preview):**
{content_preview}{'...' if len(str(source.get("content", ""))) > 500 else ''}
""")
        
        # Xây dựng prompt chính
        prompt = f"""
# NHIỆM VỤ PHÂN TÍCH DỮ LIỆU - VÒNG {task.iteration}

## THÔNG TIN ĐẦU VÀO

### Khoảng thời gian phân tích:
- Từ ngày: {task.timeframe.get('start', 'Không xác định')}
- Đến ngày: {task.timeframe.get('end', 'Không xác định')}

### Lĩnh vực tập trung:
{chr(10).join(f"- {area}" for area in task.focus_areas)}

### Dữ liệu cần phân tích:
{''.join(sources_info)}

## YÊU CẦU CỤ THỂ

{"### ĐÂY LÀ VÒNG LẶP SỐ " + str(task.iteration) + " - HÃY CẢI THIỆN PHÂN TÍCH DỰA TRÊN PHẢN HỒI TRƯỚC" if task.iteration > 1 else ""}

Hãy thực hiện phân tích tổng hợp theo đúng format đã quy định trong system prompt của bạn.

**Chú ý đặc biệt:**
1. Phát hiện các xu hướng nổi bật và pain points thực sự của người dùng
2. Tìm ra những điểm giao thoa hoặc mâu thuẫn giữa các nguồn dữ liệu
3. Đưa ra những insight sâu sắc, không chỉ tóm tắt bề mặt
4. Cung cấp bằng chứng cụ thể cho mỗi kết luận
5. Đề xuất hướng phân tích cho vòng tiếp theo (nếu cần)

## NGỮ CẢNH BỔ SUNG
{json.dumps(agent_input.context, ensure_ascii=False, indent=2) if agent_input.context else "Không có ngữ cảnh bổ sung"}

Bắt đầu phân tích ngay bây giờ:
"""
        
        return prompt.strip()
    
    def _build_idea_generation_prompt(self, task: IdeaGenerationTask, agent_input: AgentInput) -> str:
        """Xây dựng prompt cho tạo ý tưởng"""
        
        feedback_section = ""
        if task.feedback_from_ct or task.feedback_from_ae:
            feedback_section = f"""
## PHẢN HỒI CẦN XỬ LÝ

{"### Phản hồi từ CT-LLM (Tư duy Phản biện):" if task.feedback_from_ct else ""}
{task.feedback_from_ct if task.feedback_from_ct else ""}

{"### Phản hồi từ AE-LLM (Chuyên gia Đối kháng):" if task.feedback_from_ae else ""}
{task.feedback_from_ae if task.feedback_from_ae else ""}

**Yêu cầu:** Hãy giải quyết tất cả các thách thức và cải thiện ý tưởng dựa trên phản hồi trên.
"""
        
        prompt = f"""
# NHIỆM VỤ TẠO Ý TƯỞNG STARTUP - VÒNG {task.iteration}

## CƠ SỞ PHÂN TÍCH
{task.analysis_results}

{feedback_section}

## YÊU CẦU CỤ THỂ

{"### ĐÂY LÀ VÒNG CẢI THIỆN SỐ " + str(task.iteration) + " - HÃY PHÁT TRIỂN VÀ GIA CỐ CÁC Ý TƯỞNG" if task.iteration > 1 else ""}

Dựa trên phân tích trên, hãy tạo ra **{task.target_count} ý tưởng startup** chất lượng cao theo đúng format trong system prompt.

**Tiêu chí ưu tiên:**
1. **Tính khả thi cao** - Có thể triển khai với tài nguyên hạn chế
2. **Giải quyết pain points thực sự** - Dựa trên dữ liệu phân tích
3. **Mô hình kinh doanh rõ ràng** - Revenue streams cụ thể
4. **Lợi thế cạnh tranh mạnh** - Khó bị sao chép
5. **Tiềm năng thị trường lớn** - Scalable và sustainable

**Yêu cầu đặc biệt:**
- Mỗi ý tưởng phải có roadmap chi tiết
- Ước tính đầu tư và timeline realistic  
- Phân tích rủi ro và mitigation strategies
- Competitive analysis cụ thể với tên competitors

## NGỮ CẢNH BỔ SUNG
{json.dumps(agent_input.context, ensure_ascii=False, indent=2) if agent_input.context else "Không có ngữ cảnh bổ sung"}

Bắt đầu tạo ý tưởng ngay bây giờ:
"""
        
        return prompt.strip()
    
    async def validate_input(self, agent_input: AgentInput) -> bool:
        """Validate input cho Primary Agent"""
        
        if not await super().validate_input(agent_input):
            return False
        
        # Kiểm tra data type specific
        data = agent_input.data
        
        if isinstance(data, AnalysisTask):
            if not data.data_sources:
                logger.error("AnalysisTask must have data_sources")
                return False
            if not data.timeframe:
                logger.error("AnalysisTask must have timeframe") 
                return False
                
        elif isinstance(data, IdeaGenerationTask):
            if not data.analysis_results:
                logger.error("IdeaGenerationTask must have analysis_results")
                return False
            if data.target_count <= 0:
                logger.error("IdeaGenerationTask must have positive target_count")
                return False
        
        return True
    
    async def post_process_output(self, llm_response, agent_input: AgentInput) -> str:
        """Post-process output từ LLM"""
        
        content = llm_response.content
        
        # Add metadata header
        metadata_header = f"""
<!-- METADATA -->
Phase: {self.current_phase}
Iteration: {agent_input.iteration}
Timestamp: {agent_input.metadata.get('timestamp', 'unknown')}
Agent: PrimaryAgent
<!-- END METADATA -->

"""
        
        return metadata_header + content
    
    def get_current_analysis(self) -> str:
        """Lấy kết quả phân tích hiện tại"""
        return self.analysis_results
    
    def set_phase(self, phase: str):
        """Set phase hiện tại"""
        if phase in ["analysis", "idea_generation"]:
            self.current_phase = phase
            logger.info(f"PrimaryAgent phase set to: {phase}")
        else:
            logger.warning(f"Invalid phase: {phase}")

# Helper functions
def create_analysis_task(data_sources: List[Dict[str, Any]],
                        timeframe: Dict[str, str],
                        focus_areas: List[str],
                        iteration: int = 1) -> AnalysisTask:
    """Helper để tạo AnalysisTask"""
    return AnalysisTask(
        data_sources=data_sources,
        timeframe=timeframe,
        focus_areas=focus_areas,
        iteration=iteration
    )

def create_idea_generation_task(analysis_results: str,
                              target_count: int = 5,
                              feedback_from_ct: Optional[str] = None,
                              feedback_from_ae: Optional[str] = None,
                              iteration: int = 1) -> IdeaGenerationTask:
    """Helper để tạo IdeaGenerationTask"""
    return IdeaGenerationTask(
        analysis_results=analysis_results,
        target_count=target_count,
        feedback_from_ct=feedback_from_ct,
        feedback_from_ae=feedback_from_ae,
        iteration=iteration
    )
