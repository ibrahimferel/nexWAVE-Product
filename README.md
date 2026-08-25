<p align="center">
	<img src="nexWave-Frontend/public/logo-nexwave.svg" alt="nexWAVE" width="320" />
</p>

<p align="center">
	<strong>Warehouse Operations Control</strong><br/>
	Intelligent order batching + picker routing in one operational dashboard.
</p>

<p align="center">
	<img alt="Next.js" src="https://img.shields.io/badge/Next.js-16-black" />
	<img alt="React" src="https://img.shields.io/badge/React-19-149ECA" />
	<img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5-3178C6" />
	<img alt="Supabase" src="https://img.shields.io/badge/Supabase-Auth%20%2B%20Postgres-3ECF8E" />
	<img alt="Backend" src="https://img.shields.io/badge/Backend-FastAPI%20on%20Modal-5B4BFF" />
</p>

# nexWAVE

Repositori ini berisi sistem operasional warehouse end-to-end:

- Frontend web untuk manager dan operator (Next.js + Supabase)
- Backend ML/API (FastAPI di Modal) yang sudah dideploy
- Dataset dummy dan skrip backend pendukung

Tujuan dokumen ini adalah membantu juri menjalankan proyek secara lokal dari parent folder repositori ini.

## Quick Start (Juri)

```bash
cd nexWave-Frontend
cp .env.example .env.local
# lengkapi .env.local dengan secret yang sudah dibagikan
npm install
npm run dev
```

Lalu buka http://localhost:3000

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

## demo-nexWAVE

Bagian ini disiapkan agar juri cepat memahami bagaimana mencoba sistem.

| Item Demo | Keterangan |
|---|---|
| Akses aplikasi | Jalankan lokal dari `nexWave-Frontend/` |
| URL lokal | `http://localhost:3000` |
| Login manager | Google OAuth (akun yang sudah didaftarkan) |
| Login operator | Email/password dummy (sudah dibagikan) |
| Fitur kunci yang didemokan | Monitoring wave aktif, checklist picking, close wave, process pending orders |
| Backend deploy | `https://farelfebryan06--nexwave-api-fastapi-app.modal.run` |

Checklist skenario demo yang direkomendasikan:

1. Login sebagai manager dan buka dashboard wave aktif.
2. Login sebagai operator untuk menjalankan picking route.
3. Konfirmasi pick beberapa lokasi lalu cek update realtime di sisi manager.
4. Tutup wave dan lihat assignment wave berikutnya.
5. Trigger process pending orders (opsional) untuk simulasi order due.

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

Langkah ini wajib sebelum menjalankan aplikasi.

Salin template environment yang sudah disediakan:

```bash
cp .env.example .env.local
```

Lalu isi semua variabel di `.env.local` menggunakan kredensial/secret yang sudah diberikan:

```env
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_API_BASE_URL=https://farelfebryan06--nexwave-api-fastapi-app.modal.run
```

Catatan:

- `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_ANON_KEY` wajib
- `NEXT_PUBLIC_API_BASE_URL` disarankan aktif agar fitur endpoint backend dapat dipakai
- Jangan biarkan nilai placeholder (misalnya `isi-dengan-...`) tetap ada di file `.env.local`
- Setiap perubahan file env memerlukan restart development server

Tip: nilai awal contoh ada di `.env.example`, tetapi wajib diganti dengan secret asli sebelum aplikasi dijalankan.

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
	- Pastikan `.env.local` sudah dibuat dari `.env.example`
	- Pastikan semua nilai placeholder sudah diganti dengan secret yang valid
	- Restart dev server setelah mengubah env
- `EBADENGINE` saat `npm install`:
	- Update Node.js ke >= 20.9
- Login berhasil tapi data kosong:
	- Pastikan kredensial Supabase dan data project sesuai environment demo
