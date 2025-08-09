"""
Synthesis & Assessment LLM Agent - Tác nhân tổng hợp và đánh giá trong hệ thống MCTS
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from .base_agent import BaseAgent, AgentInput, AgentOutput
from config import MCTSConfig, AgentWeights, EVALUATION_CRITERIA

logger = logging.getLogger(__name__)

@dataclass
class SynthesisTask:
    """Task cho việc tổng hợp và đánh giá"""
    primary_output: str
    ct_feedback: Optional[str] = None
    ae_feedback: Optional[str] = None
    esv_results: Optional[Dict[str, Any]] = None
    phase: str = "analysis"  # "analysis" hoặc "ideas"
    iteration: int = 1

@dataclass
class LoopDecision:
    """Quyết định cho vòng lặp tiếp theo"""
    action: str  # "continue", "stop", "user_checkpoint"
    reasoning: str
    next_round_instructions: Optional[Dict[str, Any]] = None
    user_checkpoint_info: Optional[Dict[str, Any]] = None
    quality_metrics: Optional[Dict[str, Any]] = None

@dataclass
class QualityScore:
    """Điểm chất lượng chi tiết"""
    criterion: str
    raw_score: float
    weight: float
    weighted_score: float
    red_flag: bool
    reasoning: str

class SynthesisAssessmentAgent(BaseAgent):
    """
    Synthesis & Assessment Agent - Giám đốc dự án, người đưa ra quyết định
    """
    
    def __init__(self, config: MCTSConfig, llm_client):
        super().__init__("synthesis", config, llm_client)
        self.weights = config.weights
        self.quality_threshold = config.quality_threshold
        self.improvement_threshold = config.improvement_threshold
        self.red_flag_threshold = config.red_flag_threshold
        
        # Tracking metrics
        self.iteration_scores: List[float] = []
        self.iteration_decisions: List[LoopDecision] = []
        
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """
        Main processing method cho Synthesis Assessment Agent
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
            
            # Process synthesis task
            if isinstance(agent_input.data, SynthesisTask):
                return await self._process_synthesis_task(agent_input)
            else:
                # Fallback: treat as raw content for basic assessment
                return await self._process_raw_content(agent_input)
                
        except Exception as e:
            logger.error(f"Error in SynthesisAssessmentAgent.process: {str(e)}")
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=str(e)
            )
    
    async def _process_synthesis_task(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý task tổng hợp và đánh giá"""
        task: SynthesisTask = agent_input.data
        
        # Tạo prompt tổng hợp
        synthesis_prompt = self._build_synthesis_prompt(task, agent_input)
        
        # Gọi LLM với temperature thấp để đảm bảo objectivity
        llm_response = await self._make_llm_call(
            user_message=synthesis_prompt,
            temperature=0.1,  # Rất thấp để đảm bảo consistent decision making
            use_conversation_history=task.iteration > 1
        )
        
        if not llm_response.success:
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=llm_response.error
            )
        
        # Parse quality scores và metrics
        quality_scores = await self._parse_quality_scores(
            llm_response.content, task.phase
        )
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(quality_scores)
        
        # Determine loop decision
        loop_decision = await self._determine_loop_decision(
            task, overall_score, quality_scores, agent_input
        )
        
        # Update tracking
        self.iteration_scores.append(overall_score)
        self.iteration_decisions.append(loop_decision)
        
        # Post-process output
        processed_output = await self.post_process_output(llm_response, agent_input)
        
        return self._create_agent_output(
            content=processed_output,
            success=True,
            agent_input=agent_input,
            metadata={
                "phase": task.phase,
                "overall_score": overall_score,
                "quality_scores": [score.__dict__ for score in quality_scores],
                "loop_decision": loop_decision.__dict__,
                "esv_activated": task.esv_results is not None,
                "token_usage": llm_response.usage
            }
        )
    
    async def _process_raw_content(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý raw content - fallback method"""
        content = str(agent_input.data)
        
        # Create basic synthesis task
        synthesis_task = SynthesisTask(
            primary_output=content,
            phase="analysis",  # Default to analysis
            iteration=agent_input.iteration
        )
        
        # Create new agent input
        new_input = AgentInput(
            data=synthesis_task,
            context=agent_input.context,
            metadata=agent_input.metadata,
            iteration=agent_input.iteration
        )
        
        return await self._process_synthesis_task(new_input)
    
    def _build_synthesis_prompt(self, 
                               task: SynthesisTask,
                               agent_input: AgentInput) -> str:
        """Xây dựng prompt cho tổng hợp và đánh giá"""
        
        # Build input analysis section
        input_analysis = self._build_input_analysis_section(task)
        
        # Build scoring framework
        scoring_framework = self._build_scoring_framework(task.phase)
        
        # Build ESV results section
        esv_section = self._build_esv_section(task.esv_results) if task.esv_results else ""
        
        # Build decision logic
        decision_logic = self._build_decision_logic_section()

        # Diversity analysis (nếu có)
        diversity_context = ""
        idea_diversity = agent_input.context.get("idea_diversity_analysis")
        if idea_diversity:
            diversity_context = f"""
## DIVERSITY CONTEXT (Ý tưởng)

- Ideas: {idea_diversity.get('ideas_count')}
- Diversity Score: {idea_diversity.get('diversity_score')}
- Unique Audiences: {idea_diversity.get('unique_audiences')}
- Unique Business Models: {idea_diversity.get('unique_business_models')}
- Unique Techs: {idea_diversity.get('unique_techs')}
- Duplicates: {len(idea_diversity.get('duplicates', []))}
"""
        
        prompt = f"""
# NHIỆM VỤ TỔNG HỢP & ĐÁNH GIÁ - VÒNG {task.iteration}

## THÔNG TIN ĐẦU VÀO

### Phase hiện tại: {task.phase.upper()}

{input_analysis}

{esv_section}

{diversity_context}

## FRAMEWORK ĐIỂM SỐ

{scoring_framework}

## LOGIC QUYẾT ĐỊNH

{decision_logic}

## YÊU CẦU CỤ THỂ

{"### ĐÂY LÀ VÒNG ĐÁNH GIÁ SỐ " + str(task.iteration) + " - HÃY SO SÁNH VỚI CÁC VÒNG TRƯỚC VÀ TÍNH IMPROVEMENT RATE" if task.iteration > 1 else ""}

Thực hiện tổng hợp và đánh giá TOÀN DIỆN theo đúng format trong system prompt.

**Nhiệm vụ chính:**
1. **PHÂN TÍCH INPUT** - Đánh giá output từ tất cả các agents
2. **TÍNH ĐIỂM CHẤT LƯỢNG** - Áp dụng hệ thống scoring có trọng số
3. **XÁC ĐỊNH CỜ ĐỎ** - Identify critical issues
4. **GIẢI QUYẾT CONFLICTS** - Reconcile disagreements giữa agents
5. **QUYẾT ĐỊNH VÒNG LẶP** - Continue/Stop/User_Checkpoint
6. **ĐƯA RA HƯỚNG DẪN** - Instructions for next round

**Trọng số hiện tại:**
{self._format_weights()}

**Ngưỡng quyết định:**
- Quality threshold: {self.quality_threshold}/10
- Improvement threshold: {self.improvement_threshold}% (5%)
- Red flag threshold: <{self.red_flag_threshold}/10

**Chú ý đặc biệt:**
- Đánh giá objective và data-driven
- Balance giữa quality và efficiency
- Consider user experience và feedback
- Focus on actionable outcomes
- Maintain high standards nhưng realistic

## NGỮ CẢNH BỔ SUNG
{json.dumps(agent_input.context, ensure_ascii=False, indent=2) if agent_input.context else "Không có ngữ cảnh bổ sung"}

Bắt đầu tổng hợp và đánh giá ngay bây giờ:
"""
        
        return prompt.strip()
    
    def _build_input_analysis_section(self, task: SynthesisTask) -> str:
        """Xây dựng section phân tích input"""
        
        sections = []
        
        # Primary output
        sections.append(f"""
### 📄 OUTPUT TỪ PRIMARY LLM
**Độ dài:** {len(task.primary_output)} ký tự
**Preview:**
```
{task.primary_output[:500]}{'...' if len(task.primary_output) > 500 else ''}
```
""")
        
        # CT feedback
        if task.ct_feedback:
            sections.append(f"""
### 🧠 PHẢN HỒI TỪ CT-LLM (Tư duy Phản biện)
**Độ dài:** {len(task.ct_feedback)} ký tự
**Preview:**
```
{task.ct_feedback[:500]}{'...' if len(task.ct_feedback) > 500 else ''}
```
""")
        else:
            sections.append("### 🧠 PHẢN HỒI TỪ CT-LLM: Không có")
        
        # AE feedback
        if task.ae_feedback:
            sections.append(f"""
### ⚔️ PHẢN HỒI TỪ AE-LLM (Chuyên gia Đối kháng)
**Độ dài:** {len(task.ae_feedback)} ký tự  
**Preview:**
```
{task.ae_feedback[:500]}{'...' if len(task.ae_feedback) > 500 else ''}
```
""")
        else:
            sections.append("### ⚔️ PHẢN HỒI TỪ AE-LLM: Không có")
        
        return "\n".join(sections)
    
    def _build_esv_section(self, esv_results: Dict[str, Any]) -> str:
        """Xây dựng section ESV results"""
        
        if not esv_results:
            return ""
        
        queries = esv_results.get("queries", [])
        summary = esv_results.get("summary", {})
        
        section = f"""
## 🌐 KẾT QUẢ XÁC THỰC NGOÀI (ESV)

### Queries đã thực hiện:
{chr(10).join(f"- {query}" for query in queries)}

### Tóm tắt validation:
- Confirmed claims: {summary.get('confirmed', 0)}
- Refuted claims: {summary.get('refuted', 0)}  
- New information: {summary.get('new_info', 'Không có')}

### Impact lên đánh giá:
{esv_results.get('impact', 'Cần phân tích trong synthesis')}
"""
        
        return section
    
    def _build_scoring_framework(self, phase: str) -> str:
        """Xây dựng framework điểm số"""
        
        criteria = EVALUATION_CRITERIA.get(phase, EVALUATION_CRITERIA["analysis"])
        weights_dict = self.weights.__dict__
        
        framework = f"""
### TIÊU CHÍ ĐÁNH GIÁ CHO {phase.upper()}:

| Tiêu chí | Trọng số | Mô tả |
|----------|----------|-------|"""
        
        # Map criteria to weights và descriptions
        criteria_mapping = {
            "tinh_logic": ("Tính Logic", "Chuỗi suy luận hợp lý, tránh fallacy"),
            "toan_dien": ("Tính Toàn diện", "Phạm vi phân tích đầy đủ"),
            "nhat_quan": ("Tính Nhất quán", "Thống nhất nội tại"),
            "bang_chung": ("Chất lượng Bằng chứng", "Độ tin cậy của data"),
            "do_sau": ("Độ Sâu", "Chi tiết và hiểu biết context"),
            "tinh_kha_thi": ("Tính Khả thi", "Khả thi kỹ thuật và tài chính"),
            "tiem_nang_thi_truong": ("Tiềm năng Thị trường", "Market size và timing"),
            "tinh_sang_tao": ("Tính Sáng tạo", "Độ độc đáo và innovation"),
            "mo_hinh_kinh_doanh": ("Mô hình Kinh doanh", "Revenue streams bền vững"),
            "loi_the_canh_tranh": ("Lợi thế Cạnh tranh", "Differentiation mạnh"),
            "rui_ro_ky_thuat": ("Rủi ro Kỹ thuật", "Technical complexity và risks"),
            "dau_tu_ban_dau": ("Đầu tư Ban đầu", "Capital requirements")
        }
        
        for criterion in criteria:
            if criterion in criteria_mapping:
                name, desc = criteria_mapping[criterion]
                weight = getattr(self.weights, criterion, 1.0)
                framework += f"\n| {name} | {weight} | {desc} |"
        
        framework += f"""

### CÔNG THỨC TÍNH ĐIỂM:
```
Weighted_Score = Σ(Individual_Score × Weight) / Σ(Weights)
Red_Flag = ANY individual score < {self.red_flag_threshold}
```
"""
        
        return framework
    
    def _build_decision_logic_section(self) -> str:
        """Xây dựng section logic quyết định"""
        
        return f"""
### TIÊU CHÍ DỪNG:

1. **CHẤT LƯỢNG HỘI TỤ:** Score ≥ {self.quality_threshold} AND No Red Flags
2. **GIẢM DẦN CẢI THIỆN:** Improvement < {self.improvement_threshold}% for 2 rounds  
3. **GIỚI HẠN TÀI NGUYÊN:** Đạt max loops
4. **CHỈ ĐẠO NGƯỜI DÙNG:** User decision

### KÍCH HOẠT USER CHECKPOINT:
- Score improvement < 10% trong 1 vòng
- Có Red Flags nghiêm trọng  
- Conflict lớn giữa agents
- Strategic decision cần input
"""
    
    def _format_weights(self) -> str:
        """Format weights để hiển thị"""
        weights_dict = self.weights.__dict__
        return "\n".join(f"- {key}: {value}" for key, value in weights_dict.items())
    
    async def _parse_quality_scores(self, 
                                  content: str, 
                                  phase: str) -> List[QualityScore]:
        """Parse quality scores từ LLM output"""
        
        scores = []
        criteria = EVALUATION_CRITERIA.get(phase, EVALUATION_CRITERIA["analysis"])
        
        try:
            # Look for scoring table in content
            table_pattern = r"\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|"
            matches = re.findall(table_pattern, content)
            
            for match in matches:
                if len(match) >= 4:
                    criterion_text = match[0].strip()
                    score_text = match[1].strip()
                    
                    # Extract score
                    score_match = re.search(r"(\d+)", score_text)
                    if score_match:
                        raw_score = float(score_match.group(1))
                        
                        # Find matching criterion
                        for criterion in criteria:
                            if criterion in criterion_text.lower() or criterion.replace("_", " ") in criterion_text.lower():
                                weight = getattr(self.weights, criterion, 1.0)
                                weighted_score = raw_score * weight
                                red_flag = raw_score < self.red_flag_threshold
                                
                                scores.append(QualityScore(
                                    criterion=criterion,
                                    raw_score=raw_score,
                                    weight=weight,
                                    weighted_score=weighted_score,
                                    red_flag=red_flag,
                                    reasoning=match[2].strip() if len(match) > 2 else ""
                                ))
                                break
            
            # If no scores found, create default scores
            if not scores:
                logger.warning("No quality scores found, creating defaults")
                for criterion in criteria:
                    weight = getattr(self.weights, criterion, 1.0)
                    scores.append(QualityScore(
                        criterion=criterion,
                        raw_score=5.0,  # Default middle score
                        weight=weight,
                        weighted_score=5.0 * weight,
                        red_flag=True,  # Flag as questionable
                        reasoning="Could not parse from output"
                    ))
        
        except Exception as e:
            logger.error(f"Error parsing quality scores: {str(e)}")
        
        return scores
    
    def _calculate_overall_score(self, quality_scores: List[QualityScore]) -> float:
        """Tính toán điểm tổng thể"""
        
        if not quality_scores:
            return 0.0
        
        total_weighted = sum(score.weighted_score for score in quality_scores)
        total_weights = sum(score.weight for score in quality_scores)
        
        return total_weighted / total_weights if total_weights > 0 else 0.0
    
    async def _determine_loop_decision(self, 
                                     task: SynthesisTask,
                                     overall_score: float,
                                     quality_scores: List[QualityScore],
                                     agent_input: AgentInput) -> LoopDecision:
        """Xác định quyết định cho vòng lặp tiếp theo"""
        
        # Check red flags
        red_flags = [score for score in quality_scores if score.red_flag]
        has_critical_red_flags = len(red_flags) > 0
        
        # Check quality threshold
        quality_achieved = overall_score >= self.quality_threshold and not has_critical_red_flags
        
        # Check improvement rate
        improvement_rate = self._calculate_improvement_rate()
        diminishing_returns = improvement_rate < self.improvement_threshold if improvement_rate is not None else False
        
        # Check resource limits (would need to be passed in context)
        max_loops = agent_input.context.get("max_loops", 10)
        resource_limit_reached = task.iteration >= max_loops
        
        # Decision logic
        if quality_achieved:
            return LoopDecision(
                action="stop",
                reasoning=f"Quality threshold achieved: {overall_score:.2f} ≥ {self.quality_threshold}, no red flags",
                quality_metrics={
                    "overall_score": overall_score,
                    "red_flags_count": len(red_flags),
                    "improvement_rate": improvement_rate
                }
            )
        
        elif resource_limit_reached:
            return LoopDecision(
                action="stop",
                reasoning=f"Resource limit reached: {task.iteration} ≥ {max_loops}",
                quality_metrics={
                    "overall_score": overall_score,
                    "red_flags_count": len(red_flags),
                    "improvement_rate": improvement_rate
                }
            )
        
        elif diminishing_returns and task.iteration > 2:
            return LoopDecision(
                action="user_checkpoint",
                reasoning=f"Diminishing returns detected: improvement rate {improvement_rate:.1f}% < {self.improvement_threshold}%",
                user_checkpoint_info={
                    "situation": "Low improvement rate",
                    "options": [
                        "Continue with current approach",
                        "Change strategy/focus",
                        "Stop and proceed to next phase"
                    ],
                    "recommendation": "Consider changing approach"
                },
                quality_metrics={
                    "overall_score": overall_score,
                    "red_flags_count": len(red_flags),
                    "improvement_rate": improvement_rate
                }
            )
        
        elif len(red_flags) > 3:
            return LoopDecision(
                action="user_checkpoint",
                reasoning=f"Too many red flags detected: {len(red_flags)} critical issues",
                user_checkpoint_info={
                    "situation": "Multiple critical issues",
                    "options": [
                        "Address red flags and continue",
                        "Lower quality standards",
                        "Stop and accept current quality"
                    ],
                    "recommendation": "Address critical issues first"
                },
                quality_metrics={
                    "overall_score": overall_score,
                    "red_flags_count": len(red_flags),
                    "improvement_rate": improvement_rate
                }
            )
        
        else:
            # Continue with improvements
            next_instructions = self._generate_next_round_instructions(
                task, quality_scores, red_flags
            )
            
            return LoopDecision(
                action="continue",
                reasoning=f"Continue improving: score {overall_score:.2f} < {self.quality_threshold}, can improve further",
                next_round_instructions=next_instructions,
                quality_metrics={
                    "overall_score": overall_score,
                    "red_flags_count": len(red_flags),
                    "improvement_rate": improvement_rate
                }
            )
    
    def _calculate_improvement_rate(self) -> Optional[float]:
        """Tính tỷ lệ cải thiện so với vòng trước"""
        
        if len(self.iteration_scores) < 2:
            return None
        
        current_score = self.iteration_scores[-1]
        previous_score = self.iteration_scores[-2]
        
        if previous_score == 0:
            return None
        
        improvement = ((current_score - previous_score) / previous_score) * 100
        return improvement
    
    def _generate_next_round_instructions(self, 
                                        task: SynthesisTask,
                                        quality_scores: List[QualityScore],
                                        red_flags: List[QualityScore]) -> Dict[str, Any]:
        """Tạo hướng dẫn cho vòng tiếp theo"""
        
        instructions = {
            "primary_llm": {
                "priority_actions": [],
                "specific_improvements": [],
                "questions_to_address": [],
                "diversity_actions": []
            },
            "ct_llm": {
                "focus_areas": [],
                "deep_dive_topics": []
            },
            "ae_llm": {
                "attack_vectors": [],
                "role_priority": []
            }
        }
        
        # Analyze weak areas
        weak_criteria = [score for score in quality_scores if score.raw_score < 6.0]
        
        for weak_criterion in weak_criteria:
            criterion = weak_criterion.criterion
            
            if criterion in ["tinh_logic", "nhat_quan"]:
                instructions["primary_llm"]["specific_improvements"].append(
                    f"Improve {criterion}: ensure logical consistency"
                )
                instructions["ct_llm"]["focus_areas"].append(criterion)
            
            elif criterion in ["tinh_kha_thi", "mo_hinh_kinh_doanh"]:
                instructions["ae_llm"]["attack_vectors"].append(
                    f"Challenge {criterion} assumptions"
                )
                instructions["ae_llm"]["role_priority"].append("VC")
        
        # Add red flag specific instructions
        for red_flag in red_flags:
            instructions["primary_llm"]["priority_actions"].append(
                f"URGENT: Address {red_flag.criterion} (score: {red_flag.raw_score})"
            )

        # Nếu ở phase ideas, thêm chỉ dẫn đa dạng hóa dựa trên diversity score
        if task.phase == "ideas":
            diversity = agent_input.context.get("idea_diversity_analysis", {})
            div_score = float(diversity.get("diversity_score", 1.0))
            duplicates = diversity.get("duplicates", [])
            if div_score < 0.7:
                instructions["primary_llm"]["diversity_actions"].append(
                    "Tạo thêm 2 ý tưởng khác biệt rõ rệt về khách hàng mục tiêu hoặc mô hình kinh doanh."
                )
            if duplicates:
                instructions["primary_llm"]["diversity_actions"].append(
                    f"Tách/gộp hoặc chỉnh sửa các cặp ý tưởng trùng lặp: {duplicates[:3]}"
                )
        
        return instructions
    
    async def validate_input(self, agent_input: AgentInput) -> bool:
        """Validate input cho Synthesis Assessment Agent"""
        
        if not await super().validate_input(agent_input):
            return False
        
        data = agent_input.data
        
        if isinstance(data, SynthesisTask):
            if not data.primary_output.strip():
                logger.error("SynthesisTask must have primary_output")
                return False
            if data.phase not in ["analysis", "ideas"]:
                logger.error("SynthesisTask phase must be 'analysis' or 'ideas'")
                return False
        
        return True
    
    async def post_process_output(self, llm_response, agent_input: AgentInput) -> str:
        """Post-process output từ LLM"""
        
        content = llm_response.content
        
        # Add comprehensive metadata
        task = agent_input.data if isinstance(agent_input.data, SynthesisTask) else None
        
        metadata_header = f"""
<!-- METADATA -->
Agent: SynthesisAssessmentAgent
Phase: {task.phase if task else 'unknown'}
Iteration: {agent_input.iteration}
Timestamp: {agent_input.metadata.get('timestamp', 'unknown')}
Overall_Score: {self.iteration_scores[-1] if self.iteration_scores else 'N/A'}
Decision: {self.iteration_decisions[-1].action if self.iteration_decisions else 'N/A'}
Synthesis_Mode: Comprehensive_Assessment
<!-- END METADATA -->

"""
        
        return metadata_header + content
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Lấy tóm tắt performance qua các vòng lặp"""
        
        return {
            "total_iterations": len(self.iteration_scores),
            "scores_progression": self.iteration_scores,
            "final_score": self.iteration_scores[-1] if self.iteration_scores else 0,
            "best_score": max(self.iteration_scores) if self.iteration_scores else 0,
            "improvement_trend": self._calculate_improvement_rate(),
            "decisions_made": [d.action for d in self.iteration_decisions],
            "quality_achieved": self.iteration_scores[-1] >= self.quality_threshold if self.iteration_scores else False
        }
    
    def reset_tracking(self):
        """Reset tracking metrics"""
        self.iteration_scores = []
        self.iteration_decisions = []
        logger.info("Reset SynthesisAssessmentAgent tracking metrics")

# Helper functions
def create_synthesis_task(primary_output: str,
                         phase: str = "analysis",
                         ct_feedback: Optional[str] = None,
                         ae_feedback: Optional[str] = None,
                         esv_results: Optional[Dict[str, Any]] = None,
                         iteration: int = 1) -> SynthesisTask:
    """Helper để tạo SynthesisTask"""
    return SynthesisTask(
        primary_output=primary_output,
        ct_feedback=ct_feedback,
        ae_feedback=ae_feedback,
        esv_results=esv_results,
        phase=phase,
        iteration=iteration
    )
