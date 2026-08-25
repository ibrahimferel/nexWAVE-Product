"""
NexWave — Modal Deployment Script
=================================
Volume: nexwave-models-v2 (flat, 3 file — ppo_batching_v11.zip, attn_routing_v11.pt,
prod_emb.pkl, semua di root repo). Nama lama "nexwave-models" sudah tidak dipakai —
volume itu ada di state korup: `modal volume put` menulis file dengan sukses (ls/get
CLI melihatnya), tapi Function yang mount volume tsb tidak pernah melihat file itu.
Root cause-nya kemungkinan sisa upload folder `./models/` lama (format sb3
pre-zip: policy.pth dkk) yang ke-nest jadi /models/models/ karena /models sudah ada.
nexwave-models-v2 dibuat bersih untuk menghindari state itu.

PENTING — `modal volume put` (CLI) di environment ini TIDAK reliable: filenya ke-upload
dan kelihatan lewat `modal volume ls`/`get`, tapi container yang mount volume itu tetap
melihatnya MISSING. Kalau upload model baru lagi (v12 dst.), jangan pakai `modal volume
put` mentah — pakai script one-off yang copy file dari image ke volume DARI DALAM
container lalu vol.commit(), contoh:

  # seed_models.py
  import modal
  app = modal.App("nexwave-models-seed")
  vol = modal.Volume.from_name("nexwave-models-v2", create_if_missing=False)
  image = (
      modal.Image.debian_slim()
      .add_local_file("./ppo_batching_v12.zip", "/seed/ppo_batching_v12.zip")
      # ... file lain
  )
  @app.function(image=image, volumes={"/models": vol})
  def seed():
      import shutil
      vol.reload()
      shutil.copyfile("/seed/ppo_batching_v12.zip", "/models/ppo_batching_v12.zip")
      vol.commit()
  # modal run seed_models.py::seed

Kalau `modal volume put` biasa sudah reliable lagi (cek dengan verify_models setelah
upload), boleh balik pakai cara simpel ini:
  modal volume create nexwave-models-v2
  modal volume put nexwave-models-v2 ./ppo_batching_v11.zip /models/ppo_batching_v11.zip
  modal volume put nexwave-models-v2 ./attn_routing_v11.pt  /models/attn_routing_v11.pt
  modal volume put nexwave-models-v2 ./prod_emb.pkl         /models/prod_emb.pkl

Set secrets (DB-nya Supabase Postgres — lihat script_modal.sh buat contoh nyata):
  modal secret create nexwave-secrets \
    DATABASE_URL="postgresql://postgres.xxx:pass@aws-0-xxx.pooler.supabase.com:6543/postgres" \
    SUPABASE_URL="https://xxx.supabase.co" \
    N_PICKERS="7" \
    CAPACITY="27" \
    VISIBLE_WINDOW="40" \
    WMS_WEBHOOK_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
    CORS_ORIGINS="https://nexwave.vercel.app,http://localhost:3000"

  # SUPABASE_URL WAJIB buat verify_token() di bawah -- dipakai bentuk endpoint
  # JWKS Supabase (.../auth/v1/.well-known/jwks.json) buat verifikasi token login
  # Google OAuth. TIDAK ada secret yang perlu di-copy manual (project ini pakai
  # JWT Signing Keys asimetris, bukan legacy shared HS256 secret) -- endpoint
  # JWKS-nya publik by design. Detail alur login: lihat api.md dan
  # google_oauth_setup.md. SECRET_KEY lama sudah tidak dipakai di kode manapun
  # di file ini -- boleh dihapus dari secret kalau mau beres-beres.

Deploy:
  modal deploy modal_app.py

Verifikasi model:
  modal run modal_app.py::verify_models

Lihat log:
  modal logs nexwave-api
"""

import os
import pickle
import hashlib
import hmac
import json
from contextlib import asynccontextmanager

import modal

