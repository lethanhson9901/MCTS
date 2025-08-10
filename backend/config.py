"""
Cấu hình hệ thống MCTS (Multi-Agent Critical Thinking System)
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

load_dotenv()

@dataclass
class LLMConfig:
    """Cấu hình cho LLM API"""
    url: str = "http://localhost:8000/v1/chat/completions"
    model: str = "gemini-2.5-pro"
    api_key: str = "sk-1234"
    max_tokens: int = 4000
    temperature: float = 0.7
    timeout: int = 60

@dataclass
class AgentWeights:
    """Trọng số cho hệ thống điểm số"""
    tinh_kha_thi: float = 2.0
    tiem_nang_thi_truong: float = 2.5
    tinh_sang_tao: float = 1.5
    mo_hinh_kinh_doanh: float = 2.0
    loi_the_canh_tranh: float = 2.0
    rui_ro_ky_thuat: float = 1.5
    dau_tu_ban_dau: float = 1.2

@dataclass
class MCTSConfig:
    """Cấu hình chính cho hệ thống MCTS"""
    
    # Cấu hình LLM
    llm: LLMConfig = field(default_factory=LLMConfig)
    
    # Cấu hình vòng lặp
    max_analysis_loops: int = 3
    max_idea_loops: int = 4
    
    # Ngưỡng dừng
    quality_threshold: float = 9.0
    improvement_threshold: float = 0.05  # 5%
    red_flag_threshold: float = 3.0
    
    # Trọng số điểm số
    weights: AgentWeights = field(default_factory=AgentWeights)
    
    # Vai trò AE-LLM (ít nhất 2)
    adversarial_roles: List[str] = field(default_factory=lambda: ["VC", "Kỹ_sư", "Đối_thủ", "Marketing", "Pháp_lý"])
    
    # Cấu hình ESV
    enable_external_validation: bool = True
    search_timeout: int = 30
    
    # Logging
    log_level: str = "INFO"
    save_intermediate_results: bool = True
    output_dir: str = "results"
    
    def __post_init__(self):
        """Xác thực cấu hình sau khi khởi tạo"""
        if len(self.adversarial_roles) < 2:
            raise ValueError("Cần ít nhất 2 vai trò cho AE-LLM")
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

# Cấu hình mặc định toàn cục
DEFAULT_CONFIG = MCTSConfig()

# Mapping vai trò AE-LLM
ADVERSARIAL_ROLE_MAPPING = {
    "VC": "Nhà đầu tư mạo hiểm",
    "Kỹ_sư": "Kỹ sư trưởng", 
    "Đối_thủ": "Đối thủ cạnh tranh",
    "Marketing": "Chuyên gia Marketing",
    "Pháp_lý": "Chuyên gia Pháp lý"
}

# Tiêu chí đánh giá mặc định
EVALUATION_CRITERIA = {
    "analysis": [
        "tinh_logic",
        "toan_dien", 
        "nhat_quan",
        "bang_chung",
        "do_sau"
    ],
    "ideas": [
        "tinh_kha_thi",
        "tiem_nang_thi_truong", 
        "tinh_sang_tao",
        "mo_hinh_kinh_doanh",
        "loi_the_canh_tranh",
        "rui_ro_ky_thuat",
        "dau_tu_ban_dau"
    ]
}

# Mapping giữa tên tiếng Việt và field names
CRITERIA_NAME_MAPPING = {
    # Analysis criteria
    "tính logic": "tinh_logic",
    "tính toàn diện": "toan_dien", 
    "tính nhất quán": "nhat_quan",
    "bằng chứng": "bang_chung",
    "độ sâu": "do_sau",
    
    # Ideas criteria
    "tính khả thi": "tinh_kha_thi",
    "tiềm năng thị trường": "tiem_nang_thi_truong",
    "tính sáng tạo": "tinh_sang_tao", 
    "mô hình kinh doanh": "mo_hinh_kinh_doanh",
    "lợi thế cạnh tranh": "loi_the_canh_tranh",
    "rủi ro kỹ thuật": "rui_ro_ky_thuat",
    "đầu tư ban đầu": "dau_tu_ban_dau"
}

# Prompt templates directory
PROMPTS_DIR = "prompts"
