"""
Critical Thinking LLM Agent - Tác nhân tư duy phản biện trong hệ thống MCTS
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .base_agent import BaseAgent, AgentInput, AgentOutput
from config import MCTSConfig, EVALUATION_CRITERIA

logger = logging.getLogger(__name__)

@dataclass
class CriticalAnalysisTask:
    """Task cho phân tích phản biện"""
    content_to_analyze: str
    content_type: str  # "analysis" hoặc "ideas"  
    focus_areas: List[str]
    iteration: int = 1

@dataclass
class CriticalScore:
    """Điểm đánh giá chi tiết"""
    criterion: str
    score: int  # 1-10
    reasoning: str
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]

class CriticalThinkingAgent(BaseAgent):
    """
    Critical Thinking Agent - Đánh giá logic và chất lượng
    """
    
    def __init__(self, config: MCTSConfig, llm_client):
        super().__init__("critical_thinking", config, llm_client)
        self.evaluation_criteria = EVALUATION_CRITERIA
        
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """
        Main processing method cho Critical Thinking Agent
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
            
            # Process critical analysis
            if isinstance(agent_input.data, CriticalAnalysisTask):
                return await self._process_critical_analysis(agent_input)
            else:
                # Fallback: treat as raw content
                return await self._process_raw_content(agent_input)
                
        except Exception as e:
            logger.error(f"Error in CriticalThinkingAgent.process: {str(e)}")
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=str(e)
            )
    
    async def _process_critical_analysis(self, agent_input: AgentInput) -> AgentOutput:
        """Thực hiện phân tích phản biện"""
        task: CriticalAnalysisTask = agent_input.data
        
        # Xác định tiêu chí đánh giá
        criteria = self._get_evaluation_criteria(task.content_type)
        
        # Tạo prompt phân tích phản biện
        analysis_prompt = self._build_critical_analysis_prompt(task, criteria, agent_input)
        
        # Gọi LLM với temperature thấp để đảm bảo tính chính xác
        llm_response = await self._make_llm_call(
            user_message=analysis_prompt,
            temperature=0.2,  # Rất thấp để đảm bảo đánh giá khách quan
            use_conversation_history=task.iteration > 1
        )
        
        if not llm_response.success:
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=llm_response.error
            )
        
        # Parse và structured output
        structured_analysis = await self._parse_critical_analysis(
            llm_response.content, criteria
        )
        
        # Post-process output
        processed_output = await self.post_process_output(llm_response, agent_input)
        
        return self._create_agent_output(
            content=processed_output,
            success=True,
            agent_input=agent_input,
            metadata={
                "content_type": task.content_type,
                "criteria_count": len(criteria),
                "focus_areas": task.focus_areas,
                "structured_scores": structured_analysis,
                "token_usage": llm_response.usage
            }
        )
    
    async def _process_raw_content(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý raw content - fallback method"""
        content = str(agent_input.data)
        
        # Guess content type based on content
        content_type = self._guess_content_type(content)
        
        # Tạo critical analysis task
        analysis_task = CriticalAnalysisTask(
            content_to_analyze=content,
            content_type=content_type,
            focus_areas=["general_quality"],
            iteration=agent_input.iteration
        )
        
        # Tạo new agent input
        new_input = AgentInput(
            data=analysis_task,
            context=agent_input.context,
            metadata=agent_input.metadata,
            iteration=agent_input.iteration
        )
        
        return await self._process_critical_analysis(new_input)
    
    def _get_evaluation_criteria(self, content_type: str) -> List[str]:
        """Lấy tiêu chí đánh giá theo loại content"""
        return self.evaluation_criteria.get(content_type, self.evaluation_criteria["analysis"])
    
    def _guess_content_type(self, content: str) -> str:
        """Đoán loại content dựa trên nội dung"""
        content_lower = content.lower()
        
        # Keywords cho ideas
        idea_keywords = ["ý tưởng", "startup", "mô hình kinh doanh", "revenue", "mvp", "target audience"]
        
        # Keywords cho analysis  
        analysis_keywords = ["xu hướng", "phân tích", "dữ liệu", "painpoint", "insight"]
        
        idea_score = sum(1 for keyword in idea_keywords if keyword in content_lower)
        analysis_score = sum(1 for keyword in analysis_keywords if keyword in content_lower)
        
        return "ideas" if idea_score > analysis_score else "analysis"
    
    def _build_critical_analysis_prompt(self, 
                                       task: CriticalAnalysisTask,
                                       criteria: List[str], 
                                       agent_input: AgentInput) -> str:
        """Xây dựng prompt cho phân tích phản biện"""
        
        criteria_details = self._get_criteria_details(criteria, task.content_type)
        
        prompt = f"""
# NHIỆM VỤ PHÂN TÍCH PHẢN BIỆN - VÒNG {task.iteration}

## NỘI DUNG CẦN ĐÁNH GIÁ

**Loại nội dung:** {task.content_type.upper()}

**Nội dung:**
```
{task.content_to_analyze}
```

## TIÊU CHÍ ĐÁNH GIÁ

{criteria_details}

## LĨnh VỰC TẬP TRUNG
{chr(10).join(f"- {area}" for area in task.focus_areas)}

## YÊU CẦU CỤ THỂ

{"### ĐÂY LÀ VÒNG ĐÁNH GIÁ SỐ " + str(task.iteration) + " - HÃY PHÂN TÍCH SÂU HƠN DỰA TRÊN CẢI THIỆN TRƯỚC" if task.iteration > 1 else ""}

Hãy thực hiện đánh giá phản biện NGHIÊM NGẶT theo đúng format đã quy định trong system prompt.

**Nguyên tắc đánh giá:**
1. **KHÁCH QUAN TUYỆT ĐỐI** - Không thiên vị
2. **CONSTRUCTIVE CRITICISM** - Phê phán để xây dựng
3. **CHI TIẾT VÀ CỤ THỂ** - Đưa ra ví dụ minh họa
4. **ACTIONABLE FEEDBACK** - Gợi ý cải thiện thực tế
5. **PHÁT HIỆN LỖ HỔNG** - Tìm ra các weak points

**Lưu ý đặc biệt:**
- Đánh giá mỗi tiêu chí từ 1-10 với lý do cụ thể
- Chỉ ra cả điểm mạnh và điểm yếu
- Đặt câu hỏi phản biện sâu sắc
- Đề xuất cải thiện có thể thực hiện được

## NGỮ CẢNH BỔ SUNG
{json.dumps(agent_input.context, ensure_ascii=False, indent=2) if agent_input.context else "Không có ngữ cảnh bổ sung"}

Bắt đầu đánh giá phản biện ngay bây giờ:
"""
        
        return prompt.strip()
    
    def _get_criteria_details(self, criteria: List[str], content_type: str) -> str:
        """Lấy chi tiết các tiêu chí đánh giá"""
        
        # Mapping tiêu chí và mô tả
        criteria_mapping = {
            # Cho Analysis
            "tinh_logic": "**Tính Logic (1-10):** Chuỗi suy luận có hợp lý? Kết luận có xuất phát từ tiền đề? Có fallacy logic nào?",
            "toan_dien": "**Tính Toàn diện (1-10):** Đã xem xét đủ góc độ? Có missing link? Phạm vi có đầy đủ?",
            "nhat_quan": "**Tính Nhất quán (1-10):** Các phần có mâu thuẫn? Tone có thống nhất? Kết luận có hỗ trợ lẫn nhau?",
            "bang_chung": "**Chất lượng Bằng chứng (1-10):** Dữ liệu có tin cậy? Sample size đủ lớn? Có bias trong thu thập?",
            "do_sau": "**Độ Sâu (1-10):** Phân tích có chi tiết? Hiểu context? Xem xét tác động phụ?",
            
            # Cho Ideas
            "tinh_kha_thi": "**Tính Khả thi (1-10):** Khả thi kỹ thuật và tài chính? Timeline realistic?",
            "tiem_nang_thi_truong": "**Tiềm năng Thị trường (1-10):** Market size và timing? Demand thực sự?",
            "tinh_sang_tao": "**Tính Sáng tạo (1-10):** Độ độc đáo? Innovation level? Differentiation?",
            "mo_hinh_kinh_doanh": "**Mô hình Kinh doanh (1-10):** Revenue streams bền vững? Scalability?",
            "loi_the_canh_tranh": "**Lợi thế Cạnh tranh (1-10):** Competitive advantage mạnh? Moat building?",
            "rui_ro_ky_thuat": "**Rủi ro Kỹ thuật (1-10):** Technical complexity? Implementation risks?",
            "dau_tu_ban_dau": "**Đầu tư Ban đầu (1-10):** Capital requirements reasonable? Resource needs?"
        }
        
        details = []
        for criterion in criteria:
            if criterion in criteria_mapping:
                details.append(criteria_mapping[criterion])
            else:
                details.append(f"**{criterion.title()} (1-10):** Đánh giá tổng quát về {criterion}")
        
        return "\n".join(details)
    
    async def _parse_critical_analysis(self, 
                                     content: str, 
                                     criteria: List[str]) -> Dict[str, Any]:
        """Parse và structured critical analysis output"""
        
        structured = {
            "overall_score": 0.0,
            "criteria_scores": {},
            "critical_issues": [],
            "improvement_suggestions": [],
            "questions_raised": []
        }
        
        try:
            # Extract scores using regex
            for criterion in criteria:
                pattern = rf"{criterion}.*?(\d+)/10"
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    score = int(match.group(1))
                    structured["criteria_scores"][criterion] = score
            
            # Calculate overall score
            if structured["criteria_scores"]:
                structured["overall_score"] = sum(structured["criteria_scores"].values()) / len(structured["criteria_scores"])
            
            # Extract critical issues (look for sections with red flags)
            critical_patterns = [
                r"vấn đề.*?:\s*([^\.]+)",
                r"thiếu sót.*?:\s*([^\.]+)",
                r"lỗ hổng.*?:\s*([^\.]+)"
            ]
            
            for pattern in critical_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                structured["critical_issues"].extend([match.strip() for match in matches])
            
            # Extract improvement suggestions
            suggestion_patterns = [
                r"đề xuất.*?:\s*([^\.]+)",
                r"cải thiện.*?:\s*([^\.]+)",
                r"khuyến nghị.*?:\s*([^\.]+)"
            ]
            
            for pattern in suggestion_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                structured["improvement_suggestions"].extend([match.strip() for match in matches])
            
            # Extract questions
            question_patterns = [
                r"\?[^?]*\?",
                r"tại sao.*?\?",
                r"làm sao.*?\?"
            ]
            
            for pattern in question_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                structured["questions_raised"].extend([match.strip() for match in matches])
            
        except Exception as e:
            logger.warning(f"Error parsing critical analysis: {str(e)}")
        
        return structured
    
    async def validate_input(self, agent_input: AgentInput) -> bool:
        """Validate input cho Critical Thinking Agent"""
        
        if not await super().validate_input(agent_input):
            return False
        
        data = agent_input.data
        
        if isinstance(data, CriticalAnalysisTask):
            if not data.content_to_analyze.strip():
                logger.error("CriticalAnalysisTask must have content_to_analyze")
                return False
            if data.content_type not in ["analysis", "ideas"]:
                logger.error("CriticalAnalysisTask content_type must be 'analysis' or 'ideas'")
                return False
            if not data.focus_areas:
                logger.error("CriticalAnalysisTask must have focus_areas")
                return False
        
        return True
    
    async def post_process_output(self, llm_response, agent_input: AgentInput) -> str:
        """Post-process output từ LLM"""
        
        content = llm_response.content
        
        # Add metadata header
        task = agent_input.data if isinstance(agent_input.data, CriticalAnalysisTask) else None
        content_type = task.content_type if task else "unknown"
        
        metadata_header = f"""
<!-- METADATA -->
Agent: CriticalThinkingAgent
Content_Type: {content_type}
Iteration: {agent_input.iteration}
Timestamp: {agent_input.metadata.get('timestamp', 'unknown')}
Evaluation_Mode: Critical_Analysis
<!-- END METADATA -->

"""
        
        return metadata_header + content
    
    def get_quick_assessment(self, content: str, content_type: str = "analysis") -> Dict[str, Any]:
        """
        Lấy đánh giá nhanh không cần gọi LLM
        Useful cho real-time feedback
        """
        
        assessment = {
            "content_length": len(content),
            "word_count": len(content.split()),
            "has_data": bool(re.search(r'\d+%|\d+\s*(triệu|tỷ|nghìn)', content)),
            "has_examples": bool(re.search(r'ví dụ|minh họa|chẳng hạn', content, re.IGNORECASE)),
            "has_conclusions": bool(re.search(r'kết luận|tóm lại|do đó', content, re.IGNORECASE)),
            "potential_issues": []
        }
        
        # Check for potential issues
        if assessment["word_count"] < 100:
            assessment["potential_issues"].append("Nội dung quá ngắn")
        
        if not assessment["has_data"]:
            assessment["potential_issues"].append("Thiếu dữ liệu cụ thể")
        
        if not assessment["has_examples"]:
            assessment["potential_issues"].append("Thiếu ví dụ minh họa")
        
        if content_type == "ideas" and "mvp" not in content.lower():
            assessment["potential_issues"].append("Không đề cập đến MVP")
        
        return assessment

# Helper functions
def create_critical_analysis_task(content_to_analyze: str,
                                content_type: str,
                                focus_areas: List[str],
                                iteration: int = 1) -> CriticalAnalysisTask:
    """Helper để tạo CriticalAnalysisTask"""
    return CriticalAnalysisTask(
        content_to_analyze=content_to_analyze,
        content_type=content_type,
        focus_areas=focus_areas,
        iteration=iteration
    )
