import os
import httpx
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# URL base do Map-Service principal
MAP_SERVICE_URL = os.environ.get("MAP_SERVICE_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "dragao_secret_key_2026")
_parsed_base = urlparse(MAP_SERVICE_URL)


import re

def _build_safe_url(path: str) -> str:
    """Construct a URL ensuring the host always matches the configured MAP_SERVICE_URL."""
    # Ensure the path is a relative path starting with '/' and only contains safe characters
    if not path.startswith("/"):
        path = "/" + path
    if not re.match(r"^/[a-zA-Z0-9_\-\.\/]+$", path) or ".." in path:
        raise ValueError(f"Potential directory traversal or invalid path: '{path}'")
    url = f"{MAP_SERVICE_URL}{path}"
    parsed = urlparse(url)
    if parsed.hostname != _parsed_base.hostname or parsed.port != _parsed_base.port:
        raise ValueError(f"Potential SSRF: unexpected host in URL '{url}'")
    return url


async def call_map_service(method: str, path: str, json: dict | None = None) -> dict:
    """
    Faz uma chamada HTTP ao Map-Service principal.

    Args:
        method: Método HTTP ("GET", "POST", "PUT", "DELETE")
        path:   Caminho da API, ex: "/nodes" ou "/nodes/N1"
        json:   Corpo do pedido (para POST/PUT)

    Returns:
        dict com a resposta do serviço

    Raises:
        httpx.HTTPStatusError: se o serviço devolver um erro HTTP
        httpx.ConnectError: se o serviço não estiver acessível
    """
    url = _build_safe_url(path)
    timeout = 60.0 if "/batch" in path else 10.0
    headers = {"X-API-Key": API_KEY}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, json=json, headers=headers)
        response.raise_for_status()
        # DELETE pode não ter corpo
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()


async def check_map_service_health() -> dict:
    """Verifica se o Map-Service está acessível."""
    try:
        url = _build_safe_url("/map")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            return {
                "reachable": True,
                "status_code": response.status_code,
                "url": MAP_SERVICE_URL,
            }
    except Exception as e:
        return {
            "reachable": False,
            "error": str(e),
            "url": MAP_SERVICE_URL,
        }
