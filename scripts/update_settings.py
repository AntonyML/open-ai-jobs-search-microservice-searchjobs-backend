"""Update settings.py with ingest_service_url."""
import re

path = r"C:\DEV\open-ai-jobs-search\open-ai-jobs-search-fastapi-backend\app\core\settings.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace box-drawing chars
content = content.replace("\u2500", "-")

# Insert the new setting before Sentry
old = "    # --- Sentry -------------------------------------------------------------"
new = (
    "    # --- Microservice Ingesta ----------------------------------------------\n"
    '    ingest_service_url: str = "http://localhost:8001"\n'
    "\n"
    "    # --- Sentry -------------------------------------------------------------"
)
content = content.replace(old, new)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated settings.py")
