"""
MCTS Orchestrator - Quy trình chính điều phối toàn bộ hệ thống
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from config import MCTSConfig, DEFAULT_CONFIG
from core.llm_client import LLMClient
from core.esv_module import ESVModule, create_search_query
from core.scoring_system import ScoringSystem, ScoreType, CompositeScore, create_scores_from_text
from agents.base_agent import AgentOrchestrator, create_agent_input
from agents.primary_agent import PrimaryAgent, AnalysisTask, IdeaGenerationTask
from agents.critical_thinking_agent import CriticalThinkingAgent, CriticalAnalysisTask
from agents.adversarial_expert_agent import AdversarialExpertAgent, AdversarialAttackTask, AdversarialRole, get_role_from_string
from agents.synthesis_assessment_agent import SynthesisAssessmentAgent, SynthesisTask

logger = logging.getLogger(__name__)

class MCTSPhase(Enum):
    """Các giai đoạn của MCTS"""
    INITIALIZATION = "initialization"
    ANALYSIS_LOOPS = "analysis_loops"
    IDEA_LOOPS = "idea_loops"
    FINALIZATION = "finalization"
    COMPLETED = "completed"

class LoopType(Enum):
    """Loại vòng lặp"""
    ANALYSIS = "analysis"
    IDEAS = "ideas"

@dataclass
class MCTSSession:
    """Session thông tin của một lần chạy MCTS"""
    session_id: str
    config: MCTSConfig
    current_phase: MCTSPhase = MCTSPhase.INITIALIZATION
    current_loop_type: Optional[LoopType] = None
    analysis_iteration: int = 0
    ideas_iteration: int = 0
    analysis_results: str = ""
    ideas_results: str = ""
    iteration_history: List[Dict[str, Any]] = field(default_factory=list)
    user_checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    final_deliverables: Dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

class MCTSOrchestrator:
    """
    Main orchestrator cho toàn bộ hệ thống MCTS
    """
    
    def __init__(self, config: MCTSConfig = None):
        self.config = config or DEFAULT_CONFIG
        self.session: Optional[MCTSSession] = None
        
        # Components
        self.llm_client: Optional[LLMClient] = None
        self.agent_orchestrator: Optional[AgentOrchestrator] = None
        self.esv_module: Optional[ESVModule] = None
        self.scoring_system: ScoringSystem = ScoringSystem(
            self.config.weights, 
            self.config.red_flag_threshold
        )
        
        # Agents
        self.primary_agent: Optional[PrimaryAgent] = None
        self.ct_agent: Optional[CriticalThinkingAgent] = None
        self.ae_agent: Optional[AdversarialExpertAgent] = None
        self.sa_agent: Optional[SynthesisAssessmentAgent] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()
    
    async def initialize(self):
        """Khởi tạo tất cả components"""
        logger.info("Initializing MCTS Orchestrator...")
        
        # Initialize LLM client
        self.llm_client = LLMClient(self.config.llm)
        await self.llm_client.start_session()
        
        # Initialize agent orchestrator
        self.agent_orchestrator = AgentOrchestrator(self.config)
        await self.agent_orchestrator.__aenter__()
        
        # Initialize agents
        self.primary_agent = PrimaryAgent(self.config, self.llm_client)
        self.ct_agent = CriticalThinkingAgent(self.config, self.llm_client)
        self.ae_agent = AdversarialExpertAgent(self.config, self.llm_client)
        self.sa_agent = SynthesisAssessmentAgent(self.config, self.llm_client)
        
        # Register agents
        self.agent_orchestrator.register_agent(self.primary_agent)
        self.agent_orchestrator.register_agent(self.ct_agent)
        self.agent_orchestrator.register_agent(self.ae_agent)
        self.agent_orchestrator.register_agent(self.sa_agent)
        
        # Initialize ESV module
        if self.config.enable_external_validation:
            self.esv_module = ESVModule()
            await self.esv_module.start_session()
        
        logger.info("✅ MCTS Orchestrator initialized successfully")
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up MCTS Orchestrator...")
        
        if self.llm_client:
            await self.llm_client.close_session()
        
        if self.agent_orchestrator:
            await self.agent_orchestrator.__aexit__(None, None, None)
        
        if self.esv_module:
            await self.esv_module.close_session()
        
        logger.info("✅ MCTS Orchestrator cleanup completed")
    
    async def run_full_analysis(self, 
                              data_sources: List[Dict[str, Any]],
                              timeframe: Dict[str, str],
                              focus_areas: List[str],
                              user_preferences: Optional[Dict[str, Any]] = None) -> MCTSSession:
        """
        Chạy toàn bộ quy trình MCTS
        
        Args:
            data_sources: List của data sources để phân tích
            timeframe: Dict với 'start' và 'end' dates
            focus_areas: List các lĩnh vực tập trung
            user_preferences: Optional user preferences
        
        Returns:
            MCTSSession với kết quả cuối cùng
        """
        
        # Create new session
        session_id = f"mcts_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session = MCTSSession(
            session_id=session_id,
            config=self.config
        )
        
        logger.info(f"🚀 Starting MCTS Analysis Session: {session_id}")
        
        try:
            # Phase 1: Analysis Loops
            await self._run_analysis_phase(data_sources, timeframe, focus_areas)
            
            # Phase 2: Ideas Loops  
            await self._run_ideas_phase()
            
            # Phase 3: Finalization
            await self._run_finalization_phase()
            
            # Mark completion
            self.session.current_phase = MCTSPhase.COMPLETED
            self.session.end_time = datetime.now()
            
            logger.info(f"✅ MCTS Analysis Session completed: {session_id}")
            return self.session
            
        except Exception as e:
            logger.error(f"❌ Error in MCTS session {session_id}: {str(e)}")
            raise
    
    async def _run_analysis_phase(self, 
                                data_sources: List[Dict[str, Any]],
                                timeframe: Dict[str, str], 
                                focus_areas: List[str]):
        """Chạy phase phân tích"""
        
        logger.info("📊 Starting Analysis Phase...")
        self.session.current_phase = MCTSPhase.ANALYSIS_LOOPS
        self.session.current_loop_type = LoopType.ANALYSIS
        
        analysis_complete = False
        
        while not analysis_complete and self.session.analysis_iteration < self.config.max_analysis_loops:
            self.session.analysis_iteration += 1
            logger.info(f"🔄 Analysis Loop {self.session.analysis_iteration}")
            
            # Run single analysis loop
            loop_result = await self._run_single_analysis_loop(
                data_sources, timeframe, focus_areas
            )
            
            # Record iteration
            self.session.iteration_history.append({
                "phase": "analysis",
                "iteration": self.session.analysis_iteration,
                "timestamp": datetime.now().isoformat(),
                "result": loop_result
            })
            
            # Check completion criteria
            if loop_result["decision"] == "stop":
                analysis_complete = True
                self.session.analysis_results = loop_result["primary_output"]
                logger.info("✅ Analysis phase completed - quality achieved")
            elif loop_result["decision"] == "user_checkpoint":
                # Handle user checkpoint
                checkpoint_result = await self._handle_user_checkpoint(loop_result)
                if checkpoint_result["action"] == "stop":
                    analysis_complete = True
                    self.session.analysis_results = loop_result["primary_output"]
        
        if not analysis_complete:
            logger.warning("⚠️ Analysis phase stopped due to max iterations")
            # Use best result so far
            best_iteration = max(
                self.session.iteration_history,
                key=lambda x: x["result"].get("overall_score", 0)
            )
            self.session.analysis_results = best_iteration["result"]["primary_output"]
    
    async def _run_single_analysis_loop(self, 
                                      data_sources: List[Dict[str, Any]],
                                      timeframe: Dict[str, str],
                                      focus_areas: List[str]) -> Dict[str, Any]:
        """Chạy một vòng lặp phân tích"""
        
        iteration = self.session.analysis_iteration
        
        # Step 1: Primary Analysis
        analysis_task = AnalysisTask(
            data_sources=data_sources,
            timeframe=timeframe,
            focus_areas=focus_areas,
            iteration=iteration
        )
        
        primary_input = create_agent_input(
            data=analysis_task,
            context={"max_loops": self.config.max_analysis_loops},
            iteration=iteration
        )
        
        primary_output = await self.primary_agent.process(primary_input)
        
        if not primary_output.success:
            raise Exception(f"Primary agent failed: {primary_output.error}")
        
        # Step 2: Critical Thinking Analysis
        ct_focus = focus_areas or ["logic", "consistency", "evidence", "depth"]
        ct_task = CriticalAnalysisTask(
            content_to_analyze=primary_output.content,
            content_type="analysis",
            focus_areas=ct_focus,
            iteration=iteration
        )
        
        ct_input = create_agent_input(data=ct_task, iteration=iteration)
        ct_output = await self.ct_agent.process(ct_input)
        
        # Step 3: Adversarial Expert Analysis
        ae_roles = [get_role_from_string(role) for role in self.config.adversarial_roles[:2]]
        ae_roles = [role for role in ae_roles if role is not None]
        
        ae_task = AdversarialAttackTask(
            content_to_attack=primary_output.content,
            content_type="analysis",
            active_roles=ae_roles,
            attack_intensity="moderate",
            iteration=iteration
        )
        
        ae_input = create_agent_input(data=ae_task, iteration=iteration)
        ae_output = await self.ae_agent.process(ae_input)
        
        # Step 4: ESV Validation (if enabled)
        esv_results = None
        if self.esv_module:
            esv_results = await self._run_esv_validation(primary_output.content, "analysis")
        
        # Step 5: Synthesis & Assessment
        synthesis_task = SynthesisTask(
            primary_output=primary_output.content,
            ct_feedback=ct_output.content if ct_output.success else None,
            ae_feedback=ae_output.content if ae_output.success else None,
            esv_results=esv_results,
            phase="analysis",
            iteration=iteration
        )
        
        sa_input = create_agent_input(
            data=synthesis_task,
            context={"max_loops": self.config.max_analysis_loops},
            iteration=iteration
        )
        
        sa_output = await self.sa_agent.process(sa_input)
        
        if not sa_output.success:
            raise Exception(f"Synthesis agent failed: {sa_output.error}")
        
        # Extract scores và decision
        scores_data = create_scores_from_text(sa_output.content, ScoreType.ANALYSIS, self.config.weights)
        composite_score = self.scoring_system.calculate_score(scores_data, ScoreType.ANALYSIS)
        
        # Extract decision from SA output
        decision = self._extract_decision_from_sa_output(sa_output.content)
        
        return {
            "primary_output": primary_output.content,
            "ct_output": ct_output.content if ct_output.success else "",
            "ae_output": ae_output.content if ae_output.success else "",
            "sa_output": sa_output.content,
            "esv_results": esv_results,
            "composite_score": composite_score,
            "overall_score": composite_score.final_score,
            "decision": decision,
            "red_flags": len(composite_score.red_flags),
            "metadata": {
                "iteration": iteration,
                "phase": "analysis"
            }
        }
    
    async def _run_ideas_phase(self):
        """Chạy phase tạo ý tưởng"""
        
        logger.info("💡 Starting Ideas Phase...")
        self.session.current_phase = MCTSPhase.IDEA_LOOPS
        self.session.current_loop_type = LoopType.IDEAS
        
        ideas_complete = False
        
        while not ideas_complete and self.session.ideas_iteration < self.config.max_idea_loops:
            self.session.ideas_iteration += 1
            logger.info(f"🔄 Ideas Loop {self.session.ideas_iteration}")
            
            # Run single ideas loop
            loop_result = await self._run_single_ideas_loop()
            
            # Record iteration
            self.session.iteration_history.append({
                "phase": "ideas",
                "iteration": self.session.ideas_iteration,
                "timestamp": datetime.now().isoformat(),
                "result": loop_result
            })
            
            # Check completion criteria
            if loop_result["decision"] == "stop":
                ideas_complete = True
                self.session.ideas_results = loop_result["primary_output"]
                logger.info("✅ Ideas phase completed - quality achieved")
            elif loop_result["decision"] == "user_checkpoint":
                # Handle user checkpoint
                checkpoint_result = await self._handle_user_checkpoint(loop_result)
                if checkpoint_result["action"] == "stop":
                    ideas_complete = True
                    self.session.ideas_results = loop_result["primary_output"]
        
        if not ideas_complete:
            logger.warning("⚠️ Ideas phase stopped due to max iterations")
            # Use best result so far
            ideas_iterations = [h for h in self.session.iteration_history if h["phase"] == "ideas"]
            if ideas_iterations:
                best_iteration = max(ideas_iterations, key=lambda x: x["result"].get("overall_score", 0))
                self.session.ideas_results = best_iteration["result"]["primary_output"]
    
    async def _run_single_ideas_loop(self) -> Dict[str, Any]:
        """Chạy một vòng lặp tạo ý tưởng"""
        
        iteration = self.session.ideas_iteration
        
        # Get feedback from previous iteration (if any)
        previous_ct_feedback = None
        previous_ae_feedback = None
        
        if iteration > 1:
            # Get feedback from last iteration
            last_ideas_iteration = [
                h for h in self.session.iteration_history 
                if h["phase"] == "ideas" and h["iteration"] == iteration - 1
            ]
            if last_ideas_iteration:
                last_result = last_ideas_iteration[0]["result"]
                previous_ct_feedback = last_result.get("ct_output")
                previous_ae_feedback = last_result.get("ae_output")
        
        # Step 1: Primary Ideas Generation
        ideas_task = IdeaGenerationTask(
            analysis_results=self.session.analysis_results,
            feedback_from_ct=previous_ct_feedback,
            feedback_from_ae=previous_ae_feedback,
            target_count=5,
            iteration=iteration
        )
        
        primary_input = create_agent_input(
            data=ideas_task,
            context={"max_loops": self.config.max_idea_loops},
            iteration=iteration
        )
        
        primary_output = await self.primary_agent.process(primary_input)
        
        if not primary_output.success:
            raise Exception(f"Primary agent failed: {primary_output.error}")
        
        # Step 2: Critical Thinking Analysis
        ct_task = CriticalAnalysisTask(
            content_to_analyze=primary_output.content,
            content_type="ideas",
            focus_areas=["feasibility", "market_potential", "business_model"],
            iteration=iteration
        )
        
        ct_input = create_agent_input(data=ct_task, iteration=iteration)
        ct_output = await self.ct_agent.process(ct_input)
        
        # Step 3: Adversarial Expert Attack
        ae_roles = [get_role_from_string(role) for role in self.config.adversarial_roles]
        ae_roles = [role for role in ae_roles if role is not None]
        
        ae_task = AdversarialAttackTask(
            content_to_attack=primary_output.content,
            content_type="ideas",
            active_roles=ae_roles,
            attack_intensity="aggressive",  # More aggressive for ideas
            iteration=iteration
        )
        
        ae_input = create_agent_input(data=ae_task, iteration=iteration)
        ae_output = await self.ae_agent.process(ae_input)
        
        # Step 4: ESV Validation (if enabled)
        esv_results = None
        if self.esv_module:
            esv_results = await self._run_esv_validation(primary_output.content, "ideas")
        
        # Step 5: Synthesis & Assessment
        synthesis_task = SynthesisTask(
            primary_output=primary_output.content,
            ct_feedback=ct_output.content if ct_output.success else None,
            ae_feedback=ae_output.content if ae_output.success else None,
            esv_results=esv_results,
            phase="ideas",
            iteration=iteration
        )
        
        sa_input = create_agent_input(
            data=synthesis_task,
            context={"max_loops": self.config.max_idea_loops},
            iteration=iteration
        )
        
        sa_output = await self.sa_agent.process(sa_input)
        
        if not sa_output.success:
            raise Exception(f"Synthesis agent failed: {sa_output.error}")
        
        # Extract scores và decision
        scores_data = create_scores_from_text(sa_output.content, ScoreType.IDEAS, self.config.weights)
        composite_score = self.scoring_system.calculate_score(scores_data, ScoreType.IDEAS)
        
        # Extract decision from SA output
        decision = self._extract_decision_from_sa_output(sa_output.content)
        
        return {
            "primary_output": primary_output.content,
            "ct_output": ct_output.content if ct_output.success else "",
            "ae_output": ae_output.content if ae_output.success else "",
            "sa_output": sa_output.content,
            "esv_results": esv_results,
            "composite_score": composite_score,
            "overall_score": composite_score.final_score,
            "decision": decision,
            "red_flags": len(composite_score.red_flags),
            "metadata": {
                "iteration": iteration,
                "phase": "ideas"
            }
        }
    
    async def _run_esv_validation(self, content: str, content_type: str) -> Optional[Dict[str, Any]]:
        """Chạy ESV validation"""
        
        if not self.esv_module:
            return None
        
        try:
            # Extract key concepts cho validation
            from core.esv_module import extract_keywords_from_text
            keywords = extract_keywords_from_text(content, max_keywords=3)
            
            # Create search queries based on content type
            queries = []
            
            if content_type == "analysis":
                for keyword in keywords:
                    queries.append(create_search_query(
                        f"trend {keyword} 2024",
                        "trend",
                        "medium"
                    ))
            elif content_type == "ideas":
                for keyword in keywords:
                    queries.append(create_search_query(
                        f"startup {keyword} competitors",
                        "competitor", 
                        "high"
                    ))
                    queries.append(create_search_query(
                        f"market size {keyword}",
                        "market_size",
                        "medium"
                    ))
            
            # Limit số queries
            queries = queries[:5]
            
            if not queries:
                return None
            
            # Execute validation
            results = await self.esv_module.validate_multiple(queries)
            
            # Summarize results
            summary = {
                "queries_executed": len(queries),
                "confirmed": sum(1 for r in results.values() if r.validation_status == "confirmed"),
                "refuted": sum(1 for r in results.values() if r.validation_status == "refuted"),
                "inconclusive": sum(1 for r in results.values() if r.validation_status == "inconclusive"),
                "average_confidence": sum(r.confidence for r in results.values()) / len(results) if results else 0
            }
            
            return {
                "queries": list(results.keys()),
                "results": [r.__dict__ for r in results.values()],
                "summary": summary
            }
            
        except Exception as e:
            logger.warning(f"ESV validation failed: {str(e)}")
            return None
    
    def _extract_decision_from_sa_output(self, sa_output: str) -> str:
        """Extract decision từ SA agent output"""
        
        import re
        
        # Look for decision patterns
        decision_patterns = [
            r"Decision:\s*(\w+)",
            r"DECISION\s*=\s*\"?(\w+)\"?",
            r"action:\s*\"?(\w+)\"?",
            r"Recommendation:\s*(\w+)"
        ]
        
        for pattern in decision_patterns:
            match = re.search(pattern, sa_output, re.IGNORECASE)
            if match:
                decision = match.group(1).lower()
                if decision in ["continue", "stop", "user_checkpoint"]:
                    return decision
        
        # Default decision logic based on keywords
        if "stop" in sa_output.lower() or "quality achieved" in sa_output.lower():
            return "stop"
        elif "user" in sa_output.lower() and "checkpoint" in sa_output.lower():
            return "user_checkpoint"
        else:
            return "continue"
    
    async def _handle_user_checkpoint(self, loop_result: Dict[str, Any]) -> Dict[str, str]:
        """Handle user checkpoint interaction"""
        
        # For now, implement simple logic
        # In real implementation, this would present options to user
        
        checkpoint_info = {
            "situation": "Quality improvement below threshold",
            "current_score": loop_result.get("overall_score", 0),
            "red_flags": loop_result.get("red_flags", 0),
            "options": [
                "continue",
                "stop",
                "adjust_parameters"
            ]
        }
        
        # Record checkpoint
        self.session.user_checkpoints.append({
            "timestamp": datetime.now().isoformat(),
            "phase": self.session.current_loop_type.value if self.session.current_loop_type else "unknown",
            "iteration": (self.session.analysis_iteration 
                         if self.session.current_loop_type == LoopType.ANALYSIS 
                         else self.session.ideas_iteration),
            "checkpoint_info": checkpoint_info,
            "auto_decision": "continue"  # Auto-continue for now
        })
        
        logger.info(f"🚦 User checkpoint triggered - auto-continuing")
        
        return {"action": "continue"}
    
    async def _run_finalization_phase(self):
        """Chạy phase hoàn thiện"""
        
        logger.info("🏁 Starting Finalization Phase...")
        self.session.current_phase = MCTSPhase.FINALIZATION
        
        # Compile final deliverables
        self.session.final_deliverables = {
            "session_summary": {
                "session_id": self.session.session_id,
                "start_time": self.session.start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_analysis_iterations": self.session.analysis_iteration,
                "total_ideas_iterations": self.session.ideas_iteration,
                "user_checkpoints": len(self.session.user_checkpoints)
            },
            "analysis_results": {
                "final_analysis": self.session.analysis_results,
                "iteration_count": self.session.analysis_iteration
            },
            "ideas_results": {
                "final_ideas": self.session.ideas_results,
                "iteration_count": self.session.ideas_iteration
            },
            "quality_metrics": self._compile_quality_metrics(),
            "agent_performance": self._compile_agent_performance(),
            "recommendations": self._compile_recommendations(),
            "iterations": self.session.iteration_history  # thêm chi tiết từng vòng
        }
        
        # Save results if configured
        if self.config.save_intermediate_results:
            await self._save_session_results()
        
        logger.info("✅ Finalization phase completed")
    
    def _compile_quality_metrics(self) -> Dict[str, Any]:
        """Compile quality metrics từ toàn bộ session"""
        
        analysis_scores = []
        ideas_scores = []
        
        for iteration in self.session.iteration_history:
            if iteration["phase"] == "analysis":
                analysis_scores.append(iteration["result"]["overall_score"])
            elif iteration["phase"] == "ideas":
                ideas_scores.append(iteration["result"]["overall_score"])
        
        return {
            "analysis_phase": {
                "scores": analysis_scores,
                "final_score": analysis_scores[-1] if analysis_scores else 0,
                "improvement": analysis_scores[-1] - analysis_scores[0] if len(analysis_scores) > 1 else 0,
                "average_score": sum(analysis_scores) / len(analysis_scores) if analysis_scores else 0
            },
            "ideas_phase": {
                "scores": ideas_scores,
                "final_score": ideas_scores[-1] if ideas_scores else 0,
                "improvement": ideas_scores[-1] - ideas_scores[0] if len(ideas_scores) > 1 else 0,
                "average_score": sum(ideas_scores) / len(ideas_scores) if ideas_scores else 0
            }
        }
    
    def _compile_agent_performance(self) -> Dict[str, Any]:
        """Compile agent performance metrics"""
        
        if not self.agent_orchestrator:
            return {}
        
        return self.agent_orchestrator.get_all_metrics()
    
    def _compile_recommendations(self) -> List[str]:
        """Compile final recommendations"""
        
        recommendations = []
        
        # Analysis phase recommendations
        if self.session.analysis_iteration >= self.config.max_analysis_loops:
            recommendations.append("⚠️ Analysis phase reached maximum iterations - consider increasing analysis depth in future runs")
        
        # Ideas phase recommendations  
        if self.session.ideas_iteration >= self.config.max_idea_loops:
            recommendations.append("⚠️ Ideas phase reached maximum iterations - consider refining idea generation criteria")
        
        # User checkpoint recommendations
        if len(self.session.user_checkpoints) > 2:
            recommendations.append("💡 Multiple user checkpoints triggered - consider adjusting quality thresholds")
        
        # Quality recommendations
        quality_metrics = self._compile_quality_metrics()
        final_analysis_score = quality_metrics["analysis_phase"]["final_score"]
        final_ideas_score = quality_metrics["ideas_phase"]["final_score"]
        
        if final_analysis_score < 7.0:
            recommendations.append("📊 Analysis quality could be improved - consider more comprehensive data sources")
        
        if final_ideas_score < 7.0:
            recommendations.append("💡 Ideas quality could be improved - consider more rigorous validation criteria")
        
        if not recommendations:
            recommendations.append("✅ Session completed successfully with good quality metrics")
        
        return recommendations
    
    async def _save_session_results(self):
        """Save session results to files"""
        
        import os
        
        # Create results directory
        results_dir = f"{self.config.output_dir}/{self.session.session_id}"
        os.makedirs(results_dir, exist_ok=True)
        
        # Save session summary
        with open(f"{results_dir}/session_summary.json", "w", encoding="utf-8") as f:
            json.dump(self.session.__dict__, f, ensure_ascii=False, indent=2, default=str)
        
        # Save final deliverables
        with open(f"{results_dir}/final_deliverables.json", "w", encoding="utf-8") as f:
            json.dump(self.session.final_deliverables, f, ensure_ascii=False, indent=2, default=str)
        
        # Save analysis results
        with open(f"{results_dir}/analysis_results.md", "w", encoding="utf-8") as f:
            f.write(self.session.analysis_results)
        
        # Save ideas results
        with open(f"{results_dir}/ideas_results.md", "w", encoding="utf-8") as f:
            f.write(self.session.ideas_results)
        
        logger.info(f"💾 Session results saved to: {results_dir}")
    
    def get_session_status(self) -> Dict[str, Any]:
        """Lấy trạng thái hiện tại của session"""
        
        if not self.session:
            return {"status": "no_active_session"}
        
        return {
            "session_id": self.session.session_id,
            "current_phase": self.session.current_phase.value,
            "current_loop_type": self.session.current_loop_type.value if self.session.current_loop_type else None,
            "analysis_iteration": self.session.analysis_iteration,
            "ideas_iteration": self.session.ideas_iteration,
            "total_iterations": len(self.session.iteration_history),
            "user_checkpoints": len(self.session.user_checkpoints),
            "elapsed_time": (datetime.now() - self.session.start_time).total_seconds(),
            "completion_percentage": self._calculate_completion_percentage()
        }
    
    def _calculate_completion_percentage(self) -> float:
        """Tính phần trăm hoàn thành"""
        
        if not self.session:
            return 0.0
        
        phase_weights = {
            MCTSPhase.INITIALIZATION: 0.05,
            MCTSPhase.ANALYSIS_LOOPS: 0.4,
            MCTSPhase.IDEA_LOOPS: 0.4,
            MCTSPhase.FINALIZATION: 0.1,
            MCTSPhase.COMPLETED: 0.05
        }
        
        completed_phases = 0.0
        
        if self.session.current_phase == MCTSPhase.INITIALIZATION:
            completed_phases = 0.0
        elif self.session.current_phase == MCTSPhase.ANALYSIS_LOOPS:
            completed_phases = phase_weights[MCTSPhase.INITIALIZATION]
            completed_phases += phase_weights[MCTSPhase.ANALYSIS_LOOPS] * (self.session.analysis_iteration / self.config.max_analysis_loops)
        elif self.session.current_phase == MCTSPhase.IDEA_LOOPS:
            completed_phases = phase_weights[MCTSPhase.INITIALIZATION] + phase_weights[MCTSPhase.ANALYSIS_LOOPS]
            completed_phases += phase_weights[MCTSPhase.IDEA_LOOPS] * (self.session.ideas_iteration / self.config.max_idea_loops)
        elif self.session.current_phase == MCTSPhase.FINALIZATION:
            completed_phases = 0.95
        else:  # COMPLETED
            completed_phases = 1.0
        
        return min(completed_phases * 100, 100.0)

# Helper functions
def create_sample_data_sources() -> List[Dict[str, Any]]:
    """Tạo sample data sources cho testing"""
    return [
        {
            "type": "reddit",
            "description": "r/startups community discussions",
            "content": "Sample Reddit data about startup trends and painpoints..."
        },
        {
            "type": "hackernews", 
            "description": "Hacker News tech discussions",
            "content": "Sample HN data about technology trends and innovations..."
        },
        {
            "type": "product_hunt",
            "description": "Product Hunt product launches",
            "content": "Sample Product Hunt data about new product releases..."
        }
    ]

async def test_mcts_orchestrator():
    """Test MCTS orchestrator functionality"""
    
    logger.info("Testing MCTS Orchestrator...")
    
    async with MCTSOrchestrator() as orchestrator:
        # Test data
        data_sources = create_sample_data_sources()
        timeframe = {"start": "2024-01-01", "end": "2024-01-31"}
        focus_areas = ["AI/ML", "SaaS", "Fintech"]
        
        # Run analysis
        session = await orchestrator.run_full_analysis(
            data_sources=data_sources,
            timeframe=timeframe,
            focus_areas=focus_areas
        )
        
        print(f"Session completed: {session.session_id}")
        print(f"Analysis iterations: {session.analysis_iteration}")
        print(f"Ideas iterations: {session.ideas_iteration}")
        print(f"Final phase: {session.current_phase.value}")

if __name__ == "__main__":
    # Example usage
    async def main():
        await test_mcts_orchestrator()
    
    asyncio.run(main())
