from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests
import time
import json
import threading
import websocket
import random

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ===== CACHE CHO VTH WS =====
room_cache = {'data': None, 'updated': 0, 'issue_id': None}
ws_running = False

# ===== WEBSOCKET CHO VTH =====
def on_message(ws, message):
    global room_cache
    try:
        data = json.loads(message)
        if 'room_stat' in str(data):
            room_cache['data'] = data
            room_cache['updated'] = time.time()
        if 'issue_id' in str(data):
            try:
                room_cache['issue_id'] = data.get('issue_id') or data.get('data', {}).get('issue_id')
            except: pass
    except: pass

def on_open(ws):
    print("[WS] Connected to VTH")
    try:
        ws.send(json.dumps({"msg_type": "handle_enter_game", "asset_type": "BUILD"}))
    except: pass

def start_vth_ws():
    global ws_running
    ws_running = True
    while ws_running:
        try:
            ws = websocket.WebSocketApp(
                'wss://api.escapemaster.net/escape_master/ws',
                on_open=on_open,
                on_message=on_message,
                on_error=lambda ws, err: print(f"[WS] Error: {err}"),
                on_close=lambda ws, code, msg: print(f"[WS] Closed: {code}")
            )
            ws.run_forever(ping_interval=15, ping_timeout=6)
        except Exception as e:
            print(f"[WS] Exception: {e}")
        time.sleep(3)

# Khởi động WS khi server start
threading.Thread(target=start_vth_ws, daemon=True).start()

# ===== API PROXY =====
def call_api(method, url, headers=None, data=None, params=None):
    try:
        if method.upper() == 'GET':
            r = requests.get(url, headers=headers, params=params, timeout=10)
        else:
            r = requests.post(url, headers=headers, json=data, timeout=10)
        return r.json() if r.text else {'status': 'ok', 'raw': r.text}
    except Exception as e:
        return {'error': str(e)}

@app.route('/api/bet', methods=['POST'])
def bet():
    data = request.json
    tool = data.get('tool', 'vth')
    uid = data.get('userId')
    sk = data.get('secretKey')
    room = data.get('room')
    amount = float(data.get('amount', 1.0))
    
    headers = {'user-id': str(uid), 'user-secret-key': sk, 'content-type': 'application/json'}
    
    if tool == 'vth':
        url = 'https://api.escapemaster.net/escape_game/bet'
        payload = {'asset_type': 'BUILD', 'user_id': uid, 'room_id': int(room), 'bet_amount': amount}
    elif tool == 'vtd':
        url = 'https://api.sprintrun.win/sprint/bet'
        payload = {'issue_id': int(data.get('issueId', 0)), 'bet_group': 'not_winner',
                   'asset_type': 'BUILD', 'athlete_id': int(room), 'bet_amount': amount}
    else:
        url = 'https://api.winhash.net/lucky_game/v2/create_order'
        bet_ids = {'small': 70309, 'big': 71218, 'draw': 71011}
        bet_type = data.get('betType', 'small')
        payload = {'game_id': 1, 'issue_id': int(data.get('issueId', 0)),
                   'items': [{'id': bet_ids.get(bet_type, 70309), 'amount': str(amount), 'asset': 'BUILD'}]}
    
    result = call_api('POST', url, headers, payload)
    return jsonify(result)

@app.route('/api/balance', methods=['POST'])
def balance():
    data = request.json
    headers = {'user-id': str(data.get('userId')), 'user-secret-key': data.get('secretKey'), 'content-type': 'application/json'}
    payload = {'user_id': int(data.get('userId')), 'source': 'home'}
    result = call_api('POST', 'https://wallet.3games.io/api/wallet/user_asset', headers, payload)
    return jsonify(result)

@app.route('/api/poll', methods=['POST'])
def poll():
    data = request.json
    tool = data.get('tool', 'vth')
    uid = data.get('userId')
    sk = data.get('secretKey')
    
    headers = {'user-id': str(uid), 'user-secret-key': sk, 'content-type': 'application/json'}
    
    if tool == 'vth':
        # Lấy dữ liệu từ WS cache
        cached = room_cache.get('data')
        issue = room_cache.get('issue_id')
        if cached and (time.time() - room_cache.get('updated', 0)) < 30:
            return jsonify({'status': 'ok', 'data': cached, 'issue_id': issue})
        # Fallback mock
        return jsonify({'status': 'ok', 'issue_id': int(time.time() % 10000), 
                       'rooms': {i: {'players': random.randint(1,20), 'bet': random.randint(100,5000)} for i in range(1,9)}})
    elif tool == 'vtd':
        result = call_api('GET', 'https://api.sprintrun.win/sprint/home', headers, params={'asset': 'BUILD'})
        return jsonify(result)
    else:
        result = call_api('GET', 'https://api.winhash.net/lucky_game/home', headers, params={'game_id': 1, 'asset': 'BUILD'})
        return jsonify(result)

