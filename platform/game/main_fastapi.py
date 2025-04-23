from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, List, Any
import asyncio
import os
import json

from battle_manager import BattleManager
from player_loader import load_baseline_code

app = FastAPI()
battle_manager = BattleManager()

# 用于记录每个 battle_id 的 websocket clients
clients: Dict[str, List[WebSocket]] = {}

@app.post("/start_game/")
async def start_game(background_tasks: BackgroundTasks, mode: str = "mixed_test", player_codes: Dict[int, str] = None):
    # 设置环境变量
    os.environ["AVALON_DATA_DIR"] = "./data"
    os.makedirs("./data", exist_ok=True)

    # 创建玩家代码
    player_codes = create_player_codes(mode, player_codes or {})
    battle_id = battle_manager.create_battle(player_codes)
    print(f"[系统] 游戏已启动 ID: {battle_id}")

    # 在后台运行游戏主循环
    background_tasks.add_task(run_game_loop, battle_id)
    return JSONResponse(content={"battle_id": battle_id})


@app.websocket("/ws/{battle_id}")
async def websocket_endpoint(websocket: WebSocket, battle_id: str):
    await websocket.accept()
    if battle_id not in clients:
        clients[battle_id] = []
    clients[battle_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        clients[battle_id].remove(websocket)


def create_player_codes(mode: str, player_codes = {}) -> Dict[int, str]:
    if mode == "basic_test":
        basic_code = load_baseline_code("basic_player")
        for i in range(1, 8):
            if i not in player_codes:
                player_codes[i] = basic_code
    elif mode == "smart_test":
        smart_code = load_baseline_code("smart_player")
        for i in range(1, 8):
            if i not in player_codes:
                player_codes[i] = smart_code
    elif mode == "mixed_test":
        import random
        basic_code = load_baseline_code("basic_player")
        smart_code = load_baseline_code("smart_player")
        for i in range(1, 8):
            if i not in player_codes:
                player_codes[i] = smart_code if random.random() <= 0.5 else basic_code
    return player_codes


async def run_game_loop(battle_id: str):
    print(f"[系统] 等待 battle {battle_id} 完成")
    while True:
        status = battle_manager.get_battle_status(battle_id)
        if status in ["completed", "error"]:
            break
        # 推送 snapshots
        snapshots = battle_manager.get_snapshots_queue(battle_id)
        for snapshot in snapshots:
            await broadcast_snapshot(battle_id, snapshot)
        await asyncio.sleep(0.5)
    
    result = battle_manager.get_battle_result(battle_id)
    await broadcast_snapshot(battle_id, {"type": "game_result", "result": result})
    print(f"[系统] 游戏完成 ID: {battle_id}")


async def broadcast_snapshot(battle_id: str, snapshot: Dict[str, Any]):
    conns = clients.get(battle_id, [])
    disconnected = []
    for ws in conns:
        try:
            await ws.send_json(snapshot)
        except Exception:
            disconnected.append(ws)
    for d in disconnected:
        conns.remove(d)