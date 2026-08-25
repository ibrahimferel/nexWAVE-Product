"""
Bikin akun login (email+password) buat 7 operator dummy -- dijalankan SEKALI
oleh admin, BUKAN self-signup. Operator login pakai email+password ini (bukan
Google) lewat Supabase Auth yang SAMA -- backend (verify_token di modal_app.py)
nggak peduli itu login lewat Google atau email/password, keduanya sama-sama
masuk ke auth.users dan dapat baris public.users (role default 'operator' --
lihat schema.sql STEP 6).

Setelah akun dibuat, script ini juga langsung menghubungkan tiap akun ke baris
pickers yang sesuai (pickers.auth_user_id) -- jadi operator langsung bisa akses
GET /api/picker/{picker_id}/next miliknya sendiri begitu login.

Jalankan:
pip install supabase
export SUPABASE_URL="https://bxgqzavziovzpohyaubu.supabase.co"
export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ4Z3F6YXZ6aW92enBvaHlhdWJ1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzM3OTg3NSwiZXhwIjoyMTAyOTU1ODc1fQ.0Sz_E_m1hG1lgCEi-VW2vnyKwM0X9BROEjfl4nSJmxc"   # service_role key, dari Project Settings -> API
python3 create_dummy_operators.py

PASSWORD FIXED (bukan random): picker1, picker2, ..., picker7, sesuai urutan
di OPERATORS (Operator 1 = picker1, dst -- BUKAN picker_id di DB, itu SERIAL
dan bisa beda) -- gampang diinget/didiktekan buat testing/demo. JANGAN dipakai
di project yang beneran production dengan data asli -- ganti ke password
digenerate random (mis. secrets.token_urlsafe(9)) atau setup ulang akunnya
kalau sudah mau go-live.
"""
import os

from supabase import create_client
from supabase_auth.errors import AuthApiError

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]

# TIDAK ada picker_id hardcoded di sini SENGAJA -- picker_id itu SERIAL,
# nilainya bisa berubah tiap schema.sql di-re-run (lihat bug duplicate
# picker yang udah di-fix). Match ke pickers lewat "name" (sekarang UNIQUE,
# schema.sql STEP 5) -- stabil terlepas dari picker_id berapa pun.
OPERATORS = [
    {"name": "Operator 1", "email": "operator1@nexwave.local"},
    {"name": "Operator 2", "email": "operator2@nexwave.local"},
    {"name": "Operator 3", "email": "operator3@nexwave.local"},
    {"name": "Operator 4", "email": "operator4@nexwave.local"},
    {"name": "Operator 5", "email": "operator5@nexwave.local"},
    {"name": "Operator 6", "email": "operator6@nexwave.local"},
    {"name": "Operator 7", "email": "operator7@nexwave.local"},
]


def get_or_create_user(supabase, email: str, password: str, full_name: str):
    """
    Kalau email belum ada di auth.users: bikin baru. Kalau sudah ada (mis. sisa
    run sebelumnya, apalagi kalau public.users/pickers baru di-drop+recreate
    tapi auth.users TIDAK ikut ke-drop -- itu tabel Supabase, bukan punya kita):
    reset password-nya ke yang baru, jangan gagal. Return (user_id, "created"|"updated").
    """
    try:
        resp = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,  # skip verifikasi email -- akun dummy, bukan email beneran
            "user_metadata": {"full_name": full_name},
        })
        return resp.user.id, "created"
    except AuthApiError as e:
        if "already been registered" not in str(e):
            raise
        existing = next(
            (u for u in supabase.auth.admin.list_users() if u.email == email), None
        )
        if existing is None:
            raise  # kepesan "already registered" tapi nggak ketemu di list -- aneh, jangan ditelan
        supabase.auth.admin.update_user_by_id(existing.id, {"password": password})
        return existing.id, "updated"


def main():
    supabase = create_client(SUPABASE_URL, SERVICE_KEY)
    results = []

    for idx, op in enumerate(OPERATORS, start=1):
        password = f"picker{idx}"  # picker1..picker7 -- fixed, dari posisi di list, bukan picker_id DB

        user_id, action = get_or_create_user(supabase, op["email"], password, op["name"])

        # Trigger di schema.sql (handle_new_user) sudah otomatis bikin baris
        # public.users (role default 'operator') begitu auth.users kena INSERT --
        # tapi kalau tadi "updated" (bukan "created"), auth.users nggak ke-INSERT
        # ulang, jadi trigger nggak jalan lagi. Kalau public.users baru di-drop+
        # recreate (skenario schema baru), baris public.users buat akun lama ini
        # HILANG dan nggak otomatis balik -- upsert manual di sini.
        supabase.table("users").upsert(
            {"id": user_id, "role": "operator", "full_name": op["name"], "email": op["email"]},
            on_conflict="id",
        ).execute()

        # Match lewat "name" (UNIQUE, schema.sql STEP 5) -- BUKAN picker_id
        # hardcoded. picker_id itu SERIAL, nilainya nggak stabil tiap
        # schema.sql di-re-run (root cause bug picker duplicate/auth ke-miss
        # sebelumnya) -- name selalu bener terlepas dari picker_id berapa.
        result = supabase.table("pickers").update(
            {"auth_user_id": user_id}
        ).eq("name", op["name"]).execute()
        if not result.data:
            print(f"  !! WARNING: nggak ada baris pickers dengan name='{op['name']}' -- cek schema.sql STEP 5 sudah dijalankan?")

        results.append((op["name"], op["email"], password))
        print(f"  {op['name']:12s}  {op['email']}  -> user_id={user_id}  ({action})")

    print("\n=== Kredensial (password fixed pickerN, sama tiap dijalankan) ===")
    for name, email, password in results:
        print(f"  {name:12s}  {email:30s}  password: {password}")


if __name__ == "__main__":
    main()

# /opt/homebrew/Caskroom/miniconda/base/bin/python3 create_dummy_operators.py