#!/usr/bin/env bash
###############################################################################
# gate.sh — SATU perintah verifikasi. CV. Dewi Aditya ERP.
#
#   bash scripts/gate.sh          # cepat (statik + runtime inti)   ~60 detik
#   bash scripts/gate.sh --full    # + alur produk HR (absen/cuti/payslip)
#
# ─────────────────────────────────────────────────────────────────────────────
# FASE 21 — KENAPA GATE INI JAUH LEBIH KECIL DARIPADA SEBELUMNYA
# ─────────────────────────────────────────────────────────────────────────────
# Sebelumnya: 12 gate + 54 skrip alat (~16.000 baris). Akibat nyatanya:
#   · run_all_verifications.sh butuh >20 menit (12 skrip + jeda 25 detik/skrip)
#   · penjaganya sendiri jadi sumber bug: `_seg_match` simetris menyembunyikan
#     48 temuan · `fe_calls()` membaca komentar → merah palsu ·
#     `audit_duplication.py` membaca DOCSTRING sebagai penulis DB ·
#     `verify_phase_g_acc_opname.py` membocorkan stok + jurnal GL yatim ·
#     `cleanup_*_qa.py` mencocokkan teks penanda ⇒ selalu satu alat di belakang
#   · ada penjaga yang menjaga penjaga (`INV-META-01`) dan polisi "kualitas AI"
#     (`INV-QUALITY-01`) — nol nilainya bagi pengguna aplikasi
#
# 52 skrip (13.327 baris) DIHAPUS. Kriteria yang dipakai — hanya SATU pertanyaan:
#   "Kalau pemeriksaan ini hilang, apakah UANG, DATA, KEAMANAN, atau ALUR
#    PRODUK bisa rusak tanpa ada yang tahu?"
# Kalau tidak → dibuang. Pemeriksaan gaya kode, meta, dan audit duplikat tidak
# lolos kriteria itu.
###############################################################################
set -uo pipefail
CYAN='\033[96m'; GREEN='\033[92m'; RED='\033[91m'; YEL='\033[93m'; BOLD='\033[1m'; RST='\033[0m'
cd "$(dirname "$0")/.." || exit 1
RECEIPT="memory/GATE_RECEIPT.md"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
FULL=0
for a in "$@"; do [ "$a" = "--full" ] && FULL=1; done
declare -a NAMES RESULTS
OVERALL=0
START=$(date +%s)

run_gate () {  # $1=label  $2=perintah
  local label="$1"; shift
  local t0=$(date +%s)
  echo -e "\n${CYAN}${BOLD}▶ ${label}${RST}"
  bash -c "$*"
  local rc=$? t1=$(date +%s)
  if [ $rc -eq 0 ]; then
    echo -e "  ${GREEN}✓ ${label} PASS ($((t1-t0))s)${RST}"; NAMES+=("$label"); RESULTS+=("PASS")
  else
    echo -e "  ${RED}✗ ${label} FAIL (rc=$rc, $((t1-t0))s)${RST}"; NAMES+=("$label"); RESULTS+=("FAIL"); OVERALL=1
  fi
}
skip_gate () { echo -e "\n${YEL}▶ $1 — SKIP ($2)${RST}"; NAMES+=("$1"); RESULTS+=("SKIP"); }

echo -e "${CYAN}${BOLD}\n=============================================================="
echo "  GATE — CV. Dewi Aditya — $TS$([ $FULL -eq 1 ] && echo '  (--full)')"
echo -e "==============================================================${RST}"

# --- deteksi kesiapan backend + auth --------------------------------------
BACKEND_UP=0; AUTH_READY=0
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health 2>/dev/null | grep -qE "^[2-4]"; then
  BACKEND_UP=1; echo -e "${GREEN}  Backend RUNNING${RST}"
  ACODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/auth/login \
          -H "Content-Type: application/json" \
          -d '{"email":"admin@garment.com","password":"Admin@123"}' 2>/dev/null)
  [ "$ACODE" = "200" ] && { AUTH_READY=1; echo -e "${GREEN}  Admin login OK${RST}"; } \
                       || echo -e "${YEL}  Admin login HTTP $ACODE — gate runtime di-SKIP${RST}"
else
  echo -e "${YEL}  Backend down — gate runtime di-SKIP${RST}"
fi

# ══ 1. UANG & DATA (yang paling mahal kalau salah) ═══════════════════════════
run_gate "UANG/DATA — invarian GL, stok, AR/AP (verify_data_integrity)" \
         "python3 scripts/verify_data_integrity.py"
run_gate "UANG — baseline valuasi aksesoris (SSOT acc_baseline)" \
         "python3 scripts/lib/acc_baseline.py >/dev/null"