# ── Image ─────────────────────────────────────────────────────────────────────
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi==0.115.0",
        "uvicorn[standard]==0.30.6",
        "torch==2.8.0",
        "stable-baselines3==2.9.0",
        "sb3-contrib==2.9.0",
        "gymnasium==1.3.0",
        "numpy==2.4.2",
        "pandas==2.2.2",
        "networkx==3.3",
        "scikit-learn==1.5.1",
        "asyncpg==0.30.0",
        "sqlalchemy[asyncio]==2.0.36",
        "python-jose[cryptography]==3.3.0",
        "python-multipart==0.0.9",
        "httpx==0.27.0",
    )
    # Dataset CSV dimount dari repo — sesuaikan path kalau berbeda
    .add_local_dir("./dataset", remote_path="/dataset")
    # Source code API
    .add_local_dir("./api",     remote_path="/app/api")
)

# ── Volume: berisi semua model artifacts ──────────────────────────────────────
# Setelah upload, struktur di volume:
#   /models/
#   ├── _stable_baselines3_version   ← dari ./models/
#   ├── data                         ← dari ./models/
#   ├── policy.optimizer.pth         ← dari ./models/
#   ├── policy.pth                   ← dari ./models/
#   ├── pytorch_variables.pth        ← dari ./models/
#   ├── system_info.txt              ← dari ./models/
#   ├── attn_routing_v11.pt          ← upload terpisah
#   └── prod_emb.pkl                 ← upload terpisah
model_vol = modal.Volume.from_name("nexwave-models-v2", create_if_missing=False)

app = modal.App("nexwave-api")

# ── Global state: model di-load sekali saat container startup ─────────────────
_models = {}

# MODEL_DIR: folder flat di volume berisi 3 file:
#   ppo_batching_v11.zip   <- file ZIP ASLI dari training, JANGAN diextract.
#                              MaskablePPO.load() butuh file zip, bukan folder
#                              hasil extract (IsADirectoryError kalau dikasih folder).
#   attn_routing_v11.pt
#   prod_emb.pkl
MODEL_DIR    = "/models"
PPO_ZIP_PATH = f"{MODEL_DIR}/ppo_batching_v11.zip"
ATTN_PATH    = f"{MODEL_DIR}/attn_routing_v11.pt"
EMB_PATH     = f"{MODEL_DIR}/prod_emb.pkl"


def load_models_once():
    """
    Load ketiga artifact ke memory. Dipanggil di lifespan startup.
    MaskablePPO.load() butuh path ke file .zip, BUKAN folder hasil extract.
    """
    if _models:
        return _models

    import sys
    import torch
    from sb3_contrib import MaskablePPO
    sys.path.insert(0, "/app")

    # Segarkan pandangan volume — kalau file diupload dari luar (CLI) setelah
    # container ini mulai / warm-reuse, tanpa reload() perubahan tidak terlihat.
    model_vol.reload()

    # 1. Batching agent (MaskablePPO) — baca dari folder /models/
    print(f"[startup] Loading MaskablePPO dari {PPO_ZIP_PATH} ...")
    _models["ppo"] = MaskablePPO.load(PPO_ZIP_PATH)
    print(f"[startup] PPO OK — policy: {_models['ppo'].policy.__class__.__name__}")

    # 2. Routing agent (Attention Model)
    print(f"[startup] Loading Attention Model dari {ATTN_PATH} ...")
    from api.ml.routing import AttnRoutingPolicy
    attn = AttnRoutingPolicy()
    attn.load_state_dict(
        torch.load(ATTN_PATH, map_location="cpu")
    )
    attn.eval()
    _models["attn"] = attn
    print("[startup] Attention Model OK")

    # 3. GNN embedding dict
    print(f"[startup] Loading GNN embeddings dari {EMB_PATH} ...")
    with open(EMB_PATH, "rb") as f:
        _models["emb"] = pickle.load(f)
    print(f"[startup] GNN embeddings OK — {len(_models['emb'])} produk")

    # 4. Nav graph dari dataset CSV
    print("[startup] Building Nav graph dari /dataset/ ...")
    from api.ml.nav import Nav
    _models["nav"] = Nav("/dataset")
    print("[startup] Nav graph OK")

    return _models


