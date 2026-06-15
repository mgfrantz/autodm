"""
Pytest configuration for DnD LLM Game backend tests.
"""
import sys
from pathlib import Path

# Add the backend directory to Python path so app module can be imported
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))