if [ $AUTH_READY -eq 1 ]; then
  run_gate "UANG — state machine jurnal (draft→posted→voided)" \
           "python3 scripts/verify_state_machine.py"
  run_gate "UANG — nomor dokumen tak boleh kembar saat balapan (RC-5)" \
           "python3 scripts/verify_concurrency.py"
  run_gate "UANG — batas nilai AR/AP/maklon (round6)" \
           "python3 scripts/round6_verify.py"
  # ══ 2. KEAMANAN ═══════════════════════════════════════════════════════════
  run_gate "KEAMANAN — akses lintas-role & tanpa token (RBAC/IDOR)" \
           "python3 scripts/guardrails/verify_rbac_idor.py"
  run_gate "KETAHANAN — input jahat harus 4xx, bukan 500" \
           "python3 scripts/guardrails/verify_adversarial_5xx.py"
  # ══ 3. BISA DIPAKAI ═══════════════════════════════════════════════════════
  run_gate "BISA DIPAKAI — endpoint kritis terjangkau" \
           "python3 scripts/health_check.py"
  # ══ ALUR PRODUK: PRODUKSI · MAKLON · CMT (audit 2026-07-31) ════════════════
  # Menjaga 12 invarian yang cacatnya TERBUKTI merusak angka lintas portal:
  # reject hilang, produced berkurang karena reject, stok FG di luar SSOT,
  # permak tidak berefek, SJ gabungan tak bisa dibaca. Lihat
  # docs/AUDIT_PRODUKSI_MAKLON_CMT.md — jangan hapus gate ini.
  run_gate "ALUR — produksi/maklon/CMT: reject, rework, stok FG, SJ gabungan" \
           "python3 scripts/verify_produksi_maklon_invariants.py"
else
  for g in "state machine jurnal" "nomor dokumen kembar" "batas nilai AR/AP" \
           "RBAC/IDOR" "input jahat 4xx" "endpoint kritis" \
           "alur produksi/maklon/CMT"; do
    skip_gate "$g" "backend/auth belum siap"
  done
fi

# ══ 4. FITUR MATI DIAM-DIAM (statik, murah, terbukti menemukan bug produk) ═══
# Dua ini DIPERTAHANKAN karena rekam jejaknya nyata: `unreachable_code`
# menemukan handler export CSV payroll yang kehilangan dekorator (fitur mati),
# dan `fe_be_contract` menemukan 8 panggilan FE yang 404 senyap.
run_gate "FITUR MATI — handler tergabung / kode setelah return" \
         "python3 scripts/guardrails/verify_unreachable_code.py"
run_gate "FITUR MATI — panggilan FE ke endpoint yang tak ada" \
         "python3 scripts/preflight/verify_fe_be_contract.py --report-only"
run_gate "NAVIGASI — menu hantu / duplikat / kedalaman" \
         "python3 scripts/guardrails/check_nav_map.py"

# ══ 5. SESI BISA DISERAHKAN (gate lint platform harus hidup) ═════════════════
run_gate "SERAH-TERIMA — mesin lint platform hidup (import validation + oxlint)" \
         "python3 scripts/guardrails/verify_platform_lint_engine.py --quiet"

# ══ 6. ALUR PRODUK HR (hanya dengan --full; butuh backend) ═══════════════════
if [ $FULL -eq 1 ]; then
  if [ $AUTH_READY -eq 1 ]; then
    run_gate "PRODUK — absen (selfie+geofence wajib)" "python3 scripts/verify_fase16_absen.py"
    sleep 10
    run_gate "PRODUK — cuti" "python3 scripts/verify_fase17_cuti.py"
    sleep 10
    run_gate "PRODUK — payslip karyawan" "python3 scripts/verify_fase18_payslip.py"
    sleep 10
    run_gate "PRODUK — alur lembur live (HRIS)" "python3 scripts/bughunt_hris_flow.py"
  else
    skip_gate "alur produk HR" "backend/auth belum siap"
  fi
fi

# ══ RECEIPT ══════════════════════════════════════════════════════════════════
ELAPSED=$(( $(date +%s) - START ))
{
  echo "# 🧾 GATE RECEIPT — CV. Dewi Aditya ERP"
  echo
  echo "> Dihasilkan \`scripts/gate.sh\`. JANGAN edit manual."
  echo "> \"Selesai\" hanya sah bila receipt HIJAU untuk cakupan yang TIDAK di-skip."
  echo
  echo "- **Waktu:** $TS  ·  **Durasi:** ${ELAPSED}s  ·  **Mode:** $([ $FULL -eq 1 ] && echo 'full' || echo 'cepat')"
  echo "- **Backend:** $([ $BACKEND_UP -eq 1 ] && echo RUNNING || echo DOWN) · **Auth:** $([ $AUTH_READY -eq 1 ] && echo READY || echo 'NOT READY')"
  echo
  echo "| Gate | Hasil |"
  echo "|------|-------|"
  for i in "${!NAMES[@]}"; do echo "| ${NAMES[$i]} | ${RESULTS[$i]} |"; done
  echo
  if [ $OVERALL -eq 0 ]; then
    echo "## ✅ VERDICT: HIJAU — boleh lanjut / klaim selesai (untuk cakupan non-skip)."
  else
    echo "## ❌ VERDICT: MERAH — ada gate gagal. JANGAN klaim selesai."
  fi
  echo
  echo "_SKIP bukan PASS. Jalankan ulang saat backend + auth hidup._"
} > "$RECEIPT"

echo -e "\n${CYAN}${BOLD}==============================================================${RST}"
for i in "${!NAMES[@]}"; do
  case "${RESULTS[$i]}" in
    PASS) echo -e "  ${GREEN}PASS${RST}  ${NAMES[$i]}" ;;
    FAIL) echo -e "  ${RED}FAIL${RST}  ${NAMES[$i]}" ;;
    *)    echo -e "  ${YEL}SKIP${RST}  ${NAMES[$i]}" ;;
  esac
done
echo -e "  ${BOLD}durasi ${ELAPSED}s · receipt: $RECEIPT${RST}"
[ $OVERALL -eq 0 ] && echo -e "  ${GREEN}${BOLD}VERDICT: HIJAU${RST}" || echo -e "  ${RED}${BOLD}VERDICT: MERAH${RST}"
exit $OVERALL
