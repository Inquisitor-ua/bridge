"""End-to-end smoke test over the actual WebSocket endpoint (two simulated
players): create room, join, start game, and play whatever the host's first
legal move is. Then a game against a bot, played until the bot has moved on
its own. Run with `python -m backend.smoke_ws_test`.
"""
import re

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


BOT_MOVE = re.compile(r"^Бот \S+ (кладёт|берёт|пропускает|назначает)")


def bot_game():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_bot_game", "name": "Human", "level": "easy", "bots": 1})
        joined = ws.receive_json()
        assert joined["type"] == "joined", joined
        me = joined["player_id"]
        # play along (simplest legal moves) until the bot has made a move itself
        for _ in range(200):
            st = ws.receive_json()
            if st["type"] != "state":
                continue
            assert st["started"] and len(st["players"]) == 2
            assert [p["bot_level"] for p in st["players"]] == [None, "easy"]
            bot_moves = [line for line in st["log"] if BOT_MOVE.match(line)]
            if bot_moves:
                print("bot moved:", bot_moves[0])
                break
            prompt = st["prompt"]
            if prompt and prompt["player_id"] == me:
                ws.send_json({
                    "suit": {"type": "declare_suit", "suit": "hearts"},
                    "bridge": {"type": "declare_bridge", "accept": False},
                    "jack_end": {"type": "jack_end_choice", "choice": "penalty"},
                }[prompt["kind"]])
            elif st["awaiting_continue"] and me not in st["ready_ids"]:
                ws.send_json({"type": "continue_round"})
            elif st["turn_player_id"] == me and not prompt:
                if st["can_draw"] and not st["has_played_this_turn"]:
                    ws.send_json({"type": "draw_card"})
                elif st["legal_cards"] and not st["can_pass"]:
                    ws.send_json({"type": "play_cards", "cards": [st["legal_cards"][0]]})
                else:
                    ws.send_json({"type": "pass_turn"})
        else:
            raise AssertionError("the bot never moved")
        ws.send_json({"type": "create_bot_game", "name": "Human", "level": "godlike", "bots": 1})
        err = ws.receive_json()
        assert err["type"] == "error", err
    print("Bot game over WebSocket passed.")


if __name__ == "__main__":
    main()
    bot_game()
