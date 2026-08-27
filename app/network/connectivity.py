"""Network connectivity check utilities."""

import socket
import httpx
from typing import Tuple

def check_internet_connection(timeout: float = 2.0) -> bool:
    """Checks if external internet access is available via socket probe."""
    hosts_to_probe = ["8.8.8.8", "1.1.1.1"]
    for host in hosts_to_probe:
        try:
            socket.setdefaulttimeout(timeout)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, 53))
            s.close()
            return True
        except Exception:
            continue
    return False

def check_http_endpoint(url: str, timeout: float = 2.0) -> Tuple[bool, int, str]:
    """Sends a fast GET request to check HTTP endpoint status."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            return (resp.status_code == 200, resp.status_code, resp.text)
    except Exception as e:
        return (False, 0, str(e))
