"""
Scoring System - Hệ thống điểm số và Red Flag cho MCTS
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from backend.config import AgentWeights, EVALUATION_CRITERIA

logger = logging.getLogger(__name__)

class ScoreType(Enum):
    """Loại điểm số"""
    ANALYSIS = "analysis"
    IDEAS = "ideas"

class RedFlagSeverity(Enum):
    """Mức độ nghiêm trọng của Red Flag"""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class IndividualScore:
    """Điểm số cho một tiêu chí cụ thể"""
    criterion: str
    raw_score: float  # 1-10
    weight: float
    weighted_score: float
    max_possible: float  # weight * 10
    percentage: float  # (weighted_score / max_possible) * 100
    reasoning: str = ""
    evidence: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class RedFlag:
    """Cờ đỏ - điểm yếu chí mạng"""
    criterion: str
    severity: RedFlagSeverity
    description: str
    impact: str
    score: float
    threshold: float
    mitigation_suggestions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class CompositeScore:
    """Điểm số tổng hợp"""
    score_type: ScoreType
    individual_scores: List[IndividualScore]
    total_weighted_score: float
    total_possible_score: float
    final_score: float  # 0-10 scale
    percentage: float  # 0-100%
    red_flags: List[RedFlag]
    quality_grade: str  # A+, A, B+, B, C+, C, D, F
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

class ScoringSystem:
    """
    Hệ thống điểm số cho MCTS
    """
    
    def __init__(self, weights: AgentWeights, red_flag_threshold: float = 3.0):
        self.weights = weights
        self.red_flag_threshold = red_flag_threshold
        self.evaluation_criteria = EVALUATION_CRITERIA
        
        # Grade thresholds
        self.grade_thresholds = {
            "A+": 9.5,
            "A": 9.0,
            "A-": 8.5,
            "B+": 8.0,
            "B": 7.0,
            "B-": 6.5,
            "C+": 6.0,
            "C": 5.0,
            "C-": 4.0,
            "D": 3.0,
            "F": 0.0
        }
        
        # Red flag severity thresholds
        self.red_flag_severity_thresholds = {
            RedFlagSeverity.CRITICAL: 2.0,
            RedFlagSeverity.HIGH: 2.5,
            RedFlagSeverity.MEDIUM: 3.0,
            RedFlagSeverity.LOW: 3.5
        }
    
    def calculate_score(self, 
                       scores_data: Dict[str, float],
                       score_type: ScoreType,
                       reasoning_data: Optional[Dict[str, str]] = None,
                       evidence_data: Optional[Dict[str, List[str]]] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> CompositeScore:
        """
        Tính toán điểm số tổng hợp
        
        Args:
            scores_data: Dict mapping criterion -> raw score (1-10)
            score_type: ANALYSIS hoặc IDEAS
            reasoning_data: Dict mapping criterion -> reasoning text
            evidence_data: Dict mapping criterion -> list of evidence
            metadata: Additional metadata
        
        Returns:
            CompositeScore object
        """
        
        try:
            # Get criteria for this score type
            criteria = self.evaluation_criteria.get(score_type.value, [])
            
            # Calculate individual scores
            individual_scores = []
            red_flags = []
            
            for criterion in criteria:
                raw_score = scores_data.get(criterion, 5.0)  # Default to 5.0 if missing
                weight = self._get_weight_for_criterion(criterion)
                
                # Calculate weighted score
                weighted_score = raw_score * weight
                max_possible = 10.0 * weight
                percentage = (weighted_score / max_possible) * 100 if max_possible > 0 else 0
                
                # Create individual score
                individual_score = IndividualScore(
                    criterion=criterion,
                    raw_score=raw_score,
                    weight=weight,
                    weighted_score=weighted_score,
                    max_possible=max_possible,
                    percentage=percentage,
                    reasoning=reasoning_data.get(criterion, "") if reasoning_data else "",
                    evidence=evidence_data.get(criterion, []) if evidence_data else []
                )
                
                individual_scores.append(individual_score)
                
                # Check for red flags
                if raw_score < self.red_flag_threshold:
                    red_flag = self._create_red_flag(criterion, raw_score, weight)
                    red_flags.append(red_flag)
            
            # Calculate composite score
            total_weighted = sum(score.weighted_score for score in individual_scores)
            total_possible = sum(score.max_possible for score in individual_scores)
            
            final_score = (total_weighted / total_possible) * 10 if total_possible > 0 else 0
            percentage = (total_weighted / total_possible) * 100 if total_possible > 0 else 0
            
            # Determine quality grade
            quality_grade = self._determine_grade(final_score)
            
            # Create composite score
            composite_score = CompositeScore(
                score_type=score_type,
                individual_scores=individual_scores,
                total_weighted_score=total_weighted,
                total_possible_score=total_possible,
                final_score=final_score,
                percentage=percentage,
                red_flags=red_flags,
                quality_grade=quality_grade,
                metadata=metadata or {},
                timestamp=datetime.now()
            )
            
            logger.info(f"Calculated {score_type.value} score: {final_score:.2f} ({quality_grade})")
            return composite_score
            
        except Exception as e:
            logger.error(f"Error calculating score: {str(e)}")
            raise
    
    def _get_weight_for_criterion(self, criterion: str) -> float:
        """Lấy trọng số cho một tiêu chí"""
        
        weight = getattr(self.weights, criterion, None)
        if weight is not None:
            return float(weight)
        
        # Default weights nếu không tìm thấy
        default_weights = {
            "tinh_logic": 2.0,
            "toan_dien": 1.8,
            "nhat_quan": 1.5,
            "bang_chung": 2.2,
            "do_sau": 1.5,
            "tinh_kha_thi": 2.0,
            "tiem_nang_thi_truong": 2.5,
            "tinh_sang_tao": 1.5,
            "mo_hinh_kinh_doanh": 2.0,
            "loi_the_canh_tranh": 1.8,
            "rui_ro_ky_thuat": 1.5,
            "dau_tu_ban_dau": 1.2
        }
        
        return default_weights.get(criterion, 1.0)
    
    def _create_red_flag(self, criterion: str, score: float, weight: float) -> RedFlag:
        """Tạo Red Flag cho criterion có điểm thấp"""
        
        # Determine severity
        severity = RedFlagSeverity.MEDIUM  # Default
        for sev, threshold in self.red_flag_severity_thresholds.items():
            if score <= threshold:
                severity = sev
                break
        
        # Create description và impact
        descriptions = {
            "tinh_logic": "Lập luận thiếu logic hoặc có fallacy nghiêm trọng",
            "toan_dien": "Phân tích thiếu góc nhìn quan trọng hoặc bỏ sót yếu tố chính",
            "nhat_quan": "Các phần mâu thuẫn nhau hoặc không thống nhất",
            "bang_chung": "Thiếu bằng chứng cụ thể hoặc dữ liệu không đáng tin cậy",
            "do_sau": "Phân tích nông cạn, thiếu chi tiết và insight",
            "tinh_kha_thi": "Ý tưởng khó khả thi về mặt kỹ thuật hoặc tài chính",
            "tiem_nang_thi_truong": "Thị trường quá nhỏ hoặc timing không phù hợp",
            "tinh_sang_tao": "Ý tưởng thiếu sáng tạo hoặc quá generic",
            "mo_hinh_kinh_doanh": "Mô hình kinh doanh không bền vững hoặc không rõ ràng",
            "loi_the_canh_tranh": "Thiếu competitive advantage hoặc dễ bị copy",
            "rui_ro_ky_thuat": "Rủi ro kỹ thuật quá cao hoặc phức tạp",
            "dau_tu_ban_dau": "Cần vốn đầu tư quá lớn so với potential return"
        }
        
        impacts = {
            "tinh_logic": "Có thể dẫn đến sai lầm trong decision making",
            "toan_dien": "Bỏ sót cơ hội hoặc rủi ro quan trọng",
            "nhat_quan": "Gây confusion và giảm credibility",
            "bang_chung": "Kết luận không đáng tin cậy",
            "do_sau": "Thiếu insight để ra quyết định đúng",
            "tinh_kha_thi": "Startup có thể thất bại trong execution",
            "tiem_nang_thi_truong": "Khó đạt được scale và profitability",
            "tinh_sang_tao": "Dễ bị competitors vượt mặt",
            "mo_hinh_kinh_doanh": "Khó raise funding và achieve sustainability",
            "loi_the_canh_tranh": "Dễ bị competitors copy và thay thế",
            "rui_ro_ky_thuat": "Có thể gặp technical failure hoặc delay",
            "dau_tu_ban_dau": "Khó raise funding hoặc ROI thấp"
        }
        
        # Mitigation suggestions
        mitigations = {
            "tinh_logic": [
                "Review và strengthen logical reasoning",
                "Eliminate fallacies và inconsistencies",
                "Add more structured argumentation"
            ],
            "toan_dien": [
                "Conduct more comprehensive analysis",
                "Consider additional perspectives",
                "Expand scope of investigation"
            ],
            "nhat_quan": [
                "Reconcile contradictions",
                "Ensure consistent messaging",
                "Align all parts of analysis"
            ],
            "bang_chung": [
                "Gather more reliable data sources",
                "Add quantitative evidence",
                "Verify information accuracy"
            ],
            "do_sau": [
                "Conduct deeper research",
                "Add more detailed analysis",
                "Provide more insights và implications"
            ],
            "tinh_kha_thi": [
                "Reassess technical requirements",
                "Consider simpler implementation approaches",
                "Validate assumptions with experts"
            ],
            "tiem_nang_thi_truong": [
                "Research market size more thoroughly",
                "Consider alternative market segments",
                "Validate market timing assumptions"
            ],
            "tinh_sang_tao": [
                "Add unique differentiators",
                "Explore innovative approaches",
                "Combine existing solutions creatively"
            ],
            "mo_hinh_kinh_doanh": [
                "Clarify revenue streams",
                "Validate unit economics",
                "Test business model assumptions"
            ],
            "loi_the_canh_tranh": [
                "Develop stronger moats",
                "Build network effects",
                "Create switching costs"
            ],
            "rui_ro_ky_thuat": [
                "Simplify technical approach",
                "Build prototypes to validate",
                "Plan for technical contingencies"
            ],
            "dau_tu_ban_dau": [
                "Reduce initial capital requirements",
                "Consider phased approach",
                "Explore alternative funding sources"
            ]
        }
        
        return RedFlag(
            criterion=criterion,
            severity=severity,
            description=descriptions.get(criterion, f"Điểm {criterion} quá thấp"),
            impact=impacts.get(criterion, "Có thể ảnh hưởng đến chất lượng tổng thể"),
            score=score,
            threshold=self.red_flag_threshold,
            mitigation_suggestions=mitigations.get(criterion, ["Cần cải thiện điểm này"]),
            timestamp=datetime.now()
        )
    
    def _determine_grade(self, score: float) -> str:
        """Xác định grade dựa trên điểm số"""
        
        for grade, threshold in self.grade_thresholds.items():
            if score >= threshold:
                return grade
        
        return "F"
    
    def compare_scores(self, score1: CompositeScore, score2: CompositeScore) -> Dict[str, Any]:
        """So sánh 2 composite scores"""
        
        comparison = {
            "score_improvement": score2.final_score - score1.final_score,
            "percentage_improvement": score2.percentage - score1.percentage,
            "grade_change": f"{score1.quality_grade} → {score2.quality_grade}",
            "red_flags_change": len(score2.red_flags) - len(score1.red_flags),
            "improved_criteria": [],
            "degraded_criteria": [],
            "new_red_flags": [],
            "resolved_red_flags": []
        }
        
        # Compare individual criteria
        score1_dict = {s.criterion: s.raw_score for s in score1.individual_scores}
        score2_dict = {s.criterion: s.raw_score for s in score2.individual_scores}
        
        for criterion in score1_dict:
            if criterion in score2_dict:
                diff = score2_dict[criterion] - score1_dict[criterion]
                if diff > 0.5:  # Significant improvement
                    comparison["improved_criteria"].append((criterion, diff))
                elif diff < -0.5:  # Significant degradation
                    comparison["degraded_criteria"].append((criterion, diff))
        
        # Compare red flags
        score1_flags = set(flag.criterion for flag in score1.red_flags)
        score2_flags = set(flag.criterion for flag in score2.red_flags)
        
        comparison["new_red_flags"] = list(score2_flags - score1_flags)
        comparison["resolved_red_flags"] = list(score1_flags - score2_flags)
        
        return comparison
    
    def get_improvement_suggestions(self, score: CompositeScore) -> List[str]:
        """Lấy gợi ý cải thiện dựa trên điểm số"""
        
        suggestions = []
        
        # Priority: Fix red flags first
        if score.red_flags:
            suggestions.append("🚨 ƯU TIÊN: Giải quyết các Red Flags:")
            for flag in sorted(score.red_flags, key=lambda f: f.severity.value, reverse=True):
                suggestions.append(f"   - {flag.criterion}: {flag.description}")
                suggestions.extend(f"     • {suggestion}" for suggestion in flag.mitigation_suggestions[:2])
        
        # Identify weak criteria (not red flags but low scores)
        weak_criteria = [
            score for score in score.individual_scores 
            if score.raw_score < 6.0 and score.criterion not in [f.criterion for f in score.red_flags]
        ]
        
        if weak_criteria:
            suggestions.append("\n📈 ĐIỂM CẦN CẢI THIỆN:")
            for weak in sorted(weak_criteria, key=lambda w: w.raw_score):
                suggestions.append(f"   - {weak.criterion}: {weak.raw_score:.1f}/10 (weight: {weak.weight})")
        
        # Identify strengths to leverage
        strong_criteria = [score for score in score.individual_scores if score.raw_score >= 8.0]
        if strong_criteria:
            suggestions.append("\n💪 ĐIỂM MẠNH ĐỂ TẬN DỤNG:")
            for strong in sorted(strong_criteria, key=lambda s: s.raw_score, reverse=True):
                suggestions.append(f"   - {strong.criterion}: {strong.raw_score:.1f}/10")
        
        return suggestions
    
    def export_score_report(self, score: CompositeScore) -> Dict[str, Any]:
        """Export score thành format để báo cáo"""
        
        report = {
            "summary": {
                "score_type": score.score_type.value,
                "final_score": round(score.final_score, 2),
                "percentage": round(score.percentage, 1),
                "quality_grade": score.quality_grade,
                "total_criteria": len(score.individual_scores),
                "red_flags_count": len(score.red_flags),
                "timestamp": score.timestamp.isoformat()
            },
            "individual_scores": [
                {
                    "criterion": s.criterion,
                    "raw_score": s.raw_score,
                    "weight": s.weight,
                    "weighted_score": round(s.weighted_score, 2),
                    "percentage": round(s.percentage, 1),
                    "reasoning": s.reasoning
                }
                for s in score.individual_scores
            ],
            "red_flags": [
                {
                    "criterion": f.criterion,
                    "severity": f.severity.value,
                    "description": f.description,
                    "impact": f.impact,
                    "score": f.score,
                    "mitigation_suggestions": f.mitigation_suggestions
                }
                for f in score.red_flags
            ],
            "improvements": self.get_improvement_suggestions(score),
            "metadata": score.metadata
        }
        
        return report

# Helper functions
def create_scores_from_text(text: str, score_type: ScoreType, weights: AgentWeights) -> Dict[str, float]:
    """
    Extract scores từ text output của LLM
    """
    
    import re
    
    scores = {}
    criteria = EVALUATION_CRITERIA.get(score_type.value, [])
    
    # Pattern để tìm scores: "criterion_name: X/10" hoặc "criterion_name (X/10)"
    patterns = [
        r"(\w+):\s*(\d+(?:\.\d+)?)/10",
        r"(\w+)\s*\((\d+(?:\.\d+)?)/10\)",
        r"(\w+).*?(\d+(?:\.\d+)?)\s*/\s*10"
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            criterion_text, score_text = match
            
            # Try to match với known criteria
            for criterion in criteria:
                if criterion in criterion_text.lower() or criterion.replace("_", " ") in criterion_text.lower():
                    try:
                        score = float(score_text)
                        if 1.0 <= score <= 10.0:
                            scores[criterion] = score
                    except ValueError:
                        continue
    
    # Fill missing criteria với default scores
    for criterion in criteria:
        if criterion not in scores:
            scores[criterion] = 5.0  # Default neutral score
            logger.warning(f"No score found for {criterion}, using default 5.0")
    
    return scores

def calculate_improvement_rate(previous_score: CompositeScore, current_score: CompositeScore) -> float:
    """Tính tỷ lệ cải thiện giữa 2 scores"""
    
    if previous_score.final_score == 0:
        return 0.0
    
    improvement = ((current_score.final_score - previous_score.final_score) / previous_score.final_score) * 100
    return improvement

# Test function
def test_scoring_system():
    """Test scoring system functionality"""
    
    from backend.config import DEFAULT_CONFIG
    
    logger.info("Testing Scoring System...")
    
    scoring = ScoringSystem(DEFAULT_CONFIG.weights)
    
    # Test analysis score
    analysis_scores = {
        "tinh_logic": 8.5,
        "toan_dien": 7.0,
        "nhat_quan": 6.5,
        "bang_chung": 9.0,
        "do_sau": 7.5
    }
    
    analysis_score = scoring.calculate_score(
        analysis_scores,
        ScoreType.ANALYSIS,
        metadata={"test": True}
    )
    
    print(f"Analysis Score: {analysis_score.final_score:.2f} ({analysis_score.quality_grade})")
    print(f"Red Flags: {len(analysis_score.red_flags)}")
    
    # Test ideas score
    ideas_scores = {
        "tinh_kha_thi": 7.0,
        "tiem_nang_thi_truong": 8.5,
        "tinh_sang_tao": 6.0,
        "mo_hinh_kinh_doanh": 7.5,
        "loi_the_canh_tranh": 5.5,
        "rui_ro_ky_thuat": 2.5,  # This will trigger red flag
        "dau_tu_ban_dau": 8.0
    }
    
    ideas_score = scoring.calculate_score(
        ideas_scores,
        ScoreType.IDEAS,
        metadata={"test": True}
    )
    
    print(f"Ideas Score: {ideas_score.final_score:.2f} ({ideas_score.quality_grade})")
    print(f"Red Flags: {len(ideas_score.red_flags)}")
    
    # Test comparison
    comparison = scoring.compare_scores(analysis_score, ideas_score)
    print(f"Score difference: {comparison['score_improvement']:.2f}")
    
    # Test suggestions
    suggestions = scoring.get_improvement_suggestions(ideas_score)
    print("Improvement suggestions:")
    for suggestion in suggestions[:3]:
        print(f"  {suggestion}")

if __name__ == "__main__":
    test_scoring_system()
