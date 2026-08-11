import sys

# Redirect stdout and stderr to a file with flush
sys.stdout = open("server_stdout.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
sys.stderr = open("server_stderr.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115

from app import app

print("Redirected stdout and starting server...")
# LAN dashboard; auth enforced by DASHBOARD_TOKEN.
app.run(host="0.0.0.0", port=8888, debug=True, use_reloader=False)  # nosec B104
