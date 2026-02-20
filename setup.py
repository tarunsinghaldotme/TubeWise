"""
setup.py — Makes TubeWise installable as a system-wide CLI command
===================================================================
After running 'pip install .' (or 'pip install -e .'), you can use TubeWise
from anywhere on your system by simply typing:

    tubewise "https://www.youtube.com/watch?v=VIDEO_ID"

No need to:
- cd into the project folder
- Activate the virtual environment
- Type 'python agent.py'

HOW IT WORKS:
- setuptools registers 'tubewise' as a console script
- It creates a small executable wrapper in your system PATH
- That wrapper automatically uses the right Python environment
  and calls the main() function from agent.py

INSTALLATION:
    # Option 1: Install in development mode (changes to code take effect immediately)
    pip install -e .

    # Option 2: Install as a package (need to reinstall after code changes)
    pip install .

AFTER INSTALLATION:
    # Run from anywhere on your system:
    tubewise "https://www.youtube.com/watch?v=VIDEO_ID"
    tubewise "https://www.youtube.com/watch?v=VIDEO_ID" --no-notion
    tubewise --show-config
"""

from setuptools import setup, find_packages

setup(
    # ── Package metadata ──
    name="tubewise",
    version="1.0.0",
    description="🧠 TubeWise — Get wise from any YouTube video. AI-powered video summarizer.",
    author="Tarun",

    # ── Tell setuptools where to find the Python files ──
    # py_modules: List individual .py files (since we don't have a package folder)
    # This tells setuptools to include these files when installing
    py_modules=[
        "agent",
        "config",
        "transcript",
        "summarizer",
        "notion_publisher",
        "prompts",
        "models",
        "playlist",
        "queue_manager",
        "worker",
        "logging_config",
    ],

    # ── Dependencies ──
    # These get installed automatically when you run 'pip install .'
    # Same as requirements.txt but integrated into the install process
    install_requires=[
        "langchain>=0.3.0",
        "langchain-aws>=0.2.0",
        "langchain-community>=0.3.0",
        "langchain-text-splitters>=0.3.0",
        "boto3>=1.34.0",
        "youtube-transcript-api>=0.6.2",
        "yt-dlp>=2024.0.0",
        "notion-client>=2.2.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
    ],

    # ── Optional dev dependencies ──
    extras_require={
        "dev": [
            "pytest>=7.0",
        ],
    },

    # ══════════════════════════════════════════════════════════
    # THIS IS THE KEY PART — Console Script Entry Point
    # ══════════════════════════════════════════════════════════
    # This tells setuptools:
    #   "Create a command called 'tubewise' that, when run,
    #    calls the main() function from the agent module"
    #
    # Format: "command_name = module:function"
    #
    # After installation, typing 'tubewise' in terminal is equivalent to:
    #   python -c "from agent import main; main()"
    #
    # The wrapper script handles:
    #   - Finding the right Python interpreter
    #   - Setting up the module path
    #   - Calling your main() function
    # ══════════════════════════════════════════════════════════
    entry_points={
        "console_scripts": [
            "tubewise=agent:main",
            # ↑ command  ↑ module:function
            # "tubewise" = what you type in terminal
            # "agent"    = the agent.py file
            # "main"     = the main() function inside agent.py
        ],
    },

    # ── Python version requirement ──
    python_requires=">=3.9",
)