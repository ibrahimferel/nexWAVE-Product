-- ============================================================
-- Dummy data: shift_log
-- Agregat harian buat header dashboard / analytics. Angka hari ini (shift_date
-- = hari ini) dihitung dari 03_waves.sql + 04_orders.sql di atas; 2 hari sebelumnya
-- cuma angka historis masuk akal buat nge-test trend chart.
-- Bisa dijalankan kapan saja, tidak ada FK ke tabel lain.
-- ============================================================

INSERT INTO shift_log (shift_date, n_waves, total_items, total_distance, n_pickers, makespan_min, dist_per_item, fill_rate) VALUES
    ('2026-08-23', 5, 70, 8010.0, 7, 142.3, 114.4, 96.5),
    ('2026-08-22', 28, 782, 68210.4, 7, 138.7, 87.2, 97.8),
    ('2026-08-21', 25, 705, 61180.9, 6, 145.1, 86.8, 95.2)
ON CONFLICT (shift_date) DO UPDATE SET
    n_waves = EXCLUDED.n_waves,
    total_items = EXCLUDED.total_items,
    total_distance = EXCLUDED.total_distance,
    n_pickers = EXCLUDED.n_pickers,
    makespan_min = EXCLUDED.makespan_min,
    dist_per_item = EXCLUDED.dist_per_item,
    fill_rate = EXCLUDED.fill_rate;
