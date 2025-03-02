
from flask import Flask
from socketio import Server as SocketIOServer, WSGIApp as SocketIOWSGIApp

from re import split as re_split
from random import randrange, shuffle

import generate_html
import playing_cards

app = Flask(__name__, static_url_path="", static_folder="model")
sio = SocketIOServer()
app.wsgi_app = SocketIOWSGIApp(sio, app.wsgi_app)

MAX_PLAYERS_PER_LOBBY = 4
players = {}
lobbies = {}


def normalize(original_string):
    return "".join(re_split(r"[^0-9A-Za-z_\-]", original_string))


def get_player_by_name(player_name, lobby=None):
    if lobby is None:
        for player in players:
            if players[player]["name"] == player_name:
                return players[player]
    else:
        for player in lobby["players"]:
            if players[player]["name"] == player_name:
                return players[player]
    return None


def set_next_turn_index(lobby):
    for i in range(len(lobby["player_order"]) - 1):
        lobby["whose_turn_index"] = (lobby["whose_turn_index"] + 1) % len(lobby["player_order"])
        if len(players[lobby["player_order"][lobby["whose_turn_index"]]]["hand"]) > 0:
            return True
    return False


def deal_shuffled_deck(lobby):
    deck = playing_cards.deck()
    shuffle(deck)
    while len(deck) != 0:
        for player in lobby["players"].values():
            if len(deck) != 0:
                player["hand"].append(deck.pop())


def slap_results(pile, settings):
    if settings["slapDoubles"] and len(pile) >= 2 and pile[0].rank == pile[1].rank:
        return True, "Double"
    elif settings["slapSandwiches"] and len(pile) >= 3 and pile[0].rank == pile[2].rank:
        return True, "Sandwich"
    elif settings["slapMarriage"] and len(pile) >= 2 and pile[0].rank + pile[1].rank == 25:
        return True, "Marriage"
    elif settings["slapThreeAscDesc"] and len(pile) >= 3 and pile[0].rank - pile[1].rank == 1 \
            and pile[1].rank - pile[2].rank == 1:
        return True, "Three Ascending"
    elif settings["slapThreeAscDesc"] and len(pile) >= 3 and pile[2].rank - pile[1].rank == 1 \
            and pile[1].rank - pile[0].rank == 1:
        return True, "Three Descending"
    else:
        return False, ""


def clear_burn_slaps(lobby):
    for player in lobby["players"]:
        players[player]["has_burn_slapped"] = False


def reveal_hands(lobby):
    all_hands = {}
    for player in lobby["players"]:
        all_hands[players[player]["name"]] = len(players[player]["hand"])
    sio.emit("reveal_hands", all_hands, room=lobby["name"])


def prompt_deal(lobby):
    dealer_socket_id = lobby["player_order"][lobby["whose_turn_index"]]
    if len(players[dealer_socket_id]["hand"]) == 0:
        prompt_next_deal(lobby)
    else:
        lobby["current_dealer_sid"] = dealer_socket_id
        sio.emit("prompt_deal", room=dealer_socket_id)
        sio.emit("players_turn", players[dealer_socket_id]["name"],
                 room=lobby["name"], skip_sid=dealer_socket_id)


def prompt_next_deal(lobby):
    if not set_next_turn_index(lobby):
        for player in lobby["players"]:
            if len(players[player]["hand"]) > 0:
                reason = players[player]["name"] + " WINS!"
                reveal_hands(lobby)
                sio.emit("game_over", reason, room=lobby["name"])
                break
        lobby["in_progress"] = False
    else:
        prompt_deal(lobby)


def prompt_receive(lobby):
    recipient_socket_id = lobby["player_order"][lobby["whose_turn_index"]]
    lobby["current_recipient_sid"] = recipient_socket_id
    sio.emit("prompt_receive", room=recipient_socket_id)
    sio.emit("players_turn", players[recipient_socket_id]["name"],
             room=lobby["name"], skip_sid=recipient_socket_id)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/play/<full_name>")
