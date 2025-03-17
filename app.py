from flask import Flask, render_template, request, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
from google import genai
from google.genai import types
import os

# Initialize Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Replace with a secure key
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure Gemini API client
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key')  # Set via Heroku config vars
client = genai.Client(api_key=GEMINI_API_KEY)

# In-memory storage for game rooms and states
game_rooms = {}  # {room_code: {'players': [sid1, sid2], 'state': {...}}}

# Categories for prompts
PROMPT_CATEGORIES = ['Animals', 'Objects', 'Actions', 'Places']

# Generate a random room code
def generate_room_code():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))

# Fetch a prompt from Gemini API
def get_gemini_prompt(category):
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[f"Generate a creative drawing prompt for a game of Pictionary in the category: {category}"],
            config=types.GenerateContentConfig(
                max_output_tokens=50,
                temperature=0.7
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"A {category.lower()} (API error: {str(e)})"

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    room_code = generate_room_code()
    while room_code in game_rooms:
        room_code = generate_room_code()
    
    game_rooms[room_code] = {
        'players': [],
        'state': {
            'drawer': None,
            'guesser': None,
            'prompt': None,
            'round': 1,
            'scores': {sid: 0 for sid in []},
            'mode': 'timed',  # Default mode
            'time_left': 60   # 60 seconds per round
        }
    }
    session['room_code'] = room_code
    return jsonify({'room_code': room_code})

@app.route('/join_room', methods=['POST'])
def join_room():
    room_code = request.form.get('room_code').upper()
    if room_code not in game_rooms or len(game_rooms[room_code]['players']) >= 2:
        return jsonify({'error': 'Room not found or full'}), 400
    
    session['room_code'] = room_code
    return jsonify({'room_code': room_code})

@app.route('/game')
def game():
    room_code = session.get('room_code')
    if not room_code or room_code not in game_rooms:
        return redirect('/')
    return render_template('game.html', room_code=room_code)

# WebSocket Events
@socketio.on('join')
def on_join(data):
    room_code = data['room_code']
    if room_code not in game_rooms:
        return
    
    join_room(room_code)
    game = game_rooms[room_code]
    player_sid = request.sid
    
    if player_sid not in game['players']:
        game['players'].append(player_sid)
    
    # Start game when two players join
    if len(game['players']) == 2:
        game['state']['drawer'] = game['players'][0]
        game['state']['guesser'] = game['players'][1]
        game['state']['scores'] = {sid: 0 for sid in game['players']}
        game['state']['prompt'] = get_gemini_prompt(random.choice(PROMPT_CATEGORIES))
        emit('game_start', {
            'drawer': game['state']['drawer'],
            'prompt': game['state']['prompt'] if player_sid == game['state']['drawer'] else None
        }, room=room_code)

@socketio.on('draw')
def on_draw(data):
    room_code = data['room_code']
    if room_code in game_rooms:
        emit('draw_update', data, room=room_code, include_self=False)

@socketio.on('guess')
def on_guess(data):
    room_code = data['room_code']
    guess = data['guess']
    if room_code not in game_rooms:
        return
    
    game = game_rooms[room_code]
    if request.sid == game['state']['guesser']:
        if guess.lower() in game['state']['prompt'].lower():
            game['state']['scores'][request.sid] += 1
            emit('guess_correct', {'scores': game['state']['scores']}, room=room_code)
            switch_roles(room_code)
        else:
            emit('chat_message', {'message': f"Guess: {guess}"}, room=room_code)

@socketio.on('disconnect')
def on_disconnect():
    room_code = session.get('room_code')
    if room_code and room_code in game_rooms:
        game = game_rooms[room_code]
        game['players'] = [p for p in game['players'] if p != request.sid]
        if not game['players']:
            del game_rooms[room_code]
        else:
            emit('player_left', room=room_code)

# Switch roles and reset round
def switch_roles(room_code):
    game = game_rooms[room_code]
    game['state']['drawer'], game['state']['guesser'] = game['state']['guesser'], game['state']['drawer']
    game['state']['round'] += 1
    game['state']['time_left'] = 60
    game['state']['prompt'] = get_gemini_prompt(random.choice(PROMPT_CATEGORIES))
    emit('new_round', {
        'drawer': game['state']['drawer'],
        'prompt': game['state']['prompt'] if request.sid == game['state']['drawer'] else None,
        'scores': game['state']['scores']
    }, room=room_code)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)