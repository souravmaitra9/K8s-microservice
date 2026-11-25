import httpx

from agent.settings import Settings


class ToolError(Exception):
    pass


class ToolClient:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self._settings = settings
        self._http = http

    def invoke(self, name: str, arguments: dict) -> str:
        try:
            response = self._call(name, arguments)
        except httpx.HTTPError as exc:
            raise ToolError("tool unreachable") from exc
        if response.status_code >= 400:
            raise ToolError("tool returned an error")
        if len(response.content) > 1_000_000:
            raise ToolError("tool response too large")
        return response.text

    def _call(self, name: str, arguments: dict) -> httpx.Response:
        if name == "kb_search":
            query = arguments.get("query", "")
            if not isinstance(query, str) or not query.strip() or len(query) > 200:
                raise ToolError("invalid query")
            return self._http.get(
                f"{self._settings.kb_url.rstrip('/')}/v1/search",
                params={"q": query},
            )
        if name == "ticket_create":
            title = arguments.get("title")
            severity = arguments.get("severity")
            summary = arguments.get("summary")
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
                raise ToolError("invalid title")
            if severity not in {"sev1", "sev2", "sev3", "sev4"}:
                raise ToolError("invalid severity")
            if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 2000:
                raise ToolError("invalid summary")
            return self._http.post(
                f"{self._settings.tickets_url.rstrip('/')}/v1/tickets",
                json={"title": title.strip(), "severity": severity, "summary": summary.strip()},
            )
        raise ToolError("unknown tool")
