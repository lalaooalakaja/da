> 🚨 **2026-07-31 — DOKUMEN INI SUDAH DILENGKAPI:** untuk alur **selisih kirim CMT→DA** dan
> **selisih terima DA→buyer** (Portal Produksi/Maklon/Vendor CMT), pakai
> **`memory/HANDOFF_SELISIH_CMT_BUYER.md`** — di sana ada hasil uji empiris (angka nyata),
> peta kode `file:line`, 7 gap (A–G), rancangan perbaikan siap eksekusi, dan jebakan environment.
> Jangan menelusuri ulang alur tersebut dari nol.


# ✅ STATUS TERKINI 2026-07-26 (lanjutan #3) — FASE 21: PEMANGKASAN ALAT + 3 BUG NYATA

> **BACA INI DULU — men-supersede SEMUA entri di bawah.**
> ⚠️ **PERINTAH LAMA SUDAH TIDAK ADA.** `scripts/guard.sh` dan
> `scripts/run_all_verifications.sh` **DIHAPUS**. Semua contoh perintah di
> bagian-bagian di bawah (FASE 20 ke belakang) **usang** — 52 skrip yang
> dirujuknya sudah tidak ada.

## Perintah verifikasi sekarang — HANYA SATU
```
bash scripts/gate.sh            # 12 gate, ~37 detik  → memory/GATE_RECEIPT.md
bash scripts/gate.sh --full     # + alur produk HR (absen/cuti/payslip/lembur)
```

## Kenapa dipangkas (keputusan user, dan alasannya benar)
Repo ini punya **12 gate + 54 skrip alat (~16.000 baris)**. Ongkosnya nyata:
`run_all_verifications.sh` butuh **>20 menit**, dan **penjaganya sendiri menjadi
sumber bug** berulang kali:

| Penjaga | Bug di penjaganya |
|---|---|
| `verify_fe_be_contract` | `_seg_match()` simetris ⇒ 48 temuan tersembunyi; `fe_calls()` membaca komentar ⇒ merah palsu |
| `audit_duplication.py` | membaca **DOCSTRING** `saga.py` sebagai penulis DB ⇒ `payroll_runs`/`payslips` dituduh duplikat padahal koleksinya tak ada |
| `verify_phase_g_acc_opname.py` | membocorkan stok + jurnal GL yatim tiap dijalankan |
| `cleanup_*_qa.py` | mencocokkan **teks penanda** ⇒ selalu satu alat di belakang; melaporkan "tidak ada drift" untuk drift yang nyata |
| `bughunt_hris_flow.py` | docstring bilang "cleans up after itself" — **keliru**, `DELETE` hanya meng-*cancel*; 1 lembur fiktif bertanggal **2028-09-01** tertinggal di DB |
| `INV-META-01` | penjaga yang menjaga penjaga — nol nilai bagi pengguna |
| `INV-QUALITY-01` | polisi "kualitas AI" — nol nilai bagi pengguna |

**52 skrip / 13.327 baris DIHAPUS.** Kriterianya satu pertanyaan: *"kalau
pemeriksaan ini hilang, apakah UANG, DATA, KEAMANAN, atau ALUR PRODUK bisa rusak
tanpa ada yang tahu?"* Kalau tidak → dibuang.

**Yang DIPERTAHANKAN (15 skrip):** `verify_data_integrity` · `lib/acc_baseline` ·
`verify_state_machine` · `verify_concurrency` · `round6_verify` ·
`guardrails/verify_rbac_idor` · `guardrails/verify_adversarial_5xx` ·
`health_check` · `guardrails/verify_unreachable_code` ·
`preflight/verify_fe_be_contract` · `guardrails/check_nav_map` ·
`guardrails/verify_platform_lint_engine` · `verify_fase16_absen` ·
`verify_fase17_cuti` · `verify_fase18_payslip` · `bughunt_hris_flow`.

## `_archive/` DIHAPUS TOTAL (90 berkas / 46.672 baris)
`frontend/src/components/erp/_archive/` (48 berkas) dan `backend/routes/_archive/`
(42 berkas). Dibuktikan aman sebelum dihapus: nol import dari kode hidup (semua
rujukan hanya komentar), dan **jumlah route backend tetap 1651 identik** setelah
restart. `yarn build` Compiled successfully.
**Efek samping bagus:** temuan `fe_be_contract` turun **123 → 49** (74 di antaranya
memang cuma kebisingan dari folder arsip).

## 3 BUG NYATA yang ditutup sesi ini
1. **Gate lint platform memblokir penyerahan sesi** (inilah yang membuat FASE 20
   tidak bisa memanggil `finish`). Akarnya BUKAN yang tertulis di dokumen lama.
   Yang benar, dari membaca kode platform:
   `engine_success = oxlint_success AND import_success`, dan yang gagal adalah
   **Import Validation**: 35 import relatif YATIM di `_archive/**` (akibat FASE 20
   memindahkan modul tanpa memperbarui import-nya) + `setupTests.js` mengimpor
   `@testing-library/jest-dom` yang tak ada di `package.json` **dan** tak
   terpasang. Karena semua temuan oxlint tersaring allowlist, `blocking=0`, dan
   kombinasi `blocking==0 AND NOT engine_success` melempar "engine error".
   → 35 import diperbaiki (lalu foldernya dihapus total), 3 devDependency test
   dipasang, dijaga `INV-LINT-01` (bukti-merah **11/11**).
   **⚠️ KOREKSI DOKUMEN:** RCA di FASE 12 (`mobile/eslint.config.js`) dan FASE 14
   (symlink `eslint-formatter-unix`) **KELIRU** — platform memakai `--config` &
   `--format` PATH ABSOLUT, jadi config repo tak pernah dipakai gate. Iterasi
   pertama FASE 21 juga keliru (memperbaiki arm **ESLint**, padahal gate memakai
   arm **oxlint**).
2. **14 fungsi duplikat MATI di modul absen** (306 baris) di 5 berkas
   `rahaza_auto_attendance_*`. **3 di antaranya masih memuat kebijakan LAMA** yang
   FASE 16 sengaja hapus: `geofence not_verified = LOLOS` dan `wajah error =
   LOLOS`. Tidak terjangkau (dibuktikan via AST: nol pemanggil), jadi bukan bug
   aktif — tapi ranjau, karena namanya `_determine_approval` dan duduk di berkas
   clock-in biometrik. Dihapus + 21 baris impor/konstanta yatim. Absen tetap
   **48 PASS / 0 FAIL**, route absen tetap 42.
3. **Alat uji menaruh data palsu di DB.** `bughunt_hris_flow.py` sekarang
   menghapus jejaknya **di `finally`** langsung ke Mongo (bukan mengandalkan
   `DELETE` yang cuma meng-cancel). Terbukti: 8/8 PASS lalu
   `rahaza_overtime_requests = 0`.

## Bukti (dijalankan ulang sesi ini, bukan dikutip)
`gate.sh` **12/12 PASS · 37 detik** · absen **48/0** · cuti **35/0** · payslip
**25/0** · alur lembur live **8/8** · Import Validation frontend+backend
**bersih** · `yarn build` **Compiled successfully** · route backend **1651**
(tak berubah) · baseline aksesoris **Rp 9.663.750** · Buku Besar seimbang
(Dr = Cr 6.729.375) · **nol drift**.

## BERIKUTNYA (belum dikerjakan — masalah PRODUK, bukan alat)
1. **`except Exception: pass` — 17 titik, 6 di jalur stok & uang**
   (`core/stock_service.py:334`, `core/quarantine.py` ×3,
   `core/accessory_stock.py:46`, `core/stock_reconcile.py:198`). Mutasi stok bisa
   gagal **tanpa log, tanpa error** ⇒ angka salah tanpa jejak. **Prioritas 1.**
2. **44 titik penomoran `count_documents()+1`** ⇒ dua user simpan bersamaan →
   **nomor dokumen KEMBAR** (SJ/PO/invoice). SSOT `utils/counters.py` sudah ada,
   44 titik ini belum ikut.
3. **27 titik datetime naive** ⇒ batas hari laporan/absen bisa bergeser.
4. **Nol test Jest di `frontend/`** — klaim dokumen lama "perluas Jest/RTL" salah
   premis; tidak ada yang bisa diperluas. `setupTests.js` sudah siap dipakai.
5. `RahazaOrdersModule` + 17 modul lain terdeteksi tak terjangkau dari UI —
   belum diputuskan arsip/hidupkan.
6. `mobile/` = scaffold Expo 389 baris tanpa fitur ERP; dependensinya tak pernah
   dipasang. Sudah 3× jadi sumber kegagalan alat. `mobile/tsconfig.json` kini
   `extends` salinan **verbatim** `expo@54.0.35/tsconfig.base.json` yang
   di-commit, supaya bisa di-resolve tanpa node_modules.
7. SMTP sungguhan (`skipped_no_smtp`) untuk verifikasi email berlampiran.

---


# ✅ STATUS TERKINI 2026-07-26 (lanjutan #2) — FASE 20 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap: **`docs/PLAN_FASE20.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Melanjutkan titik berhenti sesi lalu**: penelusuran *"the 7 genuinely broken FE calls"*
   dari temuan advisory `fe_be_contract`. Environment dibangun ulang dari nol via
   `bootstrap.sh` (58 detik, 6 login HTTP 200, baseline aksesoris **Rp 9.663.750** —
   cocok dengan dokumen, jadi angka itu sekarang TERBUKTI reproducible).
2. **Temuan advisory itu BUKAN tech-debt.** Setelah 92 WARN ditriase satu per satu:
   **8 bug produk NYATA** (fitur mati diam-diam) + **2 false positive** + sisanya
   archive/artefak. Rinciannya di `docs/PLAN_FASE20.md` §2.
3. **Gate-nya sendiri menyembunyikan sebagian bug itu** — 4 blindspot ditutup.
   Setelah `_seg_match()` dibuat asimetris: **92 → 140 temuan** (48 sebelumnya tak terlihat).
