-- ============================================================
-- Dummy data: waves
-- 5 wave yang mewakili tiap status di lifecycle: forming -> assigned ->
-- in_progress -> done. total_distance dihitung dari Nav.route_nn() asli
-- (heuristik nearest-neighbor) atas lokasi order di wave yang sama, jadi
-- angkanya konsisten sama graph koridor di dataset/, bukan angka acak.
-- Jalankan SETELAH 02_pickers.sql (waves.picker_id FK ke pickers).
-- ============================================================

INSERT INTO waves (wave_id, status, picker_id, start_ts, finish_ts, total_items, total_distance, created_at) VALUES
    ('WAVE-DEMO-001', 'done', 3, '2026-08-23 07:15:00+07', '2026-08-23 07:42:00+07', 16, 2380.0, '2026-08-23 07:05:00+07'),
    ('WAVE-DEMO-002', 'in_progress', 1, '2026-08-23 09:10:00+07', NULL, 14, 2148.0, '2026-08-23 09:00:00+07'),
    ('WAVE-DEMO-003', 'assigned', 2, '2026-08-23 09:32:00+07', NULL, 14, 1944.0, '2026-08-23 09:25:00+07'),
    ('WAVE-DEMO-004', 'forming', NULL, NULL, NULL, 8, 0.0, '2026-08-23 09:35:00+07'),
    ('WAVE-DEMO-005', 'done', 4, '2026-08-23 08:00:00+07', '2026-08-23 08:35:00+07', 18, 1538.0, '2026-08-23 07:50:00+07')
ON CONFLICT (wave_id) DO NOTHING;
