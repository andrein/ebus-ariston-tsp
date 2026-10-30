import asyncio
from collections import deque

from conftest import ebusd
import pytest


class FakeEbusd:
    """Answers the stream mode switch like ebusd, then writes the given lines and answers sends until idle."""

    def __init__(self, greeting="direct mode started", lines=(), hex_reply="ERR: invalid argument"):
        self.greeting = greeting
        self.lines = lines
        self.hex_reply = hex_reply
        self.received = []
        self.connections = 0

    async def handle(self, reader, writer):
        self.connections += 1
        await reader.readline()
        writer.write(f"{self.greeting}\n".encode())
        for line in self.lines:
            writer.write(f"{line}\n".encode())
        await writer.drain()
        try:
            while raw := await asyncio.wait_for(reader.readline(), 0.2):
                text = raw.decode().strip()
                self.received.append(text)
                writer.write(f"{self.hex_reply if text == '-n' else text + ':done broadcast'}\n".encode())
        except TimeoutError:
            pass
        writer.close()


async def serve(fake):
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_stream_delivers_lines_and_gaps_and_reconnects(monkeypatch):
    monkeypatch.setattr(ebusd, "RECONNECT_MIN", 0.05)
    fake = FakeEbusd(lines=["37fe2000027118", "ERR: 3 messages lost"])
    lines, gaps, connection = [], [], []

    async def run():
        server, port = await serve(fake)
        stream = ebusd.EbusdStream("127.0.0.1", port, lines.append, lambda: gaps.append(1), connection.append)
        stream.start()
        while fake.connections < 2:
            await asyncio.sleep(0.01)
        assert stream.send("-s 70 fe2010057118dc0000")
        assert stream.send("-s 70 fe203b0175")
        await asyncio.sleep(0.05)
        await stream.stop()
        server.close()

    asyncio.run(run())
    assert [line.frame.data.hex() for line in lines[:1]] == ["7118"]
    assert gaps[:1] == [1]
    assert connection[:3] == [True, False, True]
    assert fake.received[-2:] == ["-s 70 fe2010057118dc0000", "-s 70 fe203b0175"]


@pytest.mark.parametrize(
    ("fake", "error"),
    [
        (FakeEbusd(greeting="usage: direct"), ebusd.StreamUnsupported),
        (FakeEbusd(hex_reply="-n:ERR: hex command not enabled"), ebusd.HexDisabled),
        (FakeEbusd(), None),
    ],
)
def test_check_needs_the_stream_mode_and_hex_sending(fake, error):
    async def run():
        server, port = await serve(fake)
        try:
            await ebusd.check("127.0.0.1", port)
        finally:
            server.close()

    if error is None:
        asyncio.run(run())
    else:
        with pytest.raises(error):
            asyncio.run(run())


class Recorder:
    def __init__(self):
        self.lines, self.gaps = [], 0
        self.stream = ebusd.EbusdStream("127.0.0.1", 0, self.lines.append, self.gap, None)

    def gap(self):
        self.gaps += 1

    def connect(self):
        self.writer = FakeWriter()
        self.stream._writer = self.writer

    def kinds(self):
        return [(line.kind, line.frame.data.hex(), line.error) for line in self.lines]


class FakeWriter:
    def __init__(self):
        self.written = b""

    def is_closing(self):
        return False

    def write(self, data):
        self.written += data


def test_messages_are_sent_one_at_a_time():
    recorder = Recorder()
    recorder.connect()
    recorder.stream.send("-s 70 FE2010057118DC0000")
    recorder.stream.send("-s 70 fe203b0175")
    assert recorder.writer.written == b"-s 70 fe2010057118dc0000\n"
    recorder.stream._handle("-s 70 fe2010057118dc0000:done broadcast", 1.0)
    assert recorder.writer.written.endswith(b"-s 70 fe203b0175\n")


def test_own_messages_are_told_apart_and_errors_fail_the_message_sent():
    recorder = Recorder()
    stream = recorder.stream
    recorder.connect()
    stream.send("-s 70 fe2010057118dc0000")
    stream.send("-s 70 fe203b0175")
    stream._handle("37fe2000027118", 1.0)
    stream._handle("70fe2010057118dc0000", 1.1)
    stream._handle("-s 70 fe2010057118dc0000:done broadcast", 1.1)
    stream._handle("313c2000025917 0400112233", 1.2)
    stream._handle("ERR: arbitration lost", 1.3)
    assert recorder.kinds() == [
        ("r", "7118", None),
        ("s", "7118dc0000", None),
        ("r", "5917", None),
        ("e", "75", "arbitration lost"),
    ]
    assert recorder.lines[2].frame.destination == 0x3C
    assert stream._queue == deque()


def test_lost_lines_are_a_gap():
    recorder = Recorder()
    recorder.stream._handle("ERR: 2 messages lost", 1.0)
    assert recorder.gaps == 1
    assert recorder.lines == []


def test_lines_that_are_no_message_are_ignored():
    recorder = Recorder()
    recorder.stream._handle("37fe20000371", 1.0)
    recorder.stream._handle("direct mode started", 1.0)
    recorder.stream._handle("ERR: invalid argument", 1.0)
    assert recorder.lines == []


def test_a_message_without_source_is_refused():
    recorder = Recorder()
    recorder.connect()
    with pytest.raises(ValueError):
        recorder.stream.send("fe203b0175")