# ── DB helper (Supabase PostgreSQL via asyncpg) ─────────────────────────────────
# Module-level (bukan cuma di dalam create_fastapi_app()) -- dipakai juga oleh
# process_due_orders_cron() (scheduled function) & dev_process_pending_orders(),
# bukan cuma endpoint FastAPI biasa.
async def get_conn():
    # statement_cache_size=0 WAJIB -- DATABASE_URL lewat Supabase pgbouncer
    # (transaction pooling mode, port 6543), yang swap physical connection
    # antar transaction. asyncpg default cache prepared statement per
    # connection -- kena pgbouncer, itu collide ("DuplicatePreparedStatement
    # Error") secara intermiten (flapping 500/200 di endpoint yang SAMA,
    # request yang SAMA). Ini fix resmi yang direkomendasikan asyncpg sendiri
    # buat kombinasi pgbouncer transaction/statement pooling mode.
    import asyncpg
    return await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)


async def run_due_orders_cycle() -> dict:
    """
    Inti dari "proses order yang udah waktunya" -- dipakai BARENG oleh
    process_due_orders_cron() (Modal Cron, otomatis tiap 10 menit) dan
    POST /api/dev/process-pending-orders (manual trigger buat testing, nggak
    perlu nunggu cron tick). Satu-satunya tempat yang beneran manggil model ML
    dalam alur generate-orders yang baru (Opsi B) -- INSERT order-nya sendiri
    sekarang murni di Supabase langsung (lihat frontend_auth.md), nggak lewat
    sini sama sekali.
    """
    models = load_models_once()
    conn = await get_conn()
    try:
        due = await conn.fetch("""
            SELECT order_id, product_ref, qty, location_id, arrival_ts
            FROM orders
            WHERE status = 'pending' AND wave_id IS NULL AND arrival_ts <= NOW()
            ORDER BY arrival_ts
        """)
        if not due:
            return {"status": "ok", "processed": 0, "batching_actions": {}, "waves_assigned": []}

        due_orders = [{
            "order_id":    r["order_id"],
            "product_ref": r["product_ref"],
            "qty":         r["qty"],
            "location_id": r["location_id"],
            "arrival_ts":  r["arrival_ts"].isoformat(),
        } for r in due]

        from api.services.batching_service import process_due_orders
        actions = await process_due_orders(
            due_orders, ppo=models["ppo"], emb=models["emb"], nav=models["nav"], conn=conn,
        )

        # Sama seperti generate-orders versi lama: wave yang baru forming
        # dicoba langsung di-assign ke picker available.
        from api.services.dispatcher import assign_wave_to_picker
        forming = await conn.fetch("""
            SELECT wave_id FROM waves WHERE status='forming' AND picker_id IS NULL
            ORDER BY created_at
        """)
        assigned = []
        for w in forming:
            picker_id = await assign_wave_to_picker(w["wave_id"], conn, models["attn"], models["nav"])
            if picker_id is None:
                break
            assigned.append({"wave_id": w["wave_id"], "picker_id": picker_id})

        print(f"[process_due_orders] {len(due_orders)} order diproses, "
              f"actions={actions}, waves_assigned={len(assigned)}")
        return {"status": "ok", "processed": len(due_orders),
                "batching_actions": actions, "waves_assigned": assigned}
    finally:
        await conn.close()


