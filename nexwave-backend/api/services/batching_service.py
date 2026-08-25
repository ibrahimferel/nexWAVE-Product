"""
Batching Service
================
Dipanggil setiap order baru masuk ke endpoint POST /api/order/new.
Menggunakan MaskablePPO untuk memutuskan: tambah order ke wave aktif,
atau tutup wave dan buka wave baru.

State wave aktif disimpan di memory (dict _state).
Di production dengan banyak instance Modal, state perlu dipindah ke Redis/DB.
Untuk MVP/demo, in-memory sudah cukup.
"""

import os
import time
import numpy as np
from typing import Optional

# ── In-memory state ────────────────────────────────────────────────────────────
# Menyimpan state wave yang sedang terbuka per shift
_state = {
    "wave":      [],       # list of order dict dalam wave aktif
    "wave_qty":  0,        # total item dalam wave aktif
    "wave_id":   None,     # ID wave aktif di DB
    "opened_at": None,     # timestamp wave dibuka (untuk timeout check)
    "queue":     [],       # antrian order yang belum dibatch
}

CAPACITY       = int(os.environ.get("CAPACITY", 27))
VISIBLE_WINDOW = int(os.environ.get("VISIBLE_WINDOW", 40))
K_BATCH        = 8
EMB_DIM        = 32
SCALE          = 800.0    # normalisasi jarak, sesuai training
ZERO_EMB       = np.zeros(EMB_DIM, dtype=np.float32)


def _emb_of(ref: str, prod_emb: dict) -> np.ndarray:
    return prod_emb.get(str(ref), ZERO_EMB)


def _build_obs(wave: list, queue: list, wave_qty: int,
               prod_emb: dict, nav) -> np.ndarray:
    """
    Bangun observation vector 54 dimensi untuk PPO agent:
    [6 statistik wave] + [32 GNN embedding agregat] + [5 fitur × 8 kandidat]
    Sama persis dengan BatchingEnv._obs() di notebook.
    """
    cap = CAPACITY

    # 6 statistik wave
    fill      = wave_qty / cap
    n_items   = min(wave_qty / cap, 1.0)
    if wave:
        dists = [nav.corridor_distance(wave[-1]["loc"], o["loc"])
                 for o in wave[:-1]] if len(wave) > 1 else [0.0]
        intra = float(np.mean(dists)) / SCALE if dists else 0.0
        dep_d = nav.depot_dist(wave[-1]["loc"]) / SCALE
    else:
        intra = 0.0
        dep_d = 0.0
    q_ratio = min(len(queue) / max(VISIBLE_WINDOW, 1), 1.0)

    now = time.time()
    if wave:
        arrivals = [o.get("arrival", now) for o in wave]
        spread   = (max(arrivals) - min(arrivals)) / 600.0
    else:
        spread = 0.0

    wave_stats = np.array(
        [fill, n_items, intra, dep_d, q_ratio, float(np.tanh(spread))],
        dtype=np.float32
    )

    # 32 GNN embedding agregat wave
    if wave:
        embs    = np.stack([_emb_of(o["ref"], prod_emb) for o in wave])
        wave_emb = embs.mean(0)
    else:
        wave_emb = ZERO_EMB.copy()

    # 8 kandidat terdekat dari VISIBLE_WINDOW
    vis = [o for o in queue[:VISIBLE_WINDOW]
           if o["qty"] <= (cap - wave_qty)]
    if wave:
        ref_loc = wave[-1]["loc"]
        vis.sort(key=lambda o: nav.corridor_distance(ref_loc, o["loc"]))
    else:
        vis.sort(key=lambda o: nav.depot_dist(o["loc"]))
    cands = vis[:K_BATCH]

    cand_feats = []
    wave_emb_norm = wave_emb / (np.linalg.norm(wave_emb) + 1e-8)
    for i in range(K_BATCH):
        if i < len(cands):
            o = cands[i]
            dist = (nav.corridor_distance(wave[-1]["loc"], o["loc"])
                    if wave else nav.depot_dist(o["loc"]))
            o_emb = _emb_of(o["ref"], prod_emb)
            o_emb_norm = o_emb / (np.linalg.norm(o_emb) + 1e-8)
            cos_sim = float(np.dot(wave_emb_norm, o_emb_norm))
            wait    = (time.time() - o.get("arrival", time.time())) / 600.0
            cand_feats += [
                o["qty"] / cap,
                min(dist / SCALE, 1.0),
                float(np.tanh(cos_sim)),
                min(nav.depot_dist(o["loc"]) / SCALE, 1.0),
                float(np.tanh(wait)),
            ]
        else:
            cand_feats += [0.0, 0.0, 0.0, 0.0, 0.0]

    obs = np.concatenate([wave_stats, wave_emb,
                          np.array(cand_feats, dtype=np.float32)])
    return obs.astype(np.float32)


