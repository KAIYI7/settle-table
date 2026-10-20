"""Data models for SettleTable Bounded Notion Reporting."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NotionExportConfig:
    """Configuration for exporting a meal to Notion."""
    token: str
    parent_id: str  # Page UUID or Database UUID
    parent_type: str = 'page_id'  # 'page_id' or 'database_id'
    mode: str = 'compact'  # 'compact' (default, <= 40 blocks) or 'detailed'
    api_version: str = '2022-06-28'


@dataclass(frozen=True)
class NotionExportResult:
    """Result of exporting a meal to Notion."""
    ok: bool
    status: str  # 'completed', 'already_exported', 'failed'
    page_id: str | None = None
    page_url: str | None = None
    error: str | None = None
    blocks_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'ok': self.ok,
            'status': self.status,
            'page_id': self.page_id,
            'page_url': self.page_url,
            'error': self.error,
            'blocks_created': self.blocks_created,
        }
