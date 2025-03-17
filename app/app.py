from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
import os
from app.room_manager import RoomManager
from app.game_logic import GameLogic
from app.gemini_api import generate_prompt

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')  # Use env var for security
socketio = SocketIO(app, cors_allowed_origins="*")  # Enable WebSockets with cross-origin support

# Initialize game management objects
room_manager = RoomManager()
game_logic = GameLogic()

# Store active games in memory (key: room_code, value: game_state)
games = {}

# Lobby route: Entry point for creating/joining rooms
@app.route('/')
def index():
    return render_template('index.html')

# Game route: Main game page
@app.route('/game/<room_code>')
def game(room_code):
    if not room_manager.room_exists(room_code) or len(room_manager.get_players(room_code)) != 2:
        return redirect(url_for('index'))
    session['room_code'] = room_code
    return render_template('game.html', room_code=room_code)

# WebSocket event: Player joins a room
@socketio.on('join')
def on_join(data):
    room_code = data['room_code']
    player_id = request.sid  # Unique session ID for the player

    # Create or join the room
    if not room_manager.room_exists(room_code):
        room_manager.create_room(room_code)
    room_manager.add_player(room_code, player_id)
    
    join_room(room_code)
    players = room_manager.get_players(room_code)

    # If two players are in the room, start the game
    if len(players) == 2:
        # Assign roles and initialize game state
        game_state = game_logic.initialize_game(players)
        games[room_code] = game_state
        
        # Generate initial drawing prompt
        prompt = generate_prompt(category="objects")  # Default category
        game_state['prompt'] = prompt
        
        # Notify players of game start and roles
        emit('game_start', {
            'players': players,
            'roles': {p: game_state['roles'][p] for p in players},
            'prompt': prompt if game_state['roles'][player_id] == 'drawer' else None,
            'mode': game_state['mode']
        }, room=room_code)
    else:
        emit('waiting', {'message': 'Waiting for another player...'}, to=player_id)

# WebSocket event: Handle drawing updates
@socketio.on('draw')
def on_draw(data):
    room_code = session.get('room_code')
    if not room_code or room_code not in games:
        return
    
    # Broadcast drawing data to the other player
    emit('draw_update', data, room=room_code, skip_sid=request.sid)

# WebSocket event: Handle chat messages (guesses)
@socketio.on('chat')
def on_chat(data):
    room_code = session.get('room_code')
    if not room_code or room_code not in games:
        return
    
    guess = data['message']
    game_state = games[room_code]
    player_id = request.sid

    # Check if the guess is correct
    if game_logic.check_guess(game_state, guess, player_id):
        game_state['scores'][player_id] += 1
        emit('correct_guess', {'player_id': player_id, 'scores': game_state['scores']}, room=room_code)
        
        # Start next round
        game_logic.next_round(game_state)
        emit('new_round', {
            'roles': game_state['roles'],
            'prompt': game_state['prompt'] if game_state['roles'][player_id] == 'drawer' else None
        }, room=room_code)
    else:
        # Broadcast the guess to the other player
        emit('chat_update', {'message': guess, 'player_id': player_id}, room=room_code, skip_sid=request.sid)

# WebSocket event: Player disconnects
@socketio.on('disconnect')
def on_disconnect():
    room_code = session.get('room_code')
    if not room_code or room_code not in games:
        return
    
    player_id = request.sid
    room_manager.remove_player(room_code, player_id)
    leave_room(room_code)
    
    if len(room_manager.get_players(room_code)) == 0:
        del games[room_code]  # Clean up empty rooms
    else:
        emit('player_left', {'message': 'Opponent disconnected'}, room=room_code)

# Run the app
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)