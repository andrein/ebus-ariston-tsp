import asyncio

from conftest import ebusd
import pytest


class FakeEbusd:
    """Answers the stream mode switch like ebusd, then writes the given lines and closes."""

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
                if text == "-n":
                    writer.write(f"{self.hex_reply}\n".encode())
        except TimeoutError:
            pass
        writer.close()


async def serve(fake):
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_stream_delivers_lines_gaps_and_rejections_and_reconnects(monkeypatch):
    monkeypatch.setattr(ebusd, "RECONNECT_MIN", 0.05)
    fake = FakeEbusd(lines=["37fe2000027118", "ERR: 3 messages lost", "ERR: arbitration lost"])
    lines, gaps, rejected, connection = [], [], [], []

    async def run():
        server, port = await serve(fake)
        stream = ebusd.EbusdStream(
            "127.0.0.1", port, lines.append, rejected.append, lambda: gaps.append(1), connection.append
        )
        stream.start()
        while fake.connections < 2:
            await asyncio.sleep(0.01)
        assert stream.send("-s 70 fe2010057118dc0000")
        await asyncio.sleep(0.05)
        await stream.stop()
        server.close()

    asyncio.run(run())
    assert [line.frame.data.hex() for line in lines[:1]] == ["7118"]
    assert gaps[:1] == [1]
    assert rejected[:1] == ["ERR: arbitration lost"]
    assert connection[:3] == [True, False, True]
    assert "-s 70 fe2010057118dc0000" in fake.received


@pytest.mark.parametrize(
    ("fake", "error"),
    [
        (FakeEbusd(greeting="usage: direct"), ebusd.StreamUnsupported),
        (FakeEbusd(hex_reply="ERR: not authorized"), ebusd.HexDisabled),
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
        self.lines, self.rejected, self.gaps = [], [], 0
        self.stream = ebusd.EbusdStream("127.0.0.1", 0, self.lines.append, self.rejected.append, self.gap, None)

    def gap(self):
        self.gaps += 1

    def connect(self):
        self.stream._writer = FakeWriter()

    def kinds(self):
        return [(line.kind, line.frame.data.hex(), line.error) for line in self.lines]


class FakeWriter:
    def __init__(self):
        self.written = b""

    def is_closing(self):
        return False

    def write(self, data):
        self.written += data


def test_own_messages_are_told_apart_and_errors_go_to_the_oldest_send():
    recorder = Recorder()
    recorder.connect()
    stream = recorder.stream
    stream.send("-s 70 FE2010057118DC0000")
    stream.send("-s 70 fe203b0175")
    stream._handle("37fe2000027118", 1.0)
    stream._handle("70fe2010057118dc0000", 1.1)
    stream._handle("313c2000025917 0400112233", 1.2)
    stream._handle("ERR: arbitration lost", 1.3)
    assert recorder.kinds() == [
        ("r", "7118", None),
        ("s", "7118dc0000", None),
        ("r", "5917", None),
        ("e", "75", "ERR: arbitration lost"),
    ]
    assert recorder.lines[2].frame.destination == 0x3C


def test_after_lost_lines_errors_cannot_be_matched():
    recorder = Recorder()
    recorder.connect()
    recorder.stream.send("-s 70 fe203b0175")
    recorder.stream._handle("ERR: 2 messages lost", 1.0)
    recorder.stream._handle("ERR: expired", 1.1)
    assert recorder.gaps == 1
    assert recorder.lines == []
    assert recorder.rejected == ["ERR: expired"]


def test_lines_that_are_no_message_are_ignored():
    recorder = Recorder()
    recorder.stream._handle("37fe20000371", 1.0)
    recorder.stream._handle("direct mode started", 1.0)
    assert recorder.lines == [] and recorder.rejected == []


def test_a_message_without_source_is_refused():
    recorder = Recorder()
    recorder.connect()
    with pytest.raises(ValueError):
        recorder.stream.send("fe203b0175")
