"""End-to-end smoke test over the actual WebSocket endpoint (two simulated
players): create room, join, start game, and play whatever the host's first
legal move is. Run with `python -m backend.smoke_ws_test`.
"""
from fastapi.testclient import TestClient

from .main import app


def main():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as guest_ws:
        host_ws.send_json({"type": "create_room", "name": "Host"})
        joined = host_ws.receive_json()
        assert joined["type"] == "joined", joined
        room_code = joined["room"]
        print("room created:", room_code)
        host_ws.receive_json()  # initial state broadcast

        guest_ws.send_json({"type": "join_room", "room": room_code, "name": "Guest"})
        joined2 = guest_ws.receive_json()
        assert joined2["type"] == "joined", joined2
        guest_ws.receive_json()  # state for guest
        host_ws.receive_json()  # state rebroadcast to host after guest joins

        host_ws.send_json({"type": "start_game"})
        host_state = host_ws.receive_json()
        guest_state = guest_ws.receive_json()
        assert host_state["type"] == "state" and host_state["started"], host_state
        print("game started. turn player:", host_state["turn_player_id"])
        print("table top:", host_state["table_top"])

        # Figure out whose turn it is and play their first legal card if any.
        turn_id = host_state["turn_player_id"]
        acting_ws = host_ws if turn_id == host_state["players"][0]["id"] else guest_ws
        acting_state = host_state if acting_ws is host_ws else guest_state
        hand = acting_state["your_hand"]
        legal_cards = acting_state["legal_cards"]
        print("acting player hand:", hand, "legal cards:", legal_cards)

        if legal_cards:
            card = legal_cards[0]
            acting_ws.send_json({"type": "play_cards", "cards": [card]})
            resp1 = acting_ws.receive_json()
            resp2 = (guest_ws if acting_ws is host_ws else host_ws).receive_json()
            print("after play, log tail:", resp1.get("log", [])[-3:])
        else:
            print("no legal move for acting player at round start (unlikely but not an error)")

    print("\nWebSocket smoke test passed.")


if __name__ == "__main__":
    main()
