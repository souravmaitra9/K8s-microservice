import secrets
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class Ticket:
    id: str
    title: str
    severity: str
    summary: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "summary": self.summary,
        }


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, Ticket] = {}

    def add(self, title: str, severity: str, summary: str) -> Ticket:
        with self._lock:
            for _ in range(5):
                ticket_id = "INC-" + secrets.token_hex(4)
                if ticket_id not in self._items:
                    ticket = Ticket(ticket_id, title, severity, summary)
                    self._items[ticket_id] = ticket
                    return ticket
        raise RuntimeError("could not allocate a ticket id")

    def get(self, ticket_id: str) -> Ticket | None:
        with self._lock:
            return self._items.get(ticket_id)
