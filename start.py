"""One-click launcher for C_manager."""
import subprocess
import time
import webbrowser
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print("🛡️  Starting C_manager - C盘守护者...")

    # Start backend
    print("  → Starting Python backend on http://localhost:8765")
    backend = subprocess.Popen(
        [sys.executable, "-m", "src.api.server"],
        cwd=ROOT,
    )
    time.sleep(2)

    # Start frontend dev server
    print("  → Starting React frontend on http://localhost:5173")
    frontend_dir = os.path.join(ROOT, "frontend")
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=frontend_dir,
        shell=True,
    )
    time.sleep(3)

    # Open browser
    print("  → Opening browser...")
    webbrowser.open("http://localhost:5173")

    print()
    print("C_manager is running!")
    print("  Backend : http://localhost:8765")
    print("  Frontend: http://localhost:5173")
    print()
    print("Press Ctrl+C to stop all processes.")

    try:
        backend.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        backend.terminate()
        frontend.terminate()
        print("Stopped.")


if __name__ == "__main__":
    main()