def _action_masks(wave: list, queue: list, wave_qty: int) -> np.ndarray:
    """
    Buat action mask: True = aksi valid.
    Aksi 0..K_BATCH-1 = tambah kandidat ke-i
    Aksi K_BATCH = tutup wave
    """
    cap  = CAPACITY
    vis  = [o for o in queue[:VISIBLE_WINDOW]
            if o["qty"] <= (cap - wave_qty)]
    if wave:
        vis.sort(key=lambda o: 0)  # sudah disort di _build_obs
    cands = vis[:K_BATCH]

    masks = np.zeros(K_BATCH + 1, dtype=bool)
    for i in range(K_BATCH):
        masks[i] = i < len(cands)
    masks[K_BATCH] = len(wave) > 0   # tutup wave hanya valid kalau tidak kosong
    return masks


def _normalize_order(order: dict) -> dict:
    """
    _build_obs/_action_masks baca o["loc"]/o["ref"]/o["arrival"] (nama field
    dari notebook training), sedangkan OrderIn/DB pakai location_id/
    product_ref/arrival_ts (string ISO) -- alias di sini, bukan rename field
    DB. Tanpa ini o["loc"]/o["ref"] KeyError (crash), dan o.get("arrival", ...)
    diam-diam selalu fallback ke "baru saja" (fitur wait-time ke agent jadi
    salah, nggak crash tapi keputusan batching-nya nggak akurat).
    """
    order = {**order, "loc": order["location_id"], "ref": order["product_ref"]}
    try:
        from datetime import datetime
        order["arrival"] = datetime.fromisoformat(
            str(order["arrival_ts"]).replace("Z", "+00:00")
        ).timestamp()
    except (KeyError, ValueError, TypeError):
        order["arrival"] = time.time()
    return order


async def _resolve_queue(ppo, emb: dict, nav, conn, max_steps: int = 200) -> list:
    """
    Loop keputusan PPO selama masih ada aksi valid -- lanjut proses SISA
    queue setelah tiap close_wave, bukan langsung return kayak decide() versi
    lama. Dipakai bareng oleh decide() (satu order real-time) dan
    process_due_orders() (banyak order sekaligus). Return list of
    (action_str, wave_id).
    """
    global _state
    results = []
    for _ in range(max_steps):
        obs   = _build_obs(_state["wave"], _state["queue"],
                           _state["wave_qty"], emb, nav)
        masks = _action_masks(_state["wave"], _state["queue"],
                              _state["wave_qty"])

        if not masks.any():
            break

        action, _ = ppo.predict(obs, action_masks=masks, deterministic=True)
        action    = int(action)

        if action == K_BATCH:
            wave_id = await _close_wave(conn)
            results.append(("close_wave", wave_id))
            continue  # sisa queue (kalau ada) masih perlu diproses

        # Tambah kandidat ke wave
        vis = [o for o in _state["queue"][:VISIBLE_WINDOW]
               if o["qty"] <= (CAPACITY - _state["wave_qty"])]
        if _state["wave"]:
            ref_loc = _state["wave"][-1]["loc"]
            vis.sort(key=lambda o: nav.corridor_distance(ref_loc, o["loc"]))
        else:
            vis.sort(key=lambda o: nav.depot_dist(o["loc"]))
        cands = vis[:K_BATCH]

        if action >= len(cands):
            break

        chosen = cands[action]
        _state["queue"].remove(chosen)
        _state["wave"].append(chosen)
        _state["wave_qty"] += chosen["qty"]

        if _state["wave_id"] is None:
            seq = await conn.fetchval("SELECT nextval('wave_id_seq')")
            _state["wave_id"] = f"WAVE-{seq:03d}"
            _state["opened_at"] = time.time()
            # Baris waves dibuat SEKARANG, bukan nanti pas _close_wave() --
            # UPDATE orders.wave_id di bawah ini FK ke waves.wave_id, jadi
            # tanpa placeholder ini bakal kena FK violation di order pertama
            # yang ditambahkan ke wave baru. _close_wave() nanti tinggal
            # UPDATE total_items-nya (ON CONFLICT DO UPDATE, bukan re-INSERT).
            await conn.execute("""
                INSERT INTO waves (wave_id, status, total_items)
                VALUES ($1, 'forming', 0)
                ON CONFLICT (wave_id) DO NOTHING
            """, _state["wave_id"])

        # Update order status di DB
        await conn.execute(
            "UPDATE orders SET status='in_wave', wave_id=$1 WHERE order_id=$2",
            _state["wave_id"], chosen["order_id"]
        )
        results.append(("add", _state["wave_id"]))

    return results


