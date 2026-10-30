"""Client for ebusd's direct stream mode: every bus message as a line, and messages sent one at a time."""

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
# A send without a message: refused as invalid when hex sending is enabled, as not enabled otherwise. Never sent.
_HEX_PROBE = "-n"
_HEX_DISABLED = "ERR: hex command not enabled"
_LOST_SUFFIX = " messages lost"
# ebusd answers every send once it is done with the bus, within seconds even when arbitration keeps failing; without
# an answer the connection is stuck and nothing else would be sent.
SEND_TIMEOUT = 15


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
                if _is_answer(text):
                    if text.endswith(_HEX_DISABLED):
                        raise HexDisabled("hex sending disabled")
                    return
        raise ConnectionError("closed by ebusd")
    finally:
        writer.close()


def _is_answer(text: str) -> bool:
    """Whether a line is ebusd's answer to a send: the message and its result, or only an error."""
    return not text.endswith(_LOST_SUFFIX) and (":" in text or text.startswith("ERR: "))


class EbusdStream:
    def __init__(
        self,
        host: str,
        port: int,
        on_line: Callable[[StreamLine], None],
        on_gap: Callable[[], None],
        on_connection: Callable[[bool], None],
    ) -> None:
        self._host = host
        self._port = port
        self._on_line = on_line
        self._on_gap = on_gap
        self._on_connection = on_connection
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None
        # The messages to send, the first one sent and waiting for ebusd's answer when _sent_at is set.
        self._queue: deque[str] = deque()
        self._sent_at: float | None = None
        self._sources: set[str] = set()

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
        """Queue a message given as -s QQ ZZPBSBNN[DD]*; it arrives as a stream line once sent, or fails."""
        if self._writer is None or self._writer.is_closing():
            _LOGGER.debug("not connected, dropped %s", message)
            return False
        option, source, _ = message.lower().split()
        if option != "-s":
            raise ValueError(f"no source address in {message}")
        self._sources.add(source)
        self._queue.append(message.lower())
        self._send_next()
        return True

    def _send_next(self) -> None:
        # ebusd reads one request at a time: a second line before the answer would be joined with the first.
        if self._sent_at is None and self._queue and self._writer is not None:
            self._writer.write(f"{self._queue[0]}\n".encode())
            self._sent_at = time.monotonic()

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
        self._queue.clear()
        self._sent_at = None
        self._writer = writer
        self._on_connection(True)

    async def _stream(self, reader: asyncio.StreamReader) -> None:
        while raw := await asyncio.wait_for(reader.readline(), IDLE_TIMEOUT):
            text = raw.decode(errors="replace").strip()
            if not text:
                continue
            now = time.monotonic()
            try:
                self._handle(text, now)
            except Exception:
                _LOGGER.exception("handling %s failed", text)
            if self._sent_at is not None and now - self._sent_at > SEND_TIMEOUT:
                raise ConnectionError(f"no answer to {self._queue[0]}")
        raise ConnectionError("closed by ebusd")

    def _handle(self, text: str, now: float) -> None:
        if _is_answer(text):
            self._answered(text, now)
            return
        if text.endswith(_LOST_SUFFIX):
            _LOGGER.warning("ebusd direct stream: %s", text)
            self._on_gap()
            return
        master = text.split(" ", 1)[0]
        try:
            frame = Frame.parse(master)
        except ValueError:
            _LOGGER.debug("ignored %s", text)
            return
        self._on_line(StreamLine(now, "s" if master[:2] in self._sources else "r", frame))

    def _answered(self, text: str, now: float) -> None:
        if self._sent_at is None:
            _LOGGER.debug("ignored %s", text)
            return
        message = self._queue.popleft()
        self._sent_at = None
        if "ERR: " in text:
            _, source, data = message.split()
            error = text[text.index("ERR: ") + 5 :]
            self._on_line(StreamLine(now, "e", Frame.parse(source + data), error))
        self._send_next()
