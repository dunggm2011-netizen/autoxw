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
vip_active = True

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
# 40 THUẬT TOÁN
# ============================================================
ROOM_ORDER = list(range(1, 7))

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

# VIP
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

ALGO_MAP = {
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

def choose_room(rooms, killed, algo_name):
    func = ALGO_MAP.get(algo_name, algo_random)
    return func(rooms, killed)

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
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TBTOOL - AUTO BET</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a12;background-image:radial-gradient(ellipse at 20% 50%,rgba(255,215,0,0.04) 0%,transparent 60%);min-height:100vh;color:#e8e8f0;font-family:'Inter',sans-serif;padding:20px}
.container{max-width:1200px;margin:0 auto}
.header{background:linear-gradient(135deg,#12121f,#1a1a2e);border:1px solid rgba(255,215,0,0.2);border-radius:16px;padding:20px 30px;margin-bottom:24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:15px}
.logo{font-family:'Orbitron',monospace;font-weight:900;font-size:28px;color:#FFD700;letter-spacing:2px}
.logo span{color:#00D4FF}
.status-badge{padding:6px 16px;border-radius:20px;font-size:12px;font-weight:600;background:rgba(0,200,83,0.15);color:#00c853;border:1px solid rgba(0,200,83,0.2)}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:24px}
.stat-card{background:rgba(18,18,30,0.8);border:1px solid rgba(255,255,255,0.05);border-radius:12px;padding:12px 16px}
.stat-label{font-size:10px;text-transform:uppercase;color:#666;letter-spacing:1px}
.stat-value{font-size:20px;font-weight:700;margin-top:3px;font-family:'Orbitron',monospace}
.stat-value.gold{color:#FFD700}
.stat-value.green{color:#00c853}
.stat-value.red{color:#ff1744}
.stat-value.blue{color:#00D4FF}
.main-grid{display:grid;grid-template-columns:340px 1fr;gap:24px}
@media(max-width:900px){.main-grid{grid-template-columns:1fr}}
.panel{background:linear-gradient(145deg,#12121f,#1a1a2a);border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:20px 24px}
.panel-title{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#888;margin-bottom:16px;display:flex;align-items:center;gap:10px}
.panel-title i{color:#FFD700}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:11px;font-weight:600;color:#888;margin-bottom:3px;letter-spacing:0.5px}
.form-group input,.form-group select{width:100%;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:8px 12px;color:#e8e8f0;font-size:13px;font-family:'Inter',sans-serif}
.form-group input:focus,.form-group select:focus{outline:none;border-color:rgba(255,215,0,0.4)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btn{padding:8px 20px;border:none;border-radius:8px;font-weight:700;font-size:13px;cursor:pointer;transition:0.25s;font-family:'Inter',sans-serif}
.btn-primary{background:linear-gradient(135deg,#FFD700,#ffb300);color:#111}
.btn-primary:hover{transform:translateY(-2px)}
.btn-success{background:linear-gradient(135deg,#00c853,#00e676);color:#fff}
.btn-success:hover{transform:translateY(-2px)}
.btn-danger{background:linear-gradient(135deg,#d50000,#ff1744);color:#fff}
.btn-danger:hover{transform:translateY(-2px)}
.btn-secondary{background:rgba(255,255,255,0.06);color:#aaa;border:1px solid rgba(255,255,255,0.08)}
.btn-secondary:hover{background:rgba(255,255,255,0.1);color:#fff}
.btn-group{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.rooms-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:14px 0}
@media(max-width:600px){.rooms-grid{grid-template-columns:repeat(3,1fr)}}
.room-card{background:rgba(255,255,255,0.03);border:2px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px;text-align:center;transition:0.3s}
.room-card .r-icon{font-size:18px;display:block}
.room-card .r-name{font-size:10px;color:#888;font-weight:600}
.room-card .r-players{font-size:18px;font-weight:700;font-family:'Orbitron',monospace;color:#00D4FF}
.room-card .r-bet{font-size:10px;color:#FFD700}
.room-card.predicted{border-color:#00c853;background:rgba(0,200,83,0.08);box-shadow:0 0 30px rgba(0,200,83,0.08)}
.room-card.killed{border-color:#ff1744;background:rgba(255,23,68,0.08)}
.prediction-box{background:rgba(255,215,0,0.04);border:1px solid rgba(255,215,0,0.1);border-radius:12px;padding:14px 20px;text-align:center;font-size:16px;font-weight:600;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.prediction-box .label{color:#888;font-weight:400}
.prediction-box .value{color:#FFD700;font-family:'Orbitron',monospace}
.logs-box{background:rgba(0,0,0,0.3);border-radius:10px;padding:10px 14px;max-height:200px;overflow-y:auto;font-size:12px;line-height:1.8;margin-top:10px;border:1px solid rgba(255,255,255,0.04)}
.log-time{color:#555;margin-right:8px}
.log-info{color:#00D4FF}
.log-win{color:#00c853}
.log-lose{color:#ff1744}
.log-warn{color:#ff9100}
.footer{text-align:center;padding:16px 0 6px;font-size:11px;color:#444;border-top:1px solid rgba(255,255,255,0.04);margin-top:20px}
.footer a{color:#FFD700;text-decoration:none}
.vip-tag{background:linear-gradient(135deg,#FFD700,#ffb300);color:#111;padding:2px 10px;border-radius:12px;font-size:10px;font-weight:700;text-transform:uppercase}
</style>
</head>
<body>
<div class="container">
<header class="header">
    <div class="logo">TB<span>TOOL</span></div>
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <span class="vip-tag"><i class="fas fa-crown"></i> VIP</span>
        <span class="status-badge" id="statusBadge"><i class="fas fa-circle" style="color:#00c853;"></i> Sẵn sàng</span>
        <span style="color:#555;font-size:13px;"><i class="fas fa-user"></i> <span id="userDisplay">---</span></span>
    </div>
</header>

<div class="stats-grid">
    <div class="stat-card"><div class="stat-label">VÁN</div><div class="stat-value gold" id="roundDisplay">---</div></div>
    <div class="stat-card"><div class="stat-label">DỰ ĐOÁN</div><div class="stat-value blue" id="predDisplay">---</div></div>
    <div class="stat-card"><div class="stat-label">KILLED</div><div class="stat-value red" id="killedDisplay">---</div></div>
    <div class="stat-card"><div class="stat-label">THUẬT TOÁN</div><div class="stat-value" style="font-size:14px;color:#00D4FF;" id="algoDisplay">RANDOM</div></div>
</div>

<div class="main-grid">
<div class="panel">
    <div class="panel-title"><i class="fas fa-sliders-h"></i> CẤU HÌNH</div>
    <div class="form-group"><label>USER ID</label><input id="userId" placeholder="Nhập userId"></div>
    <div class="form-group"><label>SECRET KEY</label><input id="secretKey" placeholder="Nhập secretKey" type="password"></div>
    <div class="form-row">
        <div class="form-group"><label>TOOL</label>
            <select id="tool">
                <option value="vtd">🏃 VTD</option>
                <option value="vth">🏠 VTH</option>
                <option value="lotto">🎲 LOTTO</option>
            </select>
        </div>
        <div class="form-group"><label>THUẬT TOÁN</label>
            <select id="algo">
                <optgroup label="FREE">
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
                </optgroup>
                <optgroup label="👑 VIP">
                    <option value="VIP_RANDOM">VIP_RANDOM</option>
                    <option value="MARKOV">MARKOV</option>
                    <option value="BAYES">BAYES</option>
                    <option value="NEURAL">NEURAL</option>
                    <option value="FUZZY">FUZZY</option>
                    <option value="GENETIC">GENETIC</option>
                    <option value="ANT_COLONY">ANT_COLONY</option>
                    <option value="PARTICLE_SWARM">PARTICLE_SWARM</option>
                    <option value="KNN">KNN</option>
                    <option value="DECISION_TREE">DECISION_TREE</option>
                    <option value="RANDOM_FOREST">RANDOM_FOREST</option>
                    <option value="GRADIENT_BOOST">GRADIENT_BOOST</option>
                    <option value="LSTM">LSTM</option>
                    <option value="TRANSFORMER">TRANSFORMER</option>
                    <option value="ENSEMBLE">ENSEMBLE</option>
                </optgroup>
            </select>
        </div>
    </div>
    <div class="form-row">
        <div class="form-group"><label>CƯỢC GỐC</label><input id="baseBet" type="number" value="1" step="0.1"></div>
        <div class="form-group"><label>TẦN SUẤT (s)</label><input id="interval" type="number" value="8" min="3"></div>
    </div>
    <div class="btn-group">
        <button class="btn btn-success" id="btnStart"><i class="fas fa-play"></i> BẮT ĐẦU</button>
        <button class="btn btn-danger" id="btnStop"><i class="fas fa-stop"></i> DỪNG</button>
        <button class="btn btn-secondary" id="btnPredict"><i class="fas fa-robot"></i> DỰ ĐOÁN</button>
    </div>
</div>

<div class="panel">
    <div class="panel-title"><i class="fas fa-chess-queen"></i> ARENA</div>
    <div class="rooms-grid" id="roomsGrid"></div>
    <div class="prediction-box">
        <span class="label"><i class="fas fa-robot"></i> DỰ ĐOÁN</span>
        <span class="value" id="predictionText">⏳ Chờ...</span>
        <span style="font-size:13px;color:#666;" id="betAmountDisplay">0.00 BUILD</span>
    </div>
    <div class="logs-box" id="logsBox">
        <div><span class="log-time">--:--:--</span> <span class="log-info">🟢 TBTOOL AUTO BET sẵn sàng</span></div>
    </div>
</div>
</div>
<div class="footer">made by <strong style="color:#FFD700;">seraph</strong> · 40 thuật toán · <i class="fas fa-phone"></i> 0365463767</div>
</div>

<script>
// ============================================================
// FRONTEND - AUTO BET
// ============================================================

const S = {
    running: false,
    userId: '',
    secretKey: '',
    tool: 'vtd',
    algo: 'RANDOM',
    baseBet: 1.0,
    interval: 8,
    currentIssue: null,
    predictedRoom: null,
    killedRoom: null,
    rooms: {},
    lastIssue: {},
    timer: null
};

const $ = id => document.getElementById(id);
const userId = $('userId'), secretKey = $('secretKey'), tool = $('tool'), algo = $('algo');
const baseBet = $('baseBet'), intervalInput = $('interval');
const roomsGrid = $('roomsGrid'), predictionText = $('predictionText'), betAmountDisplay = $('betAmountDisplay');
const roundDisplay = $('roundDisplay'), predDisplay = $('predDisplay'), killedDisplay = $('killedDisplay'), algoDisplay = $('algoDisplay');
const logsBox = $('logsBox'), statusBadge = $('statusBadge'), userDisplay = $('userDisplay');
const btnStart = $('btnStart'), btnStop = $('btnStop'), btnPredict = $('btnPredict');

function log(msg, type='info') {
    const t = new Date().toLocaleTimeString();
    const cls = type === 'win' ? 'log-win' : type === 'lose' ? 'log-lose' : type === 'warn' ? 'log-warn' : 'log-info';
    logsBox.innerHTML += `<div><span class="log-time">${t}</span> <span class="${cls}">${msg}</span></div>`;
    logsBox.scrollTop = logsBox.scrollHeight;
    if (logsBox.children.length > 100) logsBox.removeChild(logsBox.firstChild);
}

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

function renderRooms(rooms, killed, predicted) {
    const isVTD = S.tool === 'vtd';
    const names = isVTD 
        ? ['⚔️ Tấn công','🛡️ Quyền sắt','🏊 Thợ lặn','🌪️ Cơn lốc','🏇 Hiệp sĩ','🏆 Vua HR']
        : ['📦 Kho','🪑 Họp','👔 Giám đốc','💬 Chat','🎥 Giám sát','🏢 Văn phòng'];
    let html = '';
    const count = S.tool === 'vth' ? 8 : 6;
    for (let i = 1; i <= count; i++) {
        const r = rooms?.[i] || { players: 0, bet: 0 };
        let cls = 'room-card';
        if (predicted === i) cls += ' predicted';
        if (killed === i) cls += ' killed';
        const name = isVTD ? `VĐV ${i}` : (names[i-1] || `Phòng ${i}`);
        html += `<div class="${cls}">
            <span class="r-icon">${isVTD ? names[i-1]?.split(' ')[0] || '🏃' : '📦'}</span>
            <div class="r-name">${name}</div>
            <div class="r-players">${r.players || 0}</div>
            <div class="r-bet">💰 ${(r.bet || 0).toFixed(0)}</div>
        </div>`;
    }
    roomsGrid.innerHTML = html;
}

function updateUI() {
    roundDisplay.textContent = S.currentIssue || '---';
    predDisplay.textContent = S.predictedRoom ? (S.tool === 'vtd' ? `VĐV ${S.predictedRoom}` : `Phòng ${S.predictedRoom}`) : '---';
    killedDisplay.textContent = S.killedRoom ? (S.tool === 'vtd' ? `VĐV ${S.killedRoom}` : `Phòng ${S.killedRoom}`) : '---';
    algoDisplay.textContent = S.algo;
    userDisplay.textContent = S.userId || '---';
    betAmountDisplay.textContent = S.baseBet.toFixed(2) + ' BUILD';
    
    const name = S.predictedRoom ? (S.tool === 'vtd' ? `VĐV ${S.predictedRoom}` : `Phòng ${S.predictedRoom}`) : '---';
    predictionText.textContent = S.predictedRoom ? `🎯 ${name}` : '⏳ Chờ...';
    
    if (S.running) {
        statusBadge.innerHTML = '<i class="fas fa-circle" style="color:#FFD700;"></i> ĐANG CHẠY';
        btnStart.disabled = true;
        btnStart.innerHTML = '<i class="fas fa-spinner fa-spin"></i> RUNNING';
    } else {
        statusBadge.innerHTML = '<i class="fas fa-circle" style="color:#00c853;"></i> Sẵn sàng';
        btnStart.disabled = false;
        btnStart.innerHTML = '<i class="fas fa-play"></i> BẮT ĐẦU';
    }
}

async function predict() {
    const uid = userId.value.trim();
    const sk = secretKey.value.trim();
    if (!uid || !sk) {
        log('⚠️ Nhập User ID và Secret Key', 'warn');
        return;
    }
    
    S.userId = uid;
    S.secretKey = sk;
    S.tool = tool.value;
    S.algo = algo.value;
    S.baseBet = parseFloat(baseBet.value) || 1.0;
    S.interval = parseInt(intervalInput.value) || 8;
    
    const poll = await callAPI('/api/poll', {
        userId: S.userId,
        secretKey: S.secretKey,
        tool: S.tool
    });
    
    if (poll.error) {
        log('⚠️ Poll lỗi: ' + poll.error, 'warn');
        return;
    }
    
    const issue = poll?.issue_id;
    if (!issue) {
        log('⏳ Chưa có phiên mới', 'warn');
        return;
    }
    
    const rooms = poll?.rooms || {};
    const killed = poll?.killed;
    
    S.currentIssue = issue;
    S.killedRoom = killed;
    S.rooms = rooms;
    
    // Gọi backend chọn phòng theo thuật toán
    const chosen = await callAPI('/api/choose', {
        rooms: rooms,
        killed: killed,
        algo: S.algo
    });
    
    S.predictedRoom = chosen?.room || Math.floor(Math.random() * 6) + 1;
    
    renderRooms(rooms, killed, S.predictedRoom);
    updateUI();
    log(`🔮 Dự đoán: ${S.tool === 'vtd' ? 'VĐV' : 'Phòng'} ${S.predictedRoom} | Ván #${issue} | ${S.algo}`, 'info');
}

async function autoBet() {
    if (!S.running) return;
    
    const uid = userId.value.trim();
    const sk = secretKey.value.trim();
    if (!uid || !sk) {
        log('⚠️ Nhập User ID và Secret Key', 'warn');
        return;
    }
    
    S.userId = uid;
    S.secretKey = sk;
    S.tool = tool.value;
    S.algo = algo.value;
    S.baseBet = parseFloat(baseBet.value) || 1.0;
    
    const poll = await callAPI('/api/poll', {
        userId: S.userId,
        secretKey: S.secretKey,
        tool: S.tool
    });
    
    if (poll.error) {
        log('⚠️ Poll lỗi: ' + poll.error, 'warn');
        return;
    }
    
    const issue = poll?.issue_id;
    if (!issue) {
        log('⏳ Chưa có phiên mới', 'warn');
        return;
    }
    
    const key = S.tool + '_' + S.userId;
    if (S.lastIssue[key] === issue) {
        log(`⏳ Đã cược phiên #${issue}`, 'warn');
        return;
    }
    
    const rooms = poll?.rooms || {};
    const killed = poll?.killed;
    
    S.currentIssue = issue;
    S.killedRoom = killed;
    S.rooms = rooms;
    
    // Chọn phòng
    const chosen = await callAPI('/api/choose', {
        rooms: rooms,
        killed: killed,
        algo: S.algo
    });
    
    const room = chosen?.room || Math.floor(Math.random() * 6) + 1;
    S.predictedRoom = room;
    
    renderRooms(rooms, killed, room);
    updateUI();
    
    // Đặt cược
    const amt = S.baseBet;
    const bet = await callAPI('/api/bet', {
        userId: S.userId,
        secretKey: S.secretKey,
        tool: S.tool,
        room: room,
        amount: amt,
        issueId: issue
    });
    
    S.lastIssue[key] = issue;
    
    const success = bet?.code === 0 || bet?.status === 'ok' || bet?.msg === 'ok';
    if (success) {
        log(`💰 Cược ${amt} vào ${S.tool === 'vtd' ? 'VĐV' : 'Phòng'} ${room} | Ván #${issue} | ${S.algo} ✅`, 'win');
    } else {
        log(`❌ Cược thất bại: ${JSON.stringify(bet).slice(0,100)}`, 'lose');
    }
}

function start() {
    if (S.running) return;
    const uid = userId.value.trim();
    const sk = secretKey.value.trim();
    if (!uid || !sk) {
        log('⚠️ Nhập User ID và Secret Key', 'warn');
        return;
    }
    
    S.running = true;
    S.userId = uid;
    S.secretKey = sk;
    S.tool = tool.value;
    S.algo = algo.value;
    S.baseBet = parseFloat(baseBet.value) || 1.0;
    S.interval = parseInt(intervalInput.value) || 8;
    
    if (S.timer) clearInterval(S.timer);
    S.timer = setInterval(autoBet, S.interval * 1000);
    setTimeout(autoBet, 1000);
    
    log(`🚀 START | ${S.tool.toUpperCase()} | ${S.algo} | ${S.interval}s | Cược ${S.baseBet}`, 'info');
    updateUI();
}

function stop() {
    S.running = false;
    if (S.timer) { clearInterval(S.timer); S.timer = null; }
    log('⏹ STOPPED', 'warn');
    updateUI();
}

// ===== EVENTS =====
btnStart.onclick = start;
btnStop.onclick = stop;
btnPredict.onclick = predict;

// Lưu account
document.getElementById('userId').addEventListener('change', function() {
    try { localStorage.setItem('tbtool_user', this.value); } catch(e) {}
});
document.getElementById('secretKey').addEventListener('change', function() {
    try { localStorage.setItem('tbtool_secret', this.value); } catch(e) {}
});

// Load account
try {
    const u = localStorage.getItem('tbtool_user');
    const s = localStorage.getItem('tbtool_secret');
    if (u) document.getElementById('userId').value = u;
    if (s) document.getElementById('secretKey').value = s;
} catch(e) {}

// Init
updateUI();
log('🟢 TBTOOL AUTO BET sẵn sàng', 'info');
</script>
</body>
</html>
'''

# ====== API CHO THUẬT TOÁN ======
@app.route('/api/choose', methods=['POST'])
def choose():
    data = request.json
    rooms = data.get('rooms', {})
    killed = data.get('killed')
    algo_name = data.get('algo', 'RANDOM')
    room = choose_room(rooms, killed, algo_name)
    return jsonify({'room': room})

@app.route('/')
def index():
    return HTML

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
