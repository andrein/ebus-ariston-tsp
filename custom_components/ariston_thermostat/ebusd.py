"""Client for ebusd's direct stream mode: every bus message as a line, sends queued without waiting."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

from .protocol import StreamLine

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 1
RECONNECT_MAX = 30
CONNECT_TIMEOUT = 10
# ebusd only writes when there is bus traffic; the boiler and gateway talk every few seconds.
IDLE_TIMEOUT = 120
# A send without a message: refused as invalid when hex sending is enabled, as not authorized otherwise. Never sent.
_HEX_PROBE = "-n"


class StreamUnsupported(ConnectionError):
    """ebusd has no direct stream mode."""


class HexDisabled(ConnectionError):
    """ebusd refuses to send messages given in hex (--enablehex is missing)."""


async def _start_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # Nothing else may be written until ebusd confirms: it reads the mode switch as a single request.
    writer.write(b"direct -s\n")
    response = (await asyncio.wait_for(reader.readline(), CONNECT_TIMEOUT)).decode(errors="replace").strip()
    if response != "direct mode started":
        # An ebusd without the direct stream mode answers the usage text.
        raise StreamUnsupported(f"direct stream mode not supported: {response}")


async def check(host: str, port: int) -> None:
    """Raise OSError, TimeoutError or ConnectionError unless ebusd streams and sends hex messages."""
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
    try:
        await _start_stream(reader, writer)
        writer.write(f"{_HEX_PROBE}\n".encode())
        async with asyncio.timeout(CONNECT_TIMEOUT):
            while raw := await reader.readline():
                text = raw.decode(errors="replace").strip()
                if text.startswith(f"{_HEX_PROBE}:"):
                    if text.endswith("not authorized"):
                        raise HexDisabled("hex sending disabled")
                    return
        raise ConnectionError("closed by ebusd")
    finally:
        writer.close()


class EbusdStream:
    def __init__(
        self,
        host: str,
        port: int,
        on_line: Callable[[StreamLine], None],
        on_rejected: Callable[[str], None],
        on_gap: Callable[[], None],
        on_connection: Callable[[bool], None],
    ) -> None:
        self._host = host
        self._port = port
        self._on_line = on_line
        self._on_rejected = on_rejected
        self._on_gap = on_gap
        self._on_connection = on_connection
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._run(), name="ebusd direct stream")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def send(self, message: str) -> bool:
        """Queue a message given as ZZPBSBNN[DD]*; its outcome arrives as a stream line."""
        if self._writer is None or self._writer.is_closing():
            _LOGGER.debug("not connected, dropped %s", message)
            return False
        self._writer.write(f"{message}\n".encode())
        return True

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while True:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
                )
                await self._handshake(reader, writer)
                delay = RECONNECT_MIN
                await self._stream(reader)
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, ConnectionError, ValueError) as err:
                _LOGGER.warning("ebusd direct stream at %s:%s: %s", self._host, self._port, err)
            except Exception:
                _LOGGER.exception("ebusd direct stream failed")
            finally:
                if self._writer is not None:
                    self._writer = None
                    self._on_connection(False)
                if writer is not None:
                    writer.close()
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    async def _handshake(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _start_stream(reader, writer)
        self._writer = writer
        self._on_connection(True)

    async def _stream(self, reader: asyncio.StreamReader) -> None:
        while raw := await asyncio.wait_for(reader.readline(), IDLE_TIMEOUT):
            text = raw.decode(errors="replace").strip()
            if not text:
                continue
            try:
                if line := StreamLine.parse(text):
                    self._on_line(line)
                elif text.startswith("ERR: ") and text.endswith(" messages lost"):
                    _LOGGER.warning("ebusd direct stream: %s", text)
                    self._on_gap()
                else:
                    self._on_rejected(text)
            except Exception:
                _LOGGER.exception("handling %s failed", text)
        raise ConnectionError("closed by ebusd")