def serve_game(full_name):
    if full_name.find("+") == -1:
        return "<p>no name chosen</p>"
    else:
        lobby_name = full_name[:full_name.find("+")]
        player_name = full_name[full_name.find("+") + 1:]
        if lobby_name != normalize(lobby_name[:20]) or not 0 < len(lobby_name) < 20:
            return "<p>invalid lobby name</p>"
        elif player_name != normalize(player_name[:20]) or not 0 < len(player_name) < 20:
            return "<p>invalid player name</p>"
        else:
            return app.send_static_file("game.html")


@sio.event
def join_lobby(socket_id, full_name):
    if type(full_name) != str:
        return
    if full_name.find("+") == -1:
        sio.emit("denied_entry", "no name chosen", room=socket_id)
    else:
        lobby_name = full_name[:full_name.find("+")]
        player_name = full_name[full_name.find("+") + 1:]
        if lobby_name != normalize(lobby_name[:20]) or not 0 < len(lobby_name) < 20:
            sio.emit("denied_entry", "invalid lobby name", room=socket_id)
        elif player_name != normalize(player_name[:20]) or not 0 < len(player_name) < 20:
            sio.emit("denied_entry", "invalid player name", room=socket_id)
        elif lobby_name in lobbies and get_player_by_name(player_name, lobbies[lobby_name]) is not None:
            sio.emit("denied_entry", "player name is taken", room=socket_id)
        elif lobby_name in lobbies and len(lobbies[lobby_name]["players"]) >= MAX_PLAYERS_PER_LOBBY:
            sio.emit("denied_entry", "lobby is full (" + str(MAX_PLAYERS_PER_LOBBY) + " players)", room=socket_id)
        elif lobby_name in lobbies and lobbies[lobby_name]["in_progress"]:
            sio.emit("denied_entry", "game is in progress", room=socket_id)
        else:
            sio.enter_room(socket_id, lobby_name)
            new_player = {
                "socket_id": socket_id,
                "name": player_name,
                "lobby_name": lobby_name,
                "is_host": False,
                "hand": [],
                "has_burn_slapped": False
            }
            if lobby_name not in lobbies:
                new_player["is_host"] = True
                lobbies[lobby_name] = {
                    "in_progress": False,
                    "name": lobby_name,
                    "host": new_player,
                    "current_dealer_sid": "",
                    "current_recipient_sid": "",
                    "face_card_initiator_sid": "",
                    "face_card_attempts_left": -1,
                    "players": {},
                    "player_order": [],
                    "whose_turn_index": -1,
                    "settings": {},
                    "center_pile": [],
                    "can_slap": False,
                    "already_slapped": False
                }
                print("Lobby " + lobby_name + " created")

            players[socket_id] = new_player
            lobbies[lobby_name]["players"][socket_id] = new_player
            sio.emit("admit_players", new_player["name"], room=lobby_name)
            if len(lobbies[lobby_name]["players"]) == 1:
                sio.emit("become_host", "", room=socket_id)
            else:
                earlier_players = []
                for player_socket_id in lobbies[lobby_name]["players"]:
                    if player_socket_id != socket_id:
                        earlier_players.append(players[player_socket_id]["name"])
                sio.emit("admit_players", ",".join(earlier_players), room=socket_id)


@sio.event
def declare_settings(socket_id, settings):
    lobby = lobbies[players[socket_id]["lobby_name"]]
    if lobby["host"] is players[socket_id] and not lobby["in_progress"]:
        lobby["settings"] = settings
        sio.emit("update_settings", settings, room=lobby["name"], skip_sid=socket_id)


