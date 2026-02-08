from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse


COMMON_MULTI_LABEL_SUFFIXES = {
    "co.uk",
    "com.au",
    "co.in",
    "co.jp",
    "com.br",
    "com.mx",
}


class DomainVerifier:
    def __init__(self, api_key: str, enabled: bool = False) -> None:
        self.enabled = enabled and bool(api_key)
        self._client: Any = None

        if not self.enabled:
            return

        try:
            from exa_py import Exa

            self._client = Exa(api_key)
        except Exception:
            self._client = None
            self.enabled = False

    async def verify_service_domain(self, service_name: str, current_url: str) -> dict[str, Any]:
        current_domain = self._normalize_domain_from_url(current_url)
        if not self.enabled or self._client is None:
            return {
                "checked": False,
                "service_name": service_name,
                "current_domain": current_domain,
                "reason": "exa_disabled",
            }

        if not service_name.strip() or not current_domain:
            return {
                "checked": False,
                "service_name": service_name,
                "current_domain": current_domain,
                "reason": "insufficient_input",
            }

        try:
            query = f"{service_name} official website"
            results = await asyncio.to_thread(self._search_sync, query)
            candidate_domains = self._extract_domains(results)
            verified_domain = candidate_domains[0] if candidate_domains else ""

            matched = bool(
                verified_domain
                and (current_domain == verified_domain or current_domain.endswith(f".{verified_domain}"))
            )

            return {
                "checked": True,
                "service_name": service_name,
                "query": query,
                "current_domain": current_domain,
                "verified_domain": verified_domain,
                "candidate_domains": candidate_domains[:5],
                "match": matched,
            }
        except Exception as exc:
            return {
                "checked": False,
                "service_name": service_name,
                "current_domain": current_domain,
                "reason": f"exa_error:{exc}",
            }

    def _search_sync(self, query: str) -> Any:
        try:
            return self._client.search(query, num_results=5, type="neural")
        except TypeError:
            return self._client.search(query, num_results=5)

    def _extract_domains(self, search_response: Any) -> list[str]:
        domains: list[str] = []
        results = getattr(search_response, "results", None)
        if results is None and isinstance(search_response, dict):
            results = search_response.get("results", [])

        for item in results or []:
            if isinstance(item, dict):
                url = item.get("url")
            else:
                url = getattr(item, "url", None)

            if not isinstance(url, str) or not url:
                continue

            domain = self._normalize_domain_from_url(url)
            if domain and domain not in domains:
                domains.append(domain)

        return domains

    def _normalize_domain_from_url(self, url: str) -> str:
        try:
            host = (urlparse(url).hostname or "").lower().strip(".")
        except Exception:
            return ""
        if not host:
            return ""
        return self._to_registrable_domain(host)

    def _to_registrable_domain(self, host: str) -> str:
        parts = host.split(".")
        if len(parts) <= 2:
            return host

        tail_two = ".".join(parts[-2:])
        if tail_two in COMMON_MULTI_LABEL_SUFFIXES and len(parts) >= 3:
            return ".".join(parts[-3:])
        return tail_two
