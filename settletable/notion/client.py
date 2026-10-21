"""Notion API client protocols and implementations for SettleTable."""
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

NOTION_ID_REGEX = re.compile(r'^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$')
TOKEN_REDACT_REGEX = re.compile(r'(secret_|ntn_)[A-Za-z0-9_-]{10,}')


class NotionError(Exception):
    """Base error for Notion operations."""
    pass


class NotionAuthError(NotionError):
    """Authentication or permission error with Notion API."""
    pass


class NotionRateLimitError(NotionError):
    """Rate limit exceeded on Notion API."""
    pass


class NotionNotFoundError(NotionError):
    """Target parent page or database not found."""
    pass


class NotionValidationError(NotionError):
    """Invalid payload or property structure."""
    pass


def sanitize_notion_error_message(msg: str) -> str:
    """Scrub Notion tokens and Authorization headers from error strings."""
    s = TOKEN_REDACT_REGEX.sub(r'\1[REDACTED]', msg)
    s = re.sub(r'(Bearer\s+)[A-Za-z0-9_-]+', r'\1[REDACTED]', s, flags=re.IGNORECASE)
    s = re.sub(r'"token"\s*:\s*"[^"]+"', r'"token":"[REDACTED]"', s)
    return s


class NotionClientProtocol(Protocol):
    """Protocol for Notion API clients."""

    def create_page(
        self,
        token: str,
        parent: dict[str, Any],
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a page in Notion."""
        ...

    def append_block_children(
        self,
        token: str,
        block_id: str,
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Append block children to a page or block in Notion."""
        ...

    def query_block_children(
        self,
        token: str,
        block_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve block children for a block."""
        ...


class NotionHttpClient:
    """Standard library HTTP client for the Notion REST API.
    
    Hardcodes the base URL to https://api.notion.com/v1/ to prevent SSRF.
    Enforces bounded retries (sleep <= 2.0s) to prevent WSGI worker starvation.
    """

    BASE_URL = "https://api.notion.com/v1"

    def __init__(self, api_version: str = "2022-06-28", timeout_seconds: float = 8.0):
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        token: str,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json",
            "User-Agent": "SettleTable/1.0",
        }
        body_bytes = json.dumps(data).encode("utf-8") if data is not None else None

        retries = 0
        while True:
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as err:
                status = err.code
                err_body_raw = err.read().decode("utf-8", errors="replace")
                err_msg = ""
                try:
                    err_json = json.loads(err_body_raw)
                    err_msg = err_json.get("message", err_body_raw)
                except Exception:
                    err_msg = err_body_raw

                clean_msg = sanitize_notion_error_message(err_msg)

                if status == 429 or status == 503:
                    retry_after_hdr = err.headers.get("Retry-After")
                    sleep_s = 1.0
                    if retry_after_hdr:
                        try:
                            sleep_s = float(retry_after_hdr)
                        except ValueError:
                            sleep_s = 1.0

                    if retries < max_retries and sleep_s <= 2.0:
                        retries += 1
                        time.sleep(sleep_s)
                        continue
                    raise NotionRateLimitError(f"Notion rate limit exceeded: {clean_msg}") from None

                if status in (401, 403):
                    raise NotionAuthError(f"Notion authentication error ({status}): {clean_msg}") from None
                if status == 404:
                    raise NotionNotFoundError(f"Notion resource not found ({status}): {clean_msg}") from None
                if status == 400:
                    raise NotionValidationError(f"Notion validation error (400): {clean_msg}") from None

                raise NotionError(f"Notion API error ({status}): {clean_msg}") from None
            except urllib.error.URLError as err:
                clean_err = sanitize_notion_error_message(str(err.reason))
                raise NotionError(f"Network error communicating with Notion: {clean_err}") from None
            except Exception as err:
                clean_err = sanitize_notion_error_message(str(err))
                raise NotionError(f"Unexpected error communicating with Notion: {clean_err}") from None

    def create_page(
        self,
        token: str,
        parent: dict[str, Any],
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parent": parent,
            "properties": properties,
        }
        if children:
            payload["children"] = children
        return self._request(token, "POST", "pages", payload)

    def append_block_children(
        self,
        token: str,
        block_id: str,
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {"children": children}
        return self._request(token, "PATCH", f"blocks/{block_id}/children", payload)

    def query_block_children(
        self,
        token: str,
        block_id: str,
        *,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve block children for a block, handling Notion API cursor pagination."""
        all_results: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(max_pages):
            endpoint = f"blocks/{block_id}/children?page_size=100"
            if cursor:
                endpoint += f"&start_cursor={cursor}"
            res = self._request(token, "GET", endpoint)
            results = res.get("results", [])
            all_results.extend(results)
            if not res.get("has_more") or not res.get("next_cursor"):
                break
            cursor = res.get("next_cursor")
        return all_results


class MockNotionClient:
    """In-memory deterministic Notion client for air-gapped testing and CI.
    
    Validates exact Notion REST API constraints:
    - Asserts parent_id matches UUID format.
    - Asserts parent_type == 'page_id' receives only 'title' property.
    - Asserts table blocks contain valid children matching table_width.
    """

    def __init__(self):
        self.pages: dict[str, dict[str, Any]] = {}
        self.blocks: dict[str, list[dict[str, Any]]] = {}
        self._next_id = 1
        self._forced_error: tuple[type[Exception], str] | None = None
        self._rate_limit_attempts = 0

    def set_forced_error(self, err_type: type[Exception], message: str):
        """Force the next call to raise an error."""
        self._forced_error = (err_type, message)

    def clear_forced_error(self):
        self._forced_error = None

    def create_page(
        self,
        token: str,
        parent: dict[str, Any],
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self._forced_error:
            err_type, msg = self._forced_error
            self._forced_error = None
            raise err_type(msg)

        # Validate parent
        parent_id = parent.get("page_id") or parent.get("database_id")
        if not parent_id or not NOTION_ID_REGEX.match(parent_id):
            raise NotionValidationError("Invalid parent_id UUID")

        # Validate page_id parent constraints
        if "page_id" in parent:
            for k in properties:
                if k != "title":
                    raise NotionValidationError(
                        f"Cannot set property '{k}' on a page with page parent. Only 'title' is permitted."
                    )

        # Validate title presence
        if "title" not in properties:
            raise NotionValidationError("Missing required 'title' property")

        # Validate children blocks
        block_count = 0
        if children:
            for blk in children:
                block_count += 1
                btype = blk.get("type")
                if btype == "table":
                    tbl = blk.get("table", {})
                    width = tbl.get("table_width", 0)
                    rows = tbl.get("children", [])
                    if width <= 0 or not rows:
                        raise NotionValidationError("Table block requires table_width > 0 and at least 1 row child")
                    for r in rows:
                        block_count += 1
                        cells = r.get("table_row", {}).get("cells", [])
                        if len(cells) != width:
                            raise NotionValidationError(
                                f"Table row has {len(cells)} cells, expected {width} (table_width)"
                            )

        page_uuid = f"11111111-2222-3333-4444-{self._next_id:012d}"
        self._next_id += 1
        page_obj = {
            "id": page_uuid,
            "url": f"https://notion.so/{page_uuid.replace('-', '')}",
            "parent": parent,
            "properties": properties,
            "_block_count": block_count,
        }
        self.pages[page_uuid] = page_obj
        if children:
            self.blocks[page_uuid] = list(children)

        # Mirror Notion API: creating a page under page parent creates a child_page block in parent
        if "page_id" in parent:
            pid = parent["page_id"]
            title_items = properties.get("title", {}).get("title", [])
            title_str = "".join(item.get("text", {}).get("content", "") for item in title_items)
            self.blocks.setdefault(pid, []).append({
                "id": page_uuid,
                "type": "child_page",
                "child_page": {"title": title_str},
            })

        return page_obj

    def append_block_children(
        self,
        token: str,
        block_id: str,
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self._forced_error:
            err_type, msg = self._forced_error
            self._forced_error = None
            raise err_type(msg)

        if block_id not in self.blocks:
            self.blocks[block_id] = []
        self.blocks[block_id].extend(children)
        return {"results": children}

    def query_block_children(
        self,
        token: str,
        block_id: str,
        *,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        if self._forced_error:
            err_type, msg = self._forced_error
            self._forced_error = None
            raise err_type(msg)
        return list(self.blocks.get(block_id, []))
