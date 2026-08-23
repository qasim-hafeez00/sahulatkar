import sys
sys.path.append("apps/notification-service")
sys.path.append("packages/shared-python")

from src.main import app

for route in app.routes:
    print(f"{route.path} {route.name}")
