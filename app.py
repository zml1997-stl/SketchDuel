from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
import os
import requests
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Replace with a secure key
socketio = SocketIO(app, cors_allowed_origins="*")

# Store game rooms and their states
rooms = {}

# Replace with your Gemini API key (set as Heroku env variable)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key-here')
GEMINI_API_URL = "https://api.gemini.com/v1/prompt"  # Hypothetical URL, adjust per actual API docs

def get_gemini_prompt():
    try:
        headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
        payload = {"prompt": "Generate a short, creative drawing prompt for a game."}
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json().get("text", "A happy cloud")
    except Exception as e:
        print(f"Error fetching prompt: {e}")
        return "A dancing tree"  # Fallback prompt

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    room_id = request.form.get('room_id')
    username = request.form.get('username')
    if room_id in rooms:
        return jsonify({"error": "Room already exists"}), 400
    rooms[room_id] = {
        "players": [username],
        "drawer": username,
        "prompt": get_gemini_prompt(),
        "guesses": [],
        "drawing": [],
        "round": 1,
        "scores": {username: 0}
    }
    return jsonify({"room_id": room_id, "prompt": rooms[room_id]["prompt"] if username == rooms[room_id]["drawer"] else None})

@app.route('/join_room', methods=['POST'])
def join_room():
    room_id = request.form.get('room_id')
    username = request.form.get('username')
    if room_id not in rooms:
        return jsonify({"error": "Room does not exist"}), 404
    if len(rooms[room_id]["players"]) >= 2:
        return jsonify({"error": "Room is full"}), 400
    rooms[room_id]["players"].append(username)
    rooms[room_id]["scores"][username] = 0
    return jsonify({"room_id": room_id, "prompt": None})  # Guesser doesn’t see prompt

@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    emit('player_joined', {'username': username}, room=room)

@socketio.on('draw')
def handle_draw(data):
    room = data['room']
    if room in rooms:
        rooms[room]["drawing"].append(data['stroke'])
        emit('draw_update', data['stroke'], room=room, broadcast=True)

@socketio.on('guess')
def handle_guess(data):
    room = data['room']
    guess = data['guess']
    username = data['username']
    if room in rooms:
        rooms[room]["guesses"].append(guess)
        emit('new_guess', {'username': username, 'guess': guess}, room=room, broadcast=True)
        if guess.lower() == rooms[room]["prompt"].lower():
            rooms[room]["scores"][username] += 1
            emit('correct_guess', {'username': username, 'scores': rooms[room]["scores"]}, room=room, broadcast=True)
            switch_roles(room)

@socketio.on('next_round')
def next_round(data):
    room = data['room']
    if room in rooms:
        switch_roles(room)

def switch_roles(room):
    rooms[room]["round"] += 1
    rooms[room]["drawing"] = []
    rooms[room]["guesses"] = []
    rooms[room]["prompt"] = get_gemini_prompt()
    rooms[room]["drawer"] = rooms[room]["players"][1] if rooms[room]["drawer"] == rooms[room]["players"][0] else rooms[room]["players"][0]
    emit('new_round', {
        'prompt': rooms[room]["prompt"],
        'drawer': rooms[room]["drawer"],
        'round': rooms[room]["round"],
        'scores': rooms[room]["scores"]
    }, room=room, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))