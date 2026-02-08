from __future__ import annotations

import asyncio
import base64
from typing import Any

from models import ExecutionResult, PageSnapshot


class BrowserController:
    """Wrapper for Stagehand/Browserbase with a safe local fallback."""

    def __init__(
        self,
        browserbase_api_key: str = "",
        browserbase_project_id: str = "",
        model_api_key: str = "",
        stagehand_model_name: str = "anthropic/claude-sonnet-4-5",
        stagehand_timeout_sec: float = 12.0,
        enable_stagehand: bool = False,
    ) -> None:
        self.browserbase_api_key = browserbase_api_key
        self.browserbase_project_id = browserbase_project_id
        self.model_api_key = model_api_key
        self.stagehand_model_name = stagehand_model_name
        self.stagehand_timeout_sec = stagehand_timeout_sec
        self.enable_stagehand = enable_stagehand

        self.current_url = "about:blank"
        self.session_id: str | None = None
        self.live_view_url: str | None = None
        self.cdp_url: str | None = None
        self._mode = "stub"
        self._stagehand = None
        self._session = None
        self._browserbase = None

    @property
    def mode(self) -> str:
        return self._mode

    async def start(self) -> None:
        if not self.enable_stagehand:
            self._mode = "stub"
            return

        if not self.browserbase_api_key or not self.browserbase_project_id:
            self._mode = "stub"
            return

        try:
            stagehand_module = __import__("stagehand")
            async_cls = getattr(stagehand_module, "AsyncStagehand", None)
            if async_cls is None:
                self._mode = "stub"
                return

            self._stagehand = async_cls(
                browserbase_api_key=self.browserbase_api_key,
                browserbase_project_id=self.browserbase_project_id,
                model_api_key=self.model_api_key or None,
            )

            if hasattr(self._stagehand, "start"):
                await asyncio.wait_for(self._stagehand.start(), timeout=self.stagehand_timeout_sec)

            sessions = getattr(self._stagehand, "sessions", None)
            if sessions is None:
                self._mode = "stub"
                return

            self._session = await asyncio.wait_for(
                self._start_session(sessions),
                timeout=self.stagehand_timeout_sec,
            )
            self._mode = "stagehand" if self._session is not None else "stub"
            if self._mode == "stagehand":
                self.session_id = self._extract_session_id(self._session)
                self.cdp_url = self._extract_cdp_url(self._session)
                await self._populate_live_view_url()
        except Exception:
            self._mode = "stub"

    async def shutdown(self) -> None:
        if self._mode == "stagehand":
            try:
                if self._session is not None and hasattr(self._session, "end"):
                    await asyncio.wait_for(self._session.end(), timeout=self.stagehand_timeout_sec)
            except Exception:
                pass
            try:
                if self._stagehand is not None and hasattr(self._stagehand, "close"):
                    await asyncio.wait_for(self._stagehand.close(), timeout=self.stagehand_timeout_sec)
            except Exception:
                pass

    async def navigate(self, url: str) -> ExecutionResult:
        if self._mode != "stagehand" or self._session is None:
            await asyncio.sleep(0.4)
            self.current_url = url
            return ExecutionResult(success=True, message="Stub navigation complete.", current_url=url)

        try:
            await self._call_session(self._session.navigate, [{"url": url}, {"input": f"Navigate to {url}"}, {}])
            # Session responses do not expose playwright page url directly; track target url locally.
            self.current_url = url
            return ExecutionResult(success=True, message="Navigation complete.", current_url=url)
        except Exception as exc:
            return ExecutionResult(success=False, message=f"Navigation failed: {exc}", current_url=self.current_url)

    async def act(self, instruction: str) -> ExecutionResult:
        if self._mode != "stagehand" or self._session is None:
            await asyncio.sleep(0.2)
            return ExecutionResult(success=True, message=f"Stub action executed: {instruction}", current_url=self.current_url)

        try:
            await self._call_session(self._session.act, [{"input": instruction}, {"action": instruction}, {}])
            current_url = self.current_url
            return ExecutionResult(success=True, message="Action executed.", current_url=current_url)
        except Exception as exc:
            return ExecutionResult(success=False, message=f"Action failed: {exc}", current_url=self.current_url)

    async def extract(self, instruction: str) -> ExecutionResult:
        if self._mode != "stagehand" or self._session is None:
            await asyncio.sleep(0.2)
            return ExecutionResult(
                success=True,
                message="Stub extract complete.",
                current_url=self.current_url,
                extracted_data={"result": "stub", "instruction": instruction},
            )

        try:
            data = await self._call_session(
                self._session.extract,
                [{"instruction": instruction}, {"input": instruction}, {}],
                return_last=True,
            )
            current_url = self.current_url
            return ExecutionResult(
                success=True,
                message="Extract complete.",
                current_url=current_url,
                extracted_data=data,
            )
        except Exception as exc:
            return ExecutionResult(success=False, message=f"Extract failed: {exc}", current_url=self.current_url)

    async def _start_session(self, sessions: Any) -> Any:
        if hasattr(sessions, "start"):
            return await self._call_session(
                sessions.start,
                [{"model_name": self.stagehand_model_name}, {"model": self.stagehand_model_name}, {}],
                return_last=True,
            )
        if hasattr(sessions, "create"):
            return await self._call_session(
                sessions.create,
                [{"model_name": self.stagehand_model_name}, {}],
                return_last=True,
            )
        return None

    async def capture_page_state(self) -> PageSnapshot:
        snapshot = PageSnapshot(current_url=self.current_url)
        if self._mode != "stagehand" or self._session is None:
            return snapshot

        structured = await self._extract_structured_page_signals()
        if structured:
            snapshot.title = structured.get("title")
            snapshot.visible_text_excerpt = structured.get("visible_text_excerpt")
            snapshot.form_fields = structured.get("form_fields") or []
            snapshot.payment_amount = structured.get("payment_amount")
            snapshot.payee_entity = structured.get("payee_entity")
            snapshot.urgency_signals = structured.get("urgency_signals") or []

        cdp_state = await self._capture_via_cdp()
        if cdp_state:
            snapshot.current_url = cdp_state.get("current_url") or self.current_url
            snapshot.title = cdp_state.get("title") or snapshot.title
            snapshot.dom_excerpt = cdp_state.get("dom_excerpt") or snapshot.dom_excerpt
            snapshot.screenshot_b64 = cdp_state.get("screenshot_b64")

        return snapshot

    async def extract_payment_details(self) -> dict[str, str]:
        if self._mode != "stagehand" or self._session is None:
            return {"amount": "", "payee": ""}

        schema = {
            "type": "object",
            "properties": {
                "amount": {"type": "string"},
                "payee": {"type": "string"},
            },
            "required": ["amount", "payee"],
        }
        payload = await self._extract_with_schema(
            "Extract the payment amount and payee name shown on this page. "
            "If unavailable, return empty strings.",
            schema,
        )
        return {
            "amount": str(payload.get("amount", "") or "").strip(),
            "payee": str(payload.get("payee", "") or "").strip(),
        }

    def _extract_session_id(self, session: Any) -> str | None:
        sid = getattr(session, "id", None)
        if isinstance(sid, str) and sid:
            return sid

        if hasattr(session, "model_dump"):
            try:
                data = session.model_dump()
                if isinstance(data, dict):
                    if isinstance(data.get("id"), str):
                        return data.get("id")
                    payload = data.get("data") or {}
                    if isinstance(payload, dict):
                        for key in ("session_id", "sessionId"):
                            value = payload.get(key)
                            if isinstance(value, str) and value:
                                return value
            except Exception:
                return None
        return None

    def _extract_cdp_url(self, session: Any) -> str | None:
        if hasattr(session, "model_dump"):
            try:
                data = session.model_dump()
                if isinstance(data, dict):
                    payload = data.get("data") or {}
                    if isinstance(payload, dict):
                        for key in ("cdp_url", "cdpUrl"):
                            value = payload.get(key)
                            if isinstance(value, str) and value:
                                return value
            except Exception:
                return None
        return None

    async def _populate_live_view_url(self) -> None:
        if not self.session_id or not self.browserbase_api_key:
            return
        try:
            if self._browserbase is None:
                browserbase_module = __import__("browserbase")
                client_cls = getattr(browserbase_module, "Browserbase", None)
                if client_cls is None:
                    return
                self._browserbase = client_cls(api_key=self.browserbase_api_key)

            debug_data = await asyncio.to_thread(self._browserbase.sessions.debug, self.session_id)
            dump = debug_data.model_dump() if hasattr(debug_data, "model_dump") else {}
            if isinstance(dump, dict):
                live_url = dump.get("debuggerFullscreenUrl") or dump.get("debuggerUrl")
                if isinstance(live_url, str) and live_url:
                    self.live_view_url = live_url
        except Exception:
            self.live_view_url = None

    async def _extract_structured_page_signals(self) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "visible_text_excerpt": {"type": "string"},
                "form_fields": {"type": "array", "items": {"type": "string"}},
                "payment_amount": {"type": "string"},
                "payee_entity": {"type": "string"},
                "urgency_signals": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "title",
                "visible_text_excerpt",
                "form_fields",
                "payment_amount",
                "payee_entity",
                "urgency_signals",
            ],
        }
        return await self._extract_with_schema(
            "Extract page safety context: page title, visible text excerpt (max 400 chars), "
            "form field labels, payment amount if visible, payee/service name, "
            "and urgency signals like 'act now', countdown, suspension warnings.",
            schema,
        )

    async def _extract_with_schema(self, instruction: str, schema: dict[str, Any]) -> dict[str, Any]:
        if self._mode != "stagehand" or self._session is None:
            return {}
        try:
            response = await self._session.extract(instruction=instruction, schema=schema)
            data = response.model_dump() if hasattr(response, "model_dump") else {}
            result = (data.get("data") or {}).get("result") if isinstance(data, dict) else None
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    async def _capture_via_cdp(self) -> dict[str, str] | None:
        if not self.cdp_url:
            return None
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(self.cdp_url)
                context = browser.contexts[0] if browser.contexts else None
                page = context.pages[0] if context and context.pages else None
                if page is None:
                    await browser.close()
                    return None

                current_url = page.url or self.current_url
                title = await page.title()
                html = await page.content()
                screenshot_bytes = await page.screenshot(type="png", full_page=False)
                await browser.close()

                return {
                    "current_url": current_url,
                    "title": title,
                    "dom_excerpt": html[:12000],
                    "screenshot_b64": base64.b64encode(screenshot_bytes).decode("ascii"),
                }
        except Exception:
            return None

    async def _call_session(self, fn: Any, attempts: list[dict[str, Any]], return_last: bool = False) -> Any:
        last_exc: Exception | None = None
        for kwargs in attempts:
            try:
                result = await fn(**kwargs)
                if return_last:
                    return result
                return None
            except TypeError as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        return None