4. **Satu KELAS BUG BARU ditemukan & dijaga** (`INV-DEADCODE-01`): "handler tergabung".
5. **`fe_be_contract` sekarang: REAL_404 = 0** (dari 11) dan `DEADCODE = 0` (dari 16).

## ⚠️ KOREKSI KLAIM DOKUMEN
| Klaim di serah-terima lama | Kenyataan |
|---|---|
| `fe_be_contract` **HIGH 9** | **Label usang.** Gate versi sekarang melaporkan `WARN`, `0 HIGH`. Angka "9" = jumlah temuan nyata SETELAH triase, bukan severity |
| Temuan `fe_be_contract` = "tech-debt advisory, tidak mem-blok" | **Berbahaya.** Di dalamnya ada 8 fitur mati (lihat §2 PLAN_FASE20) |
| `dewi_assets.py` bersintaks rusak (dari log sesi lalu) | **KELIRU** — `py_compile` bersih; itu artefak render alat `view_file` |
| `numeric_bounds` MED 10 | sekarang **MED 1** |
| `static_antipatterns` MED 263 | sekarang **MED 253** (3 modul CMT mati diarsip) |

## 8 bug nyata yang ditutup (ringkas)
| Panggilan FE lama | Jadi | Dampak sebelumnya |
|---|---|---|
| `/api/rahaza/master/employees` (**4 titik**) | `/api/rahaza/employees` + baca `.items` | dropdown karyawan **selalu kosong** di AI Actions, HR Aset, WMS Pick List |
| `/api/finance/coa` | `/api/rahaza/coa/accounts` + parse array | mapping GL biaya karyawan **tak bisa dibuat** (dropdown akun kosong) |
| `/api/rahaza/overtime-requests` (**GET + POST**) | `/api/rahaza/overtime` + baca `.overtime` | kartu "Lembur Saya" kosong **dan setiap pengajuan lembur gagal** |
| `/api/rahaza/payroll-runs/{id}/export` | endpoint dipulihkan (dulu **kode mati**) + `downloadWithAuth` | tombol "Download CSV" payroll **mati total** |
| `/api/rahaza/payroll-runs/{id}/payslips/{sid}/adjust` | endpoint **dibuat** + header run disinkronkan | penyesuaian manual payslip **hilang tanpa error**; kolom "Adj" selalu 0 |
| `/api/collab/link-preview` | `/api/collab/search/link-preview` | pratinjau tautan kolaborasi selalu gagal |
| `/api/dewi/assets/by-code/{code}` | `/api/assets/scan-by-number/{n}` | **scan QR aset mati** (dan menembak domain yang salah) |
| `/api/rahaza/orders/{id}/generate-work-orders` | **tombol dihapus** | engine `rahaza_work_orders` sengaja dipensiunkan FASE 4 — jangan dihidupkan ulang |

> **`PUT /payslips/{pid}` yang SUDAH ADA juga diperbaiki**: ia mengubah angka slip tanpa
> menyinkronkan header run, padahal `post_payroll_run()` menyusun **jurnal GL dari header**
> ⇒ jurnal saat finalize nyata-nyata salah. Sekarang ada SSOT `_payslip_totals()` +
> `_recompute_run_totals()` di `rahaza_payroll_shared.py`.

## 🔴 2 TEMUAN TAMBAHAN — keduanya hanya muncul saat DIVERIFIKASI LEWAT UI/DB

### (a) Mismatch FIELD-level: semua kolom uang payslip menampilkan **Rp 0**
Gate kontrak hanya memeriksa **path**, jadi ini lolos total. Saat detail payroll run dibuka,
seluruh kolom uang per karyawan **Rp 0** padahal total run benar. FE membaca skema payslip
LAMA, backend menulis yang BARU:

| FE membaca | Backend menulis |
|---|---|
| `base_salary` | `earnings_total` |
| `transport_allowance` · `meal_allowance` · `production_bonus` | `allowances[]` + `allowance_total` |
| `overtime_pay` | `overtime_amount` |
| `total_deductions` | `deductions_total` |
| `net_salary` | `net_pay` |

Diperbaiki di 3 berkas — dua di antaranya **layar milik karyawan sendiri**:
`RahazaPayrollRunModule.jsx` (kolom `Transport`/`Bonus Prod.` dihapus karena backend tak
memisahkannya; ditambah `Bruto`), `PortalSayaPayslip.jsx` (fitur FASE 18),
`SelfServicePortal.jsx`. Nama lama tetap dipakai sebagai **fallback** (`modern ?? legacy`)
karena backend pun begitu.
**Diverifikasi BUKAN bug:** `RahazaHRReportsModule.jsx` — endpoint
`hr/reports/payroll-summary` memang menghasilkan `total_deductions`/`net_salary`.
Dijaga oleh **C7** (statik) + **C8** (runtime).

### (b) Drift yang ditinggalkan ALAT UJI — termasuk **jurnal GL POSTED fiktif**
Testing agent melaporkan *"All test data cleaned up successfully"*. **Keliru.** Tertinggal:
`PR-20260726-001` **FINALIZED** (`DELETE /payroll-runs/{id}` hanya izinkan `draft` ⇒ gagal
dalam diam), **jurnal `JE-20260728-0001` status POSTED Dr Rp 45.031.214** + 3 baris mirror,
dan 1 request lembur pending. Buku Besar & Neraca Saldo diturunkan dari
`rahaza_journal_lines` ⇒ **uang fiktif masuk laporan keuangan**.

Ditutup dengan **`scripts/cleanup_fase20_qa.py`** (`--dry-run`/`--apply`, idempoten,
bagian 4 khusus **jurnal GL yatim**). Bukti:
```
SEBELUM : journal_entries 9 · journal_lines 19 · total debit 51.760.589
SESUDAH : journal_entries 8 · journal_lines 16 · total debit  6.729.375
selisih = 45.031.214 (tepat jurnal fiktifnya) · Dr == Cr tetap seimbang · 24 dokumen dihapus
```
**JALANKAN `python3 scripts/cleanup_fase20_qa.py --dry-run` setiap selesai sesi pengujian.**

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash    scripts/run_all_verifications.sh        # 12 skrip (termasuk verify_fase20.py)
python3 scripts/verify_fase20.py                # 105 PASS / 0 FAIL (sentinel kontrak FE↔BE)
bash    scripts/_prove_fase20_sentinel_red.sh   # 4/4 bug → sentinel MERAH, lalu hijau lagi
python3 scripts/triage_fe_dead_calls.py         # WAJIB "REAL_404    : 0"
python3 scripts/guardrails/verify_unreachable_code.py   # INV-DEADCODE-01 (blocking)
python3 scripts/cleanup_fase20_qa.py --dry-run  # WAJIB "TOTAL akan dihapus: 0 dokumen"
bash    scripts/gate.sh                         # 10/10 HIJAU → memory/GATE_RECEIPT.md
python3 scripts/lib/acc_baseline.py             # WAJIB TOTAL = 9.663.750
```

## ⚠️ 10 PELAJARAN WAJIB (tambahan; yang lama di bawah tetap berlaku)
1. **"Tech-debt advisory" bisa menyembunyikan bug produk.** Triase sekali — jangan diwarisi
   sebagai angka di dokumen serah-terima.
2. **Guard yang menghasilkan false positive permanen = guard yang akan diabaikan.**
   Memperbaiki blindspot-nya sama pentingnya dengan memperbaiki bugnya.
3. **Menguji helper ≠ menguji pemakaiannya.** Proof merah iterasi pertama hanya 2/4:
   assert-nya memanggil `websocket_shapes()`/`_strip_js_comments()` langsung, bukan
   memeriksa bahwa GATE memakainya. A3b/A4b lahir dari kegagalan itu.
4. **Jangan buat endpoint hanya karena FE memanggilnya.** Cek dulu: engine-nya sengaja
   dipensiunkan? FE-nya menembak domain yang salah? Keduanya "selesai" dengan endpoint
   baru — dan keduanya salah.
5. **Memperbaiki URL saja sering belum memperbaiki fitur.** Samakan juga **bentuk balasan**
   dengan yang dibaca FE, kalau tidak hasilnya "200 OK tapi tabel kosong".
6. **Kalau angka payslip berubah, header run WAJIB ikut** — jurnal GL dibaca dari header.
7. **Komentar yang menyebut path lama bisa membuat gate merah palsu.** Yang diperbaiki
   guard-nya (`fe_calls()` mengabaikan komentar), bukan komentarnya yang dihapus.
8. **Gate kontrak path-level TIDAK melihat mismatch FIELD-level.** Bug "semua kolom uang
   Rp 0" hanya muncul saat layarnya benar-benar DIBUKA. Verifikasi lewat UI bukan formalitas.
9. **Jangan percaya klaim "test data cleaned up" — hitung dokumennya.** `DELETE` yang
   menolak status non-draft **gagal dalam diam**, dan jurnal GL POSTED yang tertinggal
   adalah drift termahal karena menyusup ke laporan keuangan.
10. **Assert yang bergantung data ambient akan "lewat" diam-diam di environment bersih.**
    Buat data ujimu sendiri, lalu hapus di `finally`.

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong; sistem membalas `skipped_no_smtp` +
   notifikasi in-app (perilaku benar). Bukti lampiran Excel+PDF: jalankan `aiosmtpd` lokal.
2. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
3. **Tech-debt advisory sisa** (tidak mem-blok gate): `fe_be_contract` WARN 123
   (**sudah ditriase — semuanya archive/artefak/dinamis, REAL_404 = 0**) ·
   `static_antipatterns` MED 253 · `effort_quality` HIGH 1
   (`backend/poc_variant_ssot.py:26` — URL Mongo literal di skrip POC, bukan kode produksi).
4. **Drop `accessory_legacy` di DB PRODUKSI user** — di preview no-op.
5. **46 temuan `DYNAMIC`** di `triage_fe_dead_calls.py` sudah diperiksa manual & benign
   (adapter `${path}`/`${qs}` + komposisi aksi `${action}`). Kalau mau NOL WARN, jalannya
   adalah membuat CHECK B mengerti wrapper adapter — bukan menghapus temuannya.

---

# (ARSIP) STATUS TERKINI 2026-07-26 (lanjutan) — FASE 13 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap: **`docs/PLAN_FASE13.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Environment dibangun ulang dari nol** (container baru, MongoDB KOSONG total) via
   `bootstrap.sh` — 49 detik, backend health OK, static bundle HTTP 200, 6 login HTTP 200.
   Semua angka di bawah dihasilkan ulang dari seeder, **bukan dikutip dari dokumen**.
