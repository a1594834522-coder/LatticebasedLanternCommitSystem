"""封装调用后端 API 的简单客户端。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from .config import load_config


class BackendClient:
    """面向前端的同步 HTTP 客户端。"""

    def __init__(self) -> None:
        cfg = load_config()
        self._base_url = cfg.backend_url.rstrip("/")
        self._headers: Dict[str, str] = {}
        if cfg.api_role:
            self._headers["X-API-Role"] = cfg.api_role
        if cfg.api_token:
            self._headers["X-API-Token"] = cfg.api_token
        self._session = httpx.Client(timeout=30.0)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self._headers)
        url = f"{self._base_url}{path}"
        response = self._session.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            message = self._format_error(response)
            raise RuntimeError(message)
        return response

    @staticmethod
    def _format_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
            detail = payload.get("detail")
        except Exception:
            detail = response.text
        return f"请求失败 ({response.status_code}): {detail}"

    def create_session(self, metadata: Optional[Dict[str, Any]] = None, verifier_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {"metadata": metadata or {}}
        if verifier_id:
            payload["verifier_id"] = verifier_id
        resp = self._request("POST", "/sessions", json=payload)
        return resp.json()

    def list_sessions(self) -> List[Dict[str, Any]]:
        resp = self._request("GET", "/sessions")
        return resp.json()

    def submit_rules(self, session_id: str, rules: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request("POST", f"/sessions/{session_id}/rules", json={"rules": rules})
        return resp.json()

    def submit_vector(self, session_id: str, vector: List[int]) -> Dict[str, Any]:
        resp = self._request("POST", f"/sessions/{session_id}/vector", json={"vector": vector})
        return resp.json()

    def submit_consent(self, session_id: str, decision: str, reason: Optional[str] = None) -> Dict[str, Any]:
        payload = {"decision": decision}
        if reason:
            payload["reason"] = reason
        resp = self._request("POST", f"/sessions/{session_id}/consent", json=payload)
        return resp.json()

    def execute_proof(self, session_id: str, seed: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"force": force}
        if seed is not None:
            payload["seed"] = seed
        resp = self._request("POST", f"/sessions/{session_id}/execute", json=payload)
        return resp.json()

    def get_session(self, session_id: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/sessions/{session_id}")
        return resp.json()

    def download_proof(self, session_id: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/sessions/{session_id}/proof")
        return resp.json()

    def stream_events(self, session_id: str) -> httpx.Response:
        return self._request("GET", f"/sessions/{session_id}/events", headers={"Accept": "text/event-stream"}, timeout=None)


_client: Optional[BackendClient] = None


def get_client() -> BackendClient:
    global _client
    if _client is None:
        _client = BackendClient()
    return _client
