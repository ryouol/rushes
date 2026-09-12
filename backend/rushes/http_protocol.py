"""Bound header and body reception without imposing a lifetime on SSE responses."""

import logging

import h11
from uvicorn.protocols.http.h11_impl import H11Protocol

from rushes.config import settings
from rushes.security import PROJECT_BODY_ROUTE


class CallbackAccessFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn's overload response bypasses ASGI middleware entirely.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            if isinstance(path, str) and path.split("?", 1)[0].rstrip("/") == "/api/auth/google/callback":
                record.args = (client, method, path.split("?", 1)[0], version, status)
        return True


CALLBACK_ACCESS_FILTER = CallbackAccessFilter()


class ReceiveDeadlineProtocol(H11Protocol):
    header_timeout = 60
    body_timeout = 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if CALLBACK_ACCESS_FILTER not in self.access_logger.filters:
            self.access_logger.addFilter(CALLBACK_ACCESS_FILTER)
        self.header_timer = None
        self.body_timer = None

    def connection_made(self, transport):
        super().connection_made(transport)
        self.header_timer = self.loop.call_later(self.header_timeout, self.transport.close)

    def handle_events(self):
        previous = self.cycle
        super().handle_events()
        if self.cycle is not previous:
            self.cancel_timer("header_timer")
            self.cancel_timer("body_timer")
            route = PROJECT_BODY_ROUTE.fullmatch(self.scope["path"])
            duration = (
                settings().upload_timeout_seconds
                if self.scope["method"] == "POST" and route and route[1] == "upload"
                else self.body_timeout
            )
            self.body_timer = self.loop.call_later(duration, self.transport.close)
        if self.conn.their_state is h11.IDLE or (self.cycle is not None and not self.cycle.more_body):
            self.cancel_timer("body_timer")
        if self.conn.their_state is h11.IDLE and self.header_timer is None:
            self.header_timer = self.loop.call_later(self.header_timeout, self.transport.close)

    def cancel_timer(self, name):
        timer = getattr(self, name)
        if timer is not None:
            timer.cancel()
            setattr(self, name, None)

    def connection_lost(self, exc):
        self.cancel_timer("header_timer")
        self.cancel_timer("body_timer")
        super().connection_lost(exc)
