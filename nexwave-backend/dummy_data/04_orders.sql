-- ============================================================
-- Dummy data: orders
-- 24 order sudah dibatch ke salah satu dari 5 wave di 03_waves.sql (status
-- in_wave/picked mengikuti posisi order itu di rute nyata wave-nya -- lihat
-- 05_wave_locations.sql), + 6 order 'pending' yang belum diproses batching
-- agent sama sekali (simulasi antrian baru dari WMS). arrival_ts tiap order
-- di-cluster sebelum created_at wave yang menampungnya (bukan angka acak).
-- product_ref pakai kode produk asli yang ADA di prod_emb.pkl (bukan random),
-- supaya kalau dipakai buat test /api/order/new, batching agent dapat GNN
-- embedding beneran, bukan fallback zero-vector.
-- Jalankan SETELAH 01_locations.sql dan 03_waves.sql.
-- ============================================================

INSERT INTO orders (order_id, product_ref, qty, location_id, arrival_ts, status, wave_id, picker_id) VALUES
    ('ORD-2026-000100', '02MRUH', 3, 'A-14-11', '2026-08-23 06:35:00+07', 'picked', 'WAVE-DEMO-001', 3),
    ('ORD-2026-000101', '05W6TK', 1, 'A-14-21', '2026-08-23 06:41:00+07', 'picked', 'WAVE-DEMO-001', 3),
    ('ORD-2026-000102', '066BOU', 2, 'B-13-11', '2026-08-23 06:47:00+07', 'picked', 'WAVE-DEMO-001', 3),
    ('ORD-2026-000103', '0LNUOV', 6, 'B-13-21', '2026-08-23 06:53:00+07', 'picked', 'WAVE-DEMO-001', 3),
    ('ORD-2026-000104', '0SJH1Z', 4, 'C-13-11', '2026-08-23 06:59:00+07', 'picked', 'WAVE-DEMO-001', 3),
    ('ORD-2026-000105', '122OKQ', 1, 'C-13-21', '2026-08-23 08:24:00+07', 'in_wave', 'WAVE-DEMO-002', 1),
    ('ORD-2026-000106', '1A6YTA', 2, 'D-13-11', '2026-08-23 08:30:00+07', 'in_wave', 'WAVE-DEMO-002', 1),
    ('ORD-2026-000107', '1D2ILZ', 5, 'D-13-21', '2026-08-23 08:36:00+07', 'in_wave', 'WAVE-DEMO-002', 1),
    ('ORD-2026-000108', '1ENECA', 3, 'E-13-11', '2026-08-23 08:42:00+07', 'picked', 'WAVE-DEMO-002', 1),
    ('ORD-2026-000109', '1JT1XB', 1, 'E-13-21', '2026-08-23 08:48:00+07', 'picked', 'WAVE-DEMO-002', 1),
    ('ORD-2026-000110', '2LPO6D', 2, 'F-13-11', '2026-08-23 08:54:00+07', 'picked', 'WAVE-DEMO-002', 1),
    ('ORD-2026-000111', '2OAVPY', 4, 'F-13-21', '2026-08-23 09:01:00+07', 'in_wave', 'WAVE-DEMO-003', 2),
    ('ORD-2026-000112', '2T1DJM', 6, 'G-13-11', '2026-08-23 09:07:00+07', 'in_wave', 'WAVE-DEMO-003', 2),
    ('ORD-2026-000113', '2Z7ZEP', 1, 'G-13-21', '2026-08-23 09:13:00+07', 'in_wave', 'WAVE-DEMO-003', 2),
    ('ORD-2026-000114', '32ZKOX', 3, 'H-02-11', '2026-08-23 09:19:00+07', 'in_wave', 'WAVE-DEMO-003', 2),
    ('ORD-2026-000115', '37VA62', 2, 'H-02-21', '2026-08-23 09:17:00+07', 'in_wave', 'WAVE-DEMO-004', NULL),
    ('ORD-2026-000116', '3LQL9L', 5, 'I-01-11', '2026-08-23 09:23:00+07', 'in_wave', 'WAVE-DEMO-004', NULL),
    ('ORD-2026-000117', '4E0KXI', 1, 'I-01-21', '2026-08-23 09:29:00+07', 'in_wave', 'WAVE-DEMO-004', NULL),
    ('ORD-2026-000118', '4ILN0A', 4, 'J-01-11', '2026-08-23 07:14:00+07', 'picked', 'WAVE-DEMO-005', 4),
    ('ORD-2026-000119', '4SD17H', 2, 'J-01-21', '2026-08-23 07:20:00+07', 'picked', 'WAVE-DEMO-005', 4),
    ('ORD-2026-000120', '56TC1Z', 3, 'K-01-11', '2026-08-23 07:26:00+07', 'picked', 'WAVE-DEMO-005', 4),
    ('ORD-2026-000121', '5HQR89', 1, 'K-01-21', '2026-08-23 07:32:00+07', 'picked', 'WAVE-DEMO-005', 4),
    ('ORD-2026-000122', '5IXVJ1', 6, 'L-01-11', '2026-08-23 07:38:00+07', 'picked', 'WAVE-DEMO-005', 4),
    ('ORD-2026-000123', '5MNTT7', 2, 'L-01-21', '2026-08-23 07:44:00+07', 'picked', 'WAVE-DEMO-005', 4),
    ('ORD-2026-000124', '5P2MVG', 3, 'M-01-11', '2026-08-23 09:40:00+07', 'pending', NULL, NULL),
    ('ORD-2026-000125', '5P4LRT', 1, 'M-01-21', '2026-08-23 09:42:00+07', 'pending', NULL, NULL),
    ('ORD-2026-000126', '5X8RAN', 2, 'N-01-11', '2026-08-23 09:44:00+07', 'pending', NULL, NULL),
    ('ORD-2026-000127', '63KAC1', 4, 'N-01-21', '2026-08-23 09:46:00+07', 'pending', NULL, NULL),
    ('ORD-2026-000128', '69L9MX', 1, 'O-01-11', '2026-08-23 09:48:00+07', 'pending', NULL, NULL),
    ('ORD-2026-000129', '6M2FJM', 3, 'O-01-21', '2026-08-23 09:50:00+07', 'pending', NULL, NULL)
ON CONFLICT (order_id) DO NOTHING;
