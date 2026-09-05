"""
Real-Time Multiplayer Tic-Tac-Toe — WebSocket backend.

Demonstrates real-time bidirectional communication (not just request/response
REST), server-authoritative game state, and multi-room concurrency handling —
patterns that show up in chat apps, live dashboards, and collaborative tools,
not just games.

Run:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000 in two separate browser tabs/windows to play
against yourself and see real-time sync.
"""
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from game import RoomManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Real-Time Multiplayer Tic-Tac-Toe")
manager = RoomManager()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "active_rooms": len(manager.rooms)}


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    room = manager.get_or_create(room_id)
    symbol = room.add_player(websocket)

    if symbol is None:
        await websocket.send_json({"type": "error", "message": "Room is full."})
        await websocket.close()
        return

    await websocket.send_json({"type": "assigned_symbol", "symbol": symbol})
    await manager.broadcast(room, {"type": "state", **room.state()})

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "move":
                moved = room.make_move(symbol, data.get("position"))
                if moved:
                    await manager.broadcast(room, {"type": "state", **room.state()})
                else:
                    await websocket.send_json({"type": "error", "message": "Invalid move."})

            elif msg_type == "reset":
                room.reset()
                await manager.broadcast(room, {"type": "state", **room.state()})

    except WebSocketDisconnect:
        room.remove_player(websocket)
        await manager.broadcast(room, {"type": "state", **room.state()})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
