from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
import os
import google.generativeai as genai
import random

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Replace with a secure key
socketio = SocketIO(app, cors_allowed_origins="*")

# Store game rooms and their states
rooms = {}

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key-here')
genai.configure(api_key=GEMINI_API_KEY)

# Fallback simple prompt list if API fails
SIMPLE_PROMPTS = [
    "cat", "dog", "house", "tree", "car", "sun", "moon", "star", 
    "bird", "fish", "boat", "plane", "banana", "apple", "pizza",
    "book", "hat", "shoe", "chair", "table", "flower", "clock"
]

def get_simple_prompt():
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(
            "Generate a single common noun that would be easy to draw and guess in a game like Pictionary. "
            "Provide only ONE word, nothing else."
        )
        prompt = response.text.strip()
        # If response contains more than two words, use fallback
        if len(prompt.split()) > 2:
            return random.choice(SIMPLE_PROMPTS)
        return prompt
    except Exception as e:
        print(f"Error fetching prompt: {e}")
        return random.choice(SIMPLE_PROMPTS)

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
        "prompt": get_simple_prompt(),
        "guesses": [],
        "drawing": [],
        "round": 1,
        "scores": {username: 0}
    }
    return jsonify({"room_id": room_id, "prompt": rooms[room_id]["prompt"] if username == rooms[room_id]["drawer"] else None})

@app.route('/join_room', methods=['POST'])
def join_room_route():
    room_id = request.form.get('room_id')
    username = request.form.get('username')
    if room_id not in rooms:
        return jsonify({"error": "Room does not exist"}), 404
    if len(rooms[room_id]["players"]) >= 2:
        return jsonify({"error": "Room is full"}), 400
    if username in rooms[room_id]["players"]:
        return jsonify({"error": "Username already taken in this room"}), 400
    
    rooms[room_id]["players"].append(username)
    rooms[room_id]["scores"][username] = 0
    
    # Send the current drawing state to the new player
    return jsonify({
        "room_id": room_id, 
        "prompt": None,  # Guesser doesn't see prompt
        "drawing": rooms[room_id]["drawing"]  # Send existing drawing data
    })

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
        stroke = data['stroke']
        rooms[room]["drawing"].append(stroke)
        # Broadcast to everyone in the room except sender
        emit('draw_update', stroke, room=room, include_self=False)

@socketio.on('guess')
def handle_guess(data):
    room = data['room']
    guess = data['guess']
    username = data['username']
    if room in rooms:
        rooms[room]["guesses"].append(guess)
        emit('new_guess', {'username': username, 'guess': guess}, room=room)
        
        # Check if guess is correct (case insensitive)
        room_prompt = rooms[room]["prompt"].lower()
        user_guess = guess.lower()
        
        if user_guess == room_prompt or user_guess in room_prompt.split() or room_prompt in user_guess.split():
            rooms[room]["scores"][username] += 1
            emit('correct_guess', {'username': username, 'scores': rooms[room]["scores"]}, room=room)

@socketio.on('next_round')
def next_round(data):
    room = data['room']
    if room in rooms:
        switch_roles(room)

def switch_roles(room):
    rooms[room]["round"] += 1
    rooms[room]["drawing"] = []
    rooms[room]["guesses"] = []
    rooms[room]["prompt"] = get_simple_prompt()
    
    # Switch drawer role
    if len(rooms[room]["players"]) >= 2:
        rooms[room]["drawer"] = rooms[room]["players"][1] if rooms[room]["drawer"] == rooms[room]["players"][0] else rooms[room]["players"][0]
    
    emit('new_round', {
        'prompt': rooms[room]["prompt"],
        'drawer': rooms[room]["drawer"],
        'round': rooms[room]["round"],
        'scores': rooms[room]["scores"]
    }, room=room)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)