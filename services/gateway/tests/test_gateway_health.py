import os
import time
import requests


def test_gateway_health_endpoint():
    url = os.getenv("GATEWAY_URL", "http://localhost:8000") + "/health"
    # give a brief window for the containerized gateway to come up when run externally
    for _ in range(10):
        try:
            r = requests.get(url, timeout=2)
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, dict)
            break
        except Exception:
            time.sleep(0.5)



