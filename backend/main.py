"""
MCTS Main Entry Point - CLI Interface
"""

import asyncio
import click
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from backend.config import MCTSConfig, DEFAULT_CONFIG
from backend.core.mcts_orchestrator import MCTSOrchestrator
from backend.core.llm_client import test_llm_connection

# Async click wrapper
def coro(f):
    """Decorator to make click commands work with async functions"""
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    wrapper.__name__ = f.__name__
    wrapper.__doc__ = f.__doc__
    return wrapper

# Setup console
console = Console()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mcts.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def print_banner():
    """In banner chào mừng"""
    banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║    🧠 MCTS - Multi-Agent Critical Thinking System                           ║
║    Hệ thống Tư duy Phản biện Tăng cường Đa Tác nhân                        ║
║                                                                              ║
║    Version: 2.0                                                             ║
║    Powered by: Gemini 2.5 Pro                                               ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    console.print(banner, style="bold blue")

@click.group()
@click.version_option(version="2.0")
def cli():
    """
    MCTS - Multi-Agent Critical Thinking System
    
    Hệ thống tư duy phản biện tăng cường đa tác nhân để tạo ra các ý tưởng startup 
    có chất lượng, tính khả thi và tiềm năng thành công cao.
    """
    print_banner()

@cli.command()
@click.argument('message')
@coro
async def quick(message):
    """
    🚀 Quick mode - Hỏi nhanh và nhận kết quả ngay
    
    MESSAGE: Câu hỏi hoặc yêu cầu
    
    Ví dụ:
    python main.py quick "AI trends 2024?"
    python main.py quick "Ý tưởng app cho sinh viên"
    """
    
    if not message:
        console.print("❌ Cần có câu hỏi. Ví dụ: python main.py quick 'AI trends 2024?'", style="red")
        return
    
    try:
        from backend.core.dynamic_processor import process_user_message
        
        console.print(f"⚡ Quick processing: {message}", style="yellow")
        
        response = await process_user_message(message)
        
        console.print(f"\n🤖 {response.content}", style="white")
        
        if response.suggestions:
            console.print(f"\n💡 {response.suggestions[0]}", style="dim cyan")
            
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@cli.command()
@click.option('--config', '-c', help='Đường dẫn đến file config JSON')
@click.option('--data-sources', '-d', multiple=True, help='Đường dẫn đến data sources')
@click.option('--focus-areas', '-f', multiple=True, help='Lĩnh vực tập trung (ví dụ: AI/ML, SaaS, Fintech)')
@click.option('--start-date', help='Ngày bắt đầu phân tích (YYYY-MM-DD)')
@click.option('--end-date', help='Ngày kết thúc phân tích (YYYY-MM-DD)')
@click.option('--output-dir', '-o', help='Thư mục output')
@click.option('--max-analysis-loops', type=int, help='Số vòng lặp phân tích tối đa')
@click.option('--max-idea-loops', type=int, help='Số vòng lặp ý tưởng tối đa')
@click.option('--verbose', '-v', is_flag=True, help='Hiển thị log chi tiết')
@coro
async def analyze(config, data_sources, focus_areas, start_date, end_date, 
                 output_dir, max_analysis_loops, max_idea_loops, verbose):
    """
    Chạy phân tích MCTS đầy đủ
    
    Ví dụ:
    python main.py analyze -d data/reddit.json -d data/hn.json -f "AI/ML" -f "SaaS"
    """
    
    try:
        # Load config
        mcts_config = load_config(config, {
            'output_dir': output_dir,
            'max_analysis_loops': max_analysis_loops,
            'max_idea_loops': max_idea_loops
        })
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Validate data sources
        if not data_sources:
            console.print("❌ Cần ít nhất một data source", style="red")
            return
        
        # Load data sources
        loaded_data_sources = load_data_sources(data_sources)
        
        # Set focus areas
        if not focus_areas:
            focus_areas = ["Technology", "Market_Analysis", "Business_Model"]
        
        # Set timeframe
        timeframe = {
            "start": start_date or "2024-01-01",
            "end": end_date or datetime.now().strftime("%Y-%m-%d")
        }
        
        console.print(f"\n🚀 Bắt đầu phân tích MCTS...", style="bold green")
        console.print(f"📊 Data sources: {len(loaded_data_sources)}")
        console.print(f"🎯 Focus areas: {', '.join(focus_areas)}")
        console.print(f"📅 Timeframe: {timeframe['start']} đến {timeframe['end']}")
        
        # Test LLM connection first
        console.print("\n🔍 Kiểm tra kết nối LLM...", style="yellow")
        connection_ok = await test_llm_connection(mcts_config.llm)
        
        if not connection_ok:
            console.print("❌ Không thể kết nối với LLM API", style="red")
            return
        
        console.print("✅ Kết nối LLM thành công", style="green")
        
        # Run MCTS analysis với progress tracking
        async with MCTSOrchestrator(mcts_config) as orchestrator:
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                
                # Create progress task
                task = progress.add_task("Đang chạy MCTS Analysis...", total=100)
                
                # Start analysis
                analysis_task = asyncio.create_task(
                    orchestrator.run_full_analysis(
                        data_sources=loaded_data_sources,
                        timeframe=timeframe,
                        focus_areas=list(focus_areas)
                    )
                )
                
                # Update progress periodically
                while not analysis_task.done():
                    status = orchestrator.get_session_status()
                    if status.get("status") != "no_active_session":
                        completion = status.get("completion_percentage", 0)
                        phase = status.get("current_phase", "unknown")
                        progress.update(task, completed=completion, description=f"Phase: {phase}")
                    
                    await asyncio.sleep(2)
                
                # Get result
                session = await analysis_task
                progress.update(task, completed=100, description="Hoàn thành!")
        
        # Display results
        display_results(session)
        
    except Exception as e:
        console.print(f"❌ Lỗi trong quá trình phân tích: {str(e)}", style="red")
        logger.error(f"Analysis error: {str(e)}", exc_info=True)

