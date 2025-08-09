"""
Adversarial Expert LLM Agent - Tác nhân chuyên gia đối kháng trong hệ thống MCTS
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from enum import Enum

from .base_agent import BaseAgent, AgentInput, AgentOutput
from backend.config import MCTSConfig, ADVERSARIAL_ROLE_MAPPING

logger = logging.getLogger(__name__)

class AdversarialRole(Enum):
    """Các vai trò đối kháng"""
    VC = "VC"
    ENGINEER = "Kỹ_sư"  
    COMPETITOR = "Đối_thủ"
    MARKETING = "Marketing"
    LEGAL = "Pháp_lý"

@dataclass
class AdversarialAttackTask:
    """Task cho cuộc tấn công đối kháng"""
    content_to_attack: str
    content_type: str  # "analysis" hoặc "ideas"
    active_roles: List[AdversarialRole]
    attack_intensity: str = "aggressive"  # "mild", "moderate", "aggressive"
    iteration: int = 1

@dataclass
class VulnerabilityAssessment:
    """Đánh giá điểm yếu"""
    category: str
    severity: str  # "low", "medium", "high", "critical"
    description: str
    evidence: List[str]
    potential_impact: str
    mitigation_suggestions: List[str]

class AdversarialExpertAgent(BaseAgent):
    """
    Adversarial Expert Agent - "Red Team" tấn công ý tưởng
    """
    
    def __init__(self, config: MCTSConfig, llm_client):
        super().__init__("adversarial", config, llm_client)
        self.role_mapping = ADVERSARIAL_ROLE_MAPPING
        self.active_roles: Set[AdversarialRole] = set()
        
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """
        Main processing method cho Adversarial Expert Agent
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
            
            # Process adversarial attack
            if isinstance(agent_input.data, AdversarialAttackTask):
                return await self._process_adversarial_attack(agent_input)
            else:
                # Fallback: treat as raw content to attack
                return await self._process_raw_content(agent_input)
                
        except Exception as e:
            logger.error(f"Error in AdversarialExpertAgent.process: {str(e)}")
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=str(e)
            )
    
    async def _process_adversarial_attack(self, agent_input: AgentInput) -> AgentOutput:
        """Thực hiện cuộc tấn công đối kháng"""
        task: AdversarialAttackTask = agent_input.data
        
        # Set active roles
        self.active_roles = set(task.active_roles)
        
        # Tạo prompt tấn công
        attack_prompt = self._build_adversarial_attack_prompt(task, agent_input)
        
        # Gọi LLM với temperature cao để khuyến khích aggressive thinking
        temperature = self._get_temperature_by_intensity(task.attack_intensity)
        
        llm_response = await self._make_llm_call(
            user_message=attack_prompt,
            temperature=temperature,
            use_conversation_history=task.iteration > 1
        )
        
        if not llm_response.success:
            return self._create_agent_output(
                content="",
                success=False,
                agent_input=agent_input,
                error=llm_response.error
            )
        
        # Parse vulnerabilities
        vulnerabilities = await self._parse_vulnerabilities(llm_response.content)
        
        # Post-process output
        processed_output = await self.post_process_output(llm_response, agent_input)
        
        return self._create_agent_output(
            content=processed_output,
            success=True,
            agent_input=agent_input,
            metadata={
                "content_type": task.content_type,
                "active_roles": [role.value for role in task.active_roles],
                "attack_intensity": task.attack_intensity,
                "vulnerabilities_found": len(vulnerabilities),
                "vulnerabilities": vulnerabilities,
                "token_usage": llm_response.usage
            }
        )
    
    async def _process_raw_content(self, agent_input: AgentInput) -> AgentOutput:
        """Xử lý raw content - fallback method"""
        content = str(agent_input.data)
        
        # Guess content type
        content_type = self._guess_content_type(content)
        
        # Use default roles based on content type
        default_roles = self._get_default_roles(content_type)
        
        # Tạo adversarial attack task
        attack_task = AdversarialAttackTask(
            content_to_attack=content,
            content_type=content_type,
            active_roles=default_roles,
            attack_intensity="moderate",
            iteration=agent_input.iteration
        )
        
        # Tạo new agent input
        new_input = AgentInput(
            data=attack_task,
            context=agent_input.context,
            metadata=agent_input.metadata,
            iteration=agent_input.iteration
        )
        
        return await self._process_adversarial_attack(new_input)
    
    def _guess_content_type(self, content: str) -> str:
        """Đoán loại content dựa trên nội dung"""
        content_lower = content.lower()
        
        # Keywords cho ideas
        idea_keywords = ["ý tưởng", "startup", "mô hình kinh doanh", "revenue", "mvp", "target audience", "competitive advantage"]
        
        # Keywords cho analysis  
        analysis_keywords = ["xu hướng", "phân tích", "dữ liệu", "painpoint", "insight", "thị trường"]
        
        idea_score = sum(1 for keyword in idea_keywords if keyword in content_lower)
        analysis_score = sum(1 for keyword in analysis_keywords if keyword in content_lower)
        
        return "ideas" if idea_score > analysis_score else "analysis"
    
    def _get_default_roles(self, content_type: str) -> List[AdversarialRole]:
        """Lấy các role mặc định theo loại content"""
        if content_type == "ideas":
            return [AdversarialRole.VC, AdversarialRole.COMPETITOR, AdversarialRole.ENGINEER]
        else:  # analysis
            return [AdversarialRole.VC, AdversarialRole.ENGINEER]
    
    def _get_temperature_by_intensity(self, intensity: str) -> float:
        """Lấy temperature theo mức độ tấn công"""
        intensity_mapping = {
            "mild": 0.3,
            "moderate": 0.6,
            "aggressive": 0.9
        }
        return intensity_mapping.get(intensity, 0.6)
    
    def _build_adversarial_attack_prompt(self, 
                                       task: AdversarialAttackTask,
                                       agent_input: AgentInput) -> str:
        """Xây dựng prompt cho cuộc tấn công đối kháng"""
        
        # Build roles section
        roles_section = self._build_roles_section(task.active_roles, task.attack_intensity)
        
        # Build attack scenarios
        scenarios_section = self._build_attack_scenarios(task.content_type)
        
        prompt = f"""
# NHIỆM VỤ TẤN CÔNG ĐỐI KHÁNG - VÒNG {task.iteration}

## NỘI DUNG CẦN TẤN CÔNG

**Loại nội dung:** {task.content_type.upper()}
**Mức độ tấn công:** {task.attack_intensity.upper()}

**Nội dung:**
```
{task.content_to_attack}
```

## VAI TRÒ ĐANG KÍCH HOẠT

{roles_section}

## KỊCH BẢN TẤN CÔNG

{scenarios_section}

## YÊU CẦU CỤ THỂ

{"### ĐÂY LÀ VÒNG TẤN CÔNG SỐ " + str(task.iteration) + " - HÃY TẤN CÔNG SÂU HƠN VÀ TÌM RA CÁC LỖ HỔNG TINH VI" if task.iteration > 1 else ""}

Thực hiện cuộc tấn công đối kháng **{task.attack_intensity.upper()}** theo đúng format trong system prompt.

**Nhiệm vụ chính:**
1. **TẤN CÔNG TỪNG VAI TRÒ** - Mỗi persona attack từ góc độ riêng
2. **TÌM RA ĐIỂM YẾU CHÍ MẠNG** - Critical flaws có thể giết chết ý tưởng
3. **STRESS TESTING** - Đưa ra worst-case scenarios
4. **THÁCH THỨC TRỰC TIẾP** - Đặt câu hỏi khó trả lời
5. **REALISTIC SCENARIOS** - Dựa trên kinh nghiệm thực tế

**Intensity Level: {task.attack_intensity.upper()}**
{"- Tấn công nhẹ nhàng, constructive feedback" if task.attack_intensity == "mild" else ""}
{"- Tấn công vừa phải, cân bằng giữa aggressive và constructive" if task.attack_intensity == "moderate" else ""}
{"- Tấn công mạnh mẽ, no mercy, tìm ra mọi weakness" if task.attack_intensity == "aggressive" else ""}

**Chú ý đặc biệt:**
- Mỗi role phải có perspective riêng biệt
- Đưa ra evidence và examples cụ thể
- Scenarios phải realistic và có thể xảy ra
- Focus vào actionable weaknesses
- Maintain professional tone dù aggressive

## NGỮ CẢNH BỔ SUNG
{json.dumps(agent_input.context, ensure_ascii=False, indent=2) if agent_input.context else "Không có ngữ cảnh bổ sung"}

🔥 BẮT ĐẦU CUỘC TẤN CÔNG NGAY BÂY GIỜ! 🔥
"""
        
        return prompt.strip()
    
    def _build_roles_section(self, active_roles: List[AdversarialRole], intensity: str) -> str:
        """Xây dựng section mô tả các vai trò"""
        
        role_descriptions = {
            AdversarialRole.VC: f"""
### 🏦 NHÀ ĐẦU TƯ MẠAO HIỂM (VC)
**Mindset:** Hoài nghi cực độ, đã thấy hàng ngàn pitch thất bại
**Câu thần chú:** "Tại sao tôi nên rót 1 triệu đô vào ý tưởng này thay vì 10 ý tưởng khác?"
**Attack vectors:**
- Market size có thực sự tồn tại?
- Unit economics có make sense?
- Team có track record gì?
- Exit strategy là gì?
- Tại sao không invest vào competitor đã có traction?
""",
            
            AdversarialRole.ENGINEER: f"""
### 🔧 KỸ SƯ TRƯỞNG (LEAD ENGINEER)  
**Mindset:** Perfectionist, lo ngại technical debt, prioritize stability
**Câu thần chú:** "Bạn sẽ xây dựng cái này trên nền tảng nào? Nó có chịu được 1 triệu user đồng thời không?"
**Attack vectors:**
- System architecture có scale được?
- Security vulnerabilities?
- Technical feasibility thực tế?
- Development timeline có realistic?
- Maintenance và technical debt?
""",
            
            AdversarialRole.COMPETITOR: f"""
### ⚔️ ĐỐI THỦ CẠNH TRANH (COMPETITOR)
**Mindset:** Aggressive, strategic, sẵn sàng copy và cải tiến
**Câu thần chú:** "Tôi có thể sao chép tính năng cốt lõi của bạn trong 1 tháng. Lợi thế phòng thủ của bạn là gì?"
**Attack vectors:**
- Differentiation có thực sự unique?
- Network effects hay switching costs?
- Tôi có thể làm miễn phí + ads
- Tôi có team 50 engineers, bạn compete sao?
- Patent/IP protection?
""",
            
            AdversarialRole.MARKETING: f"""
### 📈 CHUYÊN GIA MARKETING
**Mindset:** Skeptical về user adoption, hiểu customer psychology  
**Câu thần chú:** "Customers nói họ muốn X nhưng họ actually pay cho Y"
**Attack vectors:**
- Customer acquisition strategy realistic?
- Brand positioning có differentiated?
- Messaging có resonate với target audience?
- Competitor có stronger brand presence?
""",
            
            AdversarialRole.LEGAL: f"""
### ⚖️ CHUYÊN GIA PHÁP LÝ
**Mindset:** Risk-averse, focus on compliance và liability
**Câu thần chú:** "Lawsuit này có thể giết chết startup trong 6 tháng"
**Attack vectors:**
- Regulatory compliance requirements?
- IP infringement risks?
- Data privacy và GDPR?
- Liability và insurance needs?
"""
        }
        
        sections = []
        for role in active_roles:
            if role in role_descriptions:
                sections.append(role_descriptions[role])
        
        return "\n".join(sections)
    
    def _build_attack_scenarios(self, content_type: str) -> str:
        """Xây dựng các kịch bản tấn công"""
        
        if content_type == "ideas":
            return """
### 📋 SCENARIOS TESTING

#### Scenario 1: Big Tech Enters
**Tình huống:** Google/Meta/Amazon launch competing product với unlimited resources
**Questions:** Startup sẽ làm gì? Có survive được không?

#### Scenario 2: Economic Downturn  
**Tình huống:** Recession, funding winter, customers cắt budget 50%
**Questions:** Revenue drop, có survive được 12 tháng không?

#### Scenario 3: Technical Crisis
**Tình huống:** Major security breach, system failure, PR nightmare
**Questions:** Crisis management plan? Customer trust recovery?

#### Scenario 4: Key Person Risk
**Tình huống:** Founder/CTO rời khỏi công ty
**Questions:** Business có continue được không? Knowledge transfer?

#### Scenario 5: Market Saturation
**Tình huống:** 10 competitors enter cùng lúc với similar solutions
**Questions:** Differentiation strategy? Price war survival?
"""
        else:  # analysis
            return """
### 📋 SCENARIOS TESTING

#### Scenario 1: Data Bias
**Tình huống:** Dữ liệu phân tích bị bias hoặc không representative
**Questions:** Kết luận có còn valid? Alternative explanations?

#### Scenario 2: Market Shift
**Tình huống:** Market conditions thay đổi dramatically
**Questions:** Phân tích có còn relevant? Adaptability?

#### Scenario 3: Methodology Flaws
**Tình huống:** Phương pháp phân tích có fundamental flaws
**Questions:** Reliability của insights? Cross-validation?

#### Scenario 4: Competitive Intelligence
**Tình huống:** Competitors có access same data và insights
**Questions:** First-mover advantage? Unique perspective?

#### Scenario 5: Implementation Gap
**Tình huống:** Gap giữa insights và practical implementation
**Questions:** Actionability? Resource requirements?
"""
    
    async def _parse_vulnerabilities(self, content: str) -> List[VulnerabilityAssessment]:
        """Parse và extract vulnerabilities từ output"""
        
        vulnerabilities = []
        
        try:
            # Patterns để tìm vulnerabilities
            vulnerability_patterns = [
                r"ĐIỂM YẾU CHÍ MẠNG.*?:(.*?)(?=ĐIỂM YẾU|$)",
                r"Critical.*?:(.*?)(?=Major|Warning|$)",
                r"🔴.*?:(.*?)(?=🟡|🟠|$)"
            ]
            
            for pattern in vulnerability_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                
                for match in matches:
                    # Extract details from vulnerability description
                    lines = match.strip().split('\n')
                    
                    vulnerability = VulnerabilityAssessment(
                        category="critical",
                        severity="high",
                        description=lines[0] if lines else match[:100],
                        evidence=[],
                        potential_impact="",
                        mitigation_suggestions=[]
                    )
                    
                    # Parse details từ lines
                    for line in lines[1:]:
                        line = line.strip()
                        if line.startswith("- "):
                            vulnerability.evidence.append(line[2:])
                        elif "impact:" in line.lower():
                            vulnerability.potential_impact = line.split(":", 1)[1].strip()
                        elif "suggest" in line.lower() or "recommend" in line.lower():
                            vulnerability.mitigation_suggestions.append(line)
                    
                    vulnerabilities.append(vulnerability)
            
            # Limit to top vulnerabilities
            return vulnerabilities[:10]
            
        except Exception as e:
            logger.warning(f"Error parsing vulnerabilities: {str(e)}")
            return []
    
    async def validate_input(self, agent_input: AgentInput) -> bool:
        """Validate input cho Adversarial Expert Agent"""
        
        if not await super().validate_input(agent_input):
            return False
        
        data = agent_input.data
        
        if isinstance(data, AdversarialAttackTask):
            if not data.content_to_attack.strip():
                logger.error("AdversarialAttackTask must have content_to_attack")
                return False
            if data.content_type not in ["analysis", "ideas"]:
                logger.error("AdversarialAttackTask content_type must be 'analysis' or 'ideas'")
                return False
            if not data.active_roles:
                logger.error("AdversarialAttackTask must have active_roles")
                return False
            if data.attack_intensity not in ["mild", "moderate", "aggressive"]:
                logger.error("AdversarialAttackTask attack_intensity must be valid")
                return False
        
        return True
    
    async def post_process_output(self, llm_response, agent_input: AgentInput) -> str:
        """Post-process output từ LLM"""
        
        content = llm_response.content
        
        # Add metadata header
        task = agent_input.data if isinstance(agent_input.data, AdversarialAttackTask) else None
        active_roles = [role.value for role in task.active_roles] if task else []
        
        metadata_header = f"""
<!-- METADATA -->
Agent: AdversarialExpertAgent
Active_Roles: {', '.join(active_roles)}
Attack_Intensity: {task.attack_intensity if task else 'unknown'}
Iteration: {agent_input.iteration}
Timestamp: {agent_input.metadata.get('timestamp', 'unknown')}
Attack_Mode: Red_Team
<!-- END METADATA -->

"""
        
        return metadata_header + content
    
    def get_vulnerability_summary(self, vulnerabilities: List[VulnerabilityAssessment]) -> Dict[str, Any]:
        """Tạo summary của vulnerabilities"""
        
        if not vulnerabilities:
            return {
                "total_count": 0,
                "critical_count": 0,
                "severity_distribution": {},
                "top_categories": []
            }
        
        severity_count = {}
        category_count = {}
        
        for vuln in vulnerabilities:
            severity_count[vuln.severity] = severity_count.get(vuln.severity, 0) + 1
            category_count[vuln.category] = category_count.get(vuln.category, 0) + 1
        
        return {
            "total_count": len(vulnerabilities),
            "critical_count": sum(1 for v in vulnerabilities if v.severity in ["critical", "high"]),
            "severity_distribution": severity_count,
            "top_categories": sorted(category_count.items(), key=lambda x: x[1], reverse=True)[:5]
        }

# Helper functions
def create_adversarial_attack_task(content_to_attack: str,
                                 content_type: str,
                                 active_roles: List[AdversarialRole],
                                 attack_intensity: str = "moderate",
                                 iteration: int = 1) -> AdversarialAttackTask:
    """Helper để tạo AdversarialAttackTask"""
    return AdversarialAttackTask(
        content_to_attack=content_to_attack,
        content_type=content_type,
        active_roles=active_roles,
        attack_intensity=attack_intensity,
        iteration=iteration
    )

def get_role_from_string(role_str: str) -> Optional[AdversarialRole]:
    """Convert string to AdversarialRole"""
    role_mapping = {
        "vc": AdversarialRole.VC,
        "kỹ_sư": AdversarialRole.ENGINEER,
        "engineer": AdversarialRole.ENGINEER,
        "đối_thủ": AdversarialRole.COMPETITOR,
        "competitor": AdversarialRole.COMPETITOR,
        "marketing": AdversarialRole.MARKETING,
        "pháp_lý": AdversarialRole.LEGAL,
        "legal": AdversarialRole.LEGAL
    }
    
    return role_mapping.get(role_str.lower())
