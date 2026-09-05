import os
import json
import time
import random
import threading
import requests
import websocket
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from collections import defaultdict, Counter

app = Flask(__name__)
CORS(app)

# ====== CACHE ======
game_cache = {
    "vth": {"issue": None, "rooms": {}, "killed": None, "updated": 0},
    "vtd": {"issue": None, "rooms": {}, "killed": None, "updated": 0},
    "lotto": {"issue": None, "rooms": {}, "killed": None, "updated": 0}
}
vth_cache = {"rooms": {}, "issue": None, "killed": None, "updated": 0}
last_bet_issue = {}
bet_history = []
killer_history = []
seq_index = 0

# ====== VTH WEBSOCKET ======
def vth_ws_loop():
    global vth_cache, game_cache
    while True:
        try:
            def on_msg(ws, msg):
                global vth_cache, game_cache
                try:
                    data = json.loads(msg)
                    if "room_stat" in str(data):
                        vth_cache["updated"] = time.time()
                        vth_cache["rooms"] = {}
                        for r in data.get("room_stat", []):
                            rid = r.get("room_id")
                            if rid:
                                vth_cache["rooms"][rid] = {
                                    "players": r.get("user_cnt", 0),
                                    "bet": r.get("total_bet_amount", 0)
                                }
                        vth_cache["issue"] = data.get("issue_id")
                        vth_cache["killed"] = data.get("last_killed_room_id")
                        game_cache["vth"] = {
                            "issue": vth_cache["issue"],
                            "rooms": vth_cache["rooms"],
                            "killed": vth_cache["killed"],
                            "updated": vth_cache["updated"]
                        }
                except:
                    pass

            ws = websocket.WebSocketApp(
                "wss://api.escapemaster.net/escape_master/ws",
                on_open=lambda ws: ws.send(json.dumps({"msg_type": "handle_enter_game", "asset_type": "BUILD"})),
                on_message=on_msg,
                on_error=lambda ws, err: None,
                on_close=lambda ws, code, msg: None
            )
            ws.run_forever(ping_interval=15, ping_timeout=6)
        except:
            pass
        time.sleep(5)

threading.Thread(target=vth_ws_loop, daemon=True).start()

# ====== GỌI API ======
def call_api(method, url, headers=None, data=None, params=None):
    try:
        if method.upper() == 'GET':
            r = requests.get(url, headers=headers, params=params, timeout=10)
        else:
            r = requests.post(url, headers=headers, json=data, timeout=10)
        return r.json() if r.text else {}
    except:
        return {}

# ============================================================
# 40 THUẬT TOÁN - FREE (1-20) + VIP (21-40)
# ============================================================

ROOM_ORDER = list(range(1, 7))

# ----- FREE 1-20 -----
def algo_random(rooms, killed):
    return random.choice(ROOM_ORDER)