@cli.command()
@click.option('--config', '-c', help='Đường dẫn đến file config JSON')
def test_connection(config):
    """
    Kiểm tra kết nối với LLM API
    """
    
    try:
        mcts_config = load_config(config)
        
        console.print("🔍 Đang kiểm tra kết nối LLM API...", style="yellow")
        
        success = asyncio.run(test_llm_connection(mcts_config.llm))
        
        if success:
            console.print("✅ Kết nối LLM thành công!", style="green")
            console.print(f"URL: {mcts_config.llm.url}")
            console.print(f"Model: {mcts_config.llm.model}")
        else:
            console.print("❌ Không thể kết nối với LLM API", style="red")
            console.print("Vui lòng kiểm tra:")
            console.print("- URL có đúng không")
            console.print("- API key có hợp lệ không") 
            console.print("- Service có đang chạy không")
            
    except Exception as e:
        console.print(f"❌ Lỗi: {str(e)}", style="red")

@cli.command()
@click.argument('session_dir', type=click.Path(exists=True))
def show_results(session_dir):
    """
    Hiển thị kết quả từ session đã lưu
    
    SESSION_DIR: Thư mục chứa kết quả session
    """
    
    try:
        session_path = Path(session_dir)
        
        # Load session summary
        summary_file = session_path / "session_summary.json"
        if not summary_file.exists():
            console.print(f"❌ Không tìm thấy file session_summary.json trong {session_dir}", style="red")
            return
        
        with open(summary_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Display results
        display_session_summary(session_data)
        
        # Display analysis results if available
        analysis_file = session_path / "analysis_results.md"
        if analysis_file.exists():
            console.print("\n📊 KẾT QUẢ PHÂN TÍCH:", style="bold blue")
            with open(analysis_file, 'r', encoding='utf-8') as f:
                content = f.read()
                console.print(Markdown(content[:2000] + "..." if len(content) > 2000 else content))
        
        # Display ideas results if available
        ideas_file = session_path / "ideas_results.md"
        if ideas_file.exists():
            console.print("\n💡 KẾT QUẢ Ý TƯỞNG:", style="bold blue")
            with open(ideas_file, 'r', encoding='utf-8') as f:
                content = f.read()
                console.print(Markdown(content[:2000] + "..." if len(content) > 2000 else content))
                
    except Exception as e:
        console.print(f"❌ Lỗi đọc kết quả: {str(e)}", style="red")

@cli.command()
def create_sample_config():
    """
    Tạo file config mẫu
    """
    
    sample_config = {
        "llm": {
            "url": "http://localhost:8000/v1/chat/completions",
            "model": "gemini-2.5-pro",
            "api_key": "sk-1234",
            "max_tokens": 4000,
            "temperature": 0.7,
            "timeout": 60
        },
        "max_analysis_loops": 3,
        "max_idea_loops": 4,
        "quality_threshold": 9.0,
        "improvement_threshold": 0.05,
        "red_flag_threshold": 3.0,
        "weights": {
            "tinh_kha_thi": 2.0,
            "tiem_nang_thi_truong": 2.5,
            "tinh_sang_tao": 1.5,
            "mo_hinh_kinh_doanh": 2.0,
            "loi_the_canh_tranh": 1.8,
            "rui_ro_ky_thuat": 1.5,
            "dau_tu_ban_dau": 1.2
        },
        "adversarial_roles": ["VC", "Kỹ_sư", "Đối_thủ"],
        "enable_external_validation": True,
        "search_timeout": 30,
        "log_level": "INFO",
        "save_intermediate_results": True,
        "output_dir": "results"
    }
    
    config_file = "mcts_config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(sample_config, f, ensure_ascii=False, indent=2)
    
    console.print(f"✅ Đã tạo file config mẫu: {config_file}", style="green")
    console.print("Bạn có thể chỉnh sửa file này và sử dụng với tùy chọn --config")

@cli.command()
@coro
async def chat():
    """
    Bắt đầu interactive chat session với MCTS AI
    
    Mode này cho phép bạn:
    - Hỏi bất kỳ câu hỏi nào về startup/business
    - Yêu cầu phân tích dữ liệu real-time
    - Tạo ý tưởng startup từ input tự do
    - Tương tác natural language hoàn toàn
    """
    
    try:
        from backend.core.dynamic_processor import start_interactive_session
        await start_interactive_session()
        
    except Exception as e:
        console.print(f"❌ Lỗi khởi tạo chat session: {str(e)}", style="red")

@cli.command()
@click.argument('message', required=False)
@click.option('--config', '-c', help='Đường dẫn đến file config JSON')
@coro
async def ask(message, config):
    """
    Hỏi MCTS một câu hỏi hoặc yêu cầu cụ thể
    
    MESSAGE: Câu hỏi hoặc yêu cầu (nếu không có sẽ prompt)
    
    Ví dụ:
    python main.py ask "Phân tích xu hướng AI startup 2024"
    python main.py ask "Tạo ý tưởng fintech cho Gen Z"
    python main.py ask "So sánh SaaS vs PaaS market"
    """
    
    try:
        from backend.core.dynamic_processor import process_user_message
        
        # Load config
        mcts_config = load_config(config)
        
        # Get message if not provided
        if not message:
            message = click.prompt("💬 Bạn muốn hỏi gì?", type=str)
        
        if not message.strip():
            console.print("❌ Cần có câu hỏi hoặc yêu cầu", style="red")
            return
        
        console.print(f"\n🤔 Đang xử lý: {message}", style="yellow")
        
        # Process với dynamic processor
        response = await process_user_message(message, mcts_config)
        
        # Display response
        console.print("\n" + "="*60, style="blue")
        console.print("🤖 MCTS AI Response:", style="bold blue")
        console.print("="*60, style="blue")
        console.print(f"\n{response.content}", style="white")
        
        # Show metadata
        if response.success:
            console.print(f"\n✅ Response Type: {response.response_type}", style="green")
        else:
            console.print(f"\n❌ Response Type: {response.response_type}", style="red")
        
        # Show suggestions
        if response.suggestions:
            console.print("\n💡 Gợi ý tiếp theo:", style="cyan")
            for i, suggestion in enumerate(response.suggestions, 1):
                console.print(f"   {i}. {suggestion}", style="dim cyan")
        
        # Show follow-up questions
        if response.follow_up_questions:
            console.print("\n❓ Câu hỏi tiếp theo:", style="magenta")
            for i, question in enumerate(response.follow_up_questions, 1):
                console.print(f"   {i}. {question}", style="dim magenta")
        
        # Session info if available
        if response.metadata.get("session_id"):
            session_id = response.metadata["session_id"]
            console.print(f"\n💾 Session ID: {session_id}", style="dim white")
            console.print(f"📁 Results saved to: {DEFAULT_CONFIG.output_dir}/{session_id}", style="dim white")
        
    except Exception as e:
        console.print(f"❌ Lỗi xử lý request: {str(e)}", style="red")
        logger.error(f"Ask command error: {str(e)}", exc_info=True)

@cli.command()
def create_sample_data():
    """
    Tạo file dữ liệu mẫu để test (legacy command)
    
    Lưu ý: Với dynamic mode mới, bạn có thể directly input
    data mà không cần sample files. Sử dụng 'chat' hoặc 'ask'.
    """
    
    sample_data_sources = [
        {
            "type": "reddit",
            "description": "Dữ liệu từ r/startups về xu hướng startup 2024",
            "content": """
            Người dùng đang thảo luận về các xu hướng startup nổi bật:
            
            1. AI/ML Applications:
            - Nhiều startup đang tích hợp AI để cải thiện user experience
            - Đặc biệt quan tâm đến generative AI và automation
            - Pain point: Chi phí inference cao, cần optimize models
            
            2. SaaS Solutions:
            - Micro-SaaS đang trending với focus vào niche markets
            - Integration platforms được quan tâm nhiều
            - Pain point: Customer acquisition cost ngày càng cao
            
            3. Fintech Innovations:
            - Payment solutions cho emerging markets
            - DeFi tools cho retail users
            - Pain point: Regulatory compliance phức tạp
            
            Top comments cho thấy entrepreneurs quan tâm:
            - Market validation strategies
            - Product-market fit indicators  
            - Funding landscape thay đổi
            """
        },
        {
            "type": "hackernews",
            "description": "Thảo luận công nghệ từ Hacker News",
            "content": """
            Các chủ đề hot trên HN gần đây:
            
            Technology Trends:
            - WebAssembly adoption đang tăng mạnh
            - Edge computing solutions
            - Privacy-first development approaches
            - Open source AI models
            
            Developer Pain Points:
            - Tool fatigue - quá nhiều frameworks/tools
            - Performance optimization challenges
            - Security concerns with new technologies
            - Developer experience (DevEx) quan trọng hơn
            
            Market Observations:
            - Big Tech layoffs tạo cơ hội cho startups
            - Remote work tools evolution
            - Climate tech solutions được quan tâm
            - Web3 infrastructure maturing
            """
        },
        {
            "type": "product_hunt",
            "description": "Sản phẩm mới launch trên Product Hunt",
            "content": """
            Top sản phẩm được launch gần đây:
            
            AI-Powered Tools:
            - Writing assistants với specialized domains
            - Design automation tools
            - Code review và optimization platforms
            - Voice synthesis và conversion tools
            
            Productivity Solutions:
            - Team collaboration platforms
            - Project management với AI insights
            - Time tracking và productivity analytics
            - Meeting automation tools
            
            Developer Tools:
            - No-code/low-code platforms
            - API management solutions
            - Database optimization tools
            - Testing automation frameworks
            
            Market Patterns:
            - Focus on vertical solutions thay vì horizontal
            - Integration-first approach
            - Mobile-first design
            - Subscription model dominance
            """
        }
    ]
    
    # Create data directory
    Path("sample_data").mkdir(exist_ok=True)
    
    # Save individual data sources
    for i, source in enumerate(sample_data_sources):
        filename = f"sample_data/{source['type']}_data.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(source, f, ensure_ascii=False, indent=2)
        
        console.print(f"✅ Đã tạo: {filename}")
    
    console.print("\n📝 Để sử dụng dữ liệu mẫu, chạy:")
    console.print("python main.py analyze -d sample_data/reddit_data.json -d sample_data/hackernews_data.json -d sample_data/product_hunt_data.json -f 'AI/ML' -f 'SaaS' -f 'Fintech'")

@cli.command()
@click.argument('prompt', required=True)
@click.option('--analysis-loops', type=int, default=3, help='Số vòng lặp phân tích (X)')
@click.option('--idea-loops', type=int, default=3, help='Số vòng lặp ý tưởng (Y)')
@click.option('--config', '-c', help='Đường dẫn đến file config JSON')
@click.option('--no-esv', is_flag=True, help='Tắt ESV validation')
@click.option('--output', '-o', help='Thư mục xuất kết quả (ghi đè)')
@coro
async def pipeline(prompt, analysis_loops, idea_loops, config, no_esv, output):
    """
    Chạy FULL PIPELINE từ input tự do: phân tích → thử lửa → tổng hợp → lặp → báo cáo.

    Ví dụ:
    python main.py pipeline "Phân tích thị trường fintech VN và tạo ý tưởng" --analysis-loops 2 --idea-loops 3
    """
    from backend.core.reporting import generate_full_report_md

    # Load và tùy biến config
    cfg = load_config(config)
    cfg.max_analysis_loops = analysis_loops
    cfg.max_idea_loops = idea_loops
    if no_esv:
        cfg.enable_external_validation = False
    if output:
        cfg.output_dir = output

    console.print("\n🚀 Đang chạy FULL PIPELINE...", style="bold green")
    console.print(f"🧪 Vòng phân tích: {cfg.max_analysis_loops} | 💡 Vòng ý tưởng: {cfg.max_idea_loops}")

    # Tạo data source từ prompt tự do
    data_sources = [{
        "type": "user_prompt",
        "description": "Input tự do của người dùng",
        "content": prompt
    }]

    timeframe = {
        "start": datetime.now().strftime('%Y-%m-%d'),
        "end": datetime.now().strftime('%Y-%m-%d')
    }

    focus_areas = []  # để orchestrator tự phát hiện

    async with MCTSOrchestrator(cfg) as orchestrator:
        session = await orchestrator.run_full_analysis(
            data_sources=data_sources,
            timeframe=timeframe,
            focus_areas=focus_areas
        )

        # Tạo báo cáo tổng hợp Markdown
        base_output_dir = f"{cfg.output_dir}/{session.session_id}"
        report_md = generate_full_report_md(session, base_output_dir)
        report_path = f"{base_output_dir}/final_report.md"

        # Ghi ra tệp
        from pathlib import Path as _Path
        _Path(base_output_dir).mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_md)

        console.print("\n✅ Hoàn thành FULL PIPELINE", style="green")
        console.print(f"📂 Thư mục kết quả: {base_output_dir}")
        console.print(f"📄 Báo cáo cuối: {report_path}")
        console.print("\nGồm:")
        console.print("- analysis_results.md (phân tích cuối)")
        console.print("- ideas_results.md (ý tưởng cuối)")
        console.print("- final_deliverables.json (tổng hợp số liệu)")
        console.print("- final_report.md (báo cáo Markdown đầy đủ)")

