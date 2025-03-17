document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    const canvas = document.getElementById('drawingCanvas');
    const ctx = canvas.getContext('2d');
    const roomCode = document.querySelector('body').innerHTML.match(/Room: ([A-Z]{4})/)[1];

    // Canvas setup
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Drawing state
    let drawing = false;
    let lastX = 0;
    let lastY = 0;
    let history = []; // For undo functionality

    // Tool settings
    const colorPicker = document.getElementById('colorPicker');
    const brushSize = document.getElementById('brushSize');
    const eraserBtn = document.getElementById('eraserBtn');
    const undoBtn = document.getElementById('undoBtn');
    const clearBtn = document.getElementById('clearBtn');

    // Adjust canvas size on resize
    window.addEventListener('resize', () => {
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;
        redrawHistory();
    });

    // Drawing functions
    function startDrawing(x, y) {
        drawing = true;
        lastX = x;
        lastY = y;
    }

    function draw(x, y) {
        if (!drawing) return;

        ctx.beginPath();
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(x, y);
        ctx.strokeStyle = eraserBtn.classList.contains('active') ? '#FFFFFF' : colorPicker.value;
        ctx.lineWidth = brushSize.value;
        ctx.stroke();

        socket.emit('draw', {
            room_code: roomCode,
            x: lastX / canvas.width,
            y: lastY / canvas.height,
            x2: x / canvas.width,
            y2: y / canvas.height,
            color: ctx.strokeStyle,
            width: ctx.lineWidth
        });

        history.push({ x: lastX, y: lastY, x2: x, y2: y, color: ctx.strokeStyle, width: ctx.lineWidth });
        lastX = x;
        lastY = y;
    }

    function stopDrawing() {
        drawing = false;
    }

    // Mouse events
    canvas.addEventListener('mousedown', (e) => {
        if (!document.getElementById('tools').style.display) return;
        startDrawing(e.offsetX, e.offsetY);
    });

    canvas.addEventListener('mousemove', (e) => draw(e.offsetX, e.offsetY));
    canvas.addEventListener('mouseup', stopDrawing);
    canvas.addEventListener('mouseout', stopDrawing);

    // Touch events for iPhone compatibility
    canvas.addEventListener('touchstart', (e) => {
        if (!document.getElementById('tools').style.display) return;
        e.preventDefault();
        const touch = e.touches[0];
        const rect = canvas.getBoundingClientRect();
        startDrawing(touch.clientX - rect.left, touch.clientY - rect.top);
    });

    canvas.addEventListener('touchmove', (e) => {
        e.preventDefault();
        const touch = e.touches[0];
        const rect = canvas.getBoundingClientRect();
        draw(touch.clientX - rect.left, touch.clientY - rect.top);
    });

    canvas.addEventListener('touchend', stopDrawing);

    // Tool controls
    eraserBtn.addEventListener('click', () => {
        eraserBtn.classList.toggle('active');
        if (eraserBtn.classList.contains('active')) {
            colorPicker.disabled = true;
        } else {
            colorPicker.disabled = false;
        }
    });

    undoBtn.addEventListener('click', () => {
        history.pop();
        redrawHistory();
    });

    clearBtn.addEventListener('click', () => {
        history = [];
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        socket.emit('draw', { room_code: roomCode, clear: true });
    });

    // Redraw canvas from history
    function redrawHistory() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        history.forEach(stroke => {
            ctx.beginPath();
            ctx.moveTo(stroke.x, stroke.y);
            ctx.lineTo(stroke.x2, stroke.y2);
            ctx.strokeStyle = stroke.color;
            ctx.lineWidth = stroke.width;
            ctx.stroke();
        });
    }

    // Guess submission
    document.getElementById('guessForm').addEventListener('submit', (e) => {
        e.preventDefault();
        const guess = document.getElementById('guessInput').value.trim();
        if (guess) {
            socket.emit('guess', { room_code: roomCode, guess });
            document.getElementById('guessInput').value = '';
        }
    });

    // WebSocket drawing updates
    socket.on('draw_update', (data) => {
        if (data.clear) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }
        ctx.beginPath();
        ctx.moveTo(data.x * canvas.width, data.y * canvas.height);
        ctx.lineTo(data.x2 * canvas.width, data.y2 * canvas.height);
        ctx.strokeStyle = data.color;
        ctx.lineWidth = data.width;
        ctx.stroke();
    });
});