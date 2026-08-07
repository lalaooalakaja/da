#!/usr/bin/env bash
# =============================================================================
# DA37 ERP — FAST BOOTSTRAP (idempotent + parallel)
# Tujuan: setup /app dari 0 → siap-jalan secepat mungkin.
#   env (.env) -> deps (pip+yarn PARALEL, di-cache) -> restart -> health -> seed -> verify
#
# Pakai (dari dalam repo yang sudah tersalin ke /app):
#   EMERGENT_LLM_KEY=sk-emergent-xxxx bash /app/scripts/bootstrap.sh
#
# Flags:
#   --reseed        paksa seed ulang walau data sudah ada
#   --force-deps    paksa install deps walau hash tak berubah
#   --skip-deps     lewati install deps (tercepat, jika yakin sudah siap)
#   --skip-seed     lewati seeding
#
# CATATAN: TIDAK PERNAH menimpa MONGO_URL / REACT_APP_BACKEND_URL.
# =============================================================================
set -uo pipefail
START=$(date +%s)
APP=/app
BE=$APP/backend
FE=$APP/frontend
CACHE=$APP/.bootstrap_cache
mkdir -p "$CACHE"

RESEED=0; FORCE_DEPS=0; SKIP_DEPS=0; SKIP_SEED=0
for a in "$@"; do case "$a" in
  --reseed) RESEED=1;; --force-deps) FORCE_DEPS=1;; --skip-deps) SKIP_DEPS=1;; --skip-seed) SKIP_SEED=1;;
esac; done

