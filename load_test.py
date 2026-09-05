"""
Concurrency load test for the multiplayer game server.

Most tic-tac-toe WebSocket demos are shown with exactly one game, one
pair of players. This test proves the server actually handles many
independent, simultaneous game rooms correctly at once — the property
that actually matters for a real-time backend (a chat app or multiplayer
game server is worthless if it silently breaks past 2 concurrent
sessions).

Spins up N rooms, each with 2 simulated players, has them play a full
game to completion concurrently, and verifies every room reaches a
correct, independent final state with no cross-room interference.

Run against a live server:
    uvicorn main:app --host 127.0.0.1 --port 8000 &
    python load_test.py --rooms 50
"""
import asyncio
import json
import argparse
import time
import websockets
import websockets.exceptions


RECV_TIMEOUT = 15  # seconds to wait for any single expected message


async def next_state(ws, predicate):
    """Read messages from ws, skipping anything that isn't a 'state' message
    matching `predicate`, and return the first one that does.

    Draining by content rather than by a fixed count keeps this correct
    regardless of how handshake/broadcast messages interleave under high
    concurrency — the fixed-count drain this replaced would desync and
    deadlock past ~50 simultaneous rooms.
    """
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") == "state" and predicate(msg):
            return msg


async def play_full_game(uri_base: str, room_id: str, results: dict, connect_sem: asyncio.Semaphore):
    """Two simulated players play a deterministic game to a known outcome
    (X wins via top row: positions 0,1,2) in a given room."""
    moves = [
        ("p1", 0), ("p2", 3),
        ("p1", 1), ("p2", 4),
        ("p1", 2),   # p1 (X) wins top row
    ]

    ws1 = ws2 = None
    try:
        # Throttle *connection setup* only. The OS listen backlog is bounded
        # (kern.ipc.somaxconn is 128 on macOS), so opening 2*N sockets in one
        # burst makes the kernel drop SYNs well before the server is the
        # bottleneck. Once connected, all rooms still play fully concurrently.
        async with connect_sem:
            ws1 = await websockets.connect(f"{uri_base}/ws/{room_id}")
            ws2 = await websockets.connect(f"{uri_base}/ws/{room_id}")

        conns = {"p1": ws1, "p2": ws2}

        # Wait until both connections have seen a state with both players in.
        both_joined = lambda s: len(s.get("players_connected", [])) == 2
        await next_state(ws1, both_joined)
        await next_state(ws2, both_joined)

        final_state = None
        for player, position in moves:
            await conns[player].send(json.dumps({"type": "move", "position": position}))
            # Both connections should see a state where this cell is now filled.
            filled = lambda s, pos=position: s["board"][pos] != ""
            await next_state(ws2 if player == "p1" else ws1, filled)
            final_state = await next_state(conns[player], filled)

        results[room_id] = {
            "game_over": final_state.get("game_over"),
            "winner": final_state.get("winner"),
            "board": final_state.get("board"),
        }
    except (asyncio.TimeoutError, OSError, websockets.exceptions.WebSocketException) as e:
        results[room_id] = {"game_over": None, "winner": None, "board": None, "error": repr(e)}
    finally:
        for ws in (ws1, ws2):
            if ws is not None:
                await ws.close()


async def run_load_test(num_rooms: int, host: str, port: int, connect_concurrency: int):
    uri_base = f"ws://{host}:{port}"
    results = {}
    connect_sem = asyncio.Semaphore(connect_concurrency)

    start = time.time()
    tasks = [
        play_full_game(uri_base, f"loadtest-room-{i}", results, connect_sem)
        for i in range(num_rooms)
    ]
    await asyncio.gather(*tasks)
    elapsed = time.time() - start

    correct = sum(
        1 for r in results.values()
        if r["game_over"] is True and r["winner"] == "X" and r["board"] == ["X", "X", "X", "O", "O", "", "", "", ""]
    )

    print(f"Rooms run concurrently: {num_rooms}")
    print(f"Rooms with correct, independent final state: {correct}/{num_rooms}")
    print(f"Total wall-clock time: {elapsed:.2f}s")
    if correct != num_rooms:
        print("FAILURE: some rooms did not reach the expected correct state.")
        for room_id, r in results.items():
            if not (r["game_over"] is True and r["winner"] == "X"):
                print(f"  {room_id}: {r}")
    else:
        print("PASS: every concurrent room reached the correct outcome independently.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rooms", type=int, default=25)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--connect-concurrency", type=int, default=50,
                        help="max simultaneous connection handshakes (keeps the "
                             "burst under the OS listen backlog)")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.rooms, args.host, args.port, args.connect_concurrency))
