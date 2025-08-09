"""
Setup script for MCTS - Multi-Agent Critical Thinking System
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="mcts-system",
    version="2.0.0",
    author="MCTS Team",
    author_email="team@mcts.ai",
    description="Multi-Agent Critical Thinking System - Hệ thống Tư duy Phản biện Tăng cường Đa Tác nhân",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mcts-team/mcts-system",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
            "myst-parser>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "mcts=main:cli",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["prompts/*.txt", "*.md", "*.json"],
    },
    keywords=[
        "artificial intelligence",
        "multi-agent systems", 
        "critical thinking",
        "startup analysis",
        "idea generation",
        "market research",
        "llm",
        "gemini",
        "automation"
    ],
    project_urls={
        "Bug Reports": "https://github.com/mcts-team/mcts-system/issues",
        "Source": "https://github.com/mcts-team/mcts-system",
        "Documentation": "https://mcts-system.readthedocs.io/",
    },
)
