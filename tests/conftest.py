import os
import sys
from pathlib import Path

# Force mock mode BEFORE the app is imported: environment variables beat .env.
os.environ["MOCK_AI"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
