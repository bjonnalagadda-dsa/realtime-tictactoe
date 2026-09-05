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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json

from game import RoomManager

app = FastAPI(title="Real-Time Multiplayer Tic-Tac-Toe")
manager = RoomManager()


@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html") as f:
        return f.read()


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
            if data.get("type") == "move":
                position = data.get("position")
                moved = room.make_move(symbol, position)
                if moved:
                    await manager.broadcast(room, {"type": "state", **room.state()})
                else:
                    await websocket.send_json({"type": "error", "message": "Invalid move."})
    except WebSocketDisconnect:
        room.remove_player(websocket)
        await manager.broadcast(room, {"type": "state", **room.state()})


app.mount("/static", StaticFiles(directory="static"), name="static")
