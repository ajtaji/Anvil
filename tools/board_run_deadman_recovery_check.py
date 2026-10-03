#!/usr/bin/env python3
"""Desk-only deadman acknowledgement recovery over the real NetConsole."""

from __future__ import annotations

import socket
import time

import board_run


PEER = ("192.0.2.10", 5555)
ARM_REPLY = ("The deadman watchdog is armed for 15 seconds.\r\n"
             "  It covers the NEXT payload only.\r\npmf> ")
OFF_STATUS = ("The deadman watchdog is off. A payload that hangs will hang "
              "the board\r\nwith it, and getting out of that means a reset "
              "or the mains.\r\npmf> ")
ARMED_STATUS = ("The deadman watchdog is armed for 15 seconds. The next "
                "payload you\r\nrun gets a watchdog, and if it hangs the "
                "board resets itself.\r\npmf> ")


class Board:
    def __init__(self, initial: str, retry: str = "ack", unknown=False):
        self.initial = initial
        self.retry = retry
        self.unknown = unknown
        self.armed = 0
        self.sockets: list[MonitorSocket] = []

    def socket(self, _ip: str):
        sock = MonitorSocket(self, len(self.sockets))
        self.sockets.append(sock)
        return sock


class MonitorSocket:
    def __init__(self, board: Board, index: int):
        self.board = board
        self.index = index
        self.queue: list[bytes] = []
        self.commands: list[str] = []
        self.closed = False

    def settimeout(self, _seconds: float) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def say(self, text: str) -> None:
        raw = text.encode()
        self.queue.extend(raw[i:i + 11] for i in range(0, len(raw), 11))

    def sendto(self, payload: bytes, _address) -> int:
        line = payload.decode("ascii").rstrip("\r\n")
        if not line:
            self.say("\r\npmf> ")
            return len(payload)
        self.commands.append(line)
        if line == "deadman":
            if self.board.unknown and self.index == 1:
                self.say("deadman\r\n? status unavailable\r\npmf> ")
            else:
                status = ARMED_STATUS if self.board.armed == 15 else OFF_STATUS
                self.say("deadman\r\n" + status)
        elif line == "deadman 15":
            if self.index == 0:
                if self.board.initial == "lost-reply":
                    self.board.armed = 15
                elif self.board.initial == "normal":
                    self.board.armed = 15
                    self.say(line + "\r\n" + ARM_REPLY)
            elif self.board.retry == "ack":
                self.board.armed = 15
                self.say(line + "\r\n" + ARM_REPLY)
            elif self.board.retry == "lost-reply":
                self.board.armed = 15
            elif self.board.retry != "lost-command":
                raise AssertionError(self.board.retry)
        else:
            raise AssertionError(f"unexpected state-changing command: {line}")
        return len(payload)

    def recvfrom(self, _size: int):
        if self.queue:
            return self.queue.pop(0), PEER
        time.sleep(0.001)
        raise socket.timeout()


def run_case(label: str, board: Board, expected: str,
             socket_count: int, arm_count: int) -> None:
    original = board_run.NetConsole._bound_socket
    board_run.NetConsole._bound_socket = staticmethod(board.socket)
    first = None
    try:
        first = board_run.NetConsole(*PEER)
        if expected == "stop":
            try:
                board_run.arm_deadman_with_recovery(first, 15, 0.04)
            except board_run.StreamError as error:
                assert "Nothing was booted" in str(error), str(error)
            else:
                raise AssertionError(f"{label}: uncertain arm was accepted")
        else:
            current, reply, effective, detail = board_run.arm_deadman_with_recovery(
                first, 15, 0.04)
            assert effective == 15, (label, effective)
            assert detail is not None, label
            assert detail["verified_by"] == expected, (label, detail)
            assert not board_run.board_refusal(reply, "deadman 15"), label
            assert board_run.echo_pattern("deadman").search(reply.replace("\r", "")) or \
                   board_run.echo_pattern("deadman 15").search(reply.replace("\r", ""))
            current.close()
        commands = [line for sock in board.sockets for line in sock.commands]
        assert len(board.sockets) == socket_count, (label, len(board.sockets))
        assert commands.count("deadman 15") == arm_count, (label, commands)
        assert all(not line.startswith("boot") for line in commands)
        print(f"{label}: {'stopped' if expected == 'stop' else 'verified'}; "
              f"{socket_count} sockets, {arm_count} arm send(s)")
    finally:
        if first is not None:
            first.close()
        board_run.NetConsole._bound_socket = original


def main() -> None:
    assert board_run.deadman_status_seconds("deadman\r\n" + OFF_STATUS) == 0
    assert board_run.deadman_status_seconds("deadman\r\n" + ARMED_STATUS) == 15
    assert board_run.deadman_status_seconds("deadman\r\n? unknown\r\npmf> ") is None
    run_case("lost arm command, status OFF, retry ack", Board("lost-command"),
             "retry acknowledgement", 2, 2)
    run_case("lost arm reply, status armed", Board("lost-reply"),
             "status after lost arm acknowledgement", 2, 1)
    run_case("retry reply lost, final status armed",
             Board("lost-command", retry="lost-reply"),
             "status after lost retry acknowledgement", 3, 2)
    run_case("unknown first status", Board("lost-command", unknown=True),
             "stop", 2, 1)
    run_case("OFF after lost retry command",
             Board("lost-command", retry="lost-command"),
             "stop", 3, 2)
    print("board_run deadman recovery: PASS")


if __name__ == "__main__":
    main()