2. **Verifikasi dulu, baru kerja** — 3 klaim TERBUKTI (443 PASS/0 FAIL · gate 9/9 · ESLint rc=0),
   **3 klaim KELIRU** (lihat §angka baseline di bawah).
3. **3 bug tooling NYATA ditutup di akarnya** — semuanya satu penyakit: *alat uji merusak data
   yang seharusnya ia lindungi*.
4. **Regresi penuh sekarang TIDAK MENINGGALKAN DRIFT SAMA SEKALI** (pertama kali) —
   sebelumnya tiap run membocorkan +5/-3 pcs stok + 2 mutasi + 2 jurnal GL yatim.

## ⚠️ ANGKA BASELINE BERUBAH — "Rp 9.667.750" ITU RESIDU QA, JANGAN DIPAKAI LAGI
| | LAMA (residu) | **BENAR (reproducible dari seeder)** |
|---|---|---|
| `ACC-BTN-12` | 5.020 | **5.000** |
| total qty valuasi | 32.220 | **32.200** |
| nilai persediaan | Rp 9.667.750 | **Rp 9.663.750** |
| total on-hand (health) | 32.970 | **32.950** |

Selisih 20 pcs = **4 run kebocoran × 5 pcs** dari `verify_phase_g_acc_opname.py`.
SSOT tunggal sekarang: **`scripts/lib/acc_baseline.py`** (semua total DITURUNKAN dari tabel
`STOCK_BASELINE × COST_BASELINE`, ada `assert` pengaman). `cleanup_fase10_qa.py` dan
`tests/backend_test_fase12.py` **mengimpor** dari situ — angka tidak bisa lagi menyimpang.
Tetap: 10 item · 8 bernilai / 2 sengaja belum dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN`) ·
peta gudang bersih (hanya `ZNA-AKSESORIS` + `ZNA-KAIN`) · `health.affected_rows = 0`.

## 3 bug tooling yang diperbaiki
1. **Kebocoran stok + jurnal GL yatim** (`verify_phase_g_acc_opname.py`) — approve opname
   dijalankan pada material demo NYATA, dan `_cleanup()` memakai field `related_ref` yang
   **tidak pernah tersimpan** (backend menyimpan `reference_id`/`ref_id`) sehingga jurnal GL
   tak pernah terhapus. Kini skrip memakai aksesoris uji sendiri (`QA-OPN-*`), `try/finally`,
   dan jaring pengaman pemulihan stok + ledger. **49 PASS/0 FAIL**, artefak 13 → 35.
2. **Pencemaran `rahaza_costing_settings` global** (`verify_fase11/12/66.py`) — nilai uji
   (12345/77, 88000, 4321) tertinggal permanen bila ada exception/timeout, lalu jadi LENGKET.
   Ditutup dengan SSOT `scripts/lib/qa_state_guard.py` → `preserve_costing_settings(db)`
   (pemulihan di `finally`; dokumen yang semula tidak ada akan DIHAPUS).
3. **Titik buta alat audit** — `cleanup_fase10_qa.py` tidak pernah memeriksa
   `rahaza_costing_settings` (itu sebabnya audit user harus manual). Sekarang ada **bagian 5**
   deteksi + pemulihan. Bonus: `tests/backend_test_fase12.py` dulu mematok `BASE_URL` ke
   preview container lama yang **sudah mati** → kini dibaca dari `frontend/.env`.

## Sentinel baru — supaya tidak kambuh
**`scripts/verify_fase13.py`** (33 assert, terdaftar TERAKHIR di `run_all_verifications.sh`):
menjalankan skrip terawan lalu **membuktikan NOL DRIFT** pada 9 metrik, menguji guard
**saat exception**, mendeteksi mutasi/jurnal yatim, dan memeriksa nama field lewat **AST**.
**Sentinelnya sendiri sudah diuji MERAH** dengan menanam ulang bug lamanya.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash    scripts/run_all_verifications.sh     # 11 skrip → 480 PASS / 0 FAIL
python3 scripts/verify_fase13.py             # 33 PASS / 0 FAIL (sentinel drift)
python3 scripts/cleanup_fase10_qa.py --dry-run   # WAJIB "(tidak ada drift)" di bagian 4 DAN 5
bash    scripts/gate.sh                      # SEMUA HIJAU → memory/GATE_RECEIPT.md
python3 scripts/lib/acc_baseline.py          # cetak SSOT baseline + totalnya
```

## ⚠️ 6 PELAJARAN WAJIB (tambahan; yang lama di bawah tetap berlaku)
1. **Alat uji = sumber tech-debt data yang paling sering terlewat.** Tiga sesi mengejar "data
   kotor" padahal penyebabnya skrip verify-nya sendiri. Perbaiki PENULISNYA, bukan datanya.
2. **Angka baseline yang tidak reproducible dari seeder adalah RESIDU.** Kalau `--dry-run`
   selalu merah di environment segar, curigai baselinenya — bukan datanya.
3. **Alat "cleanup" yang menulis angka bisa MENGARANG data.** Restore-by-insert dengan baseline
   salah = menyuntikkan persediaan fiktif beserta nilai rupiahnya.
4. **Nama field Mongo wajib diverifikasi terhadap PENULISNYA.** `related_ref` terlihat benar
   (ada di signature backend) tapi tersimpan sebagai `reference_id`. Query yang cocok 0 dokumen
   gagal DIAM-DIAM — cek `count_documents()` sebelum percaya sebuah cleanup.
5. **Pemulihan state global adalah tugas `finally`, bukan "kalau semua lancar".**
6. **Guard yang belum pernah terlihat MERAH bukan guard.** Tanam ulang bugnya untuk membuktikan.

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong; sistem membalas `skipped_no_smtp` +
   notifikasi in-app (perilaku benar). Bukti lampiran Excel+PDF: jalankan `aiosmtpd` lokal.
2. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
3. **Tech-debt advisory** (tidak mem-blok gate): `fe_be_contract` HIGH 9 ·
   `static_antipatterns` MED 263 · `numeric_bounds` MED 10.
4. **Drop `accessory_legacy` di DB PRODUKSI user** — di preview no-op.
5. **Observasi kecil (belum ditindak):** notifikasi "Harga satuan belum diisi" menumpuk
   **4 duplikat per item** untuk 2 item yang sengaja belum dinilai (8 dokumen). Kandidat dedup;
   bukan risiko finansial.

---

# (ARSIP) STATUS TERKINI 2026-07-26 — FASE 12 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap: **`docs/PLAN_FASE12.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Verifikasi dulu, baru kerja** — dan **4 dari 5 klaim dokumen ternyata keliru**:
   suite regresi sebenarnya **401 PASS / 9 FAIL** (bukan 410/0) · `bootstrap.sh` tidak pernah
   menyeed baseline valuasi aksesoris (8 FAIL palsu) · alias `yarn_*` masih bocor lewat seeder ·
   `scripts/migrate_stock_locations_to_wh.py` yang disebut backlog **tidak pernah ada** ·
   ESLint mati total kalau dijalankan dari `/app/mobile`.
2. **4 bug nyata diperbaiki**: BUG-A (seeder menulis alias legacy), BUG-B (HPP job internal
   memakai harga bahan **0** diam-diam), BUG-B2 (material `kain`/`benang`/`interlining` tanpa
   `unit_cost` dapat fallback harga **aksesoris**), BUG-C (linter engine mati).
3. **Backlog #3 (rekonsiliasi lokasi stok) TUNTAS** — bukan dengan skrip sekali pakai, tapi
   penyakit ke-8 **`unmapped_location`** di alat "Kesehatan Skema Stok" yang sudah punya
   pratinjau → terapkan → **rollback presisi** + UI.
4. **Akar penyebabnya ditutup**: seeder demo (`maklon_seed.py`) & `link_demo_bom_materials.py`
   tidak lagi menaruh stok di lokasi pseudo `GDG-UTAMA-DEMO`; `cleanup_fase10_qa.py` baseline-nya
   ikut diperbarui (kalau tidak, `--apply` justru MEMBATALKAN rekonsiliasi).
5. **Higiene alat uji**: `bootstrap.sh` kini menyeed baseline valuasi aksesoris;
   `run_all_verifications.sh` otomatis membersihkan artefak `verify_phase6_quarantine`
   (penyebab run ke-2 selalu merah palsu) dan menjalankan `verify_fase12.py`.

## ⚠️ 5 PELAJARAN WAJIB (tambahan dari sesi ini; yang lama di bawah tetap berlaku)
1. **Uji ulang SEMUA angka di dokumen serah-terima.** Empat dari lima klaim keliru sesi ini.
2. **"Merah" belum tentu regresi produk** — bisa **pencemaran data antar-skrip uji**.
   `verify_phase6_quarantine` meninggalkan `TEST-F6-KAIN` sehingga run ke-2 menghitung stok
   DUA KALI. Kalau sebuah gate hanya merah pada run kedua, curigai kebersihan datanya dulu.
3. **Rekonsiliasi otomatis TIDAK boleh menyentuh baris yang butuh keputusan manusia.**
   Memindah + menggabungkan baris ber-qty **negatif** akan diam-diam mengurangi stok zona tujuan
   dan menghilangkan selisih dari radar. Baris yatim juga tak punya kategori ⇒ zona tujuan tak
   bisa ditentukan. Keduanya sengaja dikecualikan (dan tidak dihitung `fixable`).
