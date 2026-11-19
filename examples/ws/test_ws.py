#!/usr/bin/env python3
"""Oxygen.WS's test: a real WebSocket client (stdlib only, no dependencies)
against a running `ws` demo server, checking the handshake, frame codec,
ping/pong, fragmentation, and that an unmasked client frame is rejected.

Independent verification matters most for a handshake computation like
this one: this checks the server's Sec-WebSocket-Accept against Python's
own hashlib.sha1 + base64, not against Oxygen's own implementation of
either (which obviously always agrees with itself).

Run (from this directory, with the Hydrogen compiler on PATH):
    hy build --release --native
    ./build/ws &
    python3 test_ws.py
"""
import base64
import hashlib
import os
import socket
import struct
import sys

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18095
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

failures = 0


def handshake(sock):
    key = base64.b64encode(os.urandom(16)).decode()
    expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    sock.sendall(
        f"GET /chat HTTP/1.1\r\nHost: l\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    reply = b""
    while b"\r\n\r\n" not in reply:
        reply += sock.recv(4096)
    accept_line = [l for l in reply.split(b"\r\n") if l.lower().startswith(b"sec-websocket-accept")][0]
    got = accept_line.split(b": ", 1)[1].decode()
    if got != expected:
        raise AssertionError(f"Sec-WebSocket-Accept mismatch: got {got}, expected {expected}")


def send_frame(sock, opcode, payload, fin=True, mask=True):
    b1 = (0x80 if fin else 0) | opcode
    n = len(payload)
    maskbit = 0x80 if mask else 0
    if n < 126:
        header = bytes([b1, maskbit | n])
    elif n < 65536:
        header = bytes([b1, maskbit | 126]) + struct.pack(">H", n)
    else:
        header = bytes([b1, maskbit | 127]) + struct.pack(">Q", n)
    if mask:
        m = os.urandom(4)
        masked = bytes(b ^ m[i % 4] for i, b in enumerate(payload))
        sock.sendall(header + m + masked)
    else:
        sock.sendall(header + payload)


def recv_frame(sock):
    b1, b2 = sock.recv(2)
    opcode = b1 & 0x0F
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", sock.recv(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", sock.recv(8))[0]
    payload = b""
    while len(payload) < n:
        payload += sock.recv(n - len(payload))
    return opcode, payload


def new_conn():
    s = socket.create_connection((HOST, PORT))
    s.settimeout(5)
    handshake(s)
    return s


def check(title, fn):
    global failures
    try:
        fn()
        print(f"PASS {title}")
    except Exception as e:
        print(f"FAIL {title}: {e}")
        failures += 1


def check_handshake():
    new_conn().close()


def check_text_echo():
    s = new_conn()
    send_frame(s, 1, b"hello")
    opcode, payload = recv_frame(s)
    assert (opcode, payload) == (1, b"hello"), (opcode, payload)
    s.close()


def check_binary_echo():
    s = new_conn()
    send_frame(s, 2, b"\x01\x02\x03\xff")
    opcode, payload = recv_frame(s)
    assert (opcode, payload) == (2, b"\x01\x02\x03\xff"), (opcode, payload)
    s.close()


def check_ping_pong():
    s = new_conn()
    send_frame(s, 9, b"ping-data")  # opcode 9 = ping
    opcode, payload = recv_frame(s)
    assert (opcode, payload) == (10, b"ping-data"), (opcode, payload)  # 10 = pong
    s.close()


def check_fragmentation():
    s = new_conn()
    send_frame(s, 1, b"frag1-", fin=False)
    send_frame(s, 0, b"frag2", fin=True)  # opcode 0 = continuation
    opcode, payload = recv_frame(s)
    assert (opcode, payload) == (1, b"frag1-frag2"), (opcode, payload)
    s.close()


def check_unmasked_rejected():
    s = new_conn()
    send_frame(s, 1, b"nomask", mask=False)
    try:
        d = s.recv(100)
        assert d == b"", f"expected EOF, got {d!r}"
    except (ConnectionResetError, OSError):
        pass  # a reset is just as acceptable as a clean EOF here
    s.close()


def check_close_handshake():
    s = new_conn()
    send_frame(s, 8, b"")  # opcode 8 = close
    opcode, _ = recv_frame(s)
    assert opcode == 8, opcode
    s.close()


check("handshake: Sec-WebSocket-Accept matches independently (hashlib + base64)", check_handshake)
check("masked text frame, echoed", check_text_echo)
check("masked binary frame, echoed", check_binary_echo)
check("ping answered with pong (not surfaced to the app)", check_ping_pong)
check("fragmented message reassembled", check_fragmentation)
check("unmasked client frame rejected (connection closed)", check_unmasked_rejected)
check("close handshake", check_close_handshake)

print()
if failures == 0:
    print("all passed")
else:
    print(f"{failures} failed")
sys.exit(failures)