# ── FastAPI app ───────────────────────────────────────────────────────────────
def create_fastapi_app():
    from datetime import datetime
    from fastapi import FastAPI, HTTPException, Header, Depends, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")

    @asynccontextmanager
    async def lifespan(app_):
        load_models_once()
        yield

    api = FastAPI(title="WaveIQ API", version="v11", lifespan=lifespan)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth helper ────────────────────────────────────────────────────────────
    # Token datang dari Supabase Auth (frontend login via Google OAuth lewat
    # supabase.auth.signInWithOAuth), BUKAN diterbitkan backend ini. Project ini
    # pakai JWT Signing Keys asimetris (ECC P-256 / ES256) -- Dashboard -> Project
    # Settings -> JWT Keys -> tab "JWT Signing Keys" -- BUKAN legacy shared HS256
    # secret (tab "Legacy JWT Secret" di dashboard yang sama, sudah di-rotate jadi
    # "Previous Key", cuma valid buat token lama yang belum expired). Karena
    # asimetris, verifikasi cukup pakai kunci PUBLIK dari endpoint JWKS Supabase
    # -- nggak ada secret yang perlu di-copy manual ke Modal sama sekali, dan
    # otomatis ngikutin kalau key di-rotate lagi nanti (SUPABASE_URL yang dipakai
    # buat bentuk endpoint-nya sudah ada dari awal di nexwave-secrets).
    _jwks_cache = {"keys": [], "fetched_at": 0.0}

    def _get_jwks(force: bool = False) -> list:
        import time
        import httpx
        if force or not _jwks_cache["keys"] or time.time() - _jwks_cache["fetched_at"] > 600:
            resp = httpx.get(
                f"{os.environ['SUPABASE_URL']}/auth/v1/.well-known/jwks.json", timeout=5,
            )
            resp.raise_for_status()
            _jwks_cache["keys"] = resp.json()["keys"]
            _jwks_cache["fetched_at"] = time.time()
        return _jwks_cache["keys"]

    def verify_token(authorization: str = Header(...)) -> dict:
        from jose import jwt, jwk, JWTError
        try:
            token = authorization.replace("Bearer ", "")
            kid = jwt.get_unverified_header(token).get("kid")

            match = next((k for k in _get_jwks() if k.get("kid") == kid), None)
            if match is None:
                # kid belum ada di cache -- kemungkinan key baru saja di-rotate
                # (lihat "Create Standby Key" di dashboard), paksa refresh sekali.
                match = next((k for k in _get_jwks(force=True) if k.get("kid") == kid), None)
            if match is None:
                raise JWTError("unknown signing key")

            key = jwk.construct(match, match["alg"])
            return jwt.decode(token, key, algorithms=[match["alg"]], audience="authenticated")
        except JWTError:
            raise HTTPException(401, {"error": "unauthorized"})

    # Dua role: "manager" (lihat semua -- order, pembagian wave, rute & wave
    # tiap operator) dan "operator" (cuma rute wave dia sendiri). Endpoint yang
    # perlu tau/gate berdasarkan role pakai Depends(get_caller_profile)
    # menggantikan Depends(verify_token) biasa (masih manggil verify_token()
    # di baliknya, jadi tetap mewajibkan token valid).
    async def get_caller_profile(user: dict = Depends(verify_token)) -> dict:
        conn = await get_conn()
        try:
            profile = await conn.fetchrow("SELECT role FROM users WHERE id = $1", user["sub"])
            picker  = await conn.fetchrow("SELECT picker_id FROM pickers WHERE auth_user_id = $1", user["sub"])
            return {
                "sub":       user["sub"],
                "role":      profile["role"] if profile else "operator",
                "picker_id": picker["picker_id"] if picker else None,
            }
        finally:
            await conn.close()

    # ── HMAC helper ────────────────────────────────────────────────────────────
    def verify_hmac(body: bytes, signature: str) -> bool:
        secret = os.environ["WMS_WEBHOOK_SECRET"].encode()
        expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ── Pydantic models ────────────────────────────────────────────────────────
    class OrderIn(BaseModel):
        order_id:    str
        product_ref: str
        qty:         int
        location_id: str
        arrival_ts:  datetime  # bukan str -- Pydantic parse ISO8601 jadi datetime
        # beneran di sini, jadi (a) WMS kirim timestamp salah format -> 422 yang
        # jelas, bukan 500 asyncpg.DataError yang bingungin, dan (b) conn.execute()
        # di bawah bisa langsung terima objek datetime tanpa konversi manual --
        # asyncpg TIDAK auto-parse string ke timestamptz kayak driver lain.

    class PickConfirm(BaseModel):
        wave_id:     str
        location_id: str
        qty_actual:  int

    class WaveProblem(BaseModel):
        wave_id:     str
        location_id: str
        reason:      str

    class WaveDone(BaseModel):
        wave_id: str

    # ==========================================================================
    # ENDPOINTS
    # ==========================================================================

    @api.get("/health")
    def health():
        return {
            "status":  "ok",
            "models":  "loaded" if _models else "not_loaded",
            "version": "v11",
        }

    # ── 1. Order baru dari WMS ─────────────────────────────────────────────────
    @api.post("/api/order/new")
    async def order_new(
        request: Request,
        x_wms_signature: str = Header(...),
    ):
        body = await request.body()
        if not verify_hmac(body, x_wms_signature):
            raise HTTPException(401, {"error": "invalid_signature"})

        data    = OrderIn(**json.loads(body))
        models  = load_models_once()
        conn    = await get_conn()

        try:
            # Insert order ke DB
            await conn.execute("""
                INSERT INTO orders (order_id, product_ref, qty, location_id, arrival_ts, status)
                VALUES ($1, $2, $3, $4, $5, 'pending')
                ON CONFLICT (order_id) DO NOTHING
            """, data.order_id, data.product_ref, data.qty,
                data.location_id, data.arrival_ts)

            # Panggil batching agent
            from api.services.batching_service import decide
            action, wave_id = await decide(
                order=data.dict(),
                ppo=models["ppo"],
                emb=models["emb"],
                nav=models["nav"],
                conn=conn,
            )

            return {"action": action, "wave_id": wave_id, "order_id": data.order_id}
        finally:
            await conn.close()

    # ── 2. Semua wave aktif (dashboard manager) ────────────────────────────────
    @api.get("/api/wave/active")
    async def wave_active(caller: dict = Depends(get_caller_profile)):
        if caller["role"] != "manager":
            raise HTTPException(403, {"error": "forbidden", "message": "Cuma manager yang bisa lihat semua wave."})
        conn = await get_conn()
        try:
            waves = await conn.fetch("""
                SELECT w.wave_id, w.status, w.picker_id, w.total_items, w.total_distance,
                       p.name as picker_name
                FROM waves w
                LEFT JOIN pickers p ON w.picker_id = p.picker_id
                WHERE w.status IN ('forming','assigned','in_progress')
                ORDER BY w.created_at
            """)
            result = []
            for w in waves:
                locs = await conn.fetch("""
                    SELECT wl.location_id, wl.visit_order, wl.status,
                           wl.problem_reason,
                           o.product_ref, o.qty,
                           l.x, l.y, l.z
                    FROM wave_locations wl
                    LEFT JOIN orders o    ON wl.order_id    = o.order_id
                    LEFT JOIN locations l ON wl.location_id = l.location_id
                    WHERE wl.wave_id = $1
                    ORDER BY wl.visit_order
                """, w["wave_id"])

                result.append({
                    "wave_id":        w["wave_id"],
                    "status":         w["status"],
                    "picker_id":      w["picker_id"],
                    "picker_name":    w["picker_name"],
                    "total_items":    w["total_items"],
                    "total_distance": w["total_distance"],
                    "locations": [{
                        "location_id": l["location_id"],
                        "visit_order": l["visit_order"],
                        "status":      l["status"],
                        "product_ref": l["product_ref"],
                        "qty":         l["qty"],
                        "x":           l["x"],
                        "y":           l["y"],
                        "z":           l["z"],
                    } for l in locs],
                })
            return result
        finally:
            await conn.close()

    # ── 3. Rute picker berikutnya ──────────────────────────────────────────────
    @api.get("/api/picker/{picker_id}/next")
    async def picker_next(picker_id: int, caller: dict = Depends(get_caller_profile)):
        if caller["role"] != "manager" and caller["picker_id"] != picker_id:
            raise HTTPException(403, {"error": "forbidden", "message": "Cuma bisa lihat rute sendiri."})
        conn = await get_conn()
        try:
            wave = await conn.fetchrow("""
                SELECT wave_id, status, total_items, total_distance
                FROM waves
                WHERE picker_id = $1 AND status IN ('assigned','in_progress')
                LIMIT 1
            """, picker_id)

            if not wave:
                return {"wave_id": None, "status": "no_wave",
                        "message": "Tidak ada wave tersedia."}

            locs = await conn.fetch("""
                SELECT wl.visit_order, wl.location_id, wl.status,
                       o.product_ref, o.qty,
                       l.x, l.y, l.z
                FROM wave_locations wl
                LEFT JOIN orders o    ON wl.order_id    = o.order_id
                LEFT JOIN locations l ON wl.location_id = l.location_id
                WHERE wl.wave_id = $1
                ORDER BY wl.visit_order
            """, wave["wave_id"])

            route = []
            for i, l in enumerate(locs):
                floor     = l["z"] or 1
                prev_floor = route[-1]["floor"] if route else floor
                note      = f"Naik ke Lantai {floor} — " if floor != prev_floor else ""
                route.append({
                    "step":        l["visit_order"],
                    "location_id": l["location_id"],
                    "product_ref": l["product_ref"],
                    "qty":         l["qty"],
                    "floor":       floor,
                    "x":           l["x"],
                    "y":           l["y"],
                    "status":      l["status"],
                    "instruction": (
                        f"{note}Ambil {l['qty']} unit "
                        f"{l['product_ref']} di {l['location_id']}"
                    ),
                })

            return {
                "wave_id":        wave["wave_id"],
                "status":         wave["status"],
                "total_items":    wave["total_items"],
                "total_distance": wave["total_distance"],
                "route":          route,
            }
        finally:
            await conn.close()

    # ── 4. Konfirmasi satu lokasi selesai ──────────────────────────────────────
    @api.post("/api/pick/confirm")
    async def pick_confirm(body: PickConfirm, user: dict = Depends(verify_token)):
        from datetime import datetime, timezone
        conn = await get_conn()
        try:
            now = datetime.now(timezone.utc)

            await conn.execute("""
                UPDATE wave_locations
                SET status = 'picked', picked_ts = $1
                WHERE wave_id = $2 AND location_id = $3
            """, now, body.wave_id, body.location_id)

            # Progress
            rows = await conn.fetch("""
                SELECT wl.status, wl.visit_order, wl.location_id,
                       o.product_ref, o.qty
                FROM wave_locations wl
                LEFT JOIN orders o ON wl.order_id = o.order_id
                WHERE wl.wave_id = $1
                ORDER BY wl.visit_order
            """, body.wave_id)

            picked = sum(1 for r in rows if r["status"] == "picked")
            total  = len(rows)
            next_l = next((r for r in rows if r["status"] == "pending"), None)

            return {
                "status":      "ok",
                "location_id": body.location_id,
                "wave_progress": {
                    "picked": picked,
                    "total":  total,
                    "pct":    round(picked / total * 100, 1) if total else 0,
                },
                "next_location": {
                    "location_id": next_l["location_id"],
                    "product_ref": next_l["product_ref"],
                    "qty":         next_l["qty"],
                } if next_l else None,
            }
        finally:
            await conn.close()

    # ── 5. Laporkan masalah ────────────────────────────────────────────────────
    @api.post("/api/wave/problem")
    async def wave_problem(body: WaveProblem, user: dict = Depends(verify_token)):
        conn = await get_conn()
        try:
            await conn.execute("""
                UPDATE wave_locations
                SET status = 'problem', problem_reason = $1
                WHERE wave_id = $2 AND location_id = $3
            """, body.reason, body.wave_id, body.location_id)
            return {"status": "ok", "location_status": "problem"}
        finally:
            await conn.close()

    # ── 6. Wave selesai ────────────────────────────────────────────────────────
    @api.post("/api/wave/done")
    async def wave_done(body: WaveDone, user: dict = Depends(verify_token)):
        from datetime import datetime, timezone
        conn   = await get_conn()
        models = load_models_once()
        try:
            now = datetime.now(timezone.utc)
            wave = await conn.fetchrow(
                "SELECT picker_id, total_items, total_distance FROM waves WHERE wave_id=$1",
                body.wave_id
            )

            await conn.execute("""
                UPDATE waves SET status='done', finish_ts=$1 WHERE wave_id=$2
            """, now, body.wave_id)

            await conn.execute("""
                UPDATE pickers SET status='available', current_wave_id=NULL
                WHERE picker_id=$1
            """, wave["picker_id"])

            # Assign wave berikutnya
            from api.services.dispatcher import assign_next_wave
            next_wave = await assign_next_wave(
                picker_id=wave["picker_id"],
                conn=conn,
                ppo=models["ppo"],
                attn=models["attn"],
                emb=models["emb"],
                nav=models["nav"],
            )

            return {
                "status": "ok",
                "wave_summary": {
                    "wave_id":        body.wave_id,
                    "total_items":    wave["total_items"],
                    "total_distance": wave["total_distance"],
                },
                "next_wave": {"wave_id": next_wave} if next_wave else None,
            }
        finally:
            await conn.close()

    # ── 7. Ringkasan shift (dashboard manager) ─────────────────────────────────
    @api.get("/api/shift/summary")
    async def shift_summary(caller: dict = Depends(get_caller_profile)):
        if caller["role"] != "manager":
            raise HTTPException(403, {"error": "forbidden", "message": "Cuma manager yang bisa lihat ringkasan shift."})
        from datetime import date
        conn  = await get_conn()
        # date object asli, BUKAN .isoformat() -- sama kayak bug arrival_ts,
        # asyncpg butuh objek date/datetime beneran buat dibind ke kolom
        # DATE/TIMESTAMPTZ, bukan string, walau string-nya "keliatan" bener.
        today = date.today()
        try:
            waves  = await conn.fetch("""
                SELECT status, total_items, total_distance
                FROM waves WHERE DATE(created_at) = $1
            """, today)
            orders = await conn.fetch("""
                SELECT status FROM orders WHERE DATE(created_at) = $1
            """, today)

            total_items = sum(w["total_items"] or 0 for w in waves)
            total_dist  = sum(w["total_distance"] or 0 for w in waves)

            return {
                "shift_date":     today,
                "n_waves":        len(waves),
                "waves_done":     sum(1 for w in waves if w["status"] == "done"),
                "waves_active":   sum(1 for w in waves if w["status"] == "in_progress"),
                "waves_forming":  sum(1 for w in waves if w["status"] in ["forming","assigned"]),
                "total_items":    total_items,
                "items_picked":   sum(1 for o in orders if o["status"] == "picked"),
                "total_distance": round(total_dist, 1),
                "dist_per_item":  round(total_dist / total_items, 1) if total_items else 0,
            }
        finally:
            await conn.close()

    # ── 8. [DEV] Trigger manual proses order due (manager only) ────────────────
    @api.post("/api/dev/process-pending-orders")
    async def dev_process_pending_orders(caller: dict = Depends(get_caller_profile)):
        """
        Manual trigger buat run_due_orders_cycle() -- fungsi yang SAMA yang
        otomatis dipanggil tiap 10 menit oleh process_due_orders_cron() (Modal
        scheduled function, lihat di bawah). Dipakai buat testing tanpa nunggu
        cron tick berikutnya.

        Opsi B: INSERT order sendiri sekarang murni langsung ke Supabase dari
        frontend (lihat frontend_auth.md), dengan arrival_ts di-set 1-15 menit
        ke depan. Endpoint ini TIDAK bikin order baru -- cuma memproses order
        yang arrival_ts-nya udah lewat NOW() (status='pending', wave_id NULL).
        """
        if caller["role"] != "manager":
            raise HTTPException(403, {"error": "forbidden", "message": "Cuma manager yang bisa trigger proses order manual."})
        return await run_due_orders_cycle()

    return api


