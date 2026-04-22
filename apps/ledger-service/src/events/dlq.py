"""
Event Dead-Letter Queue (DLQ) Management

Handles failed event processing by capturing and persisting problematic messages
to a JSONL dead-letter queue. Enables replaying and diagnosing failed events.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DeadLetterMessage:
    """Represents a message that failed event listener processing."""
    event_name: str
    payload: dict[str, Any] | str
    error_type: str
    error_message: str
    timestamp: datetime
    retry_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "event_name": self.event_name,
            "payload": self.payload,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
        }


class EventDeadLetterQueue:
    """
    Manages persistence and retrieval of failed event messages.
    
    All failed events are written to reconciliation_audit_dir/dlq.jsonl
    enabling post-mortem analysis and potential replay.
    """

    DLQ_FILENAME = "event_dlq.jsonl"

    def __init__(self, audit_dir: str | None = None):
        """
        Initialize DLQ with configurable audit directory.
        
        Args:
            audit_dir: Directory for DLQ files (defaults to reconciliation_audit_dir from config)
        """
        self.audit_dir = Path(audit_dir or settings.reconciliation_audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.dlq_file = self.audit_dir / self.DLQ_FILENAME

    async def push(
        self,
        event_name: str,
        payload: dict[str, Any] | str,
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """
        Write a failed event to the dead-letter queue.
        
        Args:
            event_name: Name of the event that failed
            payload: The original event payload
            error: The exception that caused the failure
            retry_count: Number of retry attempts already made
        """
        dlq_msg = DeadLetterMessage(
            event_name=event_name,
            payload=payload,
            error_type=type(error).__name__,
            error_message=str(error),
            timestamp=datetime.now(timezone.utc),
            retry_count=retry_count,
        )
        
        try:
            with self.dlq_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dlq_msg.to_dict(), separators=(",", ":"), default=str))
                handle.write("\n")
            
            logger.warning(
                "Event pushed to DLQ",
                extra={
                    "event_name": event_name,
                    "error_type": dlq_msg.error_type,
                    "dlq_file": str(self.dlq_file),
                }
            )
        except Exception as write_error:
            logger.error(
                "Failed to write to DLQ",
                extra={
                    "event_name": event_name,
                    "write_error": str(write_error),
                }
            )

    async def get_messages(
        self,
        limit: int | None = None,
        since: datetime | None = None,
    ) -> list[DeadLetterMessage]:
        """
        Retrieve messages from the DLQ.
        
        Args:
            limit: Maximum number of messages to retrieve
            since: Only retrieve messages after this timestamp
            
        Returns:
            List of DeadLetterMessage objects
        """
        if not self.dlq_file.exists():
            return []

        messages: list[DeadLetterMessage] = []
        try:
            with self.dlq_file.open("r", encoding="utf-8") as handle:
                for line_num, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        ts = datetime.fromisoformat(data["timestamp"])
                        
                        if since and ts < since:
                            continue
                        
                        msg = DeadLetterMessage(
                            event_name=data["event_name"],
                            payload=data["payload"],
                            error_type=data["error_type"],
                            error_message=data["error_message"],
                            timestamp=ts,
                            retry_count=data.get("retry_count", 0),
                        )
                        messages.append(msg)
                        
                        if limit and len(messages) >= limit:
                            break
                    except (json.JSONDecodeError, KeyError) as parse_error:
                        logger.warning(
                            "Malformed DLQ entry",
                            extra={
                                "file": str(self.dlq_file),
                                "line": line_num,
                                "error": str(parse_error),
                            }
                        )
        except Exception as read_error:
            logger.error(
                "Failed to read DLQ",
                extra={
                    "file": str(self.dlq_file),
                    "error": str(read_error),
                }
            )

        return messages

    async def get_stats(self) -> dict[str, Any]:
        """
        Get aggregate statistics on DLQ contents.
        
        Returns:
            Dictionary with counts by event type and error type
        """
        if not self.dlq_file.exists():
            return {
                "total_messages": 0,
                "file_size_bytes": 0,
                "by_event": {},
                "by_error": {},
            }

        by_event: dict[str, int] = {}
        by_error: dict[str, int] = {}
        total = 0
        file_size = 0

        try:
            with self.dlq_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        total += 1
                        event_name = data.get("event_name", "unknown")
                        error_type = data.get("error_type", "unknown")
                        by_event[event_name] = by_event.get(event_name, 0) + 1
                        by_error[error_type] = by_error.get(error_type, 0) + 1
                    except json.JSONDecodeError:
                        pass

            file_size = self.dlq_file.stat().st_size if self.dlq_file.exists() else 0
        except Exception as e:
            logger.error("Failed to compute DLQ stats", extra={"error": str(e)})

        return {
            "total_messages": total,
            "file_size_bytes": file_size,
            "by_event": by_event,
            "by_error": by_error,
        }

    async def clear(self) -> int:
        """
        Clear the DLQ (archive for analysis first recommended).
        
        Returns:
            Number of messages cleared
        """
        if not self.dlq_file.exists():
            return 0

        # Archive the current DLQ for analysis
        archive_path = self.audit_dir / f"event_dlq_archive_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
        try:
            self.dlq_file.rename(archive_path)
            msg_count = sum(1 for line in archive_path.open() if line.strip())
            logger.info(
                "DLQ cleared and archived",
                extra={
                    "archived_to": str(archive_path),
                    "message_count": msg_count,
                }
            )
            return msg_count
        except Exception as e:
            logger.error("Failed to clear DLQ", extra={"error": str(e)})
            return 0
