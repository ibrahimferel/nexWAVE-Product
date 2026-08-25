"""
Isi tabel product_catalog dengan semua product_ref yang BENERAN ada
embedding-nya di prod_emb.pkl (198 produk) -- dijalankan SEKALI oleh admin,
setelah schema.sql (STEP 8) di-apply. Frontend baca tabel ini buat generate
order dummy yang realistis (Opsi B, generate-orders = INSERT langsung ke
Supabase, lihat frontend_auth.md) -- product_ref asal-asalan yang nggak ada
di GNN embedding bakal fallback ke zero-vector di batching agent, bukan
actually exercise embedding-nya.

Jalankan:
pip install supabase
export SUPABASE_URL="https://bxgqzavziovzpohyaubu.supabase.co"
export SUPABASE_SERVICE_KEY="..."   # service_role key, dari Project Settings -> API
python3 seed_product_catalog.py

Aman dijalankan berkali-kali -- upsert on_conflict product_ref, bukan insert
polos (nggak bakal duplicate error kalau dijalankan ulang).
"""
import os
import pickle

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]
EMB_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prod_emb.pkl")


def main():
    with open(EMB_PATH, "rb") as f:
        emb = pickle.load(f)
    product_refs = sorted(emb.keys())
    print(f"prod_emb.pkl: {len(product_refs)} product_ref")

    supabase = create_client(SUPABASE_URL, SERVICE_KEY)
    rows = [{"product_ref": ref} for ref in product_refs]

    supabase.table("product_catalog").upsert(rows, on_conflict="product_ref").execute()
    print(f"product_catalog: {len(rows)} baris ter-upsert")


if __name__ == "__main__":
    main()

# /opt/homebrew/Caskroom/miniconda/base/bin/python3 seed_product_catalog.py

# export SUPABASE_URL="https://bxgqzavziovzpohyaubu.supabase.co"
# export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ4Z3F6YXZ6aW92enBvaHlhdWJ1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzM3OTg3NSwiZXhwIjoyMTAyOTU1ODc1fQ.0Sz_E_m1hG1lgCEi-VW2vnyKwM0X9BROEjfl4nSJmxc"