4. **Kalau memindahkan lokasi stok, PERBARUI JUGA skrip baseline/cleanup.**
   `cleanup_fase10_qa.py --apply` sempat siap mengembalikan stok ke lokasi liar.
5. **Seeder = sumber tech-debt data.** Backlog "rekonsiliasi lokasi" selalu kembali karena
   SEEDER-nya yang salah menaruh stok, bukan karena datanya. Perbaiki penulisnya, bukan datanya.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash    scripts/run_all_verifications.sh     # 10 skrip → 443 PASS / 0 FAIL (auto-cleanup F6)
python3 scripts/verify_fase12.py             # 31 PASS / 0 FAIL (self-cleaning)
python3 scripts/sweep_query_robustness.py    # 7.184 request → 0 error 500
bash    scripts/gate.sh                      # 9/9 HIJAU → memory/GATE_RECEIPT.md
python3 scripts/cleanup_fase10_qa.py --dry-run   # harus "(tidak ada drift)"
```
**Baseline data demo aksesoris (WAJIB tetap seperti ini):** 10 item · nilai persediaan
**Rp 9.667.750** · 8 bernilai / 2 belum dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN` sengaja HPP 0) ·
`ACC-BTN-12` stok **5.020 di ZNA-AKSESORIS** (bukan lagi terbelah ke `int-demo-loc-1`) HPP **200**.
**Peta gudang bersih:** hanya `ZNA-AKSESORIS` + `ZNA-KAIN` yang menyimpan stok; `health` → `affected_rows = 0`.

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong; sistem membalas `skipped_no_smtp` +
   notifikasi in-app (perilaku benar). Untuk bukti lampiran Excel+PDF: jalankan `aiosmtpd` atau
   isi kredensial nyata lewat UI.
2. **Drop `accessory_legacy` di DB PRODUKSI user** — di preview no-op.
3. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
4. **Tech-debt advisory** (tidak mem-blok gate): `fe_be_contract` HIGH 9 ·
   `static_antipatterns` MED 263 · `effort_quality` HIGH 1 · `numeric_bounds` MED 10.

---

# (ARSIP) STATUS 2026-07-25 (lanjutan #4) — FASE 11 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap FASE 11: **`docs/PLAN_FASE11.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Verifikasi dulu, baru kerja.** Klaim FASE 10 (402 PASS / 0 FAIL) diuji ulang dari nol → **TERBUKTI**.
2. **BUG-R11-A ditutup TUNTAS** — dulu hanya diuji 8 sampel; kini disapu **7.184 request**
   (898 GET endpoint × 8 varian query rusak). **66 → 0 error 500**, 51 → 0 endpoint bermasalah.
   46 endpoint di 36 file router diperbaiki + helper baru `backend/utils/query_guards.py`.
3. **BUG-4 (BARU)** — `datetime` adalah SUBCLASS `date`; `GET /api/dewi/cmt/lifecycle` balas **500 pada
   request POLOS**. Diperbaiki di 3 file berjebakan sama.
4. **BUG-5 (BARU)** — jurnal modul Aset memakai kode akun hardcode yang **tidak ada di CoA**
   (`1500`/`1100`/`1590`/`8100`/`6300` vs CoA berformat `1-2500`/`1-110`). Kini diambil dari
   `rahaza_posting_profiles` lewat `routes/asset/_accounts.py`.
5. **Alias legacy `yarn_*` DIHENTIKAN penulisannya** (permintaan user) — fallback BACA tetap dijaga.
6. **gate.sh HIJAU 9/9** untuk pertama kalinya sejak 2026-07-16 (dulu 2 MERAH).

## ⚠️ 7 PELAJARAN WAJIB DIINGAT AGENT BERIKUTNYA
1. **JANGAN percaya laporan `testing_agent_v3` soal kebersihan data.** Ini kejadian **ke-3 berturut-turut**
   (iter 170, 173, dan sekarang **174**). Iter 174 melapor `"test_data_created": []` padahal meninggalkan
   3 aset + 4 jurnal. Penyebabnya: skripnya memanggil `DELETE /api/assets/{id}` dan
   `DELETE /api/rahaza/journal-entries/{id}` yang **TIDAK ADA**, jadi gagal diam-diam.
   **SELALU audit DB sendiri sesudahnya.**
2. **JANGAN uji robustness pakai sampel.** Sesi lalu menyimpulkan R11-A beres dari 8 sampel (7 di antaranya
   kebetulan sudah sembuh). Pakai `python3 scripts/sweep_query_robustness.py` — sapu semuanya.
3. **`datetime` adalah SUBCLASS `date` di Python.** `isinstance(v, date)` True untuk `datetime`.
   Selalu cek `datetime` DULU. Pakai `utils/query_guards.to_date()` / `date_key()`.
4. **Endpoint LLM merusak hasil sweep paralel.** `/api/finance/ai-cashflow` ≈ 20 detik → tetangganya
   ikut time-out dan terlihat "rusak". 5 dari 51 temuan awal ternyata false positive. **Probe ulang SERIAL.**
5. **Jebakan pustaka `requests`:** `Response.__bool__` == `Response.ok`. `if r:` bernilai **False untuk
   respons 400/422** — persis yang ingin diuji pada uji robustness. Pakai `if r is not None:`.
6. **Frontend = STATIC BUNDLE.** Setelah mengubah `frontend/src` WAJIB
   `bash /app/scripts/rebuild_frontend.sh` (atau `yarn build`) lalu `supervisorctl restart frontend`.
7. **JANGAN biarkan tool `plan` menimpa `plan.md`.** SSOT rencana proyek ada di situ (~79 KB).
   Rencana per-fase ditaruh di `docs/PLAN_FASE<N>.md`.

## ✅ Masalah setup lama yang SUDAH ditutup di akar (FASE 11)
- **`bootstrap.sh` + `@simplewebauthn/browser` (3 sesi berturut-turut gagal).** Akarnya:
  `yarn install --frozen-lockfile` GAGAL bila `frontend/yarn.lock` tidak ada di repo — dan memang
  belum pernah ter-commit. `bootstrap.sh` kini memakai frozen HANYA bila lockfile ada, dan jatuh
  otomatis ke `yarn install` biasa bila gagal. `frontend/yarn.lock` juga sudah ikut di-commit.
- **ESLint mati total ("linter engine error").** `mobile/eslint.config.js` melempar MODULE_NOT_FOUND
  bila dependensi Expo belum dipasang (memang tidak pernah dipasang di container ini) sehingga
  SELURUH gate lint mati. Config kini menurun dengan anggun.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash   scripts/run_all_verifications.sh          # 9 skrip regresi → 410 PASS / 0 FAIL
python3 scripts/verify_fase11.py                  # 108 PASS / 0 FAIL
python3 scripts/sweep_query_robustness.py         # 7.184 request → 0 error 500
python3 backend_test_fase11.py                    # 45/45 PASS (self-cleaning + verifikasi)
bash   scripts/gate.sh                            # 9/9 HIJAU → memory/GATE_RECEIPT.md
python3 scripts/cleanup_test_f6.py --apply        # bersihkan artefak F6
python3 scripts/cleanup_fase10_qa.py --apply      # kembalikan stok/HPP demo ke baseline
```
**Baseline data demo aksesoris (WAJIB tetap seperti ini):** 10 item · nilai persediaan
**Rp 9.667.750** · 8 bernilai / 2 belum dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN` sengaja HPP 0) ·
`ACC-BTN-12` stok **5.020** (5.000 di `int-demo-loc-1` + 20 di ZN-AKS) HPP **200**.
Seeder: `scripts/seed_acc_valuation_baseline.py` (idempoten, `--cleanup`).

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — user memilih "lewati dulu" sesi ini. SMTP masih kosong; sistem
   membalas `skipped_no_smtp` + notifikasi in-app (perilaku benar). Untuk bukti lampiran Excel+PDF
   benar terkirim: jalankan SMTP dummy (`aiosmtpd`) atau isi kredensial nyata lewat UI.
2. **Drop `accessory_legacy` di DB PRODUKSI user** — user memilih "lewati". Di preview no-op.
3. **Rekonsiliasi lokasi stok aksesoris** — `ACC-BTN-12`/`ACC-LBL-01`/`ACC-DA-LBL` masih menyimpan stok
   di `int-demo-loc-1`, bukan zona kanonik ZN-AKS. Aman (BUG-1 sudah diperbaiki) tapi peta gudang
   masih berantakan. Alat: `scripts/migrate_stock_locations_to_wh.py`.
4. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
5. **Tech-debt advisory** (tidak mem-blok gate, sudah lama): `fe_be_contract` HIGH 9 ·
   `static_antipatterns` MED 263 · `effort_quality` HIGH 1 (`poc_variant_ssot.py` pakai literal
   `mongodb://`) · `numeric_bounds` MED 10 (field uang Pydantic tanpa `ge=`, mis. `dewi_cmt_permak.py`).

---

# (ARSIP) STATUS 2026-07-25 (lanjutan #3) — FASE 10 TUNTAS, TERUJI & TERDOKUMENTASI
> **BACA INI DULU — men-supersede semua entri di bawah.**

