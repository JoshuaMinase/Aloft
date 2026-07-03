import subprocess
import sys
import os

# Change to the backend directory
os.chdir(r"C:\Users\Abity\OneDrive\Desktop\aloft\aloft\backend")

# Run the server
subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app", "--reload"])