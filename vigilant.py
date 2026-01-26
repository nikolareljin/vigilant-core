#!/usr/bin/env python3
"""
VigilantCore - Unified Launcher

Usage:
    python vigilant.py web        # Start web dashboard only
    python vigilant.py qt         # Start Qt desktop app only
    python vigilant.py both       # Start both (web in background)
    python vigilant.py stop       # Stop all running instances
    python vigilant.py status     # Check running status
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PID_DIR = ROOT_DIR / ".pids"
VENV_DIR = ROOT_DIR / "venv"


def get_python() -> str:
    """Get the Python executable path."""
    if sys.platform == "win32":
        venv_python = VENV_DIR / "Scripts" / "python.exe"
    else:
        venv_python = VENV_DIR / "bin" / "python"

    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def ensure_venv() -> bool:
    """Ensure virtual environment exists and has dependencies."""
    if not VENV_DIR.exists():
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)

    python = get_python()
    pip_cmd = [python, "-m", "pip", "install", "-q", "-r", str(ROOT_DIR / "requirements.txt")]

    # Check if we need to install
    try:
        subprocess.run([python, "-c", "import flask, PySide6, ollama"],
                      capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("Installing dependencies...")
        subprocess.run(pip_cmd, check=True)

    return True


def save_pid(name: str, pid: int) -> None:
    """Save a PID to file."""
    PID_DIR.mkdir(exist_ok=True)
    (PID_DIR / f"{name}.pid").write_text(str(pid))


def get_pid(name: str) -> int | None:
    """Get a saved PID."""
    pid_file = PID_DIR / f"{name}.pid"
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def remove_pid(name: str) -> None:
    """Remove a PID file."""
    pid_file = PID_DIR / f"{name}.pid"
    if pid_file.exists():
        pid_file.unlink()


def is_process_running(pid: int) -> bool:
    """Check if a process is running."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
        except Exception:
            pass
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def stop_process(name: str) -> bool:
    """Stop a process by name."""
    pid = get_pid(name)
    if pid is None:
        return False

    if not is_process_running(pid):
        remove_pid(name)
        return False

    print(f"Stopping {name} (PID {pid})...")

    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                      capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait for graceful shutdown
            for _ in range(10):
                time.sleep(0.5)
                if not is_process_running(pid):
                    break
            else:
                # Force kill if still running
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    remove_pid(name)
    return True


def start_web(background: bool = False) -> int | None:
    """Start the web dashboard."""
    python = get_python()
    cmd = [python, "-m", "src.web_app"]

    print("Starting web dashboard at http://127.0.0.1:8765 ...")

    if background:
        if sys.platform == "win32":
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        save_pid("web", proc.pid)
        print(f"Web dashboard started in background (PID {proc.pid})")
        return proc.pid
    else:
        try:
            proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
            save_pid("web", proc.pid)
            proc.wait()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            remove_pid("web")
        return None


def start_qt() -> None:
    """Start the Qt desktop app."""
    python = get_python()
    cmd = [python, "-m", "src.main"]

    print("Starting Qt desktop app...")

    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
        save_pid("qt", proc.pid)
        proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        remove_pid("qt")


def cmd_web(args: argparse.Namespace) -> None:
    """Handle 'web' command."""
    ensure_venv()
    start_web(background=False)


def cmd_qt(args: argparse.Namespace) -> None:
    """Handle 'qt' command."""
    ensure_venv()
    start_qt()


def cmd_both(args: argparse.Namespace) -> None:
    """Handle 'both' command - start web in background, then Qt."""
    ensure_venv()
    start_web(background=True)
    time.sleep(2)  # Give web app time to start
    start_qt()


def cmd_stop(args: argparse.Namespace) -> None:
    """Handle 'stop' command."""
    stopped_any = False

    if stop_process("web"):
        print("Web dashboard stopped.")
        stopped_any = True

    if stop_process("qt"):
        print("Qt app stopped.")
        stopped_any = True

    if not stopped_any:
        print("No running VigilantCore instances found.")


def cmd_status(args: argparse.Namespace) -> None:
    """Handle 'status' command."""
    web_pid = get_pid("web")
    qt_pid = get_pid("qt")

    print("VigilantCore Status")
    print("-" * 30)

    if web_pid and is_process_running(web_pid):
        print(f"Web Dashboard: Running (PID {web_pid})")
        print(f"  URL: http://127.0.0.1:8765")
    else:
        print("Web Dashboard: Stopped")
        if web_pid:
            remove_pid("web")

    if qt_pid and is_process_running(qt_pid):
        print(f"Qt Desktop:    Running (PID {qt_pid})")
    else:
        print("Qt Desktop:    Stopped")
        if qt_pid:
            remove_pid("qt")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VigilantCore - Local AI-powered monitoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vigilant.py web      Start web dashboard
  python vigilant.py qt       Start Qt desktop app
  python vigilant.py both     Start both (web in background)
  python vigilant.py stop     Stop all instances
  python vigilant.py status   Check what's running
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Web command
    web_parser = subparsers.add_parser("web", help="Start web dashboard")
    web_parser.set_defaults(func=cmd_web)

    # Qt command
    qt_parser = subparsers.add_parser("qt", help="Start Qt desktop app")
    qt_parser.set_defaults(func=cmd_qt)

    # Both command
    both_parser = subparsers.add_parser("both", help="Start both apps")
    both_parser.set_defaults(func=cmd_both)

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop all running instances")
    stop_parser.set_defaults(func=cmd_stop)

    # Status command
    status_parser = subparsers.add_parser("status", help="Check running status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