def load_config(config_file: str = None, overrides: Dict[str, Any] = None) -> MCTSConfig:
    """Load configuration từ file hoặc sử dụng default"""
    
    if config_file and Path(config_file).exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Apply overrides
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    config_data[key] = value
        
        # Create MCTSConfig từ dict (would need to implement proper deserialization)
        # For now, just use default và apply specific overrides
        config = DEFAULT_CONFIG
        
        if overrides:
            if 'output_dir' in overrides and overrides['output_dir']:
                config.output_dir = overrides['output_dir']
            if 'max_analysis_loops' in overrides and overrides['max_analysis_loops']:
                config.max_analysis_loops = overrides['max_analysis_loops']
            if 'max_idea_loops' in overrides and overrides['max_idea_loops']:
                config.max_idea_loops = overrides['max_idea_loops']
        
        return config
    else:
        return DEFAULT_CONFIG

def load_data_sources(data_source_paths: List[str]) -> List[Dict[str, Any]]:
    """Load data sources từ files"""
    
    data_sources = []
    
    for path in data_source_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data_sources.append(data)
                console.print(f"✅ Đã load: {path}")
        except Exception as e:
            console.print(f"❌ Lỗi load {path}: {str(e)}", style="red")
    
    return data_sources

def display_results(session):
    """Hiển thị kết quả session"""
    
    console.print("\n" + "="*80, style="bold blue")
    console.print("🎉 KẾT QUẢ PHÂN TÍCH MCTS", style="bold blue", justify="center")
    console.print("="*80, style="bold blue")
    
    # Session summary
    summary_table = Table(title="📊 Tóm tắt Session")
    summary_table.add_column("Thông tin", style="cyan")
    summary_table.add_column("Giá trị", style="white")
    
    summary_table.add_row("Session ID", session.session_id)
    summary_table.add_row("Thời gian bắt đầu", session.start_time.strftime("%Y-%m-%d %H:%M:%S"))
    summary_table.add_row("Thời gian kết thúc", session.end_time.strftime("%Y-%m-%d %H:%M:%S") if session.end_time else "Đang chạy")
    summary_table.add_row("Vòng lặp phân tích", str(session.analysis_iteration))
    summary_table.add_row("Vòng lặp ý tưởng", str(session.ideas_iteration))
    summary_table.add_row("Trạng thái", session.current_phase.value)
    
    console.print(summary_table)
    
    # Quality metrics
    if session.final_deliverables:
        quality_metrics = session.final_deliverables.get("quality_metrics", {})
        
        if quality_metrics:
            console.print("\n📈 CHẤT LƯỢNG KẾT QUẢ", style="bold green")
            
            analysis_metrics = quality_metrics.get("analysis_phase", {})
            ideas_metrics = quality_metrics.get("ideas_phase", {})
            
            metrics_table = Table()
            metrics_table.add_column("Phase", style="cyan")
            metrics_table.add_column("Điểm cuối", style="white")
            metrics_table.add_column("Cải thiện", style="green")
            metrics_table.add_column("Điểm TB", style="white")
            
            if analysis_metrics:
                metrics_table.add_row(
                    "Analysis",
                    f"{analysis_metrics.get('final_score', 0):.2f}/10",
                    f"+{analysis_metrics.get('improvement', 0):.2f}",
                    f"{analysis_metrics.get('average_score', 0):.2f}/10"
                )
            
            if ideas_metrics:
                metrics_table.add_row(
                    "Ideas",
                    f"{ideas_metrics.get('final_score', 0):.2f}/10",
                    f"+{ideas_metrics.get('improvement', 0):.2f}",
                    f"{ideas_metrics.get('average_score', 0):.2f}/10"
                )
            
            console.print(metrics_table)
        
        # Recommendations
        recommendations = session.final_deliverables.get("recommendations", [])
        if recommendations:
            console.print("\n💡 KHUYẾN NGHỊ", style="bold yellow")
            for rec in recommendations:
                console.print(f"  {rec}")
    
    # Output location
    if hasattr(session, 'session_id'):
        output_path = f"{DEFAULT_CONFIG.output_dir}/{session.session_id}"
        console.print(f"\n💾 Kết quả chi tiết đã được lưu tại: {output_path}", style="bold cyan")
        console.print(f"📄 Để xem kết quả: python main.py show-results {output_path}")

def display_session_summary(session_data):
    """Hiển thị tóm tắt session từ saved data"""
    
    console.print(Panel.fit(
        f"Session: {session_data.get('session_id', 'Unknown')}",
        title="📊 Session Summary",
        border_style="blue"
    ))
    
    # Create summary table
    table = Table(show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Start Time", session_data.get('start_time', 'Unknown'))
    table.add_row("End Time", session_data.get('end_time', 'Unknown'))
    table.add_row("Current Phase", session_data.get('current_phase', 'Unknown'))
    table.add_row("Analysis Iterations", str(session_data.get('analysis_iteration', 0)))
    table.add_row("Ideas Iterations", str(session_data.get('ideas_iteration', 0)))
    table.add_row("User Checkpoints", str(len(session_data.get('user_checkpoints', []))))
    
    console.print(table)

# Async commands đã được wrapped với @coro decorator

if __name__ == "__main__":
    cli()
