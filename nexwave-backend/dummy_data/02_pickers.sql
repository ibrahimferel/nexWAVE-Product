-- ============================================================
-- Dummy data: pickers
-- 7 picker (sesuai N_PICKERS default di modal_app.py), status dicampur
-- supaya dashboard bisa langsung nampilin semua state (available/busy/break/offline).
-- picker_id diisi eksplisit (bukan andalkan SERIAL) supaya 03_waves.sql dan
-- 04_orders.sql bisa mereferensikan id yang pasti sama.
-- Kalau schema.sql STEP 5 sudah pernah jalan (seed 7 Operator), file ini akan
-- UPDATE status/current_wave_id-nya, bukan bikin duplikat (lihat ON CONFLICT).
-- ============================================================

INSERT INTO pickers (picker_id, name, status, current_wave_id) VALUES
    (1, 'Operator 1', 'busy', 'WAVE-DEMO-002'),
    (2, 'Operator 2', 'busy', 'WAVE-DEMO-003'),
    (3, 'Operator 3', 'available', NULL),
    (4, 'Operator 4', 'available', NULL),
    (5, 'Operator 5', 'break', NULL),
    (6, 'Operator 6', 'available', NULL),
    (7, 'Operator 7', 'offline', NULL)
ON CONFLICT (picker_id) DO UPDATE SET
    status = EXCLUDED.status,
    current_wave_id = EXCLUDED.current_wave_id;

-- selaraskan sequence picker_id biar INSERT berikutnya (tanpa id eksplisit) tidak bentrok
SELECT setval(pg_get_serial_sequence('pickers', 'picker_id'), (SELECT MAX(picker_id) FROM pickers));