> **Sesi 2026-07-25 lanjutan #3 (environment dari repo `naababnamana/da`).** Sesi sebelumnya sudah
> MENULIS kode FASE 10 tapi berhenti tepat sebelum `testing_agent_v3`, sehingga dokumen belum di-update.
> Sesi ini: verifikasi penuh → **temukan & perbaiki 3 bug nyata** → E2E testing agent → bersih-bersih data
> → rapikan dokumen. Baca `plan.md` §SESI AKTIF (lanjutan #3) + `memory/CHANGELOG.md` entri teratas.

## FASE 10 — 4 Next Action Items (SELESAI)
1. **Prompt Terakhir** — `window.prompt()`/`window.confirm()` TERAKHIR di modul Aksesoris DIGANTI
   `OpnameActionModal` (kind: submit/cancel/approve/reject) + modal hapus aksesoris. Testid dinamis
   `opname-<kind>-modal|-confirm|-cancel|-reason|-error`. **0 dialog native tersisa di modul ini.**
2. **Jadwal Rapor** — `services/accessory_valuation_mailer.py` + `utils/email_sender.py`:
   `GET/PUT /api/acc/valuation/report-schedule`, `POST .../send-now`. Job `monthly_valuation_report_email`
   tanggal 1 pukul 06:00 WIB, lampiran Excel+PDF, idempoten per periode. SMTP diisi lewat UI
   (`smtp_security` = starttls|ssl|none). Tanpa SMTP → `skipped_no_smtp` (HTTP 200) + notifikasi in-app.
3. **Prasyarat Drop Aksesoris** — grup `accessory_legacy` kini **[SIAP]** di
   `drop_legacy_collections_guided.py --audit`: endpoint `/api/acc/internal-requests/*` & `/api/acc/loans/*`
   → **410**, pemotongan stok diangkat ke `core/accessory_issue.py` dan dipakai SSOT `deliver`,
   tab "Peminjaman" dilepas, pinjaman lama ditutup via `migrations/close_legacy_acc_loans.py`.
4. **Ringkasan Alarm Harian** — `GET/POST /api/acc/valuation/unvalued-digest[/send]` + job
   `daily_unvalued_digest` 07:30 WIB. **Notifikasi per-item TETAP jalan** (pilihan user), digest = tambahan.
   Panel UI: tab **Valuasi HPP** → `acc-val-automation` (digest + jadwal rapor + riwayat kirim).

## ⚠️ 5 PELAJARAN WAJIB DIINGAT AGENT BERIKUTNYA
1. **Restore repo:** `bootstrap.sh` (`yarn install --frozen-lockfile`) TIDAK memasang
   `@simplewebauthn/browser` (sudah terjadi 3 sesi berturut-turut). Yang bekerja:
   `cd /app/frontend && yarn add @simplewebauthn/browser@13.3.0` lalu `yarn build`.
2. **Frontend = STATIC BUNDLE.** Setelah mengubah `frontend/src` WAJIB
   `bash /app/scripts/rebuild_frontend.sh` (atau `yarn build`), kalau tidak perubahan TIDAK terlihat.
3. **JANGAN biarkan tool `plan` menimpa `plan.md`.** Sesi lalu `plan.md` master (69 KB, SSOT rencana
   proyek) tertimpa jadi 9,5 KB. Sudah dipulihkan; rencana FASE 10 dipindah ke
   `docs/PLAN_FASE10_NEXT_ACTIONS.md`.
4. **SELALU audit DB sendiri sesudah `testing_agent_v3`.** iteration_170 DAN iteration_173 sama-sama
   mengklaim "data dipulihkan" padahal meninggalkan artefak; iteration_173 bahkan "memulihkan" stok
   dengan cara MENERIMA barang sehingga HPP rata-rata bergeser. Alat: `scripts/cleanup_fase10_qa.py`.
5. **Stok aksesoris DIBACA lintas lokasi tapi (dulu) DITULIS di satu lokasi.** Kalau menambah alur
   pengeluaran aksesoris baru, pakai `core/accessory_stock.add_stock` / `issue_across_locations`,
   JANGAN memanggil `stock_service.issue(material, LOKASI_KANONIK, qty)` langsung.

## 3 BUG NYATA yang ditemukan & diperbaiki sesi ini
- **BUG-1 (kritis)** — pengeluaran aksesoris **HTTP 500** bila stok tersebar di >1 lokasi (data warisan /
  put-away / seed demo). Lolos dari semua uji sebelumnya karena skrip uji selalu membuat item BARU yang
  stoknya mendarat di lokasi kanonik. Fix: `core/accessory_stock.issue_across_locations()`.
  Repro: `python3 scripts/repro_acc_multiloc_issue.py` (self-restoring).
- **BUG-2** — `approve` opname DIAM-DIAM melewati baris yang gagal disesuaikan (sesi tampak "Completed"
  padahal selisih tidak diterapkan). Fix: `stock_failed` + `stock_failed_items` di backend & UI.
- **BUG-3** — banner hasil aksi di panel otomasi valuasi hilang seketika (klik "Kirim rapor sekarang"
  tanpa SMTP = layar diam). Fix: `load(keepFeedback)` + skeleton hanya pada muat pertama di
  `AccessoryValuationAutomation.jsx` DAN `AccessoryValuationTab.jsx`.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
python3 scripts/verify_fase10_digest_report.py       # 59 PASS
python3 scripts/verify_fase10_accessory_legacy.py    # 44 PASS
python3 scripts/verify_acc123.py                     # 62 PASS
python3 scripts/verify_fase8.py                      # 48 PASS
python3 scripts/verify_fase8plus.py                  # 24 PASS
python3 scripts/verify_phase_g_acc_opname.py         # 45 PASS (self-clean)
python3 scripts/verify_fase9_legacy_drop.py          # 24 PASS
python3 scripts/verify_fase66.py                     # 48 PASS
python3 scripts/verify_phase6_quarantine.py          # 48 PASS  → lalu cleanup_test_f6.py --apply
python3 scripts/cleanup_fase10_qa.py --dry-run       # cek drift data demo setelah semua uji
```
**Baseline data demo aksesoris:** 10 item · nilai persediaan **Rp 9.667.750** · 8 bernilai / 2 belum
dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN` sengaja ber-HPP 0 untuk memicu alarm & digest).
Seeder: `scripts/seed_acc_valuation_baseline.py` (idempoten, `--cleanup`).

## BERIKUTNYA (menunggu keputusan user)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong (sesuai pilihan user: diisi lewat UI). Untuk bukti
   lampiran Excel+PDF benar terkirim, jalankan SMTP dummy lokal (`aiosmtpd`) atau isi kredensial nyata.
2. **Eksekusi drop `accessory_legacy` di DB PRODUKSI user** (di preview no-op karena koleksinya absen).
3. **Hapus alias legacy `yarn_*`** setelah syarat panduan §5 terpenuhi.
4. **Rekonsiliasi lokasi stok aksesoris** — `ACC-BTN-12/ACC-LBL-01/ACC-DA-LBL` masih menyimpan stok di
   `int-demo-loc-1` (bukan zona kanonik ZN-AKS). Sekarang AMAN berkat BUG-1 fix, tapi memindahkannya
   lewat `scripts/migrate_stock_locations_to_wh.py` akan merapikan peta gudang.
5. Perluas Jest/RTL ke `AccessoryValuationAutomation` + `StokOpnameTab`.

---

# ✅ STATUS TERKINI 2026-07-25 — FASE 6.6 + FASE 8 SELESAI (men-supersede semua entri di bawah)

