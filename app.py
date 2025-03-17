from flask import Flask, render_template, request, session, jsonify, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import os
import logging

# Configure logging for Heroku
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting app.py initialization")

# Import Gemini API with version check
try:
    from google import genai
    from google.genai import types
    import google.generativeai as google_genai
    logger.info(f"Imported google-generativeai version: {google_genai.__version__}")
except ImportError as e:
    logger.error(f"Failed to import google.generativeai: {e}")
    raise

# Initialize Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*", engineio_logger=True)
logger.info("Flask and SocketIO initialized")

# Configure Gemini API client
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key')
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini API client initialized")
except Exception as e:
    logger.error(f"Failed to initialize Gemini client: {e}")
    client = None

# In-memory storage for game rooms
game_rooms = {}

# Prompt categories
PROMPT_CATEGORIES = ['Animals', 'Objects', 'Actions', 'Places']

def generate_room_code():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))

def get_gemini_prompt(category):
    if not client:
        logger.warning("Gemini client unavailable, using fallback prompt")
        return f"A {category.lower()} (Gemini API unavailable)"
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[f"Generate a creative drawing prompt for a game of Pictionary in the category: {category}"],
            config=types.GenerateContentConfig(
                max_output_tokens=50,
                temperature=0.7
            )
        )
        logger.info(f"Generated prompt: {response.text}")
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        return f"A {category.lower()} (API error)"

# Routes
@app.route('/')
def index():
    logger.info("Serving index.html")
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
            'scores': {},
            'mode': 'timed',
            'time_left': 60
        }
    }
    session['room_code'] = room_code
    logger.info(f"Created room: {room_code}")
    return jsonify({'room_code': room_code})

@app.route('/join_room', methods=['POST'])
def join_room():
    room_code = request.form.get('room_code', '').upper()
    if room_code not in game_rooms or len(game_rooms[room_code]['players']) >= 2:
        logger.warning(f"Failed to join room {room_code}: not found or full")
        return jsonify({'error': 'Room not found or full'}), 400
    
    session['room_code'] = room_code
    logger.info(f"Joined room: {room_code}")
    return jsonify({'room_code': room_code})

@app.route('/game')
def game():
    room_code = session.get('room_code')
    if not room_code or room_code not in game_rooms:
        logger.warning("Invalid room code, redirecting to index")
        return redirect('/')
    logger.info(f"Serving game.html for room: {room_code}")
    return render_template('game.html', room_code=room_code)

# WebSocket Events
@socketio.on('join')
def on_join(data):
    room_code = data.get('room_code')
    if room_code not in game_rooms:
        logger.warning(f"Join failed: Room {room_code} not found")
        return
    
    join_room(room_code)
    game = game_rooms[room_code]
    player_sid = request.sid
    
    if player_sid not in game['players']:
        game['players'].append(player_sid)
        logger.info(f"Player {player_sid} joined room {room_code}")
    
    if len(game['players']) == 2:
        game['state']['drawer'] = game['players'][0]
        game['state']['guesser'] = game['players'][1]
        game['state']['scores'] = {sid: 0 for sid in game['players']}
        game['state']['prompt'] = get_gemini_prompt(random.choice(PROMPT_CATEGORIES))
        emit('game_start', {
            'drawer': game['state']['drawer'],
            'prompt': game['state']['prompt'] if player_sid == game['state']['drawer'] else None
        }, room=room_code)
        logger.info(f"Game started in room {room_code}")

@socketio.on('draw')
def on_draw(data):
    room_code = data.get('room_code')
    if room_code in game_rooms:
        emit('draw_update', data, room=room_code, include_self=False)
        # logger.debug(f"Drawing update sent to room {room_code}")

@socketio.on('guess')
def on_guess(data):
    room_code = data.get('room_code')
    guess = data.get('guess', '')
    if room_code not in game_rooms:
        return
    
    game = game_rooms[room_code]
    if request.sid == game['state']['guesser']:
        if guess.lower() in game['state']['prompt'].lower():
            game['state']['scores'][request.sid] += 1
            emit('guess_correct', {'scores': game['state']['scores']}, room=room_code)
            switch_roles(room_code)
            logger.info(f"Correct guess in room {room_code}")
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
            logger.info(f"Room {room_code} deleted due to all players disconnecting")
        else:
            emit('player_left', room=room_code)
            logger.info(f"Player {request.sid} disconnected from room {room_code}")

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
    logger.info(f"Switched roles in room {room_code}, round {game['state']['round']}")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting Flask-SocketIO server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port)