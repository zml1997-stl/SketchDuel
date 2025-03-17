<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SketchDuel - Lobby</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <div class="container d-flex flex-column justify-content-center align-items-center min-vh-100">
        <h1 class="text-center mb-4">SketchDuel</h1>
        
        <!-- Create Room Section -->
        <div class="card p-4 mb-4 w-100" style="max-width: 400px;">
            <h3 class="text-center">Create a Game</h3>
            <button id="createRoomBtn" class="btn btn-primary w-100">Create Room</button>
            <p id="roomCode" class="text-center mt-3" style="display: none;">Room Code: <strong></strong></p>
        </div>

        <!-- Join Room Section -->
        <div class="card p-4 w-100" style="max-width: 400px;">
            <h3 class="text-center">Join a Game</h3>
            <form id="joinRoomForm">
                <div class="mb-3">
                    <input type="text" class="form-control" id="roomCodeInput" placeholder="Enter Room Code" maxlength="4" style="text-transform: uppercase;">
                </div>
                <button type="submit" class="btn btn-primary w-100">Join Room</button>
            </form>
            <p id="joinError" class="text-danger text-center mt-3" style="display: none;"></p>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        $(document).ready(function() {
            // Create Room
            $('#createRoomBtn').click(function() {
                $.post('/create_room', function(data) {
                    if (data.room_code) {
                        $('#roomCode strong').text(data.room_code);
                        $('#roomCode').show();
                        window.location.href = '/game';
                    }
                });
            });

            // Join Room
            $('#joinRoomForm').submit(function(e) {
                e.preventDefault();
                const roomCode = $('#roomCodeInput').val().toUpperCase();
                $.post('/join_room', { room_code: roomCode }, function(data) {
                    if (data.error) {
                        $('#joinError').text(data.error).show();
                    } else {
                        window.location.href = '/game';
                    }
                }).fail(function() {
                    $('#joinError').text('Room not found or full').show();
                });
            });
        });
    </script>
</body>
</html>