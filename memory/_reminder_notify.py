import sys, subprocess

message = sys.argv[1] if len(sys.argv) > 1 else "Reminder"

try:
    subprocess.run(["notify-send", "Lessan Reminder", message], check=False)
except FileNotFoundError:
    print(f"[Lessan Reminder] {message}")

try:
    subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], check=False)
except FileNotFoundError:
    pass
