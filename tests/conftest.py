import os
import sys

# Tests import main.py and analytics.py from the repository root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop('GEMINI_API_KEY', None)