@sio.event
def start_game(socket_id, settings):
    lobby = lobbies[players[socket_id]["lobby_name"]]
    if lobby["host"] is players[socket_id]:
        declare_settings(socket_id, settings)
        lobby["player_order"] = list(lobby["players"].keys())
        lobby["in_progress"] = True
        deal_shuffled_deck(lobby)

        first_player_index = randrange(0, len(lobby["players"]))
        lobby["whose_turn_index"] = first_player_index
        prompt_deal(lobby)


@sio.event
def deal(socket_id):
    lobby = lobbies[players[socket_id]["lobby_name"]]
    if socket_id == lobby["current_dealer_sid"]:
        dealt_card = players[socket_id]["hand"].pop(0)
        reveal_hands(lobby)
        lobby["center_pile"].insert(0, dealt_card)
        lobby["can_slap"] = True
        lobby["already_slapped"] = False
        clear_burn_slaps(lobby)
        sio.emit("witness_deal",
                 {"cardID": dealt_card.get_id(), "dealerName": players[socket_id]["name"]}, room=lobby["name"])

        prompt_next_deal(lobby)


@sio.event
def receive(socket_id):
    lobby = lobbies[players[socket_id]["lobby_name"]]
    if socket_id == lobby["current_recipient_sid"]:
        lobby["current_recipient_sid"] = ""
        lobby["can_slap"] = False
        lobby["face_card_attempts_left"] = -1
        sio.emit("witness_receive", lobby["players"][socket_id]["name"], room=lobby["name"])
        lobby["players"][socket_id]["hand"].extend(lobby["center_pile"])
        reveal_hands(lobby)
        lobby["center_pile"] = []
        prompt_deal(lobby)


@sio.event
def slap(socket_id):
    lobby = lobbies[players[socket_id]["lobby_name"]]
    if lobby["can_slap"]:
        if lobby["already_slapped"]:
            sio.emit("witness_futile_slap", lobby["players"][socket_id]["name"], room=lobby["name"])
        else:
            results = slap_results(lobby["center_pile"], lobby["settings"])
            if results[0]:
                lobby["already_slapped"] = True
                lobby["current_dealer_sid"] = ""
                lobby["whose_turn_index"] = lobby["player_order"].index(socket_id)
                sio.emit("witness_slap", lobby["players"][socket_id]["name"], room=lobby["name"])
                sio.emit("explain_slap", results[1], room=lobby["name"])
                prompt_receive(lobby)
            elif not players[socket_id]["has_burn_slapped"]:
                if len(players[socket_id]["hand"]) > 0:
                    burnt_card = players[socket_id]["hand"].pop(0)
                    players[socket_id]["has_burn_slapped"] = True
                    lobby["center_pile"].append(burnt_card)
                    sio.emit("witness_burn_slap",
                             {"burnerName": lobby["players"][socket_id]["name"],
                              "cardID": burnt_card.get_id()},
                             room=lobby["name"])
                    if lobby["current_dealer_sid"] == "":
                        prompt_receive(lobby)
                    else:
                        prompt_deal(lobby)
                    if socket_id == lobby["current_dealer_sid"] and len(players[socket_id]["hand"]) == 0:
                        prompt_next_deal(lobby)
                else:
                    sio.emit("witness_futile_slap", lobby["players"][socket_id]["name"], room=lobby["name"])


@sio.event
def connect(socket_id, environment):
    print("Socket connected: ", socket_id)


@sio.event
def ping(socket_id, data):
    sio.emit("pong", data, room=socket_id)


@sio.event
def disconnect(socket_id):
    if socket_id in players:
        lobby_name = players[socket_id]["lobby_name"]
        sio.emit("game_over", players[socket_id]["name"] + " disconnected", room=lobby_name)
        del lobbies[lobby_name]["players"][socket_id]
        if len(lobbies[lobby_name]["players"]) == 0:
            del lobbies[lobby_name]
            print("Lobby " + lobby_name + " deleted; all players disconnected")
        del players[socket_id]
    print("Socket disconnected: ", socket_id)


def startup():
    generate_html.main()

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=10010)


startup()