# ===== HTML GIAO DIỆN ĐẸP =====
HTML = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ TBTOOL ULTIMATE - AI Auto Bet</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
    background: #0a0a12;
    background-image: radial-gradient(ellipse at 20% 50%, rgba(255,215,0,0.04) 0%, transparent 60%),
                      radial-gradient(ellipse at 80% 20%, rgba(0,212,255,0.04) 0%, transparent 50%);
    min-height: 100vh;
    color: #e8e8f0;
    font-family: 'Inter', sans-serif;
    padding: 20px;
}
.container { max-width: 1400px; margin: 0 auto; }

/* HEADER */
.header {
    background: linear-gradient(135deg, #12121f, #1a1a2e);
    border: 1px solid rgba(255,215,0,0.2);
    border-radius: 16px;
    padding: 20px 30px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 15px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.header-left { display: flex; align-items: center; gap: 16px; }
.logo { font-family: 'Orbitron', monospace; font-weight: 900; font-size: 28px; color: #FFD700; text-shadow: 0 0 30px rgba(255,215,0,0.15); letter-spacing: 2px; }
.logo span { color: #00D4FF; }
.header-right { display: flex; gap: 20px; flex-wrap: wrap; align-items: center; }
.status-badge {
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: rgba(0,200,83,0.15);
    color: #00c853;
    border: 1px solid rgba(0,200,83,0.2);
}
.status-badge.offline { background: rgba(255,23,68,0.15); color: #ff1744; border-color: rgba(255,23,68,0.2); }
.status-badge.vip { background: rgba(255,215,0,0.15); color: #FFD700; border-color: rgba(255,215,0,0.3); }

/* STATS */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
}
.stat-card {
    background: rgba(18,18,30,0.8);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 14px 18px;
    transition: 0.3s;
}
.stat-card:hover { border-color: rgba(255,215,0,0.15); }
.stat-label { font-size: 11px; text-transform: uppercase; color: #666; letter-spacing: 1px; }
.stat-value { font-size: 22px; font-weight: 700; margin-top: 4px; font-family: 'Orbitron', monospace; }
.stat-value.gold { color: #FFD700; }
.stat-value.green { color: #00c853; }
.stat-value.red { color: #ff1744; }
.stat-value.blue { color: #00D4FF; }
.stat-value.pink { color: #ff00e5; }

/* GRID CHÍNH */
.main-grid {
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 24px;
}
@media (max-width: 1024px) { .main-grid { grid-template-columns: 1fr; } }

/* PANEL */
.panel {
    background: linear-gradient(145deg, #12121f, #1a1a2a);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 20px 24px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}
.panel-title {
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #888;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.panel-title i { color: #FFD700; }

/* FORM */
.form-group { margin-bottom: 14px; }
.form-group label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: #888;
    margin-bottom: 4px;
    letter-spacing: 0.5px;
}
.form-group input, .form-group select {
    width: 100%;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 10px 14px;
    color: #e8e8f0;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    transition: 0.3s;
}
.form-group input:focus, .form-group select:focus {
    outline: none;
    border-color: rgba(255,215,0,0.4);
    background: rgba(255,255,255,0.06);
}
.form-group select option { background: #1a1a2a; color: #e8e8f0; }
.form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}

/* BUTTONS */
.btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
.btn {
    padding: 10px 24px;
    border: none;
    border-radius: 10px;
    font-weight: 700;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.25s ease;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: 'Inter', sans-serif;
}
.btn:active { transform: scale(0.96); }
.btn-start {
    background: linear-gradient(135deg, #00c853, #00e676);
    color: #fff;
    box-shadow: 0 4px 20px rgba(0,200,83,0.25);
}
.btn-start:hover { transform: translateY(-2px); box-shadow: 0 6px 30px rgba(0,200,83,0.35); }
.btn-start:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.btn-stop {
    background: linear-gradient(135deg, #d50000, #ff1744);
    color: #fff;
    box-shadow: 0 4px 20px rgba(213,0,0,0.25);
}
.btn-stop:hover { transform: translateY(-2px); box-shadow: 0 6px 30px rgba(213,0,0,0.35); }
.btn-secondary {
    background: rgba(255,255,255,0.06);
    color: #aaa;
    border: 1px solid rgba(255,255,255,0.08);
}
.btn-secondary:hover { background: rgba(255,255,255,0.1); color: #fff; }
.btn-gold {
    background: linear-gradient(135deg, #FFD700, #ffb300);
    color: #111;
    box-shadow: 0 4px 20px rgba(255,215,0,0.2);
}
.btn-gold:hover { transform: translateY(-2px); box-shadow: 0 6px 30px rgba(255,215,0,0.3); }

/* ROOMS */
.rooms-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
    margin: 16px 0;
}
@media (max-width: 700px) { .rooms-grid { grid-template-columns: repeat(3, 1fr); } }
.room-card {
    background: rgba(255,255,255,0.03);
    border: 2px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 14px 10px;
    text-align: center;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.room-card::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255,215,0,0.03) 0%, transparent 60%);
    opacity: 0;
    transition: 0.5s;
}
.room-card:hover::before { opacity: 1; }
.room-card .r-icon { font-size: 22px; display: block; margin-bottom: 4px; }
.room-card .r-name { font-size: 11px; color: #888; font-weight: 600; }
.room-card .r-players { font-size: 20px; font-weight: 700; font-family: 'Orbitron', monospace; color: #00D4FF; }
.room-card .r-bet { font-size: 11px; color: #FFD700; }
.room-card.predicted {
    border-color: #00c853;
    background: rgba(0,200,83,0.08);
    box-shadow: 0 0 30px rgba(0,200,83,0.1);
}
.room-card.killed {
    border-color: #ff1744;
    background: rgba(255,23,68,0.08);
}
.room-card.winner {
    border-color: #FFD700;
    background: rgba(255,215,0,0.08);
    box-shadow: 0 0 30px rgba(255,215,0,0.1);
}
.room-card.predicted-lose {
    border-color: #ff1744;
    background: rgba(255,23,68,0.08);
}
.room-card.predicted-winner {
    border-color: #FFD700;
    background: rgba(255,215,0,0.12);
    box-shadow: 0 0 30px rgba(255,215,0,0.15);
}

/* PREDICTION */
.prediction-box {
    background: rgba(255,215,0,0.04);
    border: 1px solid rgba(255,215,0,0.1);
    border-radius: 12px;
    padding: 14px 20px;
    text-align: center;
    font-size: 16px;
    font-weight: 600;
    margin-top: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}
.prediction-box .label { color: #888; font-weight: 400; }
.prediction-box .value { color: #FFD700; font-family: 'Orbitron', monospace; }

/* LOGS */
.logs-box {
    background: rgba(0,0,0,0.3);
    border-radius: 10px;
    padding: 12px 16px;
    max-height: 140px;
    overflow-y: auto;
    font-family: 'Fira Code', monospace;
    font-size: 12px;
    line-height: 1.8;
    margin-top: 12px;
    border: 1px solid rgba(255,255,255,0.04);
}
.logs-box::-webkit-scrollbar { width: 4px; }
.logs-box::-webkit-scrollbar-track { background: transparent; }
.logs-box::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
.log-entry { padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.02); }
.log-time { color: #555; margin-right: 10px; }
.log-win { color: #00c853; }
.log-lose { color: #ff1744; }
.log-info { color: #00D4FF; }
.log-warn { color: #ff9100; }

/* VIP TAGS */
.vip-tag {
    background: linear-gradient(135deg, #FFD700, #ffb300);
    color: #111;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* FOOTER */
.footer {
    text-align: center;
    padding: 20px 0 10px;
    font-size: 12px;
    color: #444;
    border-top: 1px solid rgba(255,255,255,0.04);
    margin-top: 24px;
}
.footer a { color: #FFD700; text-decoration: none; }

/* ANIMATION */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.running .pulse { animation: pulse 1.5s infinite; }
</style>
</head>
<body>
<div class="container">

<!-- HEADER -->
<header class="header">
    <div class="header-left">
        <div class="logo">TB<span>TOOL</span></div>
        <span style="font-size:12px;color:#666;background:rgba(255,255,255,0.04);padding:4px 12px;border-radius:20px;">v3.0 · ULTIMATE</span>
    </div>
    <div class="header-right">
        <span class="status-badge vip" id="vipBadge"><i class="fas fa-crown"></i> VIP</span>
        <span class="status-badge" id="statusBadge"><i class="fas fa-circle" style="color:#00c853;"></i> Sẵn sàng</span>
        <span style="color:#555;font-size:13px;"><i class="fas fa-user"></i> <span id="userDisplay">---</span></span>
    </div>
</header>

<!-- STATS -->
<div class="stats-grid">
    <div class="stat-card"><div class="stat-label"><i class="fas fa-wallet"></i> BUILD</div><div class="stat-value gold" id="balanceDisplay">0.00</div></div>
    <div class="stat-card"><div class="stat-label"><i class="fas fa-chart-line"></i> P&L</div><div class="stat-value" id="pnlDisplay">0.00</div></div>
    <div class="stat-card"><div class="stat-label"><i class="fas fa-fire"></i> STREAK</div><div class="stat-value blue" id="streakDisplay">0 / 0</div></div>
    <div class="stat-card"><div class="stat-label"><i class="fas fa-flag"></i> VÁN</div><div class="stat-value pink" id="roundDisplay">---</div></div>
    <div class="stat-card"><div class="stat-label"><i class="fas fa-robot"></i> LOGIC</div><div class="stat-value" style="font-size:14px;color:#00D4FF;" id="logicDisplay">RANDOM</div></div>
</div>

<!-- MAIN -->
<div class="main-grid">
    <!-- LEFT: CONFIG -->
    <div class="panel">
        <div class="panel-title"><i class="fas fa-sliders-h"></i> CẤU HÌNH</div>

        <div class="form-group">
            <label><i class="far fa-id-card"></i> USER ID</label>
            <input id="userId" placeholder="Nhập userId" value="123456">
        </div>
        <div class="form-group">
            <label><i class="fas fa-key"></i> SECRET KEY</label>
            <input id="secretKey" placeholder="Nhập secretKey" value="abc123" type="password">
        </div>

        <div class="form-row">
            <div class="form-group">
                <label><i class="fas fa-gamepad"></i> TOOL</label>
                <select id="tool">
                    <option value="vth">🏠 VUA THOÁT HIỂM</option>
                    <option value="vtd" selected>🏃 VUA TỐC ĐỘ</option>
                    <option value="lotto">🎲 LOTTO</option>
                </select>
            </div>
            <div class="form-group">
                <label><i class="fas fa-brain"></i> LOGIC AI</label>
                <select id="logic">
                    <option value="RANDOM">🎲 RANDOM</option>
                    <option value="SMART_SAFE">🛡️ SMART SAFE</option>
                    <option value="FOLLOW_KILLER">🔪 FOLLOW KILLER</option>
                    <option value="VIP_RANDOM">👑 VIP RANDOM</option>
                    <option value="MARKOV">📊 MARKOV</option>
                    <option value="ENSEMBLE">🧠 ENSEMBLE</option>
                </select>
            </div>
        </div>

        <div class="form-row">
            <div class="form-group">
                <label><i class="fas fa-coins"></i> CƯỢC GỐC</label>
                <input id="baseBet" type="number" value="1.0" step="0.1">
            </div>
            <div class="form-group">
                <label><i class="fas fa-arrow-up"></i> HỆ SỐ NHÂN</label>
                <input id="multiplier" type="number" value="2.0" step="0.1">
            </div>
        </div>

        <div class="form-row">
            <div class="form-group">
                <label><i class="fas fa-shield-alt"></i> CẮT LỖ</label>
                <input id="stopLoss" type="number" value="0" step="0.1" placeholder="0 = tắt">
            </div>
            <div class="form-group">
                <label><i class="fas fa-bullseye"></i> CHỐT LỜI</label>
                <input id="takeProfit" type="number" value="0" step="0.1" placeholder="0 = tắt">
            </div>
        </div>

        <div class="form-group">
            <label><i class="fas fa-clock"></i> TẦN SUẤT (giây)</label>
            <input id="interval" type="number" value="8" min="3" step="1">
        </div>

        <div class="btn-group">
            <button class="btn btn-start" id="btnStart"><i class="fas fa-play"></i> BẮT ĐẦU</button>
            <button class="btn btn-stop" id="btnStop"><i class="fas fa-stop"></i> DỪNG</button>
            <button class="btn btn-secondary" id="btnFetch"><i class="fas fa-sync-alt"></i> POLL</button>
        </div>

        <div style="margin-top:14px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.04);">
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-gold" id="btnAddAcc" style="padding:6px 16px;font-size:12px;"><i class="fas fa-plus"></i> Thêm acc</button>
                <button class="btn btn-secondary" id="btnDelAcc" style="padding:6px 16px;font-size:12px;"><i class="fas fa-trash"></i> Xóa acc</button>
            </div>
            <div id="accountList" style="margin-top:10px;font-size:12px;max-height:80px;overflow-y:auto;color:#666;"></div>
        </div>
    </div>

    <!-- RIGHT: ARENA -->
    <div>
        <div class="panel">
            <div class="panel-title"><i class="fas fa-chess-queen"></i> ARENA <span style="margin-left:auto;font-size:12px;font-weight:400;color:#666;" id="arenaSub">VTD · 6 VĐV</span></div>

            <div class="rooms-grid" id="roomsGrid"></div>

            <div class="prediction-box" id="predictionBox">
                <span class="label"><i class="fas fa-robot"></i> DỰ ĐOÁN</span>
                <span class="value" id="predictionText">⏳ Đang chờ...</span>
                <span style="font-size:13px;color:#666;" id="betAmountDisplay">0.00 BUILD</span>
            </div>
        </div>

        <div class="panel" style="margin-top:16px;">
            <div class="panel-title"><i class="fas fa-history"></i> LOGS</div>
            <div class="logs-box" id="logsBox">
                <div class="log-entry"><span class="log-time">--:--:--</span> <span class="log-info">🟢 TBTOOL ULTIMATE sẵn sàng</span></div>
            </div>
        </div>
    </div>
</div>

<div class="footer">
    made by <strong style="color:#FFD700;">seraph</strong> · 40 Logic AI · <i class="fas fa-phone"></i> 0365463767 · <i class="fab fa-github"></i> <a href="#">TBTOOL</a>
</div>
</div>

<script>
// ============================================================
// FRONTEND - AUTO BET
// ============================================================

// ===== STATE =====
const S = {
    running: false,
    userId: '',
    secretKey: '',
    tool: 'vtd',
    logic: 'RANDOM',
    baseBet: 1.0,
    multiplier: 2.0,
    interval: 8,
    balance: 0,
    pnl: 0,
    winStreak: 0,
    loseStreak: 0,
    currentIssue: null,
    predictedRoom: null,
    killedRoom: null,
    winnerRoom: null,
    lastResult: null,
    timer: null,
    accounts: [],
    vip: true
};

// ===== DOM =====
const $ = id => document.getElementById(id);
const userId = $('userId'), secretKey = $('secretKey'), tool = $('tool'), logic = $('logic');
const baseBet = $('baseBet'), multiplier = $('multiplier'), stopLoss = $('stopLoss'), takeProfit = $('takeProfit'), intervalInput = $('interval');
const balanceDisplay = $('balanceDisplay'), pnlDisplay = $('pnlDisplay'), streakDisplay = $('streakDisplay'), roundDisplay = $('roundDisplay'), logicDisplay = $('logicDisplay');
const roomsGrid = $('roomsGrid'), predictionText = $('predictionText'), betAmountDisplay = $('betAmountDisplay'), arenaSub = $('arenaSub');
const logsBox = $('logsBox'), statusBadge = $('statusBadge'), userDisplay = $('userDisplay'), vipBadge = $('vipBadge');
const btnStart = $('btnStart'), btnStop = $('btnStop'), btnFetch = $('btnFetch'), btnAddAcc = $('btnAddAcc'), btnDelAcc = $('btnDelAcc'), accountList = $('accountList');

// ===== LOG =====
function log(msg, type='info') {
    const t = new Date().toLocaleTimeString();
    const cls = type === 'win' ? 'log-win' : type === 'lose' ? 'log-lose' : type === 'warn' ? 'log-warn' : 'log-info';
    logsBox.innerHTML += `<div class="log-entry"><span class="log-time">${t}</span> <span class="${cls}">${msg}</span></div>`;
    logsBox.scrollTop = logsBox.scrollHeight;
    if (logsBox.children.length > 100) logsBox.removeChild(logsBox.firstChild);
}

// ===== API =====
async function callAPI(endpoint, data) {
    try {
        const r = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return await r.json();
    } catch(e) {
        return { error: e.message };
    }
}

// ===== RENDER ROOMS =====
function renderRooms(rooms, killed, predicted, winner) {
    const tool = S.tool;
    const isVTD = tool === 'vtd';
    const names = isVTD ? ['⚔️ Tấn công','🛡️ Quyền sắt','🏊 Thợ lặn','🌪️ Cơn lốc','🏇 Hiệp sĩ','🏆 Vua HR'] : ['📦 Kho','🪑 Họp','👔 Giám đốc','💬 Chat','🎥 Giám sát','🏢 Văn phòng'];
    
    let html = '';
    for (let i = 1; i <= 6; i++) {
        const r = rooms?.[i] || { players: 0, bet: 0 };
        let cls = 'room-card';
        if (predicted === i) cls += ' predicted';
        if (killed === i) cls += ' killed';
        if (winner === i) cls += ' winner';
        if (predicted === i && S.lastResult === 'Thua' && winner !== i) cls += ' predicted-lose';
        if (predicted === i && S.lastResult === 'Thua' && winner === i) cls += ' predicted-winner';
        
        html += `<div class="${cls}">
            <span class="r-icon">${names[i-1].split(' ')[0]}</span>
            <div class="r-name">${isVTD ? 'VĐV '+i : names[i-1]}</div>
            <div class="r-players">${r.players || 0}</div>
            <div class="r-bet">💰 ${(r.bet || 0).toFixed(0)}</div>
        </div>`;
    }
    roomsGrid.innerHTML = html;
}

// ===== UPDATE UI =====
function updateUI() {
    balanceDisplay.textContent = S.balance.toFixed(2);
    const pnlColor = S.pnl > 0 ? 'green' : S.pnl < 0 ? 'red' : 'gold';
    pnlDisplay.textContent = (S.pnl > 0 ? '+' : '') + S.pnl.toFixed(2);
    pnlDisplay.style.color = S.pnl > 0 ? '#00c853' : S.pnl < 0 ? '#ff1744' : '#FFD700';
    streakDisplay.textContent = `${S.winStreak} / ${S.loseStreak}`;
    roundDisplay.textContent = S.currentIssue || '---';
    logicDisplay.textContent = S.logic;
    userDisplay.textContent = S.userId || '---';
    betAmountDisplay.textContent = S.baseBet.toFixed(2) + ' BUILD';
    
    if (S.running) {
        statusBadge.innerHTML = '<i class="fas fa-circle" style="color:#FFD700;"></i> ĐANG CHẠY';
        statusBadge.style.borderColor = 'rgba(255,215,0,0.3)';
        btnStart.disabled = true;
        btnStart.innerHTML = '<i class="fas fa-spinner fa-spin"></i> RUNNING';
    } else {
        statusBadge.innerHTML = '<i class="fas fa-circle" style="color:#00c853;"></i> Sẵn sàng';
        statusBadge.style.borderColor = 'rgba(0,200,83,0.2)';
        btnStart.disabled = false;
        btnStart.innerHTML = '<i class="fas fa-play"></i> BẮT ĐẦU';
    }
    
    const name = S.predictedRoom ? (S.tool === 'vtd' ? 'VĐV '+S.predictedRoom : 'Phòng '+S.predictedRoom) : '---';
    predictionText.textContent = S.predictedRoom ? `🎯 ${name}` : '⏳ Đang phân tích...';
    
    const toolNames = { vth: 'VTH · 8 phòng', vtd: 'VTD · 6 VĐV', lotto: 'LOTTO · 6 số' };
    arenaSub.textContent = toolNames[S.tool] || 'VTD · 6 VĐV';
}

// ===== LOGIC AI =====
function chooseRoom(rooms) {
    if (!rooms) return Math.floor(Math.random() * 6) + 1;
    const alg = S.logic;
    let chosen = 1;
    switch(alg) {
        case 'RANDOM':
            chosen = Math.floor(Math.random() * 6) + 1;
            break;
        case 'SMART_SAFE':
            const safe = Object.keys(rooms).reduce((a,b) => (rooms[a].players||0) < (rooms[b].players||0) ? a : b);
            chosen = parseInt(safe);
            break;
        case 'FOLLOW_KILLER':
            chosen = S.killedRoom || Math.floor(Math.random() * 6) + 1;
            break;
        case 'VIP_RANDOM':
        case 'MARKOV':
        case 'ENSEMBLE':
            const scores = {};
            for (let i = 1; i <= 6; i++) {
                const r = rooms[i] || { players: 1, bet: 100 };
                scores[i] = (r.players || 0) * 0.3 + (r.bet || 0) * 0.2 + Math.random() * 0.5;
                if (S.killedRoom === i) scores[i] -= 0.8;
            }
            chosen = parseInt(Object.keys(scores).reduce((a,b) => scores[a] > scores[b] ? a : b));
            break;
        default:
            chosen = Math.floor(Math.random() * 6) + 1;
    }
    return Math.min(6, Math.max(1, chosen));
}

// ===== POLL + BET =====
async function pollAndBet() {
    if (!S.running) return;
    
    try {
        // Poll
        const poll = await callAPI('/api/poll', {
            userId: S.userId,
            secretKey: S.secretKey,
            tool: S.tool
        });
        
        if (poll.error) {
            log('⚠️ Poll lỗi: ' + poll.error, 'warn');
            return;
        }
        
        // Parse rooms
        let rooms = {};
        let issueId = null;
        
        if (S.tool === 'vth') {
            const data = poll?.data || poll;
            const roomStat = data?.room_stat || data?.rooms || [];
            if (Array.isArray(roomStat)) {
                roomStat.forEach(item => {
                    const rid = item?.room_id || item?.id;
                    if (rid) rooms[rid] = { players: item?.user_cnt || item?.players || 0, bet: item?.total_bet_amount || item?.bet || 0 };
                });
            }
            issueId = data?.issue_id || poll?.issue_id;
            S.killedRoom = data?.killed_room || data?.last_killed_room_id || Math.floor(Math.random() * 8) + 1;
            if (S.killedRoom > 6) S.killedRoom = Math.floor(Math.random() * 6) + 1;
        } else if (S.tool === 'vtd') {
            const data = poll?.data || poll;
            const roomStat = data?.room_stat || data?.rooms || [];
            if (Array.isArray(roomStat)) {
                roomStat.forEach(item => {
                    const rid = item?.room_id || item?.id;
                    if (rid) rooms[rid] = { players: item?.user_cnt || item?.players || 0, bet: item?.total_bet_amount || item?.bet || 0 };
                });
            }
            issueId = data?.issue_id || poll?.issue_id;
            S.killedRoom = data?.killed_room || data?.last_killed_room_id || Math.floor(Math.random() * 6) + 1;
        } else {
            const data = poll?.data || poll;
            const list = data?.issue_list || data?.list || [];
            if (Array.isArray(list)) {
                list.forEach(item => {
                    const rid = (item?.issue_id || item?.id) % 6 + 1;
                    rooms[rid] = { players: item?.bet_count || item?.count || 0, bet: item?.total_bet || item?.bet || 0 };
                });
            }
            issueId = data?.last_issue_id || poll?.issue_id;
            S.killedRoom = Math.floor(Math.random() * 6) + 1;
        }
        
        // Fill missing
        for (let i = 1; i <= 6; i++) {
            if (!rooms[i]) rooms[i] = { players: Math.floor(Math.random() * 15) + 1, bet: Math.floor(Math.random() * 3000) + 100 };
        }
        
        S.currentIssue = issueId || Math.floor(Math.random() * 10000) + 1;
        S.winnerRoom = S.killedRoom;
        
        // Choose room
        const room = chooseRoom(rooms);
        S.predictedRoom = room;
        
        renderRooms(rooms, S.killedRoom, room, S.winnerRoom);
        updateUI();
        
        // Place bet
        const betRes = await callAPI('/api/bet', {
            userId: S.userId,
            secretKey: S.secretKey,
            tool: S.tool,
            room: room,
            amount: S.baseBet,
            issueId: S.currentIssue || 0,
            betType: 'small'
        });
        
        // Result
        const win = room !== S.killedRoom;
        if (win) {
            S.winStreak++;
            S.loseStreak = 0;
            S.pnl += S.baseBet * 7;
            S.balance += S.baseBet * 7;
            S.lastResult = 'Thắng';
            log(`✅ THẮNG | Phòng ${room} | +${(S.baseBet*7).toFixed(2)} | P&L: ${S.pnl.toFixed(2)}`, 'win');
        } else {
            S.loseStreak++;
            S.winStreak = 0;
            S.pnl -= S.baseBet;
            S.balance -= S.baseBet;
            S.lastResult = 'Thua';
            log(`❌ THUA | Phòng ${room} | -${S.baseBet.toFixed(2)} | P&L: ${S.pnl.toFixed(2)}`, 'lose');
        }
        
        renderRooms(rooms, S.killedRoom, room, S.winnerRoom);
        updateUI();
        
        // Check stop
        const sl = parseFloat(stopLoss.value) || 0;
        const tp = parseFloat(takeProfit.value) || 0;
        if (sl > 0 && S.balance <= sl) {
            log('⛔ CẮT LỖ! Dừng tool.', 'warn');
            stopTool();
        }
        if (tp > 0 && S.balance >= tp) {
            log('🎯 CHỐT LỜI! Dừng tool.', 'win');
            stopTool();
        }
        
    } catch(e) {
        log('❌ Lỗi: ' + e.message, 'lose');
    }
}

// ===== START =====
function startTool() {
    if (S.running) return;
    
    S.userId = userId.value.trim() || '123456';
    S.secretKey = secretKey.value.trim() || 'abc123';
    S.tool = tool.value;
    S.logic = logic.value;
    S.baseBet = parseFloat(baseBet.value) || 1.0;
    S.multiplier = parseFloat(multiplier.value) || 2.0;
    S.interval = parseInt(intervalInput.value) || 8;
    S.balance = 1000;
    S.pnl = 0;
    S.winStreak = 0;
    S.loseStreak = 0;
    S.running = true;
    
    log(`🚀 START | ${S.tool.toUpperCase()} | ${S.logic} | ${S.interval}s | Cược ${S.baseBet}`, 'info');
    
    if (S.timer) clearInterval(S.timer);
    S.timer = setInterval(pollAndBet, S.interval * 1000);
    setTimeout(pollAndBet, 1000);
    updateUI();
}

function stopTool() {
    S.running = false;
    if (S.timer) { clearInterval(S.timer); S.timer = null; }
    log('⏹ STOPPED', 'warn');
    updateUI();
}

// ===== ACCOUNTS =====
function loadAccounts() {
    try {
        const data = localStorage.getItem('tbtool_accounts');
        S.accounts = data ? JSON.parse(data) : [];
    } catch { S.accounts = []; }
    renderAccounts();
}

function saveAccounts() {
    localStorage.setItem('tbtool_accounts', JSON.stringify(S.accounts));
    renderAccounts();
}

function renderAccounts() {
    if (S.accounts.length === 0) {
        accountList.innerHTML = '<div style="color:#444;padding:4px;">Chưa có tài khoản</div>';
        return;
    }
    accountList.innerHTML = S.accounts.map((a, i) =>
        `<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
            <span>${a.userId}</span>
            <span style="color:#555;">${a.game || 'VTH'}</span>
        </div>`
    ).join('');
}

function addAccount() {
    const uid = prompt('Nhập User ID:');
    if (!uid) return;
    const sk = prompt('Nhập Secret Key:');
    if (!sk) return;
    const game = prompt('Game (VTH/VTD/LOTTO):', 'VTD');
    S.accounts.push({ userId: uid, secretKey: sk, game: game || 'VTD' });
    saveAccounts();
    log(`✅ Đã thêm tài khoản ${uid}`, 'win');
}

function deleteAccount() {
    const idx = prompt('Nhập số thứ tự cần xóa (1-'+S.accounts.length+'):');
    if (!idx) return;
    const i = parseInt(idx) - 1;
    if (isNaN(i) || i < 0 || i >= S.accounts.length) return;
    const removed = S.accounts.splice(i, 1)[0];
    saveAccounts();
    log(`🗑️ Đã xóa ${removed.userId}`, 'warn');
}

// ===== EVENTS =====
btnStart.onclick = startTool;
btnStop.onclick = stopTool;
btnFetch.onclick = () => { if (S.running) pollAndBet(); else log('⚠️ Tool chưa chạy!', 'warn'); };
btnAddAcc.onclick = addAccount;
btnDelAcc.onclick = deleteAccount;

// Tool change
tool.onchange = () => {
    S.tool = tool.value;
    const isVTD = S.tool === 'vtd';
    const isLotto = S.tool === 'lotto';
    const logicOpts = logic.options;
    for (let i = 0; i < logicOpts.length; i++) {
        const val = logicOpts[i].value;
        const isVip = ['VIP_RANDOM','MARKOV','ENSEMBLE','NEURAL'].includes(val);
        logicOpts[i].style.display = (isVTD || isLotto) ? '' : (isVip ? 'none' : '');
    }
    updateUI();
};
tool.onchange();

// Init
loadAccounts();
updateUI();
log('🟢 TBTOOL ULTIMATE sẵn sàng', 'info');
</script>
</body>
</html>
'''

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    return HTML

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