async def decide(order: dict, ppo, emb: dict, nav, conn) -> tuple:
    """
    Dipanggil dari endpoint POST /api/order/new -- SATU order real-time.
    Return: (action_str, wave_id) -- keputusan TERAKHIR yang diambil.
      action_str: "add" | "close_wave"
      wave_id: ID wave yang diupdate

    Catatan: dipanggil satu order per HTTP request, jadi queue biasanya cuma
    berisi 1 kandidat tiap kali _resolve_queue() jalan -- agent nggak punya
    pilihan nyata (add dipaksa krn cuma 1 kandidat, lalu close dipaksa krn
    queue langsung kosong). Ini kenapa order real-time cenderung 1 wave =
    1 lokasi. Buat lihat agent milih dari BANYAK kandidat sekaligus (wave
    multi-lokasi yang realistis), lihat process_due_orders() di bawah --
    dipanggil scheduled function yang ngumpulin beberapa order dulu sebelum
    minta keputusan.
    """
    global _state
    order = _normalize_order(order)
    _state["queue"].append(order)
    _state["queue"].sort(key=lambda o: o.get("arrival_ts", ""))

    results = await _resolve_queue(ppo, emb, nav, conn, max_steps=200)
    if results:
        return results[-1]
    return "add", _state["wave_id"]


async def process_due_orders(due_orders: list, ppo, emb: dict, nav, conn) -> dict:
    """
    Dipanggil scheduled function (Modal Cron, lihat modal_app.py) -- proses
    SEMUA order yang arrival_ts-nya sudah lewat SEKALIGUS, bukan satu-satu.
    Beda penting dari decide(): semua due_orders masuk ke queue DULU, baru
    loop keputusan dijalankan sekali -- jadi agent beneran punya lebih dari
    1 kandidat buat dipilih tiap langkah, bukan dipaksa add-lalu-close kayak
    kasus satu-order (lihat catatan decide() di atas).
    Return: {"add": N, "close_wave": M}
    """
    global _state
    for o in due_orders:
        _state["queue"].append(_normalize_order(o))
    _state["queue"].sort(key=lambda o: o.get("arrival_ts", ""))

    results = await _resolve_queue(ppo, emb, nav, conn, max_steps=500)
    return {
        "add":        sum(1 for a, _ in results if a == "add"),
        "close_wave": sum(1 for a, _ in results if a == "close_wave"),
    }


async def _close_wave(conn) -> str:
    """Tutup wave aktif: simpan ke DB, reset state."""
    global _state
    if _state["wave_id"] is None:
        # Fallback -- normalnya nggak pernah kejadian, wave_id sudah diisi
        # pas order pertama ditambahkan (lihat _resolve_queue), dan
        # _close_wave() cuma dipanggil kalau len(wave) > 0 (lihat action
        # mask di _action_masks). Dijaga di sini biar tetap format
        # WAVE-NNN kalau invariant itu suatu saat berubah, bukan diam-diam
        # balik ke UUID.
        seq = await conn.fetchval("SELECT nextval('wave_id_seq')")
        wave_id = f"WAVE-{seq:03d}"
    else:
        wave_id = _state["wave_id"]
    orders  = _state["wave"]
    qty     = _state["wave_qty"]

    if orders:
        await conn.execute("""
            INSERT INTO waves (wave_id, status, total_items)
            VALUES ($1, 'forming', $2)
            ON CONFLICT (wave_id) DO UPDATE SET total_items = $2
        """, wave_id, qty)

        # Satu baris wave_locations per order di wave ini -- belum ada urutan
        # kunjungan (visit_order default 0), assign_wave_to_picker() (dispatcher.py)
        # yang ngisi visit_order beneran begitu wave ini di-assign ke picker.
        # Tanpa INSERT ini, assign_wave_to_picker() nggak akan pernah nemu baris
        # buat di-routing -- wave bakal macet di status 'forming' selamanya.
        await conn.executemany("""
            INSERT INTO wave_locations (wave_id, location_id, order_id, status)
            VALUES ($1, $2, $3, 'pending')
        """, [(wave_id, o["location_id"], o["order_id"]) for o in orders])

    # Reset state untuk wave berikutnya
    _state["wave"]      = []
    _state["wave_qty"]  = 0
    _state["wave_id"]   = None
    _state["opened_at"] = None

    return wave_id


async def force_close_wave(conn) -> Optional[str]:
    """
    Paksa tutup wave (dipanggil oleh timeout scheduler).
    Return wave_id yang ditutup, atau None kalau wave kosong.
    """
    if not _state["wave"]:
        return None
    return await _close_wave(conn)