> **Sesi 2026-07-25 (environment dari repo `hanababama/da`): FASE 6.6 (rekonsiliasi skema stok A/B/C + rename
> internal `yarn_*`) dan FASE 8 (valuasi HPP aksesoris + panduan drop koleksi legacy) SELESAI & TERUJI.**
> Baca `plan.md` §SESI AKTIF + `memory/CHANGELOG.md` entri teratas + `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md`.
>
> **Ringkas:**
> - **FASE 6.6-A** — `core/stock_reconcile.py` + `routes/wms_stock_schema.py` + modul FE **"Kesehatan Skema Stok"**
>   (`wh-stock-schema`, juga tab di hub `wms-stock-hub`): deteksi 7 penyakit skema, pratinjau → terapkan → rollback
>   presisi lewat jurnal `wh_stock_schema_reconcile_log`. TIDAK pernah mengubah total on-hand.
> - **FASE 6.6-B** — SSOT `core/material_fields.py` + `frontend/src/lib/materialFields.js`: `yarn_type`→`composition`,
>   `yarn_kg_per_pcs`→`material_kg_per_pcs`, `default_yarn_cost_per_kg`→`default_material_cost_per_kg`,
>   `total_yarn_kg_per_pcs`→`total_material_kg_per_pcs`, `total_yarn_kg`→`total_material_kg`,
>   `yarn_count`→`bulk_line_count`. **Alias legacy TETAP ditulis** (0 breaking change) + migrasi backfill.
> - **FASE 8** — `core/accessory_valuation.py` (moving average), penerimaan/pengeluaran/**scrap (endpoint BARU)**
>   aksesoris kini BERNILAI + berjurnal, `routes/dewi_accessories_valuation.py`, tab FE **"Valuasi HPP"**.
>   KPI "Dipinjam" diganti "Nilai Persediaan" + "Belum Dinilai".
> - **FASE 8.8** — `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` + `migrations/drop_legacy_collections_guided.py`
>   (`--audit`/`--dry-run`/`--execute`/`--rollback`/`--purge-archives`, arsip sebelum drop).
>
> ### ⚠️ 3 PELAJARAN WAJIB DIINGAT
> 1. **Restore repo:** `bootstrap.sh` (`yarn install --frozen-lockfile`) TIDAK memasang
>    `@simplewebauthn/browser`, dan `yarn install --prefer-offline` **JUGA TIDAK CUKUP** (sudah dicoba).
>    Yang bekerja: `cd /app/frontend && yarn add @simplewebauthn/browser@13.3.0` lalu `yarn build`.
> 2. **Frontend = STATIC BUNDLE.** Modul/route BARU "tidak ketemu" atau mendarat di "Pilih Portal" ⇒ 99%
>    `frontend/build/` masih bundel LAMA. Jalankan `bash /app/scripts/rebuild_frontend.sh` DULU.
> 3. **`rahaza_material_stock` punya UNIQUE index (material_id, location_id).** Setiap skrip/route yang
>    memindahkan atau menormalkan baris stok WAJIB menghapus/menggabungkan dulu sebelum menulis, kalau tidak
>    akan kena `DuplicateKeyError` (ini bug nyata yang ketemu & difix di FASE 6.6-A).
>
> **Verifikasi cepat state:** `python3 scripts/verify_fase66.py` (48 PASS) · `python3 scripts/verify_fase8.py`
> (48 PASS) · `python3 scripts/verify_acc123.py` (62 PASS) · `python3 scripts/verify_phase6_quarantine.py`
> (48 PASS, lalu `python3 scripts/cleanup_test_f6.py --apply`).
> **INGAT rate limit login 10 req/60 detik** — jangan jalankan semua skrip berbarengan.
>
> **LANJUTAN #2 (2026-07-25) — juga SELESAI:**
> - **FASE 9**: alat drop legacy TERBUKTI lewat `scripts/verify_fase9_legacy_drop.py` (24 PASS — siklus penuh
>   arsip → drop → rollback → purge dgn data tiruan). Eksekusi grup `opname_v1` di DB ini = no-op (koleksi absen).
> - **Modal pengembalian pinjaman** menggantikan `prompt()` di tab peminjaman deprecated.
> - **Rapor valuasi Excel & PDF**: `GET /api/acc/valuation/export?format=xlsx|pdf&month=YYYY-MM`
>   (`utils/accessory_valuation_export.py`) + panel unduhan di tab Valuasi HPP.
> - **Alarm "belum dinilai"**: `core/accessory_valuation.py::notify_unvalued` dipanggil dari
>   receive/issue/scrap saat HPP 0 → notifikasi ke Admin Gudang dkk, anti-spam 1×/24 jam, non-blocking.
> - Bukti tambahan: `scripts/verify_fase8plus.py` **24 PASS** · testing_agent_v3 iteration_170 backend 100%.
> - ⚠️ **PELAJARAN**: iteration_170 melaporkan "data_changes: None" tapi meninggalkan 3 material `ZZTEST-*`,
>   3 baris stok, 6 notifikasi, 2 JE. SELALU cek DB sendiri setelah memanggil testing agent.
>
> **Berikutnya (menunggu keputusan user):** ganti `window.prompt()` terakhir (alasan menolak opname di tab
> Stok Opname) · prasyarat grup `accessory_legacy` sebelum di-drop (panduan §3) · hapus alias `yarn_*`
> (panduan §5) · perluas Jest/RTL ke modul baru.

---

# ✅ STATUS TERKINI 2026-07-25 (BACA INI DULU — men-supersede semua entri handoff historis di bawah)

> **Sesi 2026-07-25 (environment dari repo `cabanamama123/da`): FASE 7 — 3 gantungan AKSESORIS
> (ACC-1 / ACC-2 / ACC-3) SELESAI & TERUJI.** Baca `plan.md` §FASE 7 + `memory/CHANGELOG.md` entri teratas.
>
> **Ringkas:** ACC-3 peminjaman pindah ke domain ASET (`#asset-loans`; `POST /api/acc/loans` ditutup 410,
> GET & return tetap hidup) · ACC-2 `material_id` wajib untuk baris aksesoris BOM + `link-health` +
> `relink-materials` (RBAC diperketat: HR 403) + seeder tak lagi melahirkan BOM "lepas" · ACC-1 kebutuhan
> aksesoris PO membawa `material_id` + tombol "Buat Permintaan" ke SSOT `dewi_accessory_requests`.
> Bukti: `scripts/verify_acc123.py` **62 PASS / 0 FAIL**, `testing_agent_v3` iteration_167 backend **100%**,
> 0 critical bug; 3 alur UI sisa diverifikasi manual (Playwright) oleh main agent.
>
> ### ⚠️ 2 PELAJARAN YANG WAJIB DIINGAT AGENT BERIKUTNYA
> 1. **Frontend = STATIC BUNDLE.** Kalau modul/route BARU "tidak ketemu" atau deep-link mendarat di
>    **"Pilih Portal"**, 99% penyebabnya `frontend/build/` masih bundel LAMA. Jalankan
>    `bash /app/scripts/rebuild_frontend.sh` DULU sebelum menyimpulkan itu bug kode.
>    (Temuan "P1 deep-link rusak" di iteration_2 ternyata ini, bukan bug.)
> 2. **Restore repo:** `bootstrap.sh` memakai `yarn install --frozen-lockfile` yang GAGAL karena lockfile
>    repo out-of-sync ⇒ `@simplewebauthn/browser` tak terpasang ⇒ `yarn build` gagal. Jalankan
>    `cd /app/frontend && yarn install --prefer-offline` sekali, lalu rebuild.
>
> **Berikutnya (menunggu keputusan user):** FASE 6.6 rekonsiliasi baris stok skema lama A/B/C + rename
> internal `yarn_*` · FASE 8 valuasi HPP aksesoris + panduan drop koleksi legacy · bersih-bersih sisa
> domain lama aksesoris (KPI "Dipinjam" di dashboard, `prompt()` di tab peminjaman deprecated).

---

# STATUS 2026-07-21 (arsip)

> Sesi 2026-07-21: environment dipulihkan dari fresh clone + **audit "sisa backlog" selesai**. Ringkas:
>
> **1. Backlog formal (`BACKLOG_PLAN.md` ITEM 1/2/3.1/3.2) — SELESAI & TESTED.** Lihat banner status di `BACKLOG_PLAN.md` + `memory/CHANGELOG.md` (2026-07-21).
>
> **2. Kandidat dedup pintu T-1..T-5 — SUDAH DIPUTUSKAN & DIEKSEKUSI (bukan lagi "PERLU-KEPUTUSAN").** Verifikasi kode 2026-07-21:
>   - T-1 Opname material vs aksesoris = **by-design, logic BENAR** (satu koleksi `wh_opname_sessions2` dipartisi field `domain`; sisi material `$ne:"accessory"`, sisi aksesoris `=="accessory"`; stok ke SSOT `rahaza_material_stock`). Bukan split-brain.
>   - T-2/T-3 = scope-per-`moduleId` sudah diimplementasi (`AccessoryRequestInbox.jsx`, `KREATORRequestModule.jsx`), termasuk fix bug laten tombol approve RnD.
>   - T-4/T-5 = by-design + cross-link/label disambiguation, sudah diterapkan.
>   - Keputusan & bukti lengkap: `IA_RESTRUCTURE_PROPOSAL.md` §8.1. **Entri "PERLU-KEPUTUSAN T-1..T-5" di handoff lama di bawah = USANG.**
>
> **3. CMT-flow Phase A/B/C — SUDAH SELESAI & runtime-verified (bukan pekerjaan tersisa).** Change Log `memory/GUIDELINE_CMT_FLOW.md` §15: Phase A (2026-07-16), B (07-17), C (07-18). Re-run E2E 2026-07-21: `scripts/test_phase_b_e2e.py` ✅ ALL PASS, `scripts/test_phase_c_e2e.py` ✅ ALL PASS.
>
> **4. Rollout opsional (incremental):** OnwardCTA (22 modul terpasang) & paginasi tabel = tetap incremental/opsional; user memilih SKIP untuk sekarang.
>
> Tidak ada item backlog terbuka yang butuh keputusan user saat ini. Entri handoff di bawah dipertahankan sebagai **arsip historis**.

---


> ⚡ **SETUP CEPAT (BACA DULU):** untuk clone+setup dari 0, ikuti `/app/AGENT_QUICKSTART.md` → clone shallow + `EMERGENT_LLM_KEY=sk-... bash /app/scripts/bootstrap.sh` (idempoten, deps paralel+cache, seed idempoten; ~10 dtk pertama, ~7 dtk berikutnya). Jangan setup manual berurutan lagi.

# 🤝 HANDOFF (Session #26 lanjutan — RC-FLOW-UX-11 UI TESTED ✅ 100% + Bug-fix StrictMode)

> **UI Testing:** `auto_frontend_testing_agent` iter#68 = **6/6 PASS** setelah bug-fix.
> **Bug ditemukan & di-fix mid-test:** React 18 StrictMode invoke `useState` initializer 2x di dev-mode → side-effect `sessionStorage.removeItem` di initializer menyebabkan call #2 dapat null → default salah `complaints`. **Fix:** initializer sekarang PURE (baca saja), `removeItem` dipindah ke `useEffect(() => {...}, [])`. File: `MarketingAfterSalesHub.jsx` line 178-197.
> **Poles 11e (terminologi) & 11f (Log merge) SELESAI.** Semua RC-FLOW-UX-11a…11f closed.

---

# 🤝 HANDOFF (Session #26 — RC-FLOW-UX-11 Alur After-Sales/Retur DIEKSEKUSI ✅)

> **Keputusan user 8 Jul 2026:** 11a=B · 11c=B · 11d=A. Sudah diimplementasikan & tested (deep_testing_backend_v2 = **9/9 PASS**, 0 regresi). Detail: lihat "STATUS UPDATE — RC-FLOW-UX-11" di `FLOW_UX_AUDIT.md`.

**Ringkas yang berubah:**
- **Backend** — `marketing_returns_routes.py`: endpoint baru `POST /api/marketing/returns/{id}/create-wh-return` (idempoten, link 2-arah ke `wh_returns`) + `complete_return` upgrade dgn `warning` soft-guard. `dewi_wh_returns.py`: `resolve_return` callback update `marketing_returns.wh_return_status='Resolved'` bila punya `source_marketing_return_id` (non-blocking).
- **Frontend** — `ReturnsRefundsModule.jsx`: tombol "Buat Retur Fisik di Gudang" + banner ⚠️ 24-jam soft-warning + link "Buka di Gudang →". `WHReturnsModule.jsx`: `<OnwardCTA>` di detail Resolved (cross-portal ke `marketing-after-sales`). `moduleRegistry.js` + `App.js LEGACY_MODULE_TO_PORTAL`: 4 pintu legacy retur/komplain di-redirect ke `marketing-after-sales` tab. `MarketingAfterSalesHub.jsx`: baca `hub_tab_marketing-after-sales` untuk deep-link tab. `portalNav.js`: `wh-returns` label → "Retur Fisik (Gudang)".

**Belum dikerjakan (non-blocker):** RC-FLOW-UX-11e (poles terminologi), 11f (Log Penyelesaian merge `wh_returns` Resolved). Frontend UI test belum dijalankan (menunggu izin user).

---

# 🤝 HANDOFF (Session #26 — Audit Alur 11 After-Sales/Retur & Refund SELESAI ✅)

> **UPDATE:** `FLOW_UX_AUDIT.md` ditambah section baru **ALUR 11 — Retur Pelanggan → Refund → Koreksi Stok** (Toko→Gudang±Keuangan), termasuk tabel ringkasan verdict baris #11, 6 kartu RC-FLOW-UX-11a…11f (grounded ke `backend/routes/marketing_returns_routes.py` + `backend/routes/dewi_wh_returns.py` + `MarketingAfterSalesHub.jsx` + `WHReturnsModule.jsx`), update kandidat CTA berikutnya, dan update kesimpulan §9.2 (+1 blocker teknis: 2 sistem retur paralel `marketing_returns` vs `dewi_wh_returns` tanpa jembatan; `marketing.complete` tak restock).
>
> **PERLU-KEPUTUSAN USER sebelum eksekusi 11a/11c/11d** (menyentuh skema data + IA). CTA onward 11b bisa langsung dipasang (fondasi RC-FLOW-UX-CORE sudah siap).

---

# 🤝 HANDOFF (Session #25 lanjutan — RC-FLOW-UX-CORE `onNavigate` SELESAI) ✅

> Status: **fondasi navigasi onward siap untuk SEMUA modul + 2 CTA baru + 1 CTA lama** (testing iter#40 = 100%). Baca `FLOW_UX_AUDIT.md` (bagian "STATUS UPDATE — RC-FLOW-UX-CORE") untuk detail & kandidat CTA berikutnya.

## RC-FLOW-UX-CORE — yang sudah jadi
- `onNavigate(moduleId, params)` di-pass App.js ke tiap modul (PortalShell & collaboration branch) + diteruskan lewat hub (`{...props}` → `HubTabs {...rest}` → tab). SEMUA modul & tab-hub menerimanya.
- **App.js `handleNavigate` (baris ~433)** = navigasi onward penuh: cross-portal switch (pindah `selectedPortal` bila target di portal lain yg accessible), hub-tab deep target (`{tab}`→`sessionStorage.hub_tab_<hubId>`), guard modul invalid, forward `deepLinkParams`, scroll-to-top.
- **`components/erp/OnwardCTA.jsx`** = bar "Langkah Berikutnya" reusable. Pakai: `<OnwardCTA onNavigate={onNavigate} title="…" actions={[{ module:'<id>', label:'…', icon, primary, hint }]} />`.
- CTA aktif: `marketing-orders`→`fulfillment` (CROSS-PORTAL Toko→Gudang, `onward-fulfillment`), `maklon-po-360`→`maklon-billing` (`onward-maklon-billing`), `wh-purchase-orders`→`wh-receiving` (existing, buat GR).

## Menambah CTA onward (incremental, mudah)
1. Modul terima prop `onNavigate` (top-level otomatis; sub-komponen: teruskan).
2. `import OnwardCTA from './OnwardCTA'` (atau `../OnwardCTA`).
3. `<OnwardCTA onNavigate={onNavigate} actions={[{ module:'<target-id>', label:'…', icon: Ikon, primary:true }]} />` setelah header/hasil.
4. Cross-portal ditangani otomatis oleh `handleNavigate`. `module` harus id valid di `MODULE_REGISTRY`.
- **Kandidat berikut**: Alur 3 (WO→`prod-cutting`), Alur 6 (payroll→`fin-journal-*`), Alur 2 (GRN→`wh-putaway`/`wh-stock-hub`), Alur 7/8 (order→retur/komplain), Alur 9 (RnD sample approved→`rnd-techpack`/`maklon-po`).

## Catatan
- Hash URL TIDAK berubah saat klik CTA (navigasi berbasis React state) — normal, bukan bug.
- Non-kritis pre-existing: warning `<span> in <option>` di WarehouseDashboard (console-only, tak pengaruh fungsi).

---



# 🤝 HANDOFF (Session #25 — lanjut PAGINASI RC-UI-03, +45 modul) ✅ TERVERIFIKASI

> **BACA URUT**: file ini → `/app/plan.md` (Session #25 di atas) → `/app/DOCS_INDEX.md` → `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` (BAGIAN 7 = standar paginasi) → `/app/memory/FINAL_REPAIR_LOG.md` (entri RC-UI-03 Session #25 di bawah). Handoff sesi lama di bawah (arsip).

## SESSION #25 — SELESAI & TERVERIFIKASI (testing iter#39)
- **Env di-setup ulang** dari clone `argentinavsfrench/da` → /app (env preserved). Setup: `bash /app/scripts/bootstrap.sh` (backend healthy, seed OK, 6 login 200). **CATATAN**: `yarn install --frozen-lockfile` GAGAL (lockfile drift) → jalankan `cd /app/frontend && yarn install --prefer-offline` sekali, lalu `supervisorctl restart frontend`. Setelah itu `compiled successfully`.
- **RC-UI-03 paginasi +45 modul** (kumulatif ~56 pakai `ui/pagination-lite.jsx`). Batch 1 (28 single-table), Batch 2 (8 multi-tabel→list utama), Batch 3 (9). Daftar lengkap: `plan.md`/`FINAL_REPAIR_LOG.md` Session #25.
- **Alat (regen kapan pun)**: `/tmp/paginate_inject.py` (injector aman: anchor SATU `VAR.map`, hook di return TOP-LEVEL min-indent, PaginationLite setelah `</table>`), `/tmp/find_clean_tables.py` (kandidat single-table), `/tmp/inspect_tables.py` (identifikasi list utama modul multi-tabel).
- **Verified**: `hr-employees` (40) FULL 10/hal + Prev/Next (Hal x/4), `hr-attendance-hub`→Absensi Harian (40), `maklon-qc` (12), `marketing-sales` (135). ≤10 baris → label "Menampilkan a–b dari N"; 0 baris → PaginationLite `null` (by-design). 0 crash / 0 React error.

## PEKERJAAN PAGINASI TERSISA (incremental, JUJUR — ~84 modul raw-table)
1. **Modul MULTI-TAB** (tiap tab = list terpisah, butuh hook + `paged` NAMA-BEDA per tabel; injector single-hook TIDAK cukup — kerjakan manual): RahazaFGInventory (items/issues/movements), HROrgChart (units/positions), CMT stacked (deliveries/payments selain jobs), MaklonPO360/AccessoryModule/Phase7Reporting/RahazaHPP/RahazaHRReports (4–6 tabel), HRKPI, RnDTechPack.
2. **SKIP (sudah paginasi)**: yang pakai `<DataTable`/`DataTableV2`/`MasterDataCRUD` (auto 10/hal) atau punya own `[page,setPage]`/server skip+LIMIT+total (WMSModule, BudgetModule, FixedAssets, UnifiedInventory, ReportsModule, MarketingWebhooks, marketing dashboards, RahazaMaterials, RahazaOrders/Stock/ARInvoices/WorkOrders).
3. **EXEMPT**: laporan akuntansi utuh (GL/TB/PnL/BS/Aging), grid editable, matriks (FGStockMatrixView), form/dialog import-preview.

## ATURAN KERAS PAGINASI (dari bug yang ditemui — WAJIB dipatuhi)
- Hook `useClientPagination` HARUS di TOP-LEVEL komponen (indent terkecil), **sebelum SEMUA early-return** (`if(loading/empty) return`), **tak boleh** di dalam callback `.map()`.
- Bila `<table>` di cabang ternary `... : ( <table/> )` → bungkus `<>...</>` saat menambah PaginationLite (adjacent-JSX).
- **JANGAN** paginasi ulang modul yang sudah server-paginate/own-page (cek `skip`/`LIMIT`/`loadMore`/`[page,setPage]`).
- **JANGAN edit parallel search_replace di FILE yang SAMA** (race). `EmployeeLoansModule.jsx` = dead (skip).

---



# 🤝 HANDOFF UNTUK AGENT BERIKUTNYA (Session #24 — item 1 paginasi + item 2 RC-FLOW/tab-audit/FLOW-UX)

> **BACA URUT**: file ini → `/app/DOCS_INDEX.md` → `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` → `/app/IA_RESTRUCTURE_PROPOSAL.md` (§7 = audit tab §9.1 baru) → `/app/FLOW_UX_AUDIT.md` (baru, §9.2) → `/app/memory/FINAL_REPAIR_LOG.md` (Session #24 di bawah). Handoff sesi lama di bawah (arsip).

## SESSION #24 — SELESAI & TERVERIFIKASI (lanjut item 1 & 2)
- **Env setup ulang** dari clone `da71` → /app (env preserved): backend/.env + JWT_SECRET(gen)+EMERGENT_LLM_KEY; deps (pip+yarn); seed OK (`production-full`+`rahaza/seed-demo`); services RUNNING; health ok; 6 akun login 200.
- **ITEM 1 — RC-UI-03 paginasi (testing iter#38: 100%)** ✅: +7 modul custom pakai `ui/pagination-lite.jsx` @10/hal → RahazaJournalListModule (fin-journal-hub "Daftar Jurnal"), RahazaOvertimeModule (hr-overtime), RahazaAttendanceApprovalModule (hr-attendance-hub "Approval Absen"), RahazaDowntimeModule (prod-downtime), InventoryScrapModule (wms-stock-hub "Penyesuaian"), SupplierScorecardModule (wh-supplier-scorecard), ProductionMaterialReturnsModule (prod-material-returns). Verified: journal 10/hal + Prev/Next; scrap "1–10 dari 26". Total cakupan ~53 modul 10/hal.
- **ITEM 2 §9.1 — audit level-TAB** ✅ → `IA_RESTRUCTURE_PROPOSAL.md` BAGIAN 7 (skrip `/tmp/tab_audit.py`). 0 duplikat fungsional wajib-fix baru; 5 kandidat = **PERLU-KEPUTUSAN** (T-1 opname material vs aksesoris; T-2 AccessoryRequestInbox 3-menu; T-3 KREATORRequest 2-menu; T-4 approval absen 2-pintu (by-design); T-5 self-service payslip/cuti 2-portal).
- **ITEM 2 §5 — RC-FLOW write-flow+RBAC (testing iter#36→#37: 95.2%, 20/21)** ✅: **2 BUG RBAC NYATA ditemukan+fix+verified**:
  - **RC-FLOW-expense-1**: `employee_expense_claims.py` disburse cek role `'finance'` padahal role Finance kanonik = **`accounting`** → finance ditolak. Fix: tambah `accounting/staff_keuangan/hr_manager`. (finance disburse kini 200)
  - **RC-FLOW-production-1**: `rahaza_work_orders.py` `_require_admin` hanya `superadmin/admin` → SEMUA role produksi tak bisa kelola WO (koleksi `role_permissions` KOSONG). Fix: tambah `admin_produksi/supervisor_produksi/supervisor`. (spv create WO kini 200)
  - **PENTING sistemik**: `role_permissions` KOSONG → semua custom-role bergantung cek role-string hardcode per-endpoint. Bila menambah role ke portal, cek endpoint izinkan role-string-nya.
- **ITEM 2 §9.2 — FLOW_UX_AUDIT.md** ✅ (baru): audit 10 alur kritis. 0 blocker teknis (semua write-flow LULUS). Akar gesekan UX: (1) **hanya 2 file** punya CTA onward (`window.location.hash=`) → halaman hasil tak menautkan langkah berikut; (2) beberapa lompat-portal tanpa jembatan; (3) pintu duplikat (cuti/expense/opname/payslip). Usulan fondasi **RC-FLOW-UX-CORE**: teruskan `onNavigate` ke semua modul.

## PEKERJAAN TERSISA (opsional, incremental — JUJUR)
1. **RC-UI-03 paginasi** ke ~110 list-custom sisanya (mayoritas multi-komponen/multi-tabel: CMT*, Maklon*, HRKPI, WMSModule, marketing dashboards). Skrip target: `/tmp/find_custom_tables.py` (regen kapan pun). EXEMPT: laporan akuntansi utuh (GL/TB/PnL/BS/Aging) + grid editable.
2. **RC-FLOW-UX fixes** (butuh persetujuan user, §8.3): mulai dari **RC-FLOW-UX-CORE** (prop `onNavigate` ke modul) → buka CTA onward di semua alur. Lalu de-duplikasi pintu (cuti/expense/opname) = PERLU-KEPUTUSAN.
3. **§9.1 kandidat PERLU-KEPUTUSAN** (T-1..T-5) — tanyakan user sebelum eksekusi (menyentuh IA lintas-portal / SSOT backend).
4. Minor pra-ada: `UnifiedInventoryModule` console warning "unique key prop" (LOW, tidak crash).

## CATATAN CEPAT
- Semua data = SEED. Re-seed (admin): `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo`. Login admin@garment.com/Admin@123 (rate-limit 10/60dtk). 5 akun RBAC: hr/finance/spv/gudang/maklon @dewiaditya.id / `Dewi@123`. Navigasi: login → `window.location.hash='<id>'` → reload; hub → klik tab.
- **JANGAN edit parallel search_replace di FILE yang SAMA** (race → fragment `<>` bisa tak ter-apply). Edit sekuensial per file.
- `EmployeeLoansModule.jsx` = dead (di-comment di registry, tak di-import) — jangan hitung/sentuh.

---



> **BACA URUT**: file ini → `/app/DOCS_INDEX.md` → `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` → `/app/IA_RESTRUCTURE_PROPOSAL.md` → `/app/memory/FINAL_REPAIR_LOG.md`. Handoff Session #22 ada di bawah (arsip).

## SESSION #23 — SELESAI & TERVERIFIKASI (user setuju SEMUA)
- **Env di-setup ulang** dari clone repo `da70`: `.env` backend + `JWT_SECRET`(generated)+`EMERGENT_LLM_KEY`; deps terpasang; seed OK; services RUNNING.
- **PHASE A (RC-IA-warehouse-1/2/3) ✅** (testing iter#31: BE 100%, FE 95%): `wms-stock-hub` 4-tab (Opsi A); UnifiedInventory read-only + jalur adjust RESMI `rahaza/material-adjust` (per-lokasi+GL); `get_locations` union `warehouse_locations`+`wh_positions`(=44) + `create_putaway` dual-lookup; nav warehouse W-2 (6 seksi) + W-4 rename.
- **PHASE B (5 hub anti-overwhelm) ✅** (testing iter#33: 100%, 17/17 redirect): `prod-exec-hub`, `hr-expense-hub`, `hr-attendance-hub`, `fin-acctg-adjust-hub`, `rnd-design-hub`. BUG redirect id-lama difix via `LEGACY_MODULE_TO_PORTAL` (App.js) — **PENTING: setiap id lama yang dikonsolidasi ke hub WAJIB ditambah ke LEGACY_MODULE_TO_PORTAL** biar deep-link resolve portal.
- **PHASE C (PART5 UI) ✅** (testing iter#34): RC-UI-01 tema 100% (9/9) — 66 file (~582 kelas) via converter aman `/tmp/theme_fix.py` (skip dark:/text-white/by-design/_archive/eksternal + gradient netral); RC-UI-02 render 100% (12/12); RC-UI-03 komponen `ui/pagination-lite.jsx` (+hook).
- **PHASE D (RC-UI-02 render review) ✅** (testing iter#35, 100%): sweep 235 modul → 234/235 OK; ditemukan+difix BUG `MasterDataCRUD` tak unwrap respons paginasi `{items:[]}` → crash `rows.filter/filtered.slice`. Fix root (unwrap) + guard di `DataTable`/`DataTableV2`/adapter. `prod-employees` tampil 40 baris 10/hal.
- **PHASE E (RC-UI-03 lanjut) ✅**: `pagination-lite` di 3 modul custom (Buyers, WMSDeliveryNotes, CatalogManagement). Total ~36 modul paginasi 10/hal (DataTable ~23 + MasterDataCRUD ~10 + pagination-lite 3).

## PEKERJAAN TERSISA (opsional, incremental)
1. **RC-UI-03 rollout paginasi** ke list-CUSTOM sisanya (kompleks; multi-tabel) pakai `ui/pagination-lite.jsx` — banyak sudah tercakup DataTable/MasterDataCRUD.
2. **RC-FLOW** write-flow+RBAC (BAGIAN 5 PART5); §9.1 deteksi level-TAB (management/self/collaboration); §9.2 `FLOW_UX_AUDIT.md` (audit 10 alur bisnis inti end-to-end).
3. Opsi lanjut IA proposal (W-3 aksesoris 1-pintu dsb) bila user minta.

---


# 🤝 HANDOFF UNTUK AGENT BERIKUTNYA (2026-07-02, Session #22)

> **BACA URUT**: 1) file ini → 2) `/app/DOCS_INDEX.md` → 3) `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` (rencana kerja AKTIF) → 4) `/app/IA_RESTRUCTURE_PROPOSAL.md` (temuan+usulan menunggu keputusan user) → 5) `/app/memory/FINAL_REPAIR_LOG.md` (laporan per modul).

## STATUS SISTEM
- Backend/data SSOT: RC-01..RC-29 + BACKLOG-A..E SELESAI (sweep 930 GET = 0 crash). Detail: `/app/memory/CHANGELOG.md`. **JANGAN kerjakan ulang.**
- Sudah fixed & verified testing agent: duplikat menu Aset (defaultTab), duplikat tab "Stok Opname" di WMS Scanner, theme-sync LiveSessionAnalyticsDashboard, bug RC-20/22/23.
- Semua data = SEED, boleh hilang. Re-seed: `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo` (admin). Login: admin@garment.com / Admin@123 (rate-limit 10/60dtk). Navigasi modul: login → `window.location.hash='<id>'` → reload.

## PEKERJAAN TERSISA (urutan disarankan)
1. **MENUNGGU KEPUTUSAN USER** — `IA_RESTRUCTURE_PROPOSAL.md` Bagian 4 + pertanyaan akhir Session #22 (fix RC-IA-warehouse-2&3? 5 hub anti-overwhelm? stock-hub 1A? W-2/3/4?). Tanya user dulu bila belum dijawab.
2. **RC-IA-warehouse-2 🔴** (menu GRN/PutAway/Lokasi pakai `api/wms/legacy/*` — dual-door terbalik) & **RC-IA-warehouse-3 🔴** (3 pintu adjust stok, 3 endpoint beda) — instruksi fix eksplisit di proposal BAGIAN 5. WAJIB STOP-VERIFY koleksi tulis backend dulu.
3. **PART 5** (semua metode eksplisit di dokumennya): RC-UI-01 theme (112 file sisa, inventaris BAGIAN 3, contoh acuan = LiveSessionAnalyticsDashboard) · RC-UI-03 paginasi 10/hal · RC-UI-02 render 309 modul · §9.1 deteksi level-TAB portal management/self/collaboration (7 portal lain SUDAH — hasil BAGIAN 6 proposal) · §9.2 audit 10 flow kritis → buat `/app/FLOW_UX_AUDIT.md` · RC-FLOW write-flow+RBAC (BAGIAN 5 PART5).
4. Konsolidasi hub anti-overwhelm (setelah user setuju) — pakai pola terbukti: `erp/hubs/HubTabs.jsx` + `makeRedirect(hub, tabKey)` + update portalNav + `LEGACY_MODULE_TO_PORTAL` di App.js (ingat: portal marketing = key `toko`).

## ATURAN KERAS
- Ikuti PART 5 PERSIS (tabel konversi, resep per-file, template laporan). Bug report user → WAJIB verifikasi via testing agent sebelum klaim fixed.
- 1 file = 1 unit selesai (fix→lint→compile→visual→laporan ke FINAL_REPAIR_LOG.md).
- JANGAN sentuh `_archive/`, jangan re-fix yang ada di CHANGELOG, jangan ubah .env/port, backend hanya via kartu RC yang tertulis.
- Update `plan.md` (entri sesi baru di ATAS) + FINAL_REPAIR_LOG setiap selesai.
