from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, Set

try:
    import websockets
    from websockets.server import WebSocketServerProtocol, serve
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    WebSocketServerProtocol = Any  # type: ignore[assignment,misc]
    serve = None  # type: ignore[assignment]

from .base import TelemetrySink


@dataclass
class LiveEvent:
    """A telemetry event with sequence number and timestamp."""
    seq: int
    event: str
    ts: str
    payload: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WebSocketTelemetrySink(TelemetrySink):
    """Telemetry sink that broadcasts events to connected WebSocket clients.

    Implements the TelemetrySink protocol and streams events in real-time
    to any connected browser clients.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        buffer_size: int = 1000,
    ) -> None:
        if not HAS_WEBSOCKETS:
            raise ImportError(
                "websockets package is required for WebSocketTelemetrySink. "
                "Install it with: pip install websockets"
            )
        self.host = host
        self.port = port
        self._clients: Set[WebSocketServerProtocol] = set()
        self._buffer: Deque[LiveEvent] = deque(maxlen=buffer_size)
        self._seq = 0
        self._server: Any = None
        self._server_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._client_locks: Dict[WebSocketServerProtocol, asyncio.Lock] = {}
        self._agent_profiles: Dict[str, Dict[str, Any]] = {}
        self._agent_timers: Dict[str, Dict[str, Any]] = {}
        self._broadcast_queue: asyncio.Queue[LiveEvent] = asyncio.Queue()
        self._broadcaster_task: asyncio.Task[None] | None = None
        self._on_client_connect: Callable[[WebSocketServerProtocol], None] | None = None

    def emit(self, event: str, payload: dict | None = None) -> None:
        """Emit an event to all connected clients."""
        data = payload or {}
        ts = datetime.now(timezone.utc).isoformat()
        live_event = LiveEvent(seq=self._seq, event=event, ts=ts, payload=data)
        self._seq += 1
        self._buffer.append(live_event)

        # Track agent profiles for initial state
        if event == "agent.spawned":
            profile = data.get("profile")
            if isinstance(profile, dict):
                agent_id = profile.get("agent_id")
                if agent_id:
                    self._agent_profiles[agent_id] = dict(profile)
                    session = data.get("session")
                    if session:
                        self._agent_profiles[agent_id]["session"] = session

        # Track timer state
        if event == "timer.started":
            agent_id = data.get("agent_id")
            if agent_id:
                self._agent_timers[agent_id] = {
                    "duration_ms": data.get("duration_ms"),
                    "tick_seconds": data.get("tick_seconds"),
                    "started_at": data.get("started_at"),
                    "ms_left": data.get("duration_ms"),
                    "status": "active",
                }

        if event == "timer.tick":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agent_timers:
                self._agent_timers[agent_id]["ms_left"] = data.get("ms_left")

        if event == "timer.expired":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agent_timers:
                self._agent_timers[agent_id]["status"] = "expired"
                self._agent_timers[agent_id]["ms_left"] = 0

        if event == "agent.death":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agent_timers:
                self._agent_timers[agent_id]["status"] = "dead"

        # Queue for async broadcast
        try:
            self._broadcast_queue.put_nowait(live_event)
        except asyncio.QueueFull:
            pass  # Drop if queue is full

    async def start_server(self) -> None:
        """Start the WebSocket server."""
        if not HAS_WEBSOCKETS or serve is None:
            raise ImportError("websockets package is required")

        self._server = await serve(
            self._handle_client,
            self.host,
            self.port,
        )
        self._broadcaster_task = asyncio.create_task(self._broadcast_loop())

    async def stop_server(self) -> None:
        """Stop the WebSocket server."""
        if self._broadcaster_task:
            self._broadcaster_task.cancel()
            try:
                await self._broadcaster_task
            except asyncio.CancelledError:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Close all client connections
        if self._clients:
            await asyncio.gather(
                *(client.close() for client in self._clients),
                return_exceptions=True,
            )
            self._clients.clear()
            self._client_locks.clear()

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a new WebSocket client connection."""
        self._clients.add(websocket)
        try:
            # Send initial state snapshot
            await self._send_initial_state(websocket)

            if self._on_client_connect:
                self._on_client_connect(websocket)

            # Keep connection alive and handle incoming messages
            async for message in websocket:
                # Handle any client messages (e.g., ping, requests)
                await self._handle_client_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            self._client_locks.pop(websocket, None)

    async def _send_initial_state(self, websocket: WebSocketServerProtocol) -> None:
        """Send initial state snapshot to newly connected client."""
        snapshot = {
            "type": "initial_state",
            "agents": self._agent_profiles,
            "timers": self._agent_timers,
            "recent_events": [e.as_dict() for e in self._buffer],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await self._safe_send(websocket, json.dumps(snapshot))

    async def _handle_client_message(
        self, websocket: WebSocketServerProtocol, message: str
    ) -> None:
        """Handle incoming messages from clients."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "ping":
                await self._safe_send(websocket, json.dumps({"type": "pong"}))
            elif msg_type == "request_state":
                await self._send_initial_state(websocket)
        except json.JSONDecodeError:
            pass

    async def _broadcast_loop(self) -> None:
        """Background task to broadcast events to all clients."""
        while True:
            try:
                event = await self._broadcast_queue.get()
                if self._clients:
                    message = json.dumps({
                        "type": "event",
                        **event.as_dict(),
                    })
                    await asyncio.gather(
                        *(self._safe_send(client, message) for client in self._clients),
                        return_exceptions=True,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                # Never let broadcasting errors crash the loop
                pass

    async def _safe_send(self, websocket: WebSocketServerProtocol, message: str) -> None:
        """Serialize writes per connection to avoid concurrent send errors."""
        lock = self._client_locks.get(websocket)
        if lock is None:
            lock = asyncio.Lock()
            self._client_locks[websocket] = lock
        async with lock:
            await websocket.send(message)

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)

    @property
    def buffered_events(self) -> int:
        """Number of events in the buffer."""
        return len(self._buffer)


__all__ = ["WebSocketTelemetrySink", "LiveEvent"]
