# main.py
import subprocess
import sys
from pathlib import Path

# Set root folder for the project & app path
project_root = Path(__file__).resolve().parent.parent
app_path = project_root / "app" / "home_page.py"

# Launch Streamlit
subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)])