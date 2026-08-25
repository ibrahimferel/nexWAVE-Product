# nexWAVE

Repositori ini berisi sistem operasional warehouse end-to-end:

- Frontend web untuk manager dan operator (Next.js + Supabase)
- Backend ML/API (FastAPI di Modal) yang sudah dideploy
- Dataset dummy dan skrip backend pendukung

Tujuan dokumen ini adalah membantu juri menjalankan proyek secara lokal dari parent folder repositori ini.

## Gambaran Singkat Proyek

nexWAVE menggabungkan dua alur utama operasional gudang:

- Order batching: pengelompokan order ke wave
- Picker routing: rute pengambilan barang untuk operator/picker

Peran pengguna:

- Manager: melihat dashboard operasional, wave aktif, dan ringkasan shift
- Operator: menjalankan checklist picking berdasarkan rute

Arsitektur eksekusi:

- Frontend berkomunikasi ke Supabase untuk auth dan operasi data utama
- Backend Modal dipakai untuk endpoint ML/aksi tertentu (contoh: close wave, process pending orders)

Backend sudah dideploy di:

- https://farelfebryan06--nexwave-api-fastapi-app.modal.run

## Struktur Folder Penting

- `nexWave-Frontend/` -> aplikasi frontend yang dijalankan lokal
- `nexwave-backend/` -> source backend dan aset pendukung (tidak wajib dijalankan lokal untuk demo frontend)

## Cara Menjalankan (Untuk Juri)

Ikuti langkah berikut dari parent folder repositori ini.

### 1) Masuk ke folder frontend

```bash
cd nexWave-Frontend
```

### 2) Pastikan prasyarat

- Node.js versi 20.9 atau lebih baru
- npm tersedia

Cek cepat:

```bash
node -v
npm -v
```

### 3) Install dependency

```bash
npm install
```

### 4) Siapkan environment

Buat file `.env.local` di dalam folder `nexWave-Frontend/`.

Isi variabel berikut menggunakan kredensial/secret yang sudah diberikan:

```env
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://farelfebryan06--nexwave-api-fastapi-app.modal.run
```

Catatan:

- `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_ANON_KEY` wajib
- `NEXT_PUBLIC_API_BASE_URL` disarankan aktif agar fitur endpoint backend dapat dipakai

### 5) Jalankan development server

```bash
npm run dev
```

Buka:

- http://localhost:3000

Jika port 3000 sudah dipakai:

```bash
npm run dev -- -p 3001
```

### 6) (Opsional) Validasi cepat

```bash
npm run lint
npm run test
```

## Alur Login

- Manager: login via Google OAuth
- Operator: login via email/password akun dummy

Setelah login, user diarahkan sesuai role ke dashboard manager/operator.

## Catatan Demo

- Untuk kebutuhan demo penutupan wave dan pemrosesan pending orders, frontend akan menggunakan backend URL di `NEXT_PUBLIC_API_BASE_URL`.
- Operasi data lain yang berbasis Supabase tetap membutuhkan konfigurasi Supabase yang valid (sudah disiapkan melalui secret yang dibagikan).

## Troubleshooting Singkat

- Error `supabaseUrl is required`:
	- Pastikan `.env.local` sudah ada dan variabel terisi benar
	- Restart dev server setelah mengubah env
- `EBADENGINE` saat `npm install`:
	- Update Node.js ke >= 20.9
- Login berhasil tapi data kosong:
	- Pastikan kredensial Supabase dan data project sesuai environment demo