def algo_min_player(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    return min(rooms.keys(), key=lambda r: rooms.get(r, {}).get('players', 0))

def algo_min_bet(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    return min(rooms.keys(), key=lambda r: rooms.get(r, {}).get('bet', 0))

def algo_max_player(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    return max(rooms.keys(), key=lambda r: rooms.get(r, {}).get('players', 0))

def algo_max_bet(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    return max(rooms.keys(), key=lambda r: rooms.get(r, {}).get('bet', 0))

def algo_follow_killer(rooms, killed):
    return killed if killed and killed in ROOM_ORDER else random.choice(ROOM_ORDER)

def algo_avoid_killer(rooms, killed):
    candidates = [r for r in ROOM_ORDER if r != killed]
    return random.choice(candidates) if candidates else random.choice(ROOM_ORDER)

def algo_sequential(rooms, killed):
    global seq_index
    r = ROOM_ORDER[seq_index % len(ROOM_ORDER)]
    seq_index += 1
    return r

def algo_alternate(rooms, killed):
    if len(bet_history) < 2: return random.choice(ROOM_ORDER)
    last = bet_history[-1].get('room')
    candidates = [r for r in ROOM_ORDER if r != last]
    return random.choice(candidates) if candidates else random.choice(ROOM_ORDER)

def algo_hot(rooms, killed):
    if not killer_history: return random.choice(ROOM_ORDER)
    counts = Counter(killer_history)
    return max(counts, key=counts.get)

def algo_cold(rooms, killed):
    if not killer_history: return random.choice(ROOM_ORDER)
    counts = Counter(killer_history)
    return min(counts, key=counts.get)

def algo_smart_safe(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    scores = {}
    for r in ROOM_ORDER:
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        scores[r] = p * 0.5 + b * 0.0001
        if r == killed:
            scores[r] += 10
    return min(scores, key=scores.get)

def algo_probability(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    counts = Counter(killer_history[-10:])
    total = sum(counts.values()) or 1
    probs = {r: counts.get(r, 0) / total for r in ROOM_ORDER}
    return min(probs, key=probs.get)

def algo_trend(rooms, killed):
    if len(killer_history) < 5: return random.choice(ROOM_ORDER)
    last_3 = killer_history[-3:]
    if len(set(last_3)) == 1:
        candidates = [r for r in ROOM_ORDER if r != last_3[0]]
        return random.choice(candidates) if candidates else random.choice(ROOM_ORDER)
    return random.choice(ROOM_ORDER)

def algo_balance(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    avg_p = sum(r.get('players', 0) for r in rooms.values()) / len(rooms)
    avg_b = sum(r.get('bet', 0) for r in rooms.values()) / len(rooms)
    scores = {}
    for r in ROOM_ORDER:
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        scores[r] = abs(p - avg_p) + abs(b - avg_b) * 0.001
    return min(scores, key=scores.get)

def algo_pattern(rooms, killed):
    if len(killer_history) < 4: return random.choice(ROOM_ORDER)
    for i in range(len(killer_history) - 3, -1, -1):
        if killer_history[i:i+3] == killer_history[-3:]:
            return killer_history[i+3] if i+3 < len(killer_history) else random.choice(ROOM_ORDER)
    return random.choice(ROOM_ORDER)

def algo_follow_loser(rooms, killed):
    if len(bet_history) < 2: return random.choice(ROOM_ORDER)
    return bet_history[-1].get('room', random.choice(ROOM_ORDER))

def algo_median(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    sorted_p = sorted(rooms.items(), key=lambda x: x[1].get('players', 0))
    return sorted_p[len(sorted_p)//2][0]

def algo_extreme(rooms, killed):
    if not rooms: return random.choice(ROOM_ORDER)
    max_p = max(rooms.items(), key=lambda x: x[1].get('players', 0))
    min_p = min(rooms.items(), key=lambda x: x[1].get('players', 0))
    return random.choice([max_p[0], min_p[0]])

# ----- VIP 21-40 -----
def algo_vip_random(rooms, killed):
    funcs = [algo_random, algo_min_player, algo_min_bet, algo_max_player, algo_max_bet,
             algo_follow_killer, algo_avoid_killer, algo_sequential, algo_alternate,
             algo_hot, algo_cold, algo_smart_safe, algo_probability, algo_trend,
             algo_balance, algo_pattern, algo_follow_loser, algo_median, algo_extreme]
    return random.choice(funcs)(rooms, killed)

def algo_markov(rooms, killed):
    if len(killer_history) < 5: return random.choice(ROOM_ORDER)
    trans = defaultdict(lambda: defaultdict(int))
    for i in range(len(killer_history)-1):
        trans[killer_history[i]][killer_history[i+1]] += 1
    last = killer_history[-1]
    if trans[last]:
        return max(trans[last], key=trans[last].get)
    return random.choice(ROOM_ORDER)

def algo_bayes(rooms, killed):
    if len(killer_history) < 5: return random.choice(ROOM_ORDER)
    counts = Counter(killer_history)
    total = len(killer_history)
    prior = {r: 1/6 for r in ROOM_ORDER}
    likelihood = {r: (counts.get(r, 0) + 1) / (total + 6) for r in ROOM_ORDER}
    posterior = {r: prior[r] * likelihood[r] for r in ROOM_ORDER}
    total_p = sum(posterior.values())
    return min(posterior, key=lambda r: posterior[r]/total_p)

def algo_neural(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    scores = {}
    for r in ROOM_ORDER:
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        kill_count = killer_history.count(r)
        layer1 = (1 - p/20) * 0.4 + (1 - b/5000) * 0.3 + (1 - kill_count/max(1, len(killer_history))) * 0.3
        layer2 = layer1 * 0.7 + (0.3 if r == killed else 0)
        scores[r] = layer2
    return max(scores, key=scores.get)

def algo_fuzzy(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    scores = {}
    for r in ROOM_ORDER:
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        k = killer_history.count(r) / max(1, len(killer_history))
        safe = 1 - p/30 - b/10000 - k
        scores[r] = safe
    return max(scores, key=scores.get)

def algo_genetic(rooms, killed):
    if len(killer_history) < 5: return random.choice(ROOM_ORDER)
    fitness = {r: 1 - killer_history.count(r)/max(1, len(killer_history)) for r in ROOM_ORDER}
    total_f = sum(fitness.values())
    if total_f <= 0: return random.choice(ROOM_ORDER)
    rnd = random.random() * total_f
    for r, f in fitness.items():
        rnd -= f
        if rnd <= 0:
            return r
    return random.choice(ROOM_ORDER)

def algo_ant_colony(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    pheromone = {r: 1 / (killer_history.count(r) + 1) for r in ROOM_ORDER}
    return max(pheromone, key=pheromone.get)

def algo_particle_swarm(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    scores = {}
    for r in ROOM_ORDER:
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        k = killer_history.count(r)
        scores[r] = (1 - p/25) * 0.4 + (1 - b/8000) * 0.3 + (1 - k/max(1, len(killer_history))) * 0.3
    return max(scores, key=scores.get)

def algo_knn(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    k = min(3, len(killer_history))
    nearest = killer_history[-k:]
    counts = Counter(nearest)
    return min(counts, key=counts.get)

def algo_decision_tree(rooms, killed):
    if len(killer_history) < 5: return random.choice(ROOM_ORDER)
    if killed and killed in ROOM_ORDER:
        if rooms.get(killed, {}).get('players', 0) > 5:
            candidates = [r for r in ROOM_ORDER if r != killed]
            return random.choice(candidates) if candidates else random.choice(ROOM_ORDER)
    return algo_smart_safe(rooms, killed)

def algo_random_forest(rooms, killed):
    predictions = []
    for _ in range(5):
        if random.random() > 0.5:
            predictions.append(algo_hot(rooms, killed))
        else:
            predictions.append(algo_cold(rooms, killed))
    counts = Counter(predictions)
    return max(counts, key=counts.get)

def algo_gradient_boost(rooms, killed):
    if len(killer_history) < 3: return random.choice(ROOM_ORDER)
    scores = {}
    for r in ROOM_ORDER:
        base = 0.5
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        k = killer_history.count(r) / max(1, len(killer_history))
        base += 0.3 * (1 - p/20)
        base += 0.2 * (1 - b/5000)
        base -= 0.3 * k
        scores[r] = base
    return max(scores, key=scores.get)

def algo_lstm(rooms, killed):
    if len(killer_history) < 4: return random.choice(ROOM_ORDER)
    last_4 = killer_history[-4:]
    if len(set(last_4)) == 1:
        candidates = [r for r in ROOM_ORDER if r != last_4[0]]
        return random.choice(candidates) if candidates else random.choice(ROOM_ORDER)
    if last_4[0] == last_4[2] and last_4[1] == last_4[3]:
        return last_4[0]
    return algo_markov(rooms, killed)

def algo_transformer(rooms, killed):
    if len(killer_history) < 4: return random.choice(ROOM_ORDER)
    attention = {}
    for r in ROOM_ORDER:
        p = rooms.get(r, {}).get('players', 0)
        b = rooms.get(r, {}).get('bet', 0)
        k = killer_history.count(r)
        recency = 1 - (killer_history[-3:].count(r) / 3) if len(killer_history) >= 3 else 0.5
        attention[r] = recency * 0.5 + (1 - p/20) * 0.3 + (1 - b/5000) * 0.2
    return max(attention, key=attention.get)

def algo_ensemble(rooms, killed):
    votes = defaultdict(int)
    vip_funcs = [algo_markov, algo_bayes, algo_neural, algo_fuzzy, algo_genetic,
                 algo_ant_colony, algo_particle_swarm, algo_knn, algo_decision_tree,
                 algo_random_forest, algo_gradient_boost, algo_lstm, algo_transformer]
    for func in vip_funcs:
        try:
            votes[func(rooms, killed)] += 1
        except:
            pass
    if not votes:
        return random.choice(ROOM_ORDER)
    return max(votes, key=votes.get)

# ====== MAP THUẬT TOÁN ======
ALGO_MAP = {
    # FREE
    "RANDOM": algo_random,
    "MIN_PLAYER": algo_min_player,
    "MIN_BET": algo_min_bet,
    "MAX_PLAYER": algo_max_player,
    "MAX_BET": algo_max_bet,
    "FOLLOW_KILLER": algo_follow_killer,
    "AVOID_KILLER": algo_avoid_killer,
    "SEQUENTIAL": algo_sequential,
    "ALTERNATE": algo_alternate,
    "HOT": algo_hot,
    "COLD": algo_cold,
    "SMART_SAFE": algo_smart_safe,
    "PROBABILITY": algo_probability,
    "TREND": algo_trend,
    "BALANCE": algo_balance,
    "PATTERN": algo_pattern,
    "FOLLOW_LOSER": algo_follow_loser,
    "MEDIAN": algo_median,
    "EXTREME": algo_extreme,
    # VIP
    "VIP_RANDOM": algo_vip_random,
    "MARKOV": algo_markov,
    "BAYES": algo_bayes,
    "NEURAL": algo_neural,
    "FUZZY": algo_fuzzy,
    "GENETIC": algo_genetic,
    "ANT_COLONY": algo_ant_colony,
    "PARTICLE_SWARM": algo_particle_swarm,
    "KNN": algo_knn,
    "DECISION_TREE": algo_decision_tree,
    "RANDOM_FOREST": algo_random_forest,
    "GRADIENT_BOOST": algo_gradient_boost,
    "LSTM": algo_lstm,
    "TRANSFORMER": algo_transformer,
    "ENSEMBLE": algo_ensemble,
}

# ====== API ======
@app.route('/api/poll', methods=['POST'])
def poll():
    data = request.json
    tool = data.get('tool', 'vtd')
    uid = data.get('userId')
    sk = data.get('secretKey')
    
    headers = {'user-id': str(uid), 'user-secret-key': sk, 'content-type': 'application/json'}
    
    if tool == 'vth':
        cache = game_cache.get("vth", {})
        if cache.get("updated") and (time.time() - cache.get("updated", 0)) < 30:
            return jsonify({'status': 'ok', 'issue_id': cache.get("issue"), 'killed': cache.get("killed"), 'rooms': cache.get("rooms", {})})
        return jsonify({'status': 'ok', 'issue_id': None, 'rooms': {}})
    
    elif tool == 'vtd':
        result = call_api('GET', 'https://api.sprintrun.win/sprint/home', headers, params={'asset': 'BUILD'})
        rooms = {}
        issue = None
        killed = None
        if result and 'data' in result:
            issue = result.get('data', {}).get('issue_id')
            killed = result.get('data', {}).get('last_killed_room_id')
            for r in result.get('data', {}).get('room_stat', []):
                rid = r.get('room_id')
                if rid:
                    rooms[rid] = {'players': r.get('user_cnt', 0), 'bet': r.get('total_bet_amount', 0)}
        game_cache["vtd"] = {"issue": issue, "rooms": rooms, "killed": killed, "updated": time.time()}
        return jsonify({'status': 'ok', 'issue_id': issue, 'killed': killed, 'rooms': rooms})
    
    else:
        result = call_api('GET', 'https://api.winhash.net/lucky_game/home', headers, params={'game_id': 1, 'asset': 'BUILD'})
        rooms = {}
        issue = None
        killed = random.randint(1, 6)
        if result and 'data' in result:
            issue = result.get('data', {}).get('last_issue_id')
            for item in result.get('data', {}).get('issue_list', []):
                rid = (item.get('issue_id', 0) % 6) + 1
                rooms[rid] = {'players': item.get('bet_count', 0), 'bet': item.get('total_bet', 0)}
        game_cache["lotto"] = {"issue": issue, "rooms": rooms, "killed": killed, "updated": time.time()}
        return jsonify({'status': 'ok', 'issue_id': issue, 'killed': killed, 'rooms': rooms})

@app.route('/api/bet', methods=['POST'])
def bet():
    data = request.json
    tool = data.get('tool', 'vtd')
    uid = data.get('userId')
    sk = data.get('secretKey')
    room = data.get('room')
    amount = float(data.get('amount', 1.0))
    issue = data.get('issueId')
    
    headers = {'user-id': str(uid), 'user-secret-key': sk, 'content-type': 'application/json'}
    
    if tool == 'vth':
        url = 'https://api.escapemaster.net/escape_game/bet'
        payload = {'asset_type': 'BUILD', 'user_id': uid, 'room_id': int(room), 'bet_amount': amount}
    elif tool == 'vtd':
        url = 'https://api.sprintrun.win/sprint/bet'
        payload = {'issue_id': int(issue or 0), 'bet_group': 'not_winner',
                   'asset_type': 'BUILD', 'athlete_id': int(room), 'bet_amount': amount}
    else:
        url = 'https://api.winhash.net/lucky_game/v2/create_order'
        bet_ids = {'small': 70309, 'big': 71218, 'draw': 71011}
        payload = {'game_id': 1, 'issue_id': int(issue or 0),
                   'items': [{'id': bet_ids.get('small', 70309), 'amount': str(amount), 'asset': 'BUILD'}]}
    
    result = call_api('POST', url, headers, payload)
    return jsonify(result)

# ====== HTML ======
HTML = '''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TBTOOL - AUTO BET</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a12;color:#e0e0e0;font-family:monospace;padding:20px}
.container{max-width:800px;margin:0 auto}
.header{text-align:center;border:2px solid #FFD700;border-radius:12px;padding:15px;margin-bottom:20px;background:#111118}
.header h1{color:#FFD700}
.panel{background:#12121c;border:1px solid #2a2a3a;border-radius:10px;padding:16px;margin-bottom:16px}
.row{display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap}
.row label{min-width:100px;color:#aaa;font-size:13px}
.row input,.row select{background:#1a1a2a;border:1px solid #2a2a3a;color:#fff;padding:6px 12px;border-radius:6px;flex:1}
.btn{padding:8px 20px;border:none;border-radius:6px;cursor:pointer;font-weight:bold}
.btn-success{background:#00c853;color:#fff}
.btn-danger{background:#d50000;color:#fff}
.btn-warning{background:#ff9100;color:#111}
.status{background:#1a1a2a;padding:10px;border-radius:6px;font-size:13px;margin-top:10px}
.logs{background:#0a0a12;border:1px solid #1a1a2a;border-radius:6px;padding:10px;max-height:200px;overflow-y:auto;font-size:12px}
.log-win{color:#00c853}
.log-lose{color:#ff1744}
.log-info{color:#00D4FF}
.log-warn{color:#ff9100}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>🏆 TBTOOL AUTO BET</h1></div>

<div class="panel">
<div class="row"><label>User ID</label><input id="userId" placeholder="Nhập userId"></div>
<div class="row"><label>Secret Key</label><input id="secretKey" placeholder="Nhập secretKey" type="password"></div>
<div class="row"><label>Tool</label>
<select id="tool"><option value="vtd">VTD</option><option value="vth">VTH</option><option value="lotto">LOTTO</option></select></div>
<div class="row"><label>Thuật toán</label>
<select id="algo">
<option value="RANDOM">RANDOM</option>
<option value="MIN_PLAYER">MIN_PLAYER</option>
<option value="MIN_BET">MIN_BET</option>
<option value="MAX_PLAYER">MAX_PLAYER</option>
<option value="MAX_BET">MAX_BET</option>
<option value="FOLLOW_KILLER">FOLLOW_KILLER</option>
<option value="AVOID_KILLER">AVOID_KILLER</option>
<option value="SEQUENTIAL">SEQUENTIAL</option>
<option value="ALTERNATE">ALTERNATE</option>
<option value="HOT">HOT</option>
<option value="COLD">COLD</option>
<option value="SMART_SAFE">SMART_SAFE</option>
<option value="PROBABILITY">PROBABILITY</option>
<option value="TREND">TREND</option>
<option value="BALANCE">BALANCE</option>
<option value="PATTERN">PATTERN</option>
<option value="FOLLOW_LOSER">FOLLOW_LOSER</option>
<option value="MEDIAN">MEDIAN</option>
<option value="EXTREME">EXTREME</option>
<option value="VIP_RANDOM">👑 VIP_RANDOM</option>
<option value="MARKOV">👑 MARKOV</option>
<option value="BAYES">👑 BAYES</option>
<option value="NEURAL">👑 NEURAL</option>
<option value="FUZZY">👑 FUZZY</option>
<option value="GENETIC">👑 GENETIC</option>
<option value="ANT_COLONY">👑 ANT_COLONY</option>
<option value="PARTICLE_SWARM">👑 PARTICLE_SWARM</option>
<option value="KNN">👑 KNN</option>
<option value="DECISION_TREE">👑 DECISION_TREE</option>
<option value="RANDOM_FOREST">👑 RANDOM_FOREST</option>
<option value="GRADIENT_BOOST">👑 GRADIENT_BOOST</option>
<option value="LSTM">👑 LSTM</option>
<option value="TRANSFORMER">👑 TRANSFORMER</option>
<option value="ENSEMBLE">👑 ENSEMBLE</option>
</select></div>
<div class="row"><label>Cược gốc</label><input id="baseBet" type="number" value="1" step="0.1"></div>
<div class="row"><label>Tần suất (s)</label><input id="interval" type="number" value="8" min="3"></div>
<div style="display:flex;gap:10px;margin-top:10px">
<button class="btn btn-success" id="btnStart">▶️ BẮT ĐẦU</button>
<button class="btn btn-danger" id="btnStop">⏹ DỪNG</button>
</div>
<div class="status" id="status">⏳ Chưa chạy</div>
</div>

<div class="panel"><div class="logs" id="logs"></div></div>
</div>
<script>
const $=id=>document.getElementById(id);
const userId=$('userId'), secretKey=$('secretKey'), tool=$('tool'), algo=$('algo');
const baseBet=$('baseBet'), intervalInput=$('interval');
const status=$('status'), logs=$('logs');
let running=false, timer=null, lastIssue={};

function log(msg, type='info'){
    const t=new Date().toLocaleTimeString();
    const colors={info:'log-info',win:'log-win',lose:'log-lose',warn:'log-warn'};
    logs.innerHTML+=`<div class="${colors[type]||'log-info'}">${t} ${msg}</div>`;
    logs.scrollTop=logs.scrollHeight;
}

async function callAPI(endpoint, data){
    try{
        const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
        return await r.json();
    }catch(e){return {error:e.message};}
}

function chooseRoom(rooms, killed){
    // Gọi backend chọn phòng theo thuật toán
    // Mô phỏng nhanh bên frontend
    const alg=algo.value;
    if(!rooms || Object.keys(rooms).length===0) return Math.floor(Math.random()*6)+1;
    let chosen=1;
    switch(alg){
        case 'RANDOM': chosen=Math.floor(Math.random()*6)+1; break;
        case 'MIN_PLAYER': {
            let minP=999; for(const [r,data] of Object.entries(rooms)){if(data.players<minP){minP=data.players; chosen=parseInt(r);}} break;
        }
        case 'MIN_BET': {
            let minB=999999; for(const [r,data] of Object.entries(rooms)){if(data.bet<minB){minB=data.bet; chosen=parseInt(r);}} break;
        }
        case 'MAX_PLAYER': {
            let maxP=-1; for(const [r,data] of Object.entries(rooms)){if(data.players>maxP){maxP=data.players; chosen=parseInt(r);}} break;
        }
        case 'FOLLOW_KILLER': chosen=killed||Math.floor(Math.random()*6)+1; break;
        case 'AVOID_KILLER': {
            const candidates=[1,2,3,4,5,6].filter(r=>r!=killed);
            chosen=candidates.length?candidates[Math.floor(Math.random()*candidates.length)]:Math.floor(Math.random()*6)+1; break;
        }
        case 'SEQUENTIAL': {
            if(!window._seq) window._seq=0;
            chosen=(window._seq%6)+1; window._seq++; break;
        }
        case 'SMART_SAFE': {
            let best=1, bestScore=999; for(const [r,data] of Object.entries(rooms)){
                const score=data.players*0.5+data.bet*0.001+(r==killed?10:0);
                if(score<bestScore){bestScore=score; best=parseInt(r);}
            } chosen=best; break;
        }
        default: chosen=Math.floor(Math.random()*6)+1;
    }
    return Math.min(6, Math.max(1, chosen));
}

async function autoBet(){
    if(!running) return;
    const uid=userId.value.trim(), sk=secretKey.value.trim();
    if(!uid||!sk){ log('⚠️ Nhập User ID và Secret Key','warn'); return; }
    
    const poll=await callAPI('/api/poll', {userId:uid, secretKey:sk, tool:tool.value});
    if(poll.error){ log('⚠️ Poll lỗi: '+poll.error,'warn'); return; }
    
    const issue=poll?.issue_id;
    if(!issue){ log('⏳ Chưa có phiên mới','warn'); return; }
    if(lastIssue[tool.value]===issue){ log('⏳ Đã cược phiên #'+issue,'warn'); return; }
    
    const rooms=poll?.rooms||{};
    const killed=poll?.killed;
    const room=chooseRoom(rooms, killed);
    
    const amt=parseFloat(baseBet.value)||1;
    const bet=await callAPI('/api/bet', {
        userId:uid, secretKey:sk, tool:tool.value,
        room:room, amount:amt, issueId:issue
    });
    
    lastIssue[tool.value]=issue;
    log(`💰 Cược ${amt} vào ${tool.value==='vtd'?'VĐV':'Phòng'} ${room} | Ván #${issue} | ${algo.value}`, 'win');
    status.innerHTML=`✅ Đã cược phiên #${issue} | Phòng ${room} | ${amt} BUILD`;
}

function start(){
    if(running) return;
    running=true;
    if(timer) clearInterval(timer);
    const sec=parseInt(intervalInput.value)||8;
    timer=setInterval(autoBet, sec*1000);
    setTimeout(autoBet, 1000);
    status.innerHTML='🟢 ĐANG CHẠY...';
    log('🚀 START AUTO BET | '+sec+'s | '+algo.value,'info');
    $('btnStart').disabled=true;
}

function stop(){
    running=false;
    if(timer){clearInterval(timer); timer=null;}
    status.innerHTML='⏹ Đã dừng';
    log('⏹ Dừng auto bet','warn');
    $('btnStart').disabled=false;
}

$('btnStart').onclick=start;
$('btnStop').onclick=stop;
log('🟢 TBTOOL AUTO BET sẵn sàng','info');
</script>
</body>
</html>
'''

@app.route('/')
def index():
    return HTML

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
