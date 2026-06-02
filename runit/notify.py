import sys
import subprocess
import platform

_NOTIFIED = set()


def notify(title: str, message: str):
    key = (title, message)
    if key in _NOTIFIED:
        return
    _NOTIFIED.add(key)

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                capture_output=True, timeout=5
            )
        elif system == "Linux":
            for cmd in [["notify-send", title, message],
                        ["kdialog", "--title", title, "--passivepopup", message, "5"],
                        ["zenity", "--notification", "--text", f"{title}: {message}"]]:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=5)
                    break
                except FileNotFoundError:
                    continue
        elif system == "Windows":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        pass


def notify_install(package: str, project_type: str):
    msg = f"Installing {package} for {project_type} project..."
    print(f"  \U0001f4e6 {msg}")
    notify("Runit", msg)


def notify_done(success: bool, project_name: str):
    if success:
        notify("Runit", f"\u2705 {project_name} started successfully!")
    else:
        notify("Runit", f"\u274c {project_name} failed after all retries.")
