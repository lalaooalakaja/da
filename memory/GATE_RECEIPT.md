# 🧾 GATE RECEIPT — CV. Dewi Aditya ERP

> Dihasilkan `scripts/gate.sh`. JANGAN edit manual.
> "Selesai" hanya sah bila receipt HIJAU untuk cakupan yang TIDAK di-skip.

- **Waktu:** 2026-08-07 09:30:56  ·  **Durasi:** 43s  ·  **Mode:** cepat
- **Backend:** RUNNING · **Auth:** READY

| Gate | Hasil |
|------|-------|
| UANG/DATA — invarian GL, stok, AR/AP (verify_data_integrity) | PASS |
| UANG — baseline valuasi aksesoris (SSOT acc_baseline) | PASS |
| UANG — state machine jurnal (draft→posted→voided) | PASS |
| UANG — nomor dokumen tak boleh kembar saat balapan (RC-5) | PASS |
| UANG — batas nilai AR/AP/maklon (round6) | PASS |
| KEAMANAN — akses lintas-role & tanpa token (RBAC/IDOR) | PASS |
| KETAHANAN — input jahat harus 4xx, bukan 500 | PASS |
| BISA DIPAKAI — endpoint kritis terjangkau | PASS |
| ALUR — produksi/maklon/CMT: reject, rework, stok FG, SJ gabungan | PASS |
| FITUR MATI — handler tergabung / kode setelah return | PASS |
| FITUR MATI — panggilan FE ke endpoint yang tak ada | PASS |
| NAVIGASI — menu hantu / duplikat / kedalaman | PASS |
| SERAH-TERIMA — mesin lint platform hidup (import validation + oxlint) | PASS |

## ✅ VERDICT: HIJAU — boleh lanjut / klaim selesai (untuk cakupan non-skip).

_SKIP bukan PASS. Jalankan ulang saat backend + auth hidup._