# ── Debug: lihat isi mentah /models tanpa asumsi apapun ────────────────────────
@app.function(
    image=image,
    volumes={"/models": model_vol},
    timeout=60,
)
def debug_list_models():
    """
    Jalankan: modal run modal_app.py::debug_list_models
    Menampilkan isi /models APA ADANYA, tanpa cek nama file spesifik.
    Struktur yang benar sekarang: /models/ berisi 3 file flat
    (ppo_batching_v11.zip, attn_routing_v11.pt, prod_emb.pkl).
    """
    import os

    model_vol.reload()

    print("=== os.listdir('/') ===")
    print(sorted(os.listdir("/")))

    print("\n=== Apakah /models ada? ===")
    print("exists:", os.path.exists("/models"))
    print("is_dir:", os.path.isdir("/models") if os.path.exists("/models") else "N/A")

    if os.path.exists("/models"):
        print("\n=== os.listdir('/models') ===")
        items = sorted(os.listdir("/models"))
        if not items:
            print("  (KOSONG — tidak ada file sama sekali)")
        for item in items:
            full = os.path.join("/models", item)
            kind = "dir " if os.path.isdir(full) else "file"
            size = os.path.getsize(full) if os.path.isfile(full) else "-"
            print(f"  [{kind}] {item}  ({size} bytes)" if size != "-" else f"  [{kind}] {item}")


