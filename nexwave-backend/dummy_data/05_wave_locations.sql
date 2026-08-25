-- ============================================================
-- Dummy data: wave_locations
-- CATATAN: di kode saat ini (api/services/batching_service.py,
-- api/services/dispatcher.py) tidak ada INSERT INTO wave_locations di mana pun --
-- dispatcher cuma UPDATE visit_order pada baris yang sudah ada. Baris di file ini
-- adalah state yang SEHARUSNYA muncul supaya GET /api/wave/active dan dashboard
-- frontend punya data buat dirender. visit_order ngikutin urutan asli dari
-- Nav.route_nn() (lihat 03_waves.sql); status picked/active/pending ngikutin
-- POSISI DI RUTE ITU (stop 1..k sudah lewat, stop k+1 lagi dikerjakan, sisanya
-- masih nunggu) -- bukan urutan order dibuat, biar runut kayak picker jalan beneran.
-- Jalankan SETELAH 01_locations.sql, 03_waves.sql, 04_orders.sql.
-- ============================================================

INSERT INTO wave_locations (wave_id, location_id, order_id, visit_order, status, picked_ts, picker_id) VALUES
    ('WAVE-DEMO-001', 'C-13-11', 'ORD-2026-000104', 1, 'picked', '2026-08-23 07:18:00+07', 3),
    ('WAVE-DEMO-001', 'B-13-11', 'ORD-2026-000102', 2, 'picked', '2026-08-23 07:24:00+07', 3),
    ('WAVE-DEMO-001', 'B-13-21', 'ORD-2026-000103', 3, 'picked', '2026-08-23 07:30:00+07', 3),
    ('WAVE-DEMO-001', 'A-14-11', 'ORD-2026-000100', 4, 'picked', '2026-08-23 07:36:00+07', 3),
    ('WAVE-DEMO-001', 'A-14-21', 'ORD-2026-000101', 5, 'picked', '2026-08-23 07:42:00+07', 3),
    ('WAVE-DEMO-002', 'F-13-11', 'ORD-2026-000110', 1, 'picked', '2026-08-23 09:13:00+07', 1),
    ('WAVE-DEMO-002', 'E-13-11', 'ORD-2026-000108', 2, 'picked', '2026-08-23 09:19:00+07', 1),
    ('WAVE-DEMO-002', 'E-13-21', 'ORD-2026-000109', 3, 'picked', '2026-08-23 09:25:00+07', 1),
    ('WAVE-DEMO-002', 'D-13-11', 'ORD-2026-000106', 4, 'active', NULL, 1),
    ('WAVE-DEMO-002', 'D-13-21', 'ORD-2026-000107', 5, 'pending', NULL, 1),
    ('WAVE-DEMO-002', 'C-13-21', 'ORD-2026-000105', 6, 'pending', NULL, 1),
    ('WAVE-DEMO-003', 'G-13-11', 'ORD-2026-000112', 1, 'pending', NULL, 2),
    ('WAVE-DEMO-003', 'G-13-21', 'ORD-2026-000113', 2, 'pending', NULL, 2),
    ('WAVE-DEMO-003', 'F-13-21', 'ORD-2026-000111', 3, 'pending', NULL, 2),
    ('WAVE-DEMO-003', 'H-02-11', 'ORD-2026-000114', 4, 'pending', NULL, 2),
    ('WAVE-DEMO-005', 'J-01-11', 'ORD-2026-000118', 1, 'picked', '2026-08-23 08:03:00+07', 4),
    ('WAVE-DEMO-005', 'J-01-21', 'ORD-2026-000119', 2, 'picked', '2026-08-23 08:09:00+07', 4),
    ('WAVE-DEMO-005', 'K-01-11', 'ORD-2026-000120', 3, 'picked', '2026-08-23 08:15:00+07', 4),
    ('WAVE-DEMO-005', 'K-01-21', 'ORD-2026-000121', 4, 'picked', '2026-08-23 08:21:00+07', 4),
    ('WAVE-DEMO-005', 'L-01-11', 'ORD-2026-000122', 5, 'picked', '2026-08-23 08:27:00+07', 4),
    ('WAVE-DEMO-005', 'L-01-21', 'ORD-2026-000123', 6, 'picked', '2026-08-23 08:33:00+07', 4);
