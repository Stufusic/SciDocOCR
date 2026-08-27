"""LM Studio connectivity and model discovery checker."""

import httpx
from typing import List, Dict, Any, Tuple

class LMStudioChecker:
    """Checks local LM Studio instance availability and loaded models."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"):
        self.base_url = base_url.rstrip("/")

    def check_availability(self, timeout: float = 2.0) -> Tuple[bool, List[str], str]:
        """
        Queries /v1/models on LM Studio.
        Returns: (is_available, list_of_model_ids, error_message)
        """
        models_url = f"{self.base_url}/models"
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(models_url)
                if resp.status_code == 200:
                    data = resp.json()
                    model_list = [m.get("id", "default") for m in data.get("data", [])]
                    return (True, model_list, "")
                else:
                    return (False, [], f"HTTP {resp.status_code}: {resp.text}")
        except httpx.ConnectError:
            return (False, [], "LM Studio is not running or not listening on port 1234.")
        except Exception as e:
            return (False, [], str(e))
