"""Client for ebusd's direct stream mode: every bus message as a line, sends queued without waiting."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
import logging
import time

from .protocol import Frame, StreamLine

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 1
RECONNECT_MAX = 30
CONNECT_TIMEOUT = 10
# ebusd only writes when there is bus traffic; the boiler and gateway talk every few seconds.
IDLE_TIMEOUT = 120
# A send without a message: refused as invalid when hex sending is enabled, as not authorized otherwise. Never sent.
_HEX_PROBE = "-n"
_LOST_SUFFIX = " messages lost"


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
                if text.startswith("ERR: ") and not text.endswith(_LOST_SUFFIX):
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
        # The messages sent whose outcome is not known yet, as ebusd will print them. ebusd shows a sent message on the
        # stream, and an error only once all messages sent earlier are shown, so an error belongs to the oldest one.
        self._sent: deque[str] = deque()

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
        """Queue a message given as -s QQ ZZPBSBNN[DD]*; it arrives as a stream line once sent, or as a failure."""
        if self._writer is None or self._writer.is_closing():
            _LOGGER.debug("not connected, dropped %s", message)
            return False
        option, source, data = message.lower().split()
        if option != "-s":
            raise ValueError(f"no source address in {message}")
        self._writer.write(f"{message}\n".encode())
        self._sent.append(source + data)
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
        self._sent.clear()
        self._writer = writer
        self._on_connection(True)

    async def _stream(self, reader: asyncio.StreamReader) -> None:
        while raw := await asyncio.wait_for(reader.readline(), IDLE_TIMEOUT):
            text = raw.decode(errors="replace").strip()
            if not text:
                continue
            try:
                self._handle(text, time.monotonic())
            except Exception:
                _LOGGER.exception("handling %s failed", text)
        raise ConnectionError("closed by ebusd")

    def _handle(self, text: str, now: float) -> None:
        if text.startswith("ERR: "):
            if text.endswith(_LOST_SUFFIX):
                _LOGGER.warning("ebusd direct stream: %s", text)
                # Our messages may be among the lost ones, so no error can be matched to a message any more.
                self._sent.clear()
                self._on_gap()
            elif self._sent:
                self._on_line(StreamLine(now, "e", Frame.parse(self._sent.popleft()), text))
            else:
                self._on_rejected(text)
            return
        master = text.split(" ", 1)[0]
        try:
            frame = Frame.parse(master)
        except ValueError:
            _LOGGER.debug("ignored %s", text)
            return
        if master in self._sent:
            self._sent.remove(master)
            self._on_line(StreamLine(now, "s", frame))
        else:
            self._on_line(StreamLine(now, "r", frame))