c(){ printf "\033[1;36m[bootstrap]\033[0m %s\n" "$*"; }
ok(){ printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
err(){ printf "\033[1;31m  ✗ %s\033[0m\n" "$*"; }

# --- 0. sanity ---------------------------------------------------------------
[ -f "$BE/server.py" ] || { err "$BE/server.py tak ada — repo belum tersalin ke /app. Lihat AGENT_QUICKSTART.md."; exit 1; }
[ -f "$BE/requirements.txt" ] || { err "requirements.txt tak ada"; exit 1; }

# --- 1. ENV (idempoten, tak menimpa URL kritis) -----------------------------
c "1/6 Menyiapkan backend/.env"
touch "$BE/.env"
# pastikan setiap baris diakhiri newline (hindari bug baris nyambung)
[ -n "$(tail -c1 "$BE/.env")" ] && echo >> "$BE/.env"
ensure_env(){ # ensure_env KEY DEFAULTVALUE  (hanya menambah jika belum ada)
  local k="$1" v="$2"
  if ! grep -q "^${k}=" "$BE/.env"; then echo "${k}=\"${v}\"" >> "$BE/.env"; ok "set ${k}"; fi
}
grep -q "^MONGO_URL=" "$BE/.env" || echo 'MONGO_URL="mongodb://localhost:27017"' >> "$BE/.env"
ensure_env DB_NAME "test_database"
ensure_env CORS_ORIGINS "*"
# JWT_SECRET: generate jika belum ada
if ! grep -q "^JWT_SECRET=" "$BE/.env"; then
  JWT=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
  echo "JWT_SECRET=\"$JWT\"" >> "$BE/.env"; ok "generate JWT_SECRET"
fi
# EMERGENT_LLM_KEY: dari env var jika diberikan, else pertahankan yang ada
if [ -n "${EMERGENT_LLM_KEY:-}" ]; then
  if grep -q "^EMERGENT_LLM_KEY=" "$BE/.env"; then
    python3 - "$BE/.env" "$EMERGENT_LLM_KEY" <<'PY'
import sys,re
p,k=sys.argv[1],sys.argv[2]
s=open(p).read()
s=re.sub(r'^EMERGENT_LLM_KEY=.*$', f'EMERGENT_LLM_KEY="{k}"', s, flags=re.M)
open(p,'w').write(s)
PY
  else echo "EMERGENT_LLM_KEY=\"$EMERGENT_LLM_KEY\"" >> "$BE/.env"; fi
  ok "set EMERGENT_LLM_KEY (dari argumen)"
elif ! grep -q "^EMERGENT_LLM_KEY=" "$BE/.env"; then
  echo 'EMERGENT_LLM_KEY=""' >> "$BE/.env"
  warn "EMERGENT_LLM_KEY kosong — fitur AI/LLM tak jalan. Jalankan ulang: EMERGENT_LLM_KEY=sk-... bash $0"
fi
# frontend/.env: JANGAN diubah nilai kritisnya, hanya cek + tambah flag build
[ -f "$FE/.env" ] && grep -q "^REACT_APP_BACKEND_URL=" "$FE/.env" && ok "frontend/.env REACT_APP_BACKEND_URL ada" || warn "frontend/.env REACT_APP_BACKEND_URL tak ditemukan (biarkan platform yang set)"
# FASE 14 — `frontend/.env` di-gitignore, jadi clone segar KEHILANGAN dua flag
# yang WAJIB ada supaya `yarn build` selesai di container 1 core / 2 GB
# (lihat memory/PREVIEW_STABLE_MODE.md). Tanpa ini build bisa OOM / lama sekali.
if [ -f "$FE/.env" ]; then
  [ -n "$(tail -c1 "$FE/.env")" ] && echo >> "$FE/.env"
  grep -q "^GENERATE_SOURCEMAP=" "$FE/.env"    || { echo 'GENERATE_SOURCEMAP=false' >> "$FE/.env"; ok "set GENERATE_SOURCEMAP=false"; }
  grep -q "^DISABLE_ESLINT_PLUGIN=" "$FE/.env" || { echo 'DISABLE_ESLINT_PLUGIN=true' >> "$FE/.env"; ok "set DISABLE_ESLINT_PLUGIN=true"; }
fi

# --- 1b. RESOLUSI LINT DI ROOT REPO (anti "linter engine error") -------------
# `/app` tidak punya node_modules, sementara lint dijalankan DARI `/app` dengan
# `--format unix` ⇒ formatter global tak ter-resolve ⇒ rc=2 (ENGINE ERROR),
# bukan temuan lint. Detail lengkap: scripts/fix_root_lint_resolution.sh
c "1b/6 Resolusi lint root repo"
bash "$APP/scripts/fix_root_lint_resolution.sh" 2>&1 | sed 's/^/  /'

# --- 1c. SANITY LINGKUNGAN: mongod & deps benar-benar ADA -------------------
# Dua jebakan NYATA yang memakan waktu di container segar (2026-07-31):
#   1. `mongodb` berstatus STOPPED → backend hidup tapi /api/health gagal connect.
#   2. Marker cache `.bootstrap_cache/be.md5` IKUT TERSALIN dari repo, jadi
#      "backend deps sudah sesuai hash — skip" padahal container ini belum
#      pernah `pip install` (gejala: ModuleNotFoundError: openpyxl saat start).
c "1c/6 Sanity: mongod hidup + deps backend benar-benar terpasang"
if ! sudo supervisorctl status mongodb 2>/dev/null | grep -q RUNNING; then
  sudo supervisorctl start mongodb >/dev/null 2>&1 && ok "mongodb dijalankan" || warn "mongodb tidak bisa dijalankan"
else
  ok "mongodb RUNNING"
fi
# 1c-2. LIMIT FILE DESCRIPTOR MONGOD (temuan 2026-07-31)
# supervisord menjalankan mongod dengan soft limit nofile 1024 → backup/restore DB
# besar kena "Too many open files" → WT_PANIC → mongod ABORT → restore PUTUS dan
# portal Administrasi Sistem balas HTTP 500. Config supervisor READ-ONLY, jadi
# dinaikkan runtime. Backend juga menjaganya otomatis (startup + tiap 5 menit).
bash "$APP/scripts/ensure_mongod_fdlimit.sh" 2>&1 | sed 's/^/  /' || warn "gagal menaikkan limit file mongod"
if ! python3 - <<'PY' >/dev/null 2>&1
import importlib
for m in ("fastapi", "motor", "openpyxl", "reportlab", "apscheduler"):
    importlib.import_module(m)
PY
then
  warn "deps backend belum lengkap → marker cache dibuang, pip install dipaksa"
  rm -f "$CACHE/be.md5"
else
  ok "deps backend terpasang (probe import)"
fi

# --- 2. DEPS (paralel + cache via hash) -------------------------------------
c "2/6 Install deps (backend+frontend PARALEL, cache by-hash)"
BE_PID=""; FE_PID=""
if [ "$SKIP_DEPS" = "1" ]; then warn "lewati deps (--skip-deps)"; else
  # backend
  BE_HASH=$(md5sum "$BE/requirements.txt" | awk '{print $1}')
  if [ "$FORCE_DEPS" = "0" ] && [ -f "$CACHE/be.md5" ] && [ "$(cat "$CACHE/be.md5")" = "$BE_HASH" ]; then
    ok "backend deps sudah sesuai hash — skip"
  else
    ( pip install -q -r "$BE/requirements.txt" >"$CACHE/pip.log" 2>&1 && echo "$BE_HASH" > "$CACHE/be.md5" ) & BE_PID=$!
    c "  → pip install jalan di background (PID $BE_PID)"
  fi
  # frontend
  FE_HASH=$(cat "$FE/package.json" "$FE/yarn.lock" 2>/dev/null | md5sum | awk '{print $1}')
  if [ "$FORCE_DEPS" = "0" ] && [ -d "$FE/node_modules" ] && [ -f "$CACHE/fe.md5" ] && [ "$(cat "$CACHE/fe.md5")" = "$FE_HASH" ]; then
    ok "frontend deps sudah sesuai hash — skip"
  else
    # FASE 11 — AKAR MASALAH YANG SUDAH 3 SESI BERULANG:
    # `--frozen-lockfile` GAGAL TOTAL bila `frontend/yarn.lock` tidak ada di repo
    # (dan dulu memang tidak ter-commit), atau bila lockfile-nya tertinggal dari
    # package.json — gejalanya `@simplewebauthn/browser` tidak terpasang lalu
    # `yarn build` gagal. Sekarang: pakai frozen HANYA kalau lockfile-nya ada,
    # dan kalau gagal jatuh otomatis ke `yarn install` biasa (yang akan
    # membuat/memperbarui lockfile) — bukan menggantung dengan error.
    (
      cd "$FE" || exit 1
      if [ -f yarn.lock ]; then
        yarn install --frozen-lockfile --prefer-offline >"$CACHE/yarn.log" 2>&1 \
          || { echo "[bootstrap] frozen-lockfile gagal → fallback yarn install biasa" >>"$CACHE/yarn.log"
               yarn install --prefer-offline --network-timeout 600000 >>"$CACHE/yarn.log" 2>&1; }
      else
        echo "[bootstrap] yarn.lock tidak ada → yarn install biasa (lockfile akan dibuat)" >"$CACHE/yarn.log"
        yarn install --prefer-offline --network-timeout 600000 >>"$CACHE/yarn.log" 2>&1
      fi
    ) && echo "$FE_HASH" > "$CACHE/fe.md5" & FE_PID=$!
    c "  → yarn install jalan di background (PID $FE_PID)"
  fi
  [ -n "$BE_PID" ] && { wait "$BE_PID" && ok "pip install selesai" || { err "pip install GAGAL — lihat $CACHE/pip.log"; tail -15 "$CACHE/pip.log"; }; }
  [ -n "$FE_PID" ] && { wait "$FE_PID" && ok "yarn install selesai" || { err "yarn install GAGAL — lihat $CACHE/yarn.log"; tail -15 "$CACHE/yarn.log"; }; }
fi

# --- 2b. BUILD FRONTEND STATIC BUNDLE (stable-mode) -------------------------
# This container serves a PREBUILT static bundle via static_server.js (NOT the
# CRA dev server). A fresh clone has no build/, so we build it here. Safe:
# low priority (nice -n 19) + capped Node heap (1024MB via package.json build
# script) so the backend keeps answering the health probe and we stay under the
# 2GB cgroup cap. See /app/memory/PREVIEW_STABLE_MODE.md
c "2b/6 Frontend static bundle (stable-mode)"
if [ -f "$FE/build/index.html" ] && [ "$FORCE_DEPS" = "0" ]; then
  ok "build/ sudah ada — skip (setelah ubah src: bash /app/scripts/rebuild_frontend.sh)"
else
  c "  → yarn build (nice -n 19; beberapa menit di 1 core, heap 1024MB)"
  if ( cd "$FE" && nice -n 19 yarn build >"$CACHE/fe_build.log" 2>&1 ); then
    ok "frontend build OK"
  else
    err "frontend build GAGAL — lihat $CACHE/fe_build.log"; tail -20 "$CACHE/fe_build.log"
  fi
fi


# --- 3. RESTART SERVICES -----------------------------------------------------
c "3/6 Restart services (backend+frontend)"
sudo supervisorctl restart backend frontend >/dev/null 2>&1
ok "restart dikirim"

# --- 4. TUNGGU HEALTH --------------------------------------------------------
c "4/6 Menunggu backend health"
HEALTHY=0
for i in $(seq 1 40); do
  if curl -sf http://localhost:8001/api/health >/dev/null 2>&1; then HEALTHY=1; ok "backend healthy ($((i*2))s)"; break; fi
  sleep 2
done
[ "$HEALTHY" = "1" ] || { err "backend TIDAK healthy dalam 80s — cek: tail -50 /var/log/supervisor/backend.err.log"; }

# --- 5. LOGIN admin + SEED (idempoten) --------------------------------------
c "5/6 Login admin + seed"
TOKEN=""
if [ "$HEALTHY" = "1" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
    -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
fi
if [ -z "$TOKEN" ]; then
  warn "login admin gagal (mungkin belum ada user). Menjalankan seed untuk membuat akun..."
fi
NEED_SEED=1
if [ "$SKIP_SEED" = "1" ]; then NEED_SEED=0; warn "lewati seed (--skip-seed)"; fi
if [ "$NEED_SEED" = "1" ] && [ "$RESEED" = "0" ] && [ -n "$TOKEN" ]; then
  EMP=$(curl -s "http://localhost:8001/api/rahaza/employees" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('total',len(d)) if isinstance(d,dict) else len(d))" 2>/dev/null || echo 0)
  if [ "${EMP:-0}" -gt 0 ] 2>/dev/null; then NEED_SEED=0; ok "data sudah ter-seed (employees=$EMP) — skip (pakai --reseed utk paksa)"; fi
fi
if [ "$NEED_SEED" = "1" ] && [ "$HEALTHY" = "1" ]; then
  # jika belum ada token (user belum ada), coba seed tanpa auth dulu—kebanyakan seed butuh admin,
  # jadi kita andalkan default admin sudah dibuat saat startup; login lagi setelah delay singkat.
  [ -z "$TOKEN" ] && sleep 2 && TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
  if [ -n "$TOKEN" ]; then
    seed_ep(){
      local path="$1"
      local code
      code=$(curl -s -m 180 -o /tmp/seed_resp.json -w "%{http_code}" -X POST "http://localhost:8001${path}" -H "Authorization: Bearer $TOKEN")
      if [ "$code" = "200" ] || [ "$code" = "201" ]; then
        ok "seed ${path} OK"
      else
        err "seed ${path} gagal (HTTP ${code}): $(head -c 200 /tmp/seed_resp.json 2>/dev/null)"
      fi
    }
    c "  → seed master + demo (produksi, HR, maklon, marketing, phase 2-3-5)"
    seed_ep /api/rahaza/setup/seed-sample
    seed_ep /api/rahaza/hr-seed/run
    seed_ep /api/seed/maklon-full
    seed_ep /api/marketing/seed-sample-data
    seed_ep /api/dewi/seed-demo-full
    c "  → seed akun 5 role (hr/finance/spv/gudang/maklon @dewiaditya.id)"
    if python3 /app/backend/scripts/seed_role_accounts.py >/dev/null 2>&1; then ok "role accounts OK"; else warn "seed_role_accounts gagal (jalankan manual)"; fi
    # ACC-2 — jaring pengaman kopling BOM ↔ master material. Seeder BARU sudah
    # menautkan baris BOM sejak awal, tapi DB yang lahir dari seeder LAMA masih
    # menyimpan baris `material_id: null` (rantai BOM → kebutuhan aksesoris PO →
    # stok putus). Skrip ini idempoten: buat master yang belum ada + tautkan
    # baris yang kodenya cocok. Cek hasilnya di UI: banner kesehatan BOM.
    c "  → tautkan BOM demo ke master material (ACC-2 link-health)"
    if (cd /app/backend && python3 scripts/link_demo_bom_materials.py >/tmp/link_bom.log 2>&1); then
      ok "link BOM demo OK ($(grep -c 'linked' /tmp/link_bom.log >/dev/null 2>&1; grep 'BOM lines linked' /tmp/link_bom.log | head -1))"
    else
      warn "link_demo_bom_materials gagal (lihat /tmp/link_bom.log)"
    fi
    # FASE 12 — BASELINE VALUASI AKSESORIS (temuan verifikasi 2026-07-26).
    # `verify_fase10_digest_report.py` mengasumsikan baseline demo aksesoris ADA
    # (10 item, 2 di antaranya sengaja ber-HPP 0 supaya alarm & digest punya isi).
    # Karena bootstrap TIDAK pernah menjalankan seeder ini, DB hasil bootstrap
    # segar selalu memberi 8 FAIL PALSU (digest 0 item) dan bikin agent berikutnya
    # mengira ada regresi. Seeder idempoten (`--cleanup` untuk membersihkan).
    c "  → baseline valuasi aksesoris (10 item, 8 bernilai / 2 belum dinilai)"
    if (cd /app && python3 scripts/seed_acc_valuation_baseline.py >/tmp/seed_acc_val.log 2>&1); then
      ok "baseline valuasi aksesoris OK ($(grep 'nilai persediaan' /tmp/seed_acc_val.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_acc_valuation_baseline gagal (lihat /tmp/seed_acc_val.log)"
    fi
    # 2026-08-07 — MASTER SUPPLIER. Bootstrap tidak pernah menyeed ini, sehingga
    # environment segar selalu punya `rahaza_suppliers` = 0 dan tiga layar Portal
    # Pengadaan (Master Supplier, Penilaian Supplier, Analisis Belanja) tampil
    # kosong. Lebih parah: alur "PR disetujui → Buat Purchase Order" MENTOK di UI
    # karena dialog PO mewajibkan supplier dipilih dari master. Seeder idempoten
    # (`--cleanup` untuk membuang). Hanya master + daftar harga: tidak menyentuh
    # stok/jurnal, jadi baseline gate tidak berubah.
    c "  → master supplier demo + daftar harga (Portal Pengadaan)"
    if (cd /app && python3 scripts/seed_procurement_suppliers_demo.py >/tmp/seed_suppliers.log 2>&1); then
      ok "master supplier OK ($(grep 'SELESAI' /tmp/seed_suppliers.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_procurement_suppliers_demo gagal (lihat /tmp/seed_suppliers.log)"
    fi
    # 2026-08-07 (sesi lanjutan) — DATA DEMO RANTAI PERSETUJUAN.
    # Bootstrap segar meninggalkan `dewi_procurement_requests` = 0 DAN
    # `acc_purchase_requests` = 0, sehingga tiga layar inti Portal Pengadaan
    # (Permintaan Pengadaan, Request Pembelian Aksesoris, Dashboard Pengadaan)
    # tampak RUSAK padahal hanya kosong — dan rantai persetujuan dept → keuangan
    # → final tidak bisa dilihat/diuji lewat layar sama sekali. Sesi sebelumnya
    # mengkurasi data ini dengan panggilan manual, jadi hilang tiap DB dibangun
    # ulang. Seeder ini IDEMPOTEN, memakai API sungguhan (jadi jejak audit &
    # notifikasinya asli), dan tidak menyentuh stok/jurnal. `--cleanup` membuang.
    # HARUS setelah master supplier: skenario ke-4 (PR → Purchase Order) memilih
    # supplier dari master.
    c "  → data demo rantai persetujuan (PR pengadaan + PR aksesoris)"
    if (cd /app && python3 scripts/seed_approval_demo.py >/tmp/seed_approval.log 2>&1); then
      ok "data demo persetujuan OK ($(grep -c '✓' /tmp/seed_approval.log) langkah)"
    else
      warn "seed_approval_demo gagal (lihat /tmp/seed_approval.log)"
      tail -5 /tmp/seed_approval.log | sed 's/^/      /'
    fi
  else
    err "tak bisa login admin utk seed — cek backend log"
  fi
fi

# --- 6. VERIFY LOGIN (admin + 5 role) ---------------------------------------
c "6/6 Verifikasi login akun"
if [ "$HEALTHY" = "1" ]; then
  check_login(){ curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d "{\"email\":\"$1\",\"password\":\"$2\"}"; }
  A=$(check_login admin@garment.com Admin@123); printf "    admin@garment.com -> HTTP %s\n" "$A"
  for e in hr finance spv gudang maklon; do
    C=$(check_login "${e}@dewiaditya.id" "Dewi@123"); printf "    %-8s@dewiaditya.id -> HTTP %s\n" "$e" "$C"
  done
fi

# --- FRONTEND static-mode check ---------------------------------------------
if [ -f "$FE/build/index.html" ]; then
  FE_HTTP=$(curl -s -m 8 -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null)
  FE_STATE="static bundle served (HTTP ${FE_HTTP})"
else
  FE_STATE="build/ MISSING — run: bash /app/scripts/rebuild_frontend.sh"
fi

END=$(date +%s)
echo ""
c "SELESAI dalam $((END-START)) detik."
printf "  backend health : %s\n" "$([ "$HEALTHY" = 1 ] && echo OK || echo GAGAL)"
printf "  frontend       : %s\n" "${FE_STATE:-(kompilasi belum selesai; cek lagi ~20s)}"
printf "  preview        : lihat frontend/.env REACT_APP_BACKEND_URL\n"
echo "  Login: admin@garment.com / Admin@123  |  role: {hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123"