# ── Modal function ─────────────────────────────────────────────────────────────
@app.function(
    image=image,
    volumes={"/models": model_vol},
    secrets=[modal.Secret.from_name("nexwave-secrets")],
    timeout=300,
    # min_containers=1,  # uncomment untuk hilangkan cold start
)
@modal.asgi_app()
def fastapi_app():
    return create_fastapi_app()


# ── Scheduled: proses order yang udah waktunya (Opsi B) ──────────────────────
@app.function(
    image=image,
    volumes={"/models": model_vol},
    secrets=[modal.Secret.from_name("nexwave-secrets")],
    timeout=180,
    schedule=modal.Period(minutes=10),
)
async def process_due_orders_cron():
    """
    Jalan otomatis tiap 10 menit (Opsi B). Order di-INSERT langsung ke Supabase
    dari frontend dengan arrival_ts 1-15 menit ke depan (lihat
    frontend_auth.md) -- begitu arrival_ts sebuah order <= NOW(), fungsi ini
    yang narik order tsb ke antrian batching_service dan assign wave ke
    picker. Logic-nya sama persis dengan POST /api/dev/process-pending-orders,
    cuma jalan otomatis tanpa perlu dipanggil manual.
    """
    await run_due_orders_cycle()


# ── Verify models (one-off, jalankan sebelum deploy) ─────────────────────────
@app.function(
    image=image,
    volumes={"/models": model_vol},
    secrets=[modal.Secret.from_name("nexwave-secrets")],
    timeout=120,
)
def verify_models():
    """
    Cek semua model bisa di-load.
    Jalankan: modal run modal_app.py::verify_models
    """
    import torch
    from sb3_contrib import MaskablePPO

    # Segarkan pandangan volume sebelum cek — wajib kalau file baru saja
    # diupload lewat CLI di luar container ini.
    model_vol.reload()

    # Cek file yang dibutuhkan — cuma 3 file flat di /models/
    required = {
        "ppo_batching_v11.zip": PPO_ZIP_PATH,   # file ZIP ASLI, jangan diextract
        "attn_routing_v11.pt":  ATTN_PATH,
        "prod_emb.pkl":         EMB_PATH,
    }

    print("=== Cek file di /models/ ===")
    all_ok = True
    for fname, path in required.items():
        ok   = os.path.exists(path)
        size = os.path.getsize(path) if ok else 0
        print(f"  {'✓' if ok else '✗'} {fname:<30} "
              f"{f'{size/1024:.1f} KB' if ok else 'MISSING'}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nAda file missing! Upload (flat, JANGAN diextract zip-nya):")
        print("  modal volume put nexwave-models-v2 ./ppo_batching_v11.zip /models/ppo_batching_v11.zip")
        print("  modal volume put nexwave-models-v2 ./attn_routing_v11.pt  /models/attn_routing_v11.pt")
        print("  modal volume put nexwave-models-v2 ./prod_emb.pkl         /models/prod_emb.pkl")
        return

    # Load MaskablePPO dari file ZIP (bukan folder)
    print("\n=== Load MaskablePPO ===")
    ppo = MaskablePPO.load(PPO_ZIP_PATH)
    print(f"  ✓ Policy class : {ppo.policy.__class__.__name__}")
    print(f"  ✓ Observation  : {ppo.observation_space}")
    print(f"  ✓ Action space : {ppo.action_space}")

    # Load Attention Model
    print("\n=== Load Attention Model ===")
    state = torch.load(ATTN_PATH, map_location="cpu")
    print(f"  ✓ Layer count  : {len(state)}")
    print(f"  ✓ Keys (5)     : {list(state.keys())[:5]}")

    # Load GNN embeddings
    print("\n=== Load GNN Embeddings ===")
    with open(EMB_PATH, "rb") as f:
        emb = pickle.load(f)
    sample = next(iter(emb.values()))
    print(f"  ✓ Produk unik  : {len(emb)}")
    print(f"  ✓ Dimensi emb  : {sample.shape}")
    print(f"  ✓ Contoh key   : {list(emb.keys())[:3]}")

    print("\n=== Semua model OK — siap deploy ===")
    print("Jalankan: modal deploy modal_app.py")