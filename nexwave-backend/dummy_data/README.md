# Dummy data — cara pakai

DML doang (schema-nya di [../schema.sql](../schema.sql), jalankan itu duluan kalau tabel belum ada). Semua data di sini realistis, bukan asal:
- `location_id`/`x`/`y`/`z` di [01_locations.sql](01_locations.sql) adalah 48 baris asli dari [../dataset/Storage_Location.csv](../dataset/Storage_Location.csv) (sampling per block+floor), bukan koordinat karangan.
- `product_ref` di [04_orders.sql](04_orders.sql) adalah kode produk yang beneran ADA embedding-nya di `prod_emb.pkl` (198 produk), supaya kalau dipakai buat test `POST /api/order/new`, batching agent dapat GNN embedding sungguhan, bukan fallback zero-vector.
- `total_distance` di [03_waves.sql](03_waves.sql) dan `visit_order` di [05_wave_locations.sql](05_wave_locations.sql) dihitung dari `Nav.route_nn()` asli (`api/ml/nav.py`) atas lokasi-lokasi di wave yang sama — bukan angka acak.

## Skenario
Satu "shift" hari ini (2026-08-23), 5 wave mewakili tiap status di lifecycle:

| wave_id | status | picker | cerita |
|---|---|---|---|
| WAVE-DEMO-001 | done | Operator 3 | selesai pagi, semua lokasi picked |
| WAVE-DEMO-005 | done | Operator 4 | selesai pagi (lebih awal dari 001) |
| WAVE-DEMO-002 | in_progress | Operator 1 | 3 dari 6 stop sudah picked, 1 lagi `active`, sisanya `pending` — urutannya ngikutin rute asli, bukan urutan insert |
| WAVE-DEMO-003 | assigned | Operator 2 | baru di-assign, belum mulai jalan (semua `pending`) |
| WAVE-DEMO-004 | forming | (belum ada) | masih nunggu order lain, **belum ada baris `wave_locations`** — konsisten sama kode: rute baru dibikin pas wave di-assign, bukan pas masih forming |

Plus 6 order lagi yang statusnya `pending` (belum masuk wave manapun) — simulasi antrian baru dari WMS yang belum diproses batching agent.

7 picker (`02_pickers.sql`) dicampur statusnya (`busy` x2, `available` x3, `break` x1, `offline` x1) supaya UI dashboard picker bisa langsung dites nampilin semua state.

## Urutan jalanin
FK antar tabel artinya urutan ini wajib (Supabase SQL Editor → New Query, atau `psql -f`):
```
01_locations.sql
02_pickers.sql
03_waves.sql
04_orders.sql
05_wave_locations.sql
06_shift_log.sql
```
Semua idempotent (`ON CONFLICT DO NOTHING`/`DO UPDATE`) — aman dijalankan ulang.

Sudah dites end-to-end: schema.sql + keenam file ini dijalankan berurutan di Postgres 16 lokal (bukan project Supabase asli), nol error, dan query yang sama persis dengan yang dipakai `GET /api/wave/active` / `GET /api/shift/summary` di `modal_app.py` sudah dicoba manual — hasilnya sesuai skenario di atas.

## Yang perlu diingat
`wave_locations` untuk WAVE-DEMO-001/002/003/005 di sini diisi manual oleh file ini. Di kode backend saat ini (`api/services/dispatcher.py`, `api/services/batching_service.py`), **tidak ada satupun `INSERT INTO wave_locations`** — jadi wave yang terbentuk dari alur order beneran (`POST /api/order/new`) tidak akan otomatis punya baris di tabel ini sampai ada yang nambahin logic-nya. Detail di [../api.md](../api.md).
