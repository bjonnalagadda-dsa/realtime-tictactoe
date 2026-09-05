# Real-Time Multiplayer Tic-Tac-Toe (WebSocket Backend)

A real-time multiplayer game backend built with FastAPI + WebSockets,
supporting multiple simultaneous game rooms with server-authoritative
game state.

## Why this project

Most CRUD/REST projects show request-response patterns. This shows a
different and important pattern: real-time, bidirectional, stateful
communication — the same underlying pattern used in chat apps, live
dashboards, collaborative editing tools, and multiplayer games, not
just this specific game.

## Stack

- **FastAPI** — web framework + WebSocket support
- **Native WebSockets** (no external real-time service) — direct
  understanding of the protocol, not just a wrapper library
- **Vanilla JS frontend** — a working, playable demo client, no framework needed

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` in **two separate browser tabs**, use the
same room code in both, and play against yourself to see real-time
state sync between two independent connections.

## What it demonstrates

- WebSocket connection lifecycle (connect, message, disconnect handling)
- Server-authoritative state (the server validates every move — a
  client can't just claim a win)
- Multi-room concurrency (many games running independently at once)
- Real-time broadcast to multiple connected clients

## Architecture

`game.py` — pure game logic and room/connection management, framework-agnostic
`main.py` — FastAPI WebSocket endpoint wiring
`static/index.html` — demo client (connects via native browser WebSocket API)

Verified end-to-end with a scripted two-player WebSocket test simulating
a full game to a win condition.

## Concurrency Load Test

A single working game is easy to fake. This includes an actual load test
proving the server correctly isolates many simultaneous, independent
games — the property that actually matters for a real-time backend.

Run it (server must be running):
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 &
python load_test.py --rooms 50
```

**Real result:**
```
Rooms run concurrently: 50
Rooms with correct, independent final state: 50/50
Total wall-clock time: 0.09s
PASS: every concurrent room reached the correct outcome independently.
```

50 concurrent rooms (100 simulated players) each play a full deterministic
game to completion, verified to reach the correct win state with zero
cross-room state leakage, in under a tenth of a second.

Push it higher with `--rooms N`. Past a few hundred simultaneous
connections opened in one burst you can hit the OS's socket accept
backlog (`kern.ipc.somaxconn`, 128 on stock macOS) and see rooms report
`TimeoutError` — that's the client-side load generator and the kernel,
not the server. `--connect-concurrency` throttles how many handshakes
are attempted at once to stay under that ceiling.

**Bugs found and fixed during this testing** (in the load test, not the
server):
- The initial version drained a *fixed count* of handshake/broadcast
  messages per connection. Past ~50 concurrent rooms the message
  interleaving shifted, the count desynced, and both sides blocked on a
  `recv()` that never came — an infinite hang with no output. Now it
  drains *by content* (skip until the expected `state` arrives) and every
  `recv()` has a timeout, so a stuck room fails loudly instead of hanging
  the whole run.
- Connection setup is now throttled with a semaphore so the test measures
  the server, not the local accept queue.
