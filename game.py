"""
Core game state and WebSocket connection management for real-time
multiplayer Tic-Tac-Toe. Supports multiple simultaneous game rooms.
"""
from typing import Dict, List, Optional
from fastapi import WebSocket


class GameRoom:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.board: List[str] = [""] * 9
        self.players: Dict[str, WebSocket] = {}   # symbol ("X"/"O") -> websocket
        self.turn: str = "X"
        self.winner: Optional[str] = None
        self.game_over: bool = False

    def add_player(self, websocket: WebSocket) -> Optional[str]:
        if "X" not in self.players:
            self.players["X"] = websocket
            return "X"
        elif "O" not in self.players:
            self.players["O"] = websocket
            return "O"
        return None  # room full — spectator/rejected

    def remove_player(self, websocket: WebSocket):
        for symbol, ws in list(self.players.items()):
            if ws == websocket:
                del self.players[symbol]

    def reset(self):
        """Clear the board for a rematch, keeping both players connected."""
        self.board = [""] * 9
        self.turn = "X"
        self.winner = None
        self.game_over = False

    def make_move(self, symbol: str, position: int) -> bool:
        if self.game_over:
            return False
        if symbol != self.turn:
            return False
        if position < 0 or position > 8 or self.board[position] != "":
            return False

        self.board[position] = symbol
        self._check_winner()
        self.turn = "O" if self.turn == "X" else "X"
        return True

    def _check_winner(self):
        wins = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
            (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
            (0, 4, 8), (2, 4, 6),             # diagonals
        ]
        for a, b, c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                self.winner = self.board[a]
                self.game_over = True
                return
        if "" not in self.board:
            self.game_over = True  # draw, winner stays None

    def state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "winner": self.winner,
            "game_over": self.game_over,
            "players_connected": list(self.players.keys()),
        }


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}

    def get_or_create(self, room_id: str) -> GameRoom:
        if room_id not in self.rooms:
            self.rooms[room_id] = GameRoom(room_id)
        return self.rooms[room_id]

    async def broadcast(self, room: GameRoom, message: dict):
        for ws in list(room.players.values()):
            try:
                await ws.send_json(message)
            except Exception:
                pass
