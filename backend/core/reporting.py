from __future__ import annotations

"""
Reporting helpers để tạo báo cáo Markdown chi tiết cho session MCTS
"""

from typing import Any, Dict, List, Optional
from backend.core.mcts_orchestrator import MCTSSession


def _md_heading(text: str, level: int = 2) -> str:
    return f"{'#' * level} {text}\n\n"


def _md_kv(label: str, value: Any) -> str:
    return f"- **{label}**: {value}\n"


def _truncate(text: str, max_len: int = 1200) -> str:
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n...[đã rút gọn]...\n"


def _md_code_block(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```\n\n"


def _format_iteration_block(iteration: Dict[str, Any]) -> str:
    idx = iteration.get("iteration") or iteration.get("metadata", {}).get("iteration")
    phase = iteration.get("phase", "unknown")
    result = iteration.get("result", {})

    parts: List[str] = []
    parts.append(_md_heading(f"Vòng {idx} - Phase: {phase}", 3))

    # Scores/Decision
    parts.append(_md_kv("Điểm tổng", f"{result.get('overall_score', 0):.2f}/10"))
    parts.append(_md_kv("Quyết định", result.get("decision", "unknown")))
    parts.append(_md_kv("Số Red Flags", result.get("red_flags", 0)))

    # Agent outputs (truncated)
    if result.get("primary_output"):
        parts.append(_md_heading("Primary LLM Output", 4))
        parts.append(_md_code_block(_truncate(result["primary_output"])) )

    if result.get("ct_output"):
        parts.append(_md_heading("CT-LLM (Tư duy Phản biện)", 4))
        parts.append(_md_code_block(_truncate(result["ct_output"])) )

    if result.get("ae_output"):
        parts.append(_md_heading("AE-LLM (Chuyên gia Đối kháng)", 4))
        parts.append(_md_code_block(_truncate(result["ae_output"])) )

    if result.get("sa_output"):
        parts.append(_md_heading("SA-LLM (Tổng hợp & Đánh giá)", 4))
        parts.append(_md_code_block(_truncate(result["sa_output"])) )

    # ESV
    if result.get("esv_results"):
        parts.append(_md_heading("Kết quả ESV (Tìm kiếm & Xác thực Ngoài)", 4))
        try:
            esv = result["esv_results"]
            queries = esv.get("queries") or esv.get("queries_executed")
            if queries:
                parts.append("- **Queries đã thực hiện:**\n")
                for q in queries:
                    parts.append(f"  - {q}\n")
            summary = esv.get("summary")
            if summary:
                parts.append("\n- **Tóm tắt:**\n")
                for k, v in summary.items():
                    parts.append(f"  - {k}: {v}\n")
            parts.append("\n")
        except Exception:
            pass

    return "".join(parts)


def _format_quality_metrics(session: MCTSSession) -> str:
    parts: List[str] = []
    d = session.final_deliverables.get("quality_metrics", {}) if session.final_deliverables else {}
    analysis = d.get("analysis_phase", {})
    ideas = d.get("ideas_phase", {})

    parts.append(_md_heading("Chỉ số Chất lượng", 3))
    if analysis:
        parts.append(_md_heading("Analysis Phase", 4))
        parts.append(_md_kv("Điểm cuối", f"{analysis.get('final_score', 0):.2f}/10"))
        parts.append(_md_kv("Cải thiện", f"{analysis.get('improvement', 0):.2f}"))
        parts.append(_md_kv("Điểm trung bình", f"{analysis.get('average_score', 0):.2f}/10"))
    if ideas:
        parts.append(_md_heading("Ideas Phase", 4))
        parts.append(_md_kv("Điểm cuối", f"{ideas.get('final_score', 0):.2f}/10"))
        parts.append(_md_kv("Cải thiện", f"{ideas.get('improvement', 0):.2f}"))
        parts.append(_md_kv("Điểm trung bình", f"{ideas.get('average_score', 0):.2f}/10"))
    parts.append("\n")
    # Diversity & Novelty (nếu có)
    ideas_block = session.final_deliverables.get("ideas_results", {}) if session.final_deliverables else {}
    diversity = ideas_block.get("diversity_analysis") or {}
    novelty = ideas_block.get("novelty") or {}
    if diversity or novelty:
        parts.append(_md_heading("Đa dạng & Tính mới của Ý tưởng", 3))
        if diversity:
            parts.append(_md_kv("Số ý tưởng", diversity.get("ideas_count", 0)))
            parts.append(_md_kv("Diversity Score", diversity.get("diversity_score", 0.0)))
            parts.append(_md_kv("Unique Audiences", diversity.get("unique_audiences", 0)))
            parts.append(_md_kv("Unique Business Models", diversity.get("unique_business_models", 0)))
            parts.append(_md_kv("Unique Techs", diversity.get("unique_techs", 0)))
        if novelty:
            summary = novelty.get("summary", {})
            parts.append(_md_kv("Avg Novelty", summary.get("avg_novelty", 0.0)))
            low_list = summary.get("low_novelty_ideas", [])
            if low_list:
                parts.append(_md_kv("Ý tưởng cần cải thiện novelty", ", ".join(low_list[:5])))
        parts.append("\n")
    return "".join(parts)


def _format_agent_performance(session: MCTSSession) -> str:
    parts: List[str] = []
    perf = session.final_deliverables.get("agent_performance", {}) if session.final_deliverables else {}
    if not perf:
        return ""
    parts.append(_md_heading("Hiệu năng Tác nhân", 3))
    for agent, stats in perf.items():
        parts.append(_md_heading(agent, 4))
        for k, v in stats.items():
            parts.append(_md_kv(k, v))
        parts.append("\n")
    return "".join(parts)


def generate_full_report_md(session: MCTSSession, base_output_dir: Optional[str] = None) -> str:
    """Tạo báo cáo Markdown toàn diện cho một session MCTS."""
    parts: List[str] = []

    # Header
    parts.append(_md_heading("BÁO CÁO CUỐI CÙNG - MCTS (Multi-Agent Critical Thinking System)", 1))

    # Session summary
    parts.append(_md_heading("Tóm tắt Session", 2))
    parts.append(_md_kv("Session ID", session.session_id))
    parts.append(_md_kv("Bắt đầu", session.start_time.strftime('%Y-%m-%d %H:%M:%S')))
    parts.append(_md_kv("Kết thúc", session.end_time.strftime('%Y-%m-%d %H:%M:%S') if session.end_time else "Đang chạy"))
    parts.append(_md_kv("Số vòng lặp phân tích", session.analysis_iteration))
    parts.append(_md_kv("Số vòng lặp ý tưởng", session.ideas_iteration))

    # File links (nếu có)
    if base_output_dir:
        parts.append("\n")
        parts.append(_md_kv("File phân tích cuối", f"{base_output_dir}/analysis_results.md"))
        parts.append(_md_kv("File ý tưởng cuối", f"{base_output_dir}/ideas_results.md"))
        parts.append(_md_kv("Final deliverables (JSON)", f"{base_output_dir}/final_deliverables.json"))

    # Quality metrics
    parts.append("\n")
    parts.append(_format_quality_metrics(session))

    # Iteration details
    parts.append(_md_heading("Chi tiết theo Vòng Lặp", 2))
    for it in session.iteration_history:
        parts.append(_format_iteration_block(it))

    # Recommendations
    if session.final_deliverables and session.final_deliverables.get("recommendations"):
        parts.append(_md_heading("Khuyến nghị Cuối cùng", 2))
        for rec in session.final_deliverables["recommendations"]:
            parts.append(f"- {rec}\n")
        parts.append("\n")

    # Appendix: raw JSON links
    parts.append(_md_heading("Phụ lục", 2))
    parts.append("Bạn có thể kiểm tra thêm các tệp JSON/MD trong thư mục kết quả để xem chi tiết đầy đủ.\n\n")

    return "".join(parts)
