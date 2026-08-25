"""
Dispatcher Service
==================
Assign wave ke picker yang paling tepat menggunakan load balancing
(workload terkecil di antara picker yang available).

Dipanggil dari:
  - POST /api/wave/done → assign wave berikutnya ke picker yang baru selesai
  - Saat wave baru terbentuk (close_wave) → cari picker available
"""

import os
import time
from typing import Optional

from api.ml.routing import route_best

N_PICKERS = int(os.environ.get("N_PICKERS", 7))


async def assign_wave_to_picker(wave_id: str, conn,
                                 attn, nav) -> Optional[int]:
    """
    Assign satu wave ke picker yang paling available.
    Menghitung rute via route_best dan update DB.
    Return picker_id yang ditugaskan, atau None kalau tidak ada.
    """
    # Ambil wave locations untuk hitung rute
    locs_rows = await conn.fetch("""
        SELECT wl.location_id, o.qty, o.product_ref
        FROM wave_locations wl
        LEFT JOIN orders o ON wl.order_id = o.order_id
        WHERE wl.wave_id = $1
        ORDER BY wl.visit_order
    """, wave_id)

    locs = [r["location_id"] for r in locs_rows]
    if not locs:
        return None

    # Hitung rute optimal
    dist, route = route_best(attn, locs, nav)

    # Cari picker available dengan workload terkecil
    pickers = await conn.fetch("""
        SELECT p.picker_id,
               COUNT(w.wave_id) FILTER (WHERE w.status = 'done') as waves_done,
               SUM(w.total_distance) FILTER (WHERE w.status = 'done') as total_dist
        FROM pickers p
        LEFT JOIN waves w ON w.picker_id = p.picker_id
        WHERE p.status = 'available'
        GROUP BY p.picker_id
        ORDER BY COALESCE(SUM(w.total_distance) FILTER (WHERE w.status='done'), 0)
    """)

    if not pickers:
        return None

    picker_id = pickers[0]["picker_id"]

    # Update wave: set picker, rute, jarak
    await conn.execute("""
        UPDATE waves
        SET picker_id = $1, status = 'assigned',
            total_distance = $2, start_ts = NOW()
        WHERE wave_id = $3
    """, picker_id, dist, wave_id)

    # Update urutan kunjungan di wave_locations
    for i, loc_id in enumerate(route):
        await conn.execute("""
            UPDATE wave_locations
            SET visit_order = $1
            WHERE wave_id = $2 AND location_id = $3
        """, i + 1, wave_id, loc_id)

    # Update picker status
    await conn.execute("""
        UPDATE pickers
        SET status = 'busy', current_wave_id = $1
        WHERE picker_id = $2
    """, wave_id, picker_id)

    return picker_id


async def assign_next_wave(picker_id: int, conn,
                            ppo, attn, emb, nav) -> Optional[str]:
    """
    Cari wave berikutnya yang forming/belum punya picker,
    lalu assign ke picker ini.
    Return wave_id yang diassign, atau None kalau tidak ada.
    """
    # Cari wave yang sudah forming tapi belum punya picker
    wave = await conn.fetchrow("""
        SELECT wave_id FROM waves
        WHERE status = 'forming' AND picker_id IS NULL
        ORDER BY created_at
        LIMIT 1
    """)

    if not wave:
        # Tidak ada wave pending — picker standby
        await conn.execute("""
            UPDATE pickers SET status='available', current_wave_id=NULL
            WHERE picker_id=$1
        """, picker_id)
        return None

    wave_id = wave["wave_id"]

    # Assign wave ini ke picker
    await assign_wave_to_picker(wave_id, conn, attn, nav)

    # Override picker_id ke picker yang baru selesai
    await conn.execute("""
        UPDATE waves SET picker_id=$1 WHERE wave_id=$2
    """, picker_id, wave_id)

    await conn.execute("""
        UPDATE pickers SET status='busy', current_wave_id=$1
        WHERE picker_id=$2
    """, wave_id, picker_id)

    return wave_id


async def build_picker_schedule(waves: list, router_fn,
                                 n_pickers: int = N_PICKERS,
                                 speed: float = 1.2,
                                 pick_sec: float = 8.0) -> list:
    """
    Buat jadwal picker offline (untuk evaluasi/laporan).
    Sama dengan assign_to_pickers() di notebook.
    Return: list of picker schedules.
    """
    seq      = sorted(waves, key=lambda wv: min(o["arrival"] for o in wv))
    free     = [0.0] * n_pickers
    workload = [0.0] * n_pickers
    sched    = [[] for _ in range(n_pickers)]

    for wv in seq:
        items = sum(o["qty"] for o in wv)
        locs  = list(dict.fromkeys(o["loc"] for o in wv))
        d, route = router_fn(locs)
        ready = max(o.get("arrival", 0) for o in wv)
        dur   = d / speed + pick_sec * items

        available = [i for i in range(n_pickers) if free[i] <= ready]
        pidx = (min(available, key=lambda i: workload[i])
                if available else int(min(range(n_pickers), key=lambda i: free[i])))

        start  = max(free[pidx], ready)
        finish = start + dur
        free[pidx]     = finish
        workload[pidx] += dur

        loc_to_refs = {}
        for o in wv:
            loc_to_refs.setdefault(o["loc"], []).append(o["ref"])
        pick_seq = [(loc, ref) for loc in route
                    for ref in loc_to_refs.get(loc, [])]

        sched[pidx].append({
            "wave_orders":    [o["ref"] for o in wv],
            "locations":      route,
            "pick_sequence":  pick_seq,
            "n_items":        items,
            "distance":       d,
            "start":          start,
            "finish":         finish,
            "duration_min":   dur / 60,
        })

    return sched
