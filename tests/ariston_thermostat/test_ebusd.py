import asyncio

from conftest import ebusd
import pytest


class FakeEbusd:
    """Answers the stream mode switch like ebusd, then writes the given lines and closes."""

    def __init__(self, greeting="direct mode started", lines=(), hex_reply="-n: ERR: invalid argument"):
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
    fake = FakeEbusd(lines=["1000.000 r 37fe2000027118", "ERR: 3 messages lost", "ERR: arbitration lost"])
    lines, gaps, rejected, connection = [], [], [], []

    async def run():
        server, port = await serve(fake)
        stream = ebusd.EbusdStream(
            "127.0.0.1", port, lines.append, rejected.append, lambda: gaps.append(1), connection.append
        )
        stream.start()
        while fake.connections < 2:
            await asyncio.sleep(0.01)
        assert stream.send("fe2010057118dc0000")
        await asyncio.sleep(0.05)
        await stream.stop()
        server.close()

    asyncio.run(run())
    assert [line.frame.data.hex() for line in lines[:1]] == ["7118"]
    assert gaps[:1] == [1]
    assert rejected[:1] == ["ERR: arbitration lost"]
    assert connection[:3] == [True, False, True]
    assert "fe2010057118dc0000" in fake.received


@pytest.mark.parametrize(
    ("fake", "error"),
    [
        (FakeEbusd(greeting="usage: direct"), ebusd.StreamUnsupported),
        (FakeEbusd(hex_reply="-n: ERR: not authorized"), ebusd.HexDisabled),
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
