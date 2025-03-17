from flask import Flask, render_template, request, session, jsonify, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting app.py initialization")

try:
    import google.generativeai as genai
    logger.info(f"Imported google.generativeai version: {genai.__version__}")
except ImportError as e:
    logger.error(f"Failed to import google.generativeai: {e}")
    raise

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*", engineio_logger=True, async_mode='eventlet')
logger.info("Flask and SocketIO initialized")

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key')
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("Gemini API configured and model initialized")
except Exception as e:
    logger.error(f"Failed to initialize Gemini client: {e}")
    gemini_model = None

game_rooms = {}

PROMPT_CATEGORIES = ['Animals', 'Objects', 'Actions', 'Places']

def generate_room_code():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))

def get_gemini_prompt(category):
    if not gemini_model:
        logger.warning("Gemini model unavailable, using fallback prompt")
        return f"A {category.lower()} (Gemini API unavailable)"
    try:
        response = gemini_model.generate_content(
            f"Generate a creative drawing prompt for a game of Pictionary in the category: {category}",
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=50,
                temperature=0.7
            )
        )
        logger.info(f"Generated prompt: {response.text}")
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        return f"A {category.lower()} (API error)"

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
            'time_left': 60,
            'ready': {}
        }
    }
    session['room_code'] = room_code
    logger.info(f"Created room: {room_code}")
    return jsonify({'room_code': room_code})

@app.route('/join_room', methods=['POST'])
def join_room():
    room_code = request.form.get('room_code', '').upper()
    if room_code not in game_rooms:
        logger.warning(f"Room {room_code} not found")
        return jsonify({'error': 'Room not found'}), 400
    if len(game_rooms[room_code]['players']) >= 2:
        logger.warning(f"Room {room_code} is full")
        return jsonify({'error': 'Room is full'}), 400
    
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

@socketio.on('join')
def on_join(data):
    room_code = data.get('room_code')
    if room_code not in game_rooms:
        logger.warning(f"Join failed: Room {room_code} not found")
        emit('error', {'message': 'Room not found'})
        return
    
    join_room(room=room_code)  # Fix: Use keyword argument
    game = game_rooms[room_code]
    player_sid = request.sid
    
    if player_sid not in game['players']:
        game['players'].append(player_sid)
        game['state']['ready'][player_sid] = False
        logger.info(f"Player {player_sid} joined room {room_code}")
    
    emit('player_update', {'players': len(game['players']), 'ready': sum(game['state']['ready'].values())}, room=room_code)

@socketio.on('ready')
def on_ready(data):
    room_code = data.get('room_code')
    if room_code not in game_rooms:
        logger.warning(f"Ready failed: Room {room_code} not found")
        return
    
    game = game_rooms[room_code]
    player_sid = request.sid
    game['state']['ready'][player_sid] = True
    logger.info(f"Player {player_sid} marked ready in room {room_code}")
    
    emit('player_update', {'players': len(game['players']), 'ready': sum(game['state']['ready'].values())}, room=room_code)
    
    if len(game['players']) == 2 and all(game['state']['ready'].values()):
        game['state']['drawer'] = game['players'][0]
        game['state']['guesser'] = game['players'][1]
        game['state']['scores'] = {sid: 0 for sid in game['players']}
        game['state']['prompt'] = get_gemini_prompt(random.choice(PROMPT_CATEGORIES))
        logger.info(f"Game starting in room {room_code} with prompt: {game['state']['prompt']}")
        emit('game_start', {
            'drawer': game['state']['drawer'],
            'prompt': game['state']['prompt'] if request.sid == game['state']['drawer'] else None
        }, room=room_code)

@socketio.on('draw')
def on_draw(data):
    room_code = data.get('room_code')
    if room_code in game_rooms:
        emit('draw_update', data, room=room_code, include_self=False)

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
        else:
            emit('chat_message', {'message': f"Guess: {guess}"}, room=room_code)

@socketio.on('disconnect')
def on_disconnect():
    room_code = session.get('room_code')
    if room_code and room_code in game_rooms:
        game = game_rooms[room_code]
        player_sid = request.sid
        game['players'] = [p for p in game['players'] if p != player_sid]
        game['state']['ready'].pop(player_sid, None)
        if not game['players']:
            del game_rooms[room_code]
            logger.info(f"Room {room_code} deleted")
        else:
            emit('player_left', room=room_code)
            logger.info(f"Player {player_sid} disconnected from {room_code}")

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
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting Flask-SocketIO server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port)