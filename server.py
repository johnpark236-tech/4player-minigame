from __future__ import annotations
import asyncio, json, math, random, secrets, time
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

app=FastAPI(title="4player-minigame")
ROOT=Path(__file__).parent
rooms={}
lock=asyncio.Lock()
COLLISION=0.095
BASE_SPEED=0.34

def code4():
    for _ in range(100):
        c=f"{random.randint(0,9999):04d}"
        if c not in rooms:return c
    raise RuntimeError("room code exhausted")

def public(room):
    now=time.monotonic()
    fuse=max(0, room.get("explode_at",0)-now) if room["status"]=="playing" else 0
    return {"type":"state","code":room["code"],"status":room["status"],"host":room["host"],
      "bomb":room.get("bomb"),"fuse":round(fuse,1),"winner":room.get("winner"),
      "players":[{"id":p["id"],"name":p["name"],"x":p["x"],"y":p["y"],"alive":p["alive"]} for p in room["players"].values()]}

async def broadcast(room):
    msg=json.dumps(public(room),ensure_ascii=False)
    dead=[]
    for pid,ws in room["sockets"].items():
        try: await ws.send_text(msg)
        except: dead.append(pid)
    for pid in dead: room["sockets"].pop(pid,None)

async def start_round(room):
    ids=list(room["players"])
    spots=[(.18,.22),(.82,.22),(.18,.78),(.82,.78)]
    random.shuffle(spots)
    for i,pid in enumerate(ids):
        p=room["players"][pid]; p.update(x=spots[i][0],y=spots[i][1],alive=True)
    room.update(status="playing",winner=None,bomb=random.choice(ids),explode_at=time.monotonic()+random.uniform(8,14),last_pass=0)
    await broadcast(room)

async def explode(room):
    if room["status"]!="playing": return
    victim=room.get("bomb")
    if victim in room["players"]: room["players"][victim]["alive"]=False
    alive=[pid for pid,p in room["players"].items() if p["alive"]]
    if len(alive)<=1:
        room.update(status="finished",bomb=None,winner=alive[0] if alive else None,explode_at=0)
    else:
        room["bomb"]=random.choice(alive); room["explode_at"]=time.monotonic()+random.uniform(7,12); room["last_pass"]=0
    await broadcast(room)

async def ticker():
    while True:
        await asyncio.sleep(.1)
        for room in list(rooms.values()):
            if room["status"]=="playing" and time.monotonic()>=room.get("explode_at",999999):
                await explode(room)

@app.on_event("startup")
async def startup(): asyncio.create_task(ticker())

@app.get("/")
async def index(): return FileResponse(ROOT/"static"/"index.html")

@app.get("/health")
async def health(): return {"ok":True,"rooms":len(rooms)}

@app.websocket("/ws")
async def ws_endpoint(ws:WebSocket):
    await ws.accept(); pid=None; room=None
    try:
        while True:
            data=json.loads(await ws.receive_text()); action=data.get("action")
            if action=="create":
                async with lock:
                    c=code4(); pid=secrets.token_hex(4); name=str(data.get("name","방장"))[:12] or "방장"
                    room={"code":c,"host":pid,"status":"lobby","winner":None,"bomb":None,"players":{},"sockets":{}}
                    room["players"][pid]={"id":pid,"name":name,"x":.5,"y":.5,"alive":True}; room["sockets"][pid]=ws; rooms[c]=room
                await ws.send_text(json.dumps({"type":"joined","id":pid,"code":c})); await broadcast(room)
            elif action=="join":
                c=str(data.get("code","")).zfill(4); room=rooms.get(c)
                if not room or room["status"]!="lobby" or len(room["players"])>=4:
                    await ws.send_text(json.dumps({"type":"error","message":"입장할 수 없는 방입니다."},ensure_ascii=False)); continue
                pid=secrets.token_hex(4); name=str(data.get("name","플레이어"))[:12] or "플레이어"
                room["players"][pid]={"id":pid,"name":name,"x":.5,"y":.5,"alive":True}; room["sockets"][pid]=ws
                await ws.send_text(json.dumps({"type":"joined","id":pid,"code":c})); await broadcast(room)
            elif action=="start" and room and pid==room["host"] and len(room["players"])>=2:
                await start_round(room)
            elif action=="move" and room and room["status"]=="playing" and pid in room["players"]:
                p=room["players"][pid]
                if not p["alive"]: continue
                tx=max(.05,min(.95,float(data.get("x",p["x"])))); ty=max(.08,min(.92,float(data.get("y",p["y"]))))
                dx,dy=tx-p["x"],ty-p["y"]; dist=math.hypot(dx,dy)
                step=BASE_SPEED*(1.2 if room["bomb"]==pid else 1)
                if dist>step: tx=p["x"]+dx/dist*step; ty=p["y"]+dy/dist*step
                p["x"],p["y"]=tx,ty
                now=time.monotonic()
                if room["bomb"]==pid and now-room.get("last_pass",0)>.7:
                    for oid,o in room["players"].items():
                        if oid!=pid and o["alive"] and math.hypot(o["x"]-p["x"],o["y"]-p["y"])<COLLISION:
                            room["bomb"]=oid; room["last_pass"]=now; break
                await broadcast(room)
            elif action=="rematch" and room and pid==room["host"] and len(room["players"])>=2:
                await start_round(room)
    except (WebSocketDisconnect,ValueError,KeyError,json.JSONDecodeError):
        pass
    finally:
        if room and pid:
            room["sockets"].pop(pid,None); room["players"].pop(pid,None)
            if not room["players"]: rooms.pop(room["code"],None)
            else:
                if room["host"]==pid: room["host"]=next(iter(room["players"]))
                if room.get("bomb")==pid and room["status"]=="playing":
                    alive=[x for x,p in room["players"].items() if p["alive"]]
                    if alive: room["bomb"]=random.choice(alive)
                await broadcast(room)
