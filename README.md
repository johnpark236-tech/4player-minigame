# 4player-minigame

Mobile-first real-time 2–4 player mini-game platform.

## MVP 01 — 폭탄 돌리기
- 4-digit room code
- 2–4 players
- Host starts the round
- Touch/click to move
- Bomb holder moves 1.2x faster
- Collision passes the bomb
- Random fuse, elimination, last survivor wins
- Rematch supported

## Local
```bash
pip install -r requirements.txt
uvicorn server:app --reload
```

Open http://localhost:8000

## Render
Blueprint: `render.yaml`
Health check: `/health`
