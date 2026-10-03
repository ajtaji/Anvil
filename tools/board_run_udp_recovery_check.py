#!/usr/bin/env python3
"""Desk-only UDP loss proof for board_run's read-only preflight recovery.

The real NetConsole runs over scripted socket instances. One loses the
command entirely; another receives the command but loses its prompt-ended
reply after the echo. Each must use exactly one fresh peer and one retry.
"""

from __future__ import annotations

import socket
import time

import board_run


PEER = ("192.0.2.10", 5555)


class ScriptedSocket:
    def __init__(self, behavior: str):
        self.behavior = behavior
        self.queue: list[bytes] = []
        self.commands: list[str] = []
        self.closed = False

    def settimeout(self, _seconds: float) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def sendto(self, payload: bytes, _address) -> int:
        line = payload.decode("ascii").rstrip("\r\n")
        if not line:
            self.queue.append(b"\r\npmf> ")
        else:
            self.commands.append(line)
            if self.behavior == "echo-only":
                self.queue.extend((line[:3].encode(),
                                   line[3:].encode() + b"\r\n"))
            elif self.behavior == "good":
                answer = ("Anvil build 244" if line == "version" else
                          "stage a file at 00800000")
                data = f"{line}\r\n{answer}\r\npmf> ".encode()
                self.queue.extend(data[i:i + 7] for i in range(0, len(data), 7))
        return len(payload)

    def recvfrom(self, _size: int):
        if self.queue:
            return self.queue.pop(0), PEER
        time.sleep(0.001)
        raise socket.timeout()


def scenario(line: str, first_behavior: str, bytes_expected: bool,
             echo_expected: bool) -> None:
    sockets = [ScriptedSocket(first_behavior), ScriptedSocket("good")]
    opened: list[ScriptedSocket] = []
    original = board_run.NetConsole._bound_socket

    def bound(_ip: str) -> ScriptedSocket:
        result = sockets[len(opened)]
        opened.append(result)
        return result

    board_run.NetConsole._bound_socket = staticmethod(bound)
    try:
        first = board_run.NetConsole(*PEER)
        current, response, detail = board_run.read_only_command_with_recovery(
            first, line, 0.04)
        assert current is not first
        assert len(opened) == 2, opened
        assert opened[0].commands == [line]
        assert opened[1].commands == [line]
        assert opened[0].closed
        assert detail is not None
        assert (detail["first_received_bytes"] > 0) is bytes_expected
        assert detail["first_echo_seen"] is echo_expected
        assert board_run.echo_pattern(line).search(response.replace("\r", ""))
        assert board_run.PROMPT_RE.search(response.replace("\r", ""))
        assert "[host: " in "".join(current.transcript)
        current.close()
    finally:
        board_run.NetConsole._bound_socket = original
    print(f"{line} / {first_behavior}: one fresh-console retry, full reply")


def no_stateful_retry() -> None:
    sock = ScriptedSocket("good")
    original = board_run.NetConsole._bound_socket
    board_run.NetConsole._bound_socket = staticmethod(lambda _ip: sock)
    try:
        console = board_run.NetConsole(*PEER)
        for line in ("net recv 5001 800000", "deadman 15", "boot mem 800000"):
            try:
                board_run.read_only_command_with_recovery(console, line, 0.04)
            except ValueError:
                pass
            else:
                raise AssertionError(f"state-changing command accepted: {line}")
        assert not sock.commands
        console.close()
    finally:
        board_run.NetConsole._bound_socket = original
    print("state-changing commands: retry helper rejects without sending")


def retry_is_bounded() -> None:
    sockets = [ScriptedSocket("drop"), ScriptedSocket("drop")]
    opened: list[ScriptedSocket] = []
    original = board_run.NetConsole._bound_socket

    def bound(_ip: str) -> ScriptedSocket:
        result = sockets[len(opened)]
        opened.append(result)
        return result

    board_run.NetConsole._bound_socket = staticmethod(bound)
    try:
        first = board_run.NetConsole(*PEER)
        try:
            board_run.read_only_command_with_recovery(first, "version", 0.04)
        except board_run.StreamError as error:
            assert "one read-only retry also failed" in str(error)
            assert "0 bytes" in str(error) and "echo not seen" in str(error)
        else:
            raise AssertionError("two lost commands were accepted")
        assert len(opened) == 2
        assert [s.commands for s in opened] == [["version"], ["version"]]
        assert opened[1].closed
        first.close()
    finally:
        board_run.NetConsole._bound_socket = original
    print("two losses: stops after the one permitted retry")


def main() -> None:
    scenario("version", "drop", False, False)
    scenario("map", "echo-only", True, True)
    retry_is_bounded()
    no_stateful_retry()
    print("board_run UDP recovery: PASS")


if __name__ == "__main__":
    main()
