# PRD — CV. Dewi Aditya ERP

## Overview
Integrated ERP (React + FastAPI + MongoDB) for a garment business covering Online Shop,
Maklon (contract manufacturing), Production (Cutting · CMT · QC · Packing), HR/SDM,
Warehouse (WMS), Marketing/KOL, and a full Finance/Accounting suite (37 modules).
UI language: **Indonesian**. Theme: global light mode (ThemeProvider + CSS variables).

## Architecture
- **Backend**: FastAPI. Entry `server.py` registers modular routers from `/app/backend/routes/`.
  All API routes prefixed with `/api`. Auth: JWT via `auth.py` (`require_auth`).
  DB: MongoDB via `motor` (`database.get_db()`). Docs use UUID string `id` + `{"_id": 0}` projections.
- **Frontend**: React + Shadcn/UI + Tailwind. Core routing in `App.js`. Multi-portal shell at
  `components/erp/PortalSelector.jsx`; module registry `components/erp/moduleRegistry.js`;
  nav in `components/erp/portal-shell/portalNav.js`.

## Personas
- Super Admin (admin@garment.com) — full access.
- Finance/Accounting staff, HR staff, Production operators, Maklon clients, LiveHost/KOL creators, Vendors.

## Core Finance integration chains (validated)
- Journal → post to GL → Trial Balance (balanced) / GL / P&L / Balance Sheet / Cash Flow → void/reverse.
- AR invoice → payment → cash movement + GL. AP invoice → approval → payment → GL.
- P2P: PR → PO → GRN/3-way-match → AP invoice → payment.
- Fixed Assets: register → depreciation (per + batch) → disposal → GL (via Posting Profiles).
- Accruals → post → reverse → recurring-templates. Budget → items → variance. Periods → close/lock.
- Posting Profiles (33 event_type→GL mappings) drive auto-GL posting across events.

## Kontrak API — aturan yang WAJIB diikuti (ditetapkan FASE 11, 2026-07-25)
- **Query param WAJIB tervalidasi.** Parameter yang dideklarasikan harus memakai batas
  `Query(..., ge=…, le=…)`; yang dibaca manual dari `request.query_params` harus lewat
  `backend/utils/query_guards.py` (`q_int`, `q_date`, `q_year_month`, `q_period`, …).
  **Input sampah = HTTP 400/422, TIDAK PERNAH 500.** Gate: `scripts/sweep_query_robustness.py`
  (sapu seluruh GET endpoint × 8 varian query rusak; harus 0 error 5xx).
- **Tanggal dari Mongo harus dinormalkan.** `datetime` adalah SUBCLASS `date` di Python, jadi
  `isinstance(v, date)` juga True untuk `datetime`. Selalu pakai `to_date()` / `date_key()` dari
  `utils/query_guards.py`; jangan memotong string tanggal dengan `[:10]` tanpa normalisasi.
- **Kode akun jurnal HARUS berasal dari `rahaza_posting_profiles`,** bukan hardcode. CoA proyek ini
  berformat bersegmen (`1-2500`, `2-1100`), bukan 4-digit. Gate: `verify_data_integrity` INV-GL-3.
- **Nama field material memakai nama KANONIK saja** (`composition`, `material_kg_per_pcs`,
  `default_material_cost_per_kg`, `total_material_kg_per_pcs`, `total_material_kg`,
  `bulk_line_count`). Alias legacy `yarn_*` **tidak ditulis lagi** sejak FASE 11; endpoint masih
  MENERIMA nama legacy sebagai input dan `read_field()` masih bisa MEMBACA dokumen lama.
- **Setiap skrip uji WAJIB membersihkan artefaknya lalu MENGHITUNG ULANG untuk membuktikannya** —
  termasuk dokumen turunan (mis. jurnal yang lahir otomatis dari pembuatan aset/invoice).

## Modul lintas-portal yang wajib diketahui (sejak 2026-07)

- **Satuan & konversi (multi-UOM)** — SSOT `backend/core/uom.py`. Stok & HPP SELALU disimpan
  dalam satuan dasar; kemasan (pak/karton/rol) adalah faktor pengali. Titik masuk stok menerima
  field opsional `input_uom`. Mengganti satuan dasar item berstok HANYA lewat endpoint rebase
  (`POST /api/rahaza/materials/{id}/rebase-uom`) supaya qty & HPP ikut dikonversi.
  Guardrail: `scripts/guardrails/verify_uom_integrity.py`.
- **Penomoran dokumen** — SATU generator race-safe `utils/counters.gen_prefixed_number`, kini
  membaca format owner dari koleksi `doc_number_configs` (layar `sys-doc-numbering`).
  Katalog jenis dokumen: `backend/data/doc_number_registry.py`. Format rusak selalu jatuh
  ke bawaan kode — penomoran tidak boleh memblokir transaksi. JANGAN membuat generator kedua.
- **Asisten ERP CV. Dewi Aditya** — jawab dari basis pengetahuan statis
  `backend/data/portal_kb/*.json` lebih dulu (gratis); AI hanya cadangan. Menambah pengetahuan
  = menyunting JSON, bukan menulis kode.
- **Semua panggilan LLM** lewat `ai_cost_tracker.tracked_llm_call` → Anthropic SDK resmi dengan
  `ANTHROPIC_API_KEY`. Dilarang memanggil SDK LLM langsung dari route.

## Status — Juli 2026
**Healthy & stable.** COA 177 akun + 38 posting profiles (semuanya remapped ke CoA DA).
Auto-jurnal coverage 100%: 38 event types aktif (AR/AP/Payroll/Inventory/FA/Bank/Kasbon/Maklon/Variance).
Production seed 100% sukses (0 errors). Periode dinamis (3 bulan terakhir s/d bulan berjalan).
**Audit portal selesai (HR, Finance, Produksi, Gudang, Maklon, Marketing)** — semua modul render
tanpa crash & tabel terisi (testing_agent iteration_20 & 21).
- Gudang/WMS: lokasi, stok+ledger, GRN+inspeksi, fabric rolls, CMT dispatch, surat jalan, opname,
  fulfillment (queue+allocate), retur — semua ber-data (Section 50 seed).
- Maklon: dashboard, PO (dewi_maklon_pos SSOT), sample, invoice+payment, QC, dispatch, klien, catalog.
- Marketing: KOL+Leaderboard (fix 500), LiveHost (fix collection), Target Bulanan (actual dari
  marketing_sales_data), Unified Orders, sales harian.
Regression suite: `/app/backend/tests/` — test_iteration_21 (25), test_p2p_full_cycle (E2E PR→PO→GR→AP→bayar→3-way matched), test_rbac_multiuser (role/portal separation), test_p2p_create_po (13). Semua pass.
**P2P Procurement** full cycle end-to-end OK (3 bug diperbaiki: counter bentrok, propagasi qty GR→PO untuk PO turunan PR via po_item_id, basis pajak 3-way match). Data terhubung ter-seed; dashboard PR/3-Way Match/AP Aging terisi.
**Multi-user RBAC**: 5 role user (hr/accounting/supervisor_produksi/admin_gudang/admin_maklon), portal terpisah; deep-link guard aktif. Lihat test_credentials.md.
**P2 — Approval Badge (TopBar)** [NEW — iteration_23]: Badge clipboard di TopBar menampilkan jumlah item yang perlu tindakan (PR submitted + AP sent/partial_paid + HR pending) berdasarkan peran. Endpoint `GET /api/approval-inbox/badge`. Klik dropdown + navigasi ke modul relevan. Semua role (admin/finance/hr/gudang) menampilkan kategori sesuai aksesnya.
**P3 — Channel GL Mapping UI** [NEW — iteration_23]: Modul 'Channel → Akun GL' di Finance portal (Piutang AR). Menampilkan 13 channel (Shopee 4, TikTok 6, Tokopedia 1, Maklon 2) dengan kode + nama akun Dr/Cr. Filter per platform, edit inline, seed default button. Endpoint CRUD `/api/rahaza/channel-gl-mapping`. Nama akun diambil dari COA `/api/rahaza/coa/accounts`.
**P1 — AI Modules (Cash Flow Prediction + HR Attrition)** [NEW — iteration_24]: EMERGENT_LLM_KEY ditambahkan ke .env. `dewi_cashflow_ai.py` difix (`UserMessage(text=)` + model `gpt-5.1`). HR Attrition batch dikurangi menjadi 10 employees untuk mencegah proxy timeout. SSE auth LiveHost difix (`payload['host_id']` bukan `['sub']`). Semua AI modules berjalan via `gpt-5.1`.
**LiveHost Portal (/livehost)** [NEW — iteration_24]: 4 hosts (ayu/dian/sinta/rani @dewiaditya.id) sekarang punya `password_hash` + `status:active`. Login JWT difix (`_create_livehost_token` signature). Shift field names dinormalisasi (`shift_name→shift_type`, `scheduled_start→shift_start_time`). Notifikasi difix (KeyError: shift_type). Password: `Host@123`.
See CHANGELOG.md for dated changes and ROADMAP.md for backlog.

## Key credentials
See `/app/memory/test_credentials.md` (admin@garment.com / Admin@123).

## Session log — Fase 2 FIX: State machine enforcement + verifikasi RBAC live (Feb 2026)
Temuan verifikasi independen user: PO Draft bisa langsung Closed via /status (200).
- **Keputusan: BUG-FIX (kategori C-1..M-3), bukan port** — referensi sommerville-adopt sendiri hanya
  memvalidasi keanggotaan PO_STATUSES tanpa cek urutan (transition_po_status & close_po unguarded).
  Matrix mengikuti PRODUKSI_TOBE_FLOW_FINAL: Draft→Confirmed→Distributed→In Production→Production
  Complete→(Variance Review ↔ Return Review, opsional/skippable)→Ready to Close→Closed.
  `PO_STATUS_TRANSITIONS` + `PO_CLOSABLE_STATUSES` di production_pos.py; transisi non-adjacent → 400.
  close_po hanya sah dari status pasca-produksi (Production Complete/Variance Review/Return Review/
  Ready to Close); Closed→Closed ditolak.
- **Audit endpoint status lain (hasil per endpoint)**:
  · PUT /vendor-shipments/{id} — SEBELUMNYA bebas $set → kini hanya Sent→Received (nilai lain/mundur 400).
  · PUT /buyer-shipments/{id} — ship_status manual DITOLAK 400 (dikelola otomatis engine dispatch).
  · PUT /material-requests/{id} — keputusan hanya dari Pending (Approved/Rejected); ubah keputusan → 400;
    generic update tidak lagi bisa menyentuh field status (dicegah duplikasi/flip tanpa efek samping).
  · PUT /production-returns/{id} — status forward-only sesuai STATUS_OPTIONS referensi:
    Repair Needed→In Repair→Completed→Shipped Back; mundur/nilai asing → 400.
  · PUT /production-variances/{id} — matrix Reported→(Acknowledged|Resolved)→Resolved; mundur → 400.
  · production_jobs — TIDAK ada endpoint status manual (auto In Progress→Completed via progress) → aman.
  · PUT /buyer-shipment-items/{id}/received — sudah ter-guard qty (I-2/received-based) → aman.
  · Inspeksi dobel — sudah 400 (verified sebelumnya) → aman.
- **RBAC live verified**: cmtvendor@dewiaditya.id (cmt_vendor) → GET vendor-shipments/jobs 200 scoped
  vendor sendiri; POST/DELETE/status production-pos → 403. Lockout login_attempts direset.
  maklon@dewiaditya.id = admin_maklon (BUKAN cmt_vendor) — test_credentials.md diperjelas.
- **Testing**: POC 78/78 PASS (71 + 7 kasus state machine baru), edges 45/45, maklon inti 17/17.

## Session log — Fase 2: Maklon Backend Port identik SOMMERVILLE (Feb 2026)
GREEN LIGHT diberikan; keputusan diratifikasi: F-1 port dari sommerville-adopt (canonical),
F-2 Option A production_pos+business_type='maklon' (satu engine), F-3 semua default AD/VP.
- **Engine SOMMERVILLE diport** (backend-only): `routes/production_pos.py`, `vendor_shipment.py`,
  `production_execution.py`, `exceptions.py`, `buyer_shipment.py` + `core/` + `cascade_delete.py` —
  identik reference, dengan: business_type propagation (PO→shipment→job→dispatch→request→defect→retur→variance,
  fix D4/GDG-1), RBAC-1=B remap (`routes/production_rbac.py`: admin→admin/admin_maklon; vendor→vendor/cmt_vendor
  via vendor_id|cmt_vendor_id; klien_maklon di-deny dari semua endpoint engine), master resolve DA
  (garments|vendor_partners, buyers|dewi_maklon_clients), invariants I-1/I-2/I-3/I-5 + fixes C-1..M-3 +
  received-based caps (phases 17-19) terbawa. Serial endpoints tetap di operations_serials.py (tidak diduplikasi).
- **Bridge finance (FIN-2)**: `routes/production_maklon_bridge.py` — mirror dewi_maklon_pos (id=po_id) +
  Draft AR rahaza_ar_invoices otomatis saat PO maklon Confirmed (hook di create/transisi/quick-complete);
  post-ar dewi_maklon_finance → JE GL terbukti jalan. Cascade delete membersihkan mirror+draft AR.
- **Klien tracking**: `routes/maklon_client_tracking.py` — GET /api/maklon-client/pos + /pos/{id}/tracking
  (progress per item + dispatch bertahap), scoped buyer_id.
- **Seeder AD-4**: POST /api/seed/maklon-full (fresh re-seed, idempoten).
- **Dipertahankan dari DA**: variance post-gl/retry-posting (merged ke exceptions.py),
  stage-qty/stage-summary (`routes/production_stage_tracking.py`, dipakai RahazaOrdersModule aktif).
- **Router lama diarsip**: routes/_archive/pre_sommerville/ (production_po, production(+jobs/progress/
  returns/variances/work_orders), backup).
- **Testing**: POC `tests/flow_maklon_sommerville_test.py` 71/71 PASS (happy path penuh, I-1/I-3/C-1 guards,
  variance OVER/UNDER, RBAC, E11 REQ-RPL→child shipment -R1→child job, finance JE). Regression 10 flow suites
  PASS (maklon inti/cmt/client-portal, produksi inti/material-wo/qc-rework*, keuangan AR/jurnal, gudang outbound,
  aksesoris). *qc-rework test diperbaiki: assertion global → delta (endpoint flow-summary tanpa window tanggal,
  pre-existing, bukan regresi port).
- **NEXT**: FE Maklon (batch build sesuai PREVIEW_STABLE_MODE) → Fase 3 Produksi internal + adapters E10 →
  Fase 4 hapus rahaza multi-stage (D1-D5) → Fase 5 bridges + full test. Lalu: analisis flow bisnis Portal
  Marketing (fase analisis terpisah, sudah diminta user).

## Session log — Discovery & Code Review (Feb 2026, fresh environment)
- Environment re-setup from scratch: /app hanya berisi template → cloned `sadkasdlsha/da` ke /app;
  reference repo `msajsjfaskf/sommerville-adopt` di-clone ke `/app/refs/sommerville-adopt` (reference only, TIDAK di-serve/build).
- Env recreated (gitignored): backend/.env (JWT_SECRET generated, EMERGENT_LLM_KEY="" — AI modules 503, deferred),
  frontend/.env (REACT_APP_BACKEND_URL preserved + GENERATE_SOURCEMAP=false + DISABLE_ESLINT_PLUGIN=true).
- PREVIEW_STABLE_MODE dipatuhi: FE = static bundle (rebuild_frontend.sh, build OK 56s), NO dev server.
- Verified: backend+mongo+static FE RUNNING; login admin + 5 role accounts 200; `GET /api/openapi.json` 200;
  seed `production-full` + `rahaza/seed-demo` sukses; login page renders (screenshot).
- `memory/test_credentials.md` hilang (gitignored) → dibuat ulang.
- Discovery report A–F delivered (semua dokumen acuan Sommerville adoption + E1–E11 dibaca; gap analysis disusun).
- NEXT: eksekusi adopsi menunggu lampu hijau user — Fase 2 (Maklon identik SOMMERVILLE) → Fase 3 (Produksi internal + adapters E10)
  → Fase 4 (hapus rahaza multi-stage D1–D5) → Fase 5 (bridges + full test). Backend-first, batch FE build, UI testing di akhir (strategi 2GB).

## Session log — FASE 3: Produksi Internal + adapters E10 (Feb 2026) — SELESAI, ALL PASS
- **Engine sama, business_type="internal"**: PO internal via `production_pos.py` + adapter
  `routes/production_internal_adapter.py` (D3 model_id FK wajib → rahaza_models; ACC-1=A po_accessories
  auto-explode dari BOM; GDG-2=A MI draft-from-job → gudang konfirmasi → stok SSOT rahaza_material_stock;
  HR-1 progress optional operator_id+process_id → mirror rahaza_wip_events shape payroll (employee_id,
  event_type=complete, qty_done, rate_per_pcs, event_date) → payroll per-pcs existing TETAP jalan;
  AD-2 overhead rate×produced; AD-3 job Completed → HPP snapshot per job (anchor job_id) + JE WIP→FG;
  FIN-1/E10 COGS per dispatch buyer shipment; MKT-1=B from-order→PO internal; MKT-2 catalog model_id FK).
- **Fix posting hooks (rahaza_posting.py)**: `post_wip_to_fg_on_job_complete` & `post_cogs_on_buyer_dispatch`
  disesuaikan ke pola engine existing — mapping keys `debit_fg_inventory`/`credit_wip`
  (profile wip_to_fg_on_wo_complete) dan `debit_cogs_material/labor/overhead`+`credit_fg_inventory`
  (profile cogs_shipment, split per komponen HPP snapshot job, qty/qty_completed), lines pakai
  `account_code`, signature positional `_create_posted_je(db, je_date, memo, source_module, source_ref,
  lines, user)`. TIDAK ada engine/profile posting baru.
- **KEPUTUSAN (data fix, didokumentasikan sesuai arahan user)**: profile existing
  `cogs_shipment.debit_cogs_overhead` di DB menunjuk `5-3000` "HPP Overhead Pabrik" yang di CoA aktif
  adalah HEADER (is_group, punya anak 5-3100..5-3400) → non-postable. Diubah via update data ke `5-250`
  "Biaya Overhead Pabrik (BOP)" (postable) — nilai IDENTIK dengan `DA_POSTING_PROFILES` di kode
  (rahaza_posting_profiles.py L513). Catatan laten: `DEFAULT_PROFILES` seed masih berisi 5-3000,
  hanya berlaku jika DB kosong di-seed ulang dari template default.
- **Fix script POC (bukan produk)**: `tests/flow_internal_sommerville_test.py` bukti payroll dibaca via
  `GET /api/rahaza/payroll-runs/{id}` (response POST create = header run saja, by design existing);
  cleanup payslips per run_id ditambahkan.
- **JE evidence (POC)**: WIP→FG job internal → Dr 1-1404 FG / Cr 1-1403 WIP, nilai = Σ JE material issue
  (basis MI, fallback HPP snapshot), source_module=production_job, source_ref=wip_fg_job:{job_id}, idempoten.
  COGS dispatch → Dr 5-1000 (material) + Dr 5-2000 (labor) + Dr 5-250 (overhead) / Cr 1-1404 FG,
  source_module=buyer_dispatch, source_ref=cogs_job:{shipment_id}:seq{n}, idempoten per dispatch seq.
- **Testing**: POC `tests/flow_internal_sommerville_test.py` **41/41 PASS** (D3 FK, ACC-1, allowed_next
  Draft=['Confirmed'], GDG-2 gate+stok, HR-1 mirror+payroll pcs 10×500=5.000, AD-3 WIP→FG, COGS 2 dispatch
  idempoten per seq, MKT-1/MKT-2, state machine internal Draft→Closed→400). Regression penuh PASS:
  maklon sommerville 78/78, maklon edges 45/45, maklon_inti 17/17, cmt_vendor ALL, client_portal 29 ALL,
  alur_produksi_inti 18/18, qc_rework ALL, keuangan jurnal/AR/AP ALL, kas_bank 30 ALL, sdm_payroll ALL.
  (Catatan test env: login rate-limit 10 req/60s per IP → antar-suite perlu jeda.)
- **FE Fase 3 BELUM dibuild** (sesuai scope backend-only). NEXT: FE Produksi Internal (batch build sesuai
  PREVIEW_STABLE_MODE) → Fase 4 hapus rahaza multi-stage (D1-D5) → Fase 5 bridges + full test.

## Session log — FASE 4: Hapus engine rahaza multi-stage / D1-D5 (Feb 2026) — backend only
- **Router diarsip → `routes/_archive/rahaza_multistage/` (23 file)**: rahaza_work_orders,
  rahaza_bundles(+mgmt/docs/rework/backup), rahaza_execution, rahaza_andon, rahaza_aps(+scheduler),
  rahaza_qc_v2 (qc_events+defect_codes, QC-2=BUANG), rahaza_oee, rahaza_line_monitoring
  (+services/line_monitoring_service.py), rahaza_tv, rahaza_rework, rahaza_lkp, rahaza_wizard,
  rahaza_backlog, rahaza_material_reservation (per-WO), dewi_cutting, qc.py & finishing.py
  (engine template lama, dead D5, 0 pemanggil FE). Total 139 endpoint dihapus dari openapi.
- **server.py**: import+include router arsip dicabut; create_index koleksi DELETE dihapus
  (lines, line_assignments, WO, bundles, andon, qc_events, defect_codes, reservations, lkp, cutting);
  wip_events & material_issues re-index `job_id`; **fix laten index**: rahaza_hpp_snapshots unique
  work_order_id (non-partial, bentrok null utk snapshot per-job) → partial unique job_id + partial
  unique work_order_id; /api/metrics hitung production_pos+production_jobs (bukan WO).
- **Bedah file KEEP**: dewi_maklon._sync_wo_status → no-op stub; dashboard_routes avg_oee=None
  (OEE engine gone); rahaza_alerts hapus Andon SLA check; rahaza_inventory_issues hapus endpoint
  `POST /material-issues/draft-from-wo` (diganti draft-from-job Fase 3); rahaza_hpp hapus
  `GET/POST /hpp/work-order/{wo_id}(/snapshot)` (HPP per job di production_internal_adapter).
- **Hardening**: (a) post-gl variance body kosong → 404/400, BUKAN 500 (terverifikasi curl);
  (b) seed DEFAULT_PROFILES cogs_shipment.debit_cogs_overhead 5-3000 (header) → 5-250 (BOP).
- **Data drop (SETELAH mongodump ke /app/backups/fase4_20260713/, reversible, README ada)**:
  rahaza_work_orders(25), rahaza_bundles(45), rahaza_qc_events(27), rahaza_defect_codes(8),
  rahaza_andon_events(0)+settings(1), rahaza_lines(12), rahaza_line_assignments(100),
  rahaza_material_reservations(0), rahaza_lkp(0), dewi_cutting_requests(0)+batches(0).
  Dibiarkan (KEEP/REPURPOSE): material_stock/materials/issues, wip_events, hpp_snapshots,
  costing_settings, processes, machines, shifts, payroll/attendance, wms_*, finance, variances.
- **Referensi pasif yg dibiarkan (baca koleksi dropped → hasil kosong, tidak error)**: dashboards/
  reports/analytics_ai/ai_aggregates, production_stage_tracking, universal_scan (branch WO/bundle),
  production_control_tower, shift_handover, rahaza_shipments/hpp maklon-order lama, seeder lama
  (production_seed_full/demo_seed masih tulis koleksi lama JIKA dipanggil — akan diganti fresh
  re-seed final Fase 5).
- **Test lama diarsip → tests/_archive/**: flow_alur_produksi_inti, flow_produksi_qc_rework,
  flow_produksi_cutting, flow_produksi_aps. GAP COVERAGE: QC/defect kini via material_defect_reports
  (tercakup suite maklon: inspeksi, defect, retur, rework); cutting/aps/andon TIDAK punya padanan
  di engine baru (by design E10 — multi-stage dibuang). flow_maklon_edges_test diupdate: cek
  flow-summary (engine lama) → cek /api/production-jobs.
- **FE terdampak (29 komponen, INPUT FASE 5 — belum disentuh)**: lihat daftar di laporan Fase 4
  (RahazaWorkOrdersModule, RahazaBundlesModule, BundleReworkBoard/ScannerModal/DetailPage,
  ProcessExecutionModule, QuickInputPanel, SimpleDailyInputModule, OperatorView, AndonPanel/Board,
  APSGantt/AutoScheduleDialog, RahazaFPY/Pareto/DefectCodes, OeeDashboard/RahazaOEE,
  LineMonitoringModule, ShopFloorTV, ReworkAnalytics, LKPDialog, ProductionWizardModule,
  RahazaBacklogModule, RahazaMaterialReservationModule, CuttingProcessModule, DOManagementModule,
  RahazaHPPModule (hpp/work-order), RahazaMaterialIssueModule (draft-from-wo),
  RahazaBulkMIModule, RahazaLineAssignmentsModule, bundleTickets.js).
- **Follow-up temuan testing agent (iteration_95, minor)**: penulis aktif terakhir koleksi WO =
  dewi_maklon_pos.py (confirm insert WO legacy + cancel update WO) → dimatikan; wo_number tetap
  digenerate sebagai nomor tracking item (kompat response `work_orders_created` & FE). Test
  flow_maklon_inti_test TC-06 diupdate (verifikasi wo_number tracking + WO collection TIDAK dibuat)
  → 17/17 PASS; koleksi rahaza_work_orders terverifikasi GONE pasca run. Penulis tersisa hanya
  SEEDER lama (rahaza_demo_seed/rahaza_admin_seed/production_seed_full — manual, diganti fresh
  re-seed final Fase 5) + reads pasif (tidak menciptakan koleksi).
- **Regression Fase 4 (16 suite, ALL PASS)**: internal 41, sommerville 78, edges 45 (1 check
  diupdate ke engine baru), maklon_inti 17, cmt_vendor 17, client_portal 29, payroll ALL
  (26 slips + JE finalize/payment; fix bug test pre-existing: parsing key `items` GET employees),
  gudang inbound 16 / outbound 9 / opname 14, keuangan jurnal 11 / AR 7 / AP 7 / kas-bank 30,
  material_wo 11, aksesoris 21. Verifikasi independen testing agent (iteration_95): 100% —
  openapi 17/17 pola arsip bersih + 9/9 KEEP hadir + 4/4 curl + 164/164 flow tests.

## FASE 5 (FINAL) — SELESAI (2026-07-13)
- **Backend**: bridges selesai + fresh re-seed FINAL (AD-4) via POST /api/seed/maklon-full
  (idempoten): maklon PO-MK-DEMO-1/2 + internal PO-INT-DEMO-1/2/3 + master DA-TS01/BOM/stok/
  operator borongan. test_credentials.md diupdate. Seeder lama diarsip (410).
- **Frontend (1 batch, 1x rebuild via scripts/rebuild_frontend.sh)**: UI Portal Produksi & Maklon
  di shell DA (moduleRegistry), tombol aksi status dinamis dari allowed_next
  (ProductionPOModule.jsx L824-841, data-testid po-action-{status}), VendorCMTEnginePortal.jsx
  (/vendor-cmt, login scoped cmt_vendor → VendorPortalApp 11 menu), ClientMaklonPortal.jsx
  (/klien-maklon, tracking read-only klien_maklon), 29 komponen mati Fase 4 + 81 redirect mati
  moduleRegistry dibersihkan.
- **Regression pasca re-seed**: internal 41/41 + maklon 78/78 PASS (flow_internal_sommerville_test,
  flow_maklon_sommerville_test).
- **UI E2E penuh (iteration_96)**: 5 skenario PASS — (1) admin create PO internal + allowed_next
  live Draft→Confirmed→Distributed; (2) portal maklon list/detail; (3) vendor CMT scoped
  (negative login reject + 4 modul render); (4) klien read-only (0 tombol mutasi); (5) sweep
  20 menu (13 produksi + 7 maklon) 0 blank/0 fatal console error/0 module-not-found.
- **Fix minor pasca-E2E (backend-only, tanpa rebuild)**: /api/vendor/dashboard 403 utk cmt_vendor —
  guard legacy role 'vendor' → is_vendor()/vendor_identity() dari production_rbac.py
  (dashboard_routes.py L392). Verified: dashboard vendor tampil metrics, 0 console error.
- **By-design (backlog P2)**: detail modal PO maklon tidak embed info job (JOB-*) — job dikelola
  via modul 'Production Jobs' terpisah di sidebar. Opsional: panel job di detail PO.
- **Data demo pristine**: 5 PO demo persis; artefak uji PO-MK-TEST-VERIFY-1 dihapus (cascade).

## FIX: Akses Absen Geo dari Portal Saya (2026-07-13)
- Laporan user: "tidak ada tombol/menu absen di portal saya" → KASUS A (gap discoverability,
  bukan fitur hilang). Fitur absen geo LENGKAP dan hidup di route /absen (AbsenPage.jsx:
  selfie+geolocation+AI, WebAuthn, login mandiri; BE rahaza_attendance.py clock-in/out +
  geofence Haversine vs rahaza_office_locations, suite selfie/webauthn/zkteco terdaftar).
  Jalur lama self-service (OperatorView) diarsip Fase 5 tanpa pengganti akses di portal.
- Fix minimal: tombol "Absen Sekarang" (data-testid=absen-now-btn) di kartu profil
  SelfServicePortal.jsx (Portal Saya / self-dashboard) → window.location /absen.
- Catatan insiden: frontend/build/ ditemukan HILANG (tersapu proses eksternal pasca
  git squash/Save-to-GitHub) → dipulihkan bersamaan 1x rebuild fix ini.
- Verified E2E: /absen login hr@ → status hari ini tampil; Portal Saya → tombol muncul →
  klik → /absen. 0 fatal console error.

## Session log — FASE 6.6 + FASE 8 (2026-07-25, environment dari repo `hanababama/da`)

**Konteks**: user meminta melanjutkan development dari repo GitHub `hanababama/da` dengan verifikasi + menjalankan
guideline. Environment dipulihkan (clone → rsync → `bootstrap.sh` → build static bundle), baseline diverifikasi
(`verify_acc123.py` 62 PASS), lalu dua fase dikerjakan sesuai pilihan user.

### FASE 6.6-A — Rekonsiliasi baris stok skema lama A/B/C
- **Kenapa**: `rahaza_material_stock` historis punya 3 bentuk baris — A (kanonik `location_id`+`qty`),
  B (lokasi BERSARANG + `total_qty`, domain aksesoris lama), C (tanpa lokasi + `available_quantity`, alur FG/CMT).
  Writer sudah satu pintu sejak FASE 2, tapi baris warisan membuat layar per-lokasi kehilangan stok, memunculkan
  baris kembar, dan `available_quantity` basi (risiko over-allocation).
- **Apa**: `core/stock_reconcile.py` (7 detektor + scan/reconcile/rollback/logs, jurnal
  `wh_stock_schema_reconcile_log`), `routes/wms_stock_schema.py` (`/api/wms/stock-schema/*`),
  `migrations/migrate_reconcile_stock_schema.py`, FE `StockSchemaHealthModule.jsx`
  (modul `wh-stock-schema` + tab "Kesehatan Skema" di hub `wms-stock-hub`).
- **Jaminan**: total on-hand TIDAK berubah; `negative_qty` & `orphan_material` hanya dilaporkan (butuh
  Opname/Penyesuaian resmi); setiap eksekusi bisa di-rollback presisi.
- **Bug nyata**: UNIQUE index (material_id, location_id) ⇒ urutan operasi harus hapus-dulu-lalu-tulis.

### FASE 6.6-B — Rename internal `yarn_*` → field netral (alias kompatibilitas)
- SSOT `core/material_fields.py` + `frontend/src/lib/materialFields.js`. Kanonik baru: `composition`,
  `material_kg_per_pcs`, `default_material_cost_per_kg`, `total_material_kg_per_pcs`, `total_material_kg`,
  `bulk_line_count`. **Alias legacy tetap ditulis** ⇒ dok DB lama, laporan, dan integrasi tidak pecah.
- 13 file backend + 9 file frontend dialihkan; migrasi backfill `migrate_rename_yarn_fields.py`
  (`--discover`/`--execute`/`--rollback`). Label UI Indonesia: "Jenis/Komposisi", "Bahan utama/pcs (kg)",
  "Total bahan (kg)", "Default Bahan/kg", "N bahan" (bukan "N benang").

### FASE 8 — Valuasi HPP Aksesoris
- `core/accessory_valuation.py`: moving average (WAC) saat penerimaan, koreksi HPP manual, ringkasan valuasi,
  riwayat HPP (`rahaza_material_cost_history`).
- Mutasi aksesoris kini BERNILAI + berjurnal: terima → `inventory_receive`; keluar → `post_accessory_issue`
  (Dr WIP / Cr Persediaan); **scrap (endpoint BARU `POST /api/acc/stock/scrap`)** → `inventory_adjust`
  reason=scrap (Dr Beban Scrap 6-4300 / Cr Persediaan). Posting non-fatal & transparan (`je.posted` + alasan).
- `routes/dewi_accessories_valuation.py` (`/api/acc/valuation*`), KPI dashboard `total_stock_value` +
  `unvalued_items`, FE tab "Valuasi HPP" (+ ledger mutasi bernilai & riwayat HPP), input harga di modal Terima.
- `core/stock_rbac.py` menjadi SSOT role operasi stok (dipakai karantina + scrap aksesoris).

### FASE 8.8 — Panduan drop koleksi legacy
- `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` (prinsip, 4 grup kandidat + status, prasyarat, checklist) +
  `migrations/drop_legacy_collections_guided.py` (audit → dry-run → arsip → drop → rollback → purge).

### Bukti
`verify_fase66.py` 48/48 · `verify_fase8.py` 48/48 · `verify_acc123.py` 62/62 ·
`verify_phase6_quarantine.py` 48/48 · testing_agent_v3 iteration_169 backend 100% & 0 critical ·
verifikasi UI manual Playwright untuk semua alur tulis (rekonsiliasi, Set HPP, Scrap, Terima bernilai) ·
FE lint 0 error · ruff 0 issue (file baru) · `yarn build` Compiled successfully · DB kembali ke baseline.

### FASE 10 — Otomasi Valuasi Aksesoris + Penutupan Domain Legacy (2026-07-25, lanjutan #3)
**1. Ringkasan alarm harian "belum dinilai".** `GET /api/acc/valuation/unvalued-digest` (pratinjau) +
`POST .../send` + job `daily_unvalued_digest` **07:30 WIB**: SATU notifikasi berisi SELURUH aksesoris
ber-HPP 0 (kode, nama, stok, jumlah mutasi 24 jam) ke role penanggung jawab, idempoten 1×/hari.
Notifikasi **per-item tetap jalan** (anti-spam 1×/24 jam per material) — digest adalah TAMBAHAN, bukan
pengganti (pilihan user).

**2. Rapor valuasi bulanan otomatis via email.** `services/accessory_valuation_mailer.py` +
`utils/email_sender.py` (smtplib bawaan, tanpa dependensi baru). Job `monthly_valuation_report_email`
**tanggal 1 pukul 06:00 WIB**: rapor periode bulan lalu, lampiran **Excel + PDF**, penerima = role
keuangan/accounting + `valuation_report_extra_emails`. Idempoten per periode (kecuali tombol "Kirim
sekarang"). Riwayat di `acc_valuation_report_runs`. **SMTP dikonfigurasi lewat UI** (Pusat Notifikasi →
Konfigurasi Provider: host/port/user/`smtp_security` starttls|ssl|none). Bila SMTP belum diisi, rapor
TETAP dibuat dan ringkasannya dikirim sebagai notifikasi in-app dengan status `skipped_no_smtp` —
tidak pernah gagal senyap. UI: tab **Valuasi HPP** → panel `acc-val-automation`.

**3. Prasyarat drop `accessory_legacy` TUNTAS.** `acc_internal_requests` & `acc_loans` sudah tidak punya
jalur tulis/baca aktif: endpoint `/api/acc/internal-requests/*` dan `/api/acc/loans/*` → **410**;
logika pemotongan stok diangkat ke `core/accessory_issue.py` (`check_availability` + `issue_accessory`)
dan dipakai `POST /api/dewi/accessory-requests/{id}/deliver` (validasi semua baris dulu, idempoten,
"stok tidak cukup" → 400); tab "Peminjaman" dilepas dari UI; pinjaman lama ditutup otomatis via
`migrations/close_legacy_acc_loans.py` (stok dikembalikan, bisa rollback); KPI dashboard `active_loans`
→ `ready_to_deliver`. Grup kini **[SIAP]** di `drop_legacy_collections_guided.py --audit`.

**4. Modal menggantikan dialog native TERAKHIR.** `OpnameActionModal` (submit/cancel/approve/reject)
dengan validasi inline "Alasan wajib diisi…" + modal hapus aksesoris. **Tidak ada lagi
`window.prompt`/`confirm`/`alert` di modul Aksesoris.**

**5. Perbaikan integritas stok (BUG-1, kritis).** `core/accessory_stock.issue_across_locations()`:
pengeluaran aksesoris kini memotong **lintas lokasi** (lokasi kanonik dulu, lalu baris terbesar; baris
warisan lokasi-bersarang lewat `issue_row`). Sebelumnya pembaca mengagregasi semua lokasi tetapi penulis
hanya satu lokasi ⇒ **HTTP 500** untuk item yang stoknya duduk di lokasi lain (data warisan/put-away/seed
demo). Ikut memperbaiki `/acc/stock/issue`, `/scrap`, SSOT `deliver`, dan `approve` opname.

**6. Transparansi opname (BUG-2).** `approve` kini melaporkan `stock_failed` + `stock_failed_items`
(sebelumnya baris gagal di-`continue` diam-diam sehingga sesi tampak "Completed" padahal selisihnya tidak
pernah diterapkan). UI menampilkan baris merah beserta detail penyebabnya.

**Bukti:** 402 PASS / 0 FAIL pada 9 skrip verifikasi · `testing_agent_v3` iteration_173 0 critical/0 minor ·
verifikasi UI manual Playwright untuk seluruh alur tulis · FE lint 0 error · `yarn build` sukses ·
DB kembali ke baseline demo (10 item · Rp 9.667.750 · 8 bernilai / 2 belum dinilai).

---

# ADDENDUM — FASE IA (2026-07-26): Restrukturisasi IA, Portal Cutting, Seed Data Nyata

## Peta Portal (14)
| Portal | id | Catatan |
|---|---|---|
| Manajemen | `management` | **Khusus eksekutif** — 2 section (Ringkasan Eksekutif, Strategi & Approval) |
| **Administrasi Sistem** | `sysadmin` | **BARU** — split dari Manajemen. Akses: `super_admin` + `admin` saja. 2 section: Akses & Audit, Sistem & Data (termasuk pintu **Backup Data**) |
| Produksi | `production` | tidak berubah |
| **Cutting** | `cutting` | **BARU** — roll kain ➜ kain pola (potongan). 3 pintu: Dashboard, Order Cutting, Master Potongan |
| Gudang | `warehouse` | `wh-material-issue` dipindah ke section OUTBOUND |
| Aksesoris | `accessories` | 3 section ➜ **1 section** (7 pintu) |
| Keuangan | `finance` | disusun ulang mengikuti **siklus uang** (6 section, 24 pintu utuh) |
| SDM / HRIS | `hr` | **3 section**: Manajemen Karyawan (8) · Manajemen Organisasi (8) · Analitik & Laporan (8) |
| Maklon | `maklon` | +pintu **Komponen Kurang** (`cmt-component-requests`) yang sebelumnya tak punya menu |
| Marketing | `toko` | tidak berubah |
| RnD | `rnd` | tidak berubah |
| Manajemen Aset | `assets` | **`singleDoor: true`** — sidebar & pill disembunyikan, navigasi via tab modul |
| Kolaborasi | `collaboration` | tidak berubah |
| Portal Saya | `self` | tidak berubah |

## Aturan IA yang WAJIB dipatuhi (dijaga `scripts/guardrails/check_nav_map.py`)
- Navigasi **datar 2 tingkat**: Section → Pintu (guard `NAV-FLAT`).
- Section: **≥2 pintu** (`NAV-SINGLE`) dan **≤8 pintu** (`NAV-MAX`).
- Label pintu: tanpa tanda kurung, ≤3 kata, bukan HURUF BESAR semua (`NAV-LABEL`).
- Satu isi tidak boleh punya dua pintu di portal yang sama (`NAV-DUPTAB`).
- Semua id menu wajib ada di `moduleRegistry.js` (`NAV-GHOST`).
- **BARU `NAV-SOLO`**: portal ber-flag `singleDoor: true` wajib benar-benar 1 section × 1 pintu.
- moduleId lama TIDAK dihapus saat menu dirombak → deep-link (`/#<id>`) tetap hidup lewat
  `moduleRegistry.js` + `App.js LEGACY_MODULE_TO_PORTAL` + heuristik prefix.

## Modul Cutting (`/api/cutting/*`, `backend/routes/cutting.py`)
State: `draft → in_progress → completed` (`cancel` hanya bila belum ada progres).
- Koleksi: `cutting_orders`, `cutting_progress` (indeks dibuat saat startup agar SELALU ter-backup).
- Mutasi stok **hanya** lewat SSOT `core/stock_service.py` (`issue` kain, `add` potongan)
  → `rahaza_material_stock` + `rahaza_stock_ledger` tetap satu kebenaran.
- Output potongan = dokumen `rahaza_materials` baru: `is_cut_panel: true`, `type: fabric`,
  `unit: pcs`, `category: POTONGAN`, `source_material_id`, kode `CUT-<STYLE>-<WARNA>-<SIZE>` (idempoten).
- **Stok disimpan per (material, lokasi)** — order cutting WAJIB memakai gudang yang benar-benar
  memegang stok. `/input-materials` mengembalikan `stock_locations` + `best_location_id`;
  `start` memvalidasi per-lokasi dan mengalihkan order ke gudang berstok bila perlu.
- HPP potongan = (kain terpakai × harga kain) ÷ potongan jadi, ditulis ke `unit_cost` saat complete.
- Bukti alur: `scripts/poc_cutting_flow.py` & `scripts/poc_cutting_flow_v2.py` (keduanya LULUS).

## Data
- Seed demo lama **dihapus total**. Master data nyata dari 7 Excel owner di-seed lewat
  `scripts/seed_da_master_from_excel.py [--wipe] [--no-stock]`.
- Isi: 25 karyawan (+akun login, payroll profile, tunjangan), 6 lokasi kerja, 7 unit organisasi,
  18 posisi, 143 kain, 335 aksesoris, 553 barang jadi, 55 model produk (+spek), 19 style techpack,
  58 vendor CMT, 8 akun marketplace + target.
- **Transaksi sengaja kosong.** Saldo awal stok ditandai `saldo_awal` di ledger.
- Batas ambil dokumen master: `MASTER_FETCH_LIMIT = 20000` (dulu `.to_list(500)` memotong data senyap).

---

# ADDENDUM 2 — Notifikasi Berkategori, RBAC, Light Mode (2026-07-27)

## Light mode = default
`ThemeProvider defaultTheme="light"` + `getSystemTheme()` selalu `'light'`.
**Akar masalah "kartu tanpa background":** di light mode `--card-surface` dulu
`rgba(255,255,255,0.82)` di atas latar terang ⇒ kontras kartu↔latar ~nol.
Sekarang: `--card-surface: #FFFFFF` (solid), `--glass-border: rgba(15,23,42,0.14)`,
`--shadow-card` diperkuat (hairline 1px + soft shadow). Perbaikan di level TOKEN
sehingga berlaku untuk seluruh GlassCard/GlassPanel/tabel di semua portal.

## Notifikasi berkategori (`backend/routes/notification_categories.py`)
- Kategori = **portal sumber** (11: Gudang, Produksi, Cutting, Maklon, Keuangan,
  SDM, Marketing, Aksesoris, Aset, RnD, Sistem). Diturunkan saat baca dari
  `link_module` (prefix) → `type` ⇒ **notifikasi lama tidak perlu migrasi**.
- Bel = ringkas (hitungan per kategori + 3 terbaru) → tombol **Lihat Semua**
  membuka popup **Pusat Notifikasi** (filter kategori, tandai dibaca, lompat modul).
- `notif_category_config`: matriks **kategori × role** (pintu admin `#sys-notif-config`
  di Portal Administrasi Sistem). Default diturunkan dari `PORTAL_ACCESS`
  supaya tidak ada sumber kebenaran RBAC kedua. SUPER_ROLES selalu menerima semua.
- `notif_user_prefs`: user boleh **membisukan** kategori untuk dirinya sendiri,
  tapi tidak bisa membuka kategori yang ditutup admin.
- Endpoint: `/api/notifications/{categories,categorized,category-config,my-category-prefs}`.

## RBAC di-wiring ulang (FE `portalAccess.js` ⇄ BE `routes/shared.py`, identik)
- `rnd_staff` & `marketing_kol` **dicabut** dari portal `management` (kini khusus eksekutif).
- Portal `cutting` & `sysadmin` ditambahkan di kedua sisi; `sysadmin` = SUPER_ROLES saja.
- `admin_gudang` ditambahkan ke `assets` (dia yang memegang alat/aset fisik).
- Terverifikasi: user role `hr` hanya bisa membuka SDM + Portal Saya + Kolaborasi;
  11 portal lain terkunci; endpoint admin menolak dengan 403.

## Standar UI Light Mode — Tabel, Kartu & Tombol (2026-07-27)
Keluhan owner: di light mode tabel "tidak punya background kartu" (baris menyatu
dengan latar), tombol memakai warna mentah, dan teks abu terlalu pudar.

**Keputusan produk:**
- Setiap tabel WAJIB berdiri di atas permukaan kartu solid (`--card-surface`,
  putih di light mode) dengan hairline `--glass-border`, radius `--radius-lg`,
  dan `--shadow-card`.
- Tombol aksi utama WAJIB memakai token `hsl(var(--primary))` +
  `hsl(var(--primary-foreground))` — dilarang memakai `bg-blue-500` dkk.
- Badge/status TETAP memakai warna semantik, tapi versi soft (pastel + teks
  gelap) supaya sinyalnya terbaca.
- Kartu KPI memakai komponen `StatCard` (putih + aksen tipis di kiri), bukan
  blok pastel penuh.
- Dark & Classic mode tidak boleh terpengaruh: semua aturan baru di-scope
  `html.light`.

**Implementasi:** `frontend/src/components/ui/data-card.jsx` (DataCard,
DataCardHeader, DataTableShell, StatCard, EmptyRow) + baseline CSS global di
`frontend/src/index.css`. Detail lengkap & cara regenerasi ada di
`memory/HANDOFF_UI_TABEL.md`.

---

# ADDENDUM 3 — Impor Data Produksi Internal & Maklon dari Excel owner (2026-07-31)

**Sumber:** `data_import/DATA_PRODUKSI_MAKLOON_SPLIT_3.xlsx` (5 sheet). User minta impor
data produksi **internal (INVOICE DA)** & **maklon (INVOICE AE)**, cek kesesuaian dulu,
master lain boleh dibuat. Keputusan user: No PO→PO, No Invoice→serial(SN); snapshot (tanpa
rincian tiap setor, "sudah di tahap kirim ke DA"); auto-create master yang belum ada (CMT +
produk), CMT kosong→placeholder; dashboard Kejar CMT TIDAK diubah (fokus maklon); fokus 2 sheet.

**Pemetaan ke koleksi kanonik (dibaca `services/cmt_kejar.py` + `cmt_intake.py`):**
- `No PO` (PO-DA-xxx/PO-AE-xxx) → `production_pos.po_number`; `business_type` internal|maklon.
- `No Invoice` → `po_items.serial_number` (1 PO = banyak SN, sesuai dukungan SN sistem).
- `Jml Order` → `po_items.qty` = `vendor_shipment_items.qty_sent` (potongan dikirim ke CMT).
- `Total Disetor`→`cmt_receipt_lines.qty_shipped_by_cmt`; `Diterima Bersih`→`qty_actual`;
  `Reject Potongan`→`reject_qty`. `cmt_receipts.status='Approved'` (snapshot, `kali_setor`=1/PO).
- Nilai monitoring asli Excel disimpan utuh di `po_items.excel_*` (total_disetor, reject,
  retur_penjahit, diterima_bersih, sisa_potongan, kali_setor, status, alert, deadline, tgl_kirim).
- `Nama CMT` → `vendor_partners` (vendor_id PO + shipment + receipt). `Koh Tri (SnBM)` dibuat
  di `dewi_maklon_clients` sebagai buyer maklon; internal customer_name="DA Group (Internal)".

**Importer:** `scripts/import_produksi_maklon_from_excel.py` — **idempoten** (semua dok bertanda
`import_source='excel_produksi_maklon_v1'`, dibersihkan lebih dulu saat re-run; master yang
dibuat import juga bertanda & hanya itu yang dibersihkan — seed asli tidak disentuh).
**Insert langsung** ke koleksi kanonik → TIDAK memicu efek samping finance (draft AR maklon),
BOM explode internal, atau posting FG-stock. Re-run aman.

**Hasil impor (terverifikasi):** production_pos **89** (internal 53 + maklon 36), po_items **321**,
vendor_shipments 81 (+292 item +81 inspeksi), cmt_receipts 55 (+156 line).
Master auto-create: vendor_partners **+2** (P Aan, P Suratno) & sinkron status 14 + placeholder
`(Belum Ditentukan)`; rahaza_models **+13** (SKU produk belum ada di master); 1 klien maklon.

**Cek kesesuaian (compatibility):** struktur sistem SUDAH SESUAI. Master CMT sebelumnya sudah ada
(58 `vendor_partners`, cocok dgn sheet "daftar CMT"). SKU 44/57 match master lama; 13 dibuat baru.
Sheet **"produk sedang PO" DILEWATI** (100% redundan dgn Internal+Maklon → cegah PO ganda).
"produk buyer" (potongan masuk) invoice 100% overlap → info intake tercermin lewat vendor_shipments.

**Verifikasi:** service `owner_dashboard`/`compute_po_kejar` cocok angka Excel (spot PO-AE-002:
ordered 936 / disetor 935 / bersih 930 / sisa 1); API e2e `GET /api/production-pos`,
`/api/dewi/cmt-kejar/dashboard`, `/api/dewi/cmt-intake/batches` 200; UI **Monitoring CMT** render
(Potongan ke CMT 11.956 · Disetor 6.011 · Sisa 5.945 · 24 TELAT). Static bundle di-rebuild.
**Catatan:** tab "Cek Seri" menandai 7 seri "dobel" — WAJAR karena 1 No Invoice memang tersebar di
beberapa baris warna/ukuran (peringatan read-only, bukan error). Ongkos jahit = 0 (rate tak ada di Excel).

# ADDENDUM — SELISIH KIRIM (SHORT SHIPMENT) CMT→DA & DA→BUYER (2026-08-01)

## Aturan bisnis (ditetapkan owner 2026-08-01)
DUA kasus yang HARUS dibedakan:
* **REJECT** — barang SAMPAI tapi cacat → `produced_qty` vendor tetap, barang masuk karantina QC,
  lalu permak (sendiri / retur CMT). *(sudah ada sejak FASE 1)*
* **SELISIH KIRIM** — barang **TIDAK SAMPAI**. Vendor klaim kirim 100, DA terima 90:
  1. **dokumen = kenyataan** → deklarasi/penerimaan dikoreksi menjadi 90 (klaim asli disimpan terpisah);
  2. 10 pcs = **kewajiban pengirim** (`open`, TANPA batas waktu) → **sisa kirim vendor NAIK 10** supaya
     bisa dikirim ulang; selisih tertutup OTOMATIS saat kiriman ulang selesai QC;
  3. **bukan** klaim finansial otomatis. Keputusan tanggungan (CMT / DA) hanya bila barang dinyatakan
     HILANG — di sisi buyer keputusan itu diambil saat PO ditutup;
  4. koreksi boleh **sepihak Admin DA** + **notifikasi vendor** (tidak ada proses sanggahan).

## Model data
| Koleksi / field | Arti |
|---|---|
| `cmt_short_shipments` (`SEL-CMT-xxxxx`) | dokumen selisih kirim vendor CMT → DA (`open`/`resolved`/`cancelled`, `resolution`, `history`) |
| `buyer_short_records` (`SEL-BYR-xxxxx`) | dokumen selisih kirim DA → buyer (+ `finance_decision`, `stock_returned_at`, `stock_writeoff_at`) |
| `cmt_receipt_lines.qty_claimed_by_cmt` | KLAIM vendor (dokumen asli) |
| `cmt_receipt_lines.qty_shipped_by_cmt` | qty yang BENAR-BENAR sampai (dokumen resmi setelah QC) |
| `cmt_receipt_lines.qty_short` / `short_status` | selisih baris + statusnya |
| `production_job_items.qty_claimed_by_vendor` | Σ klaim vendor |
| `production_job_items.qty_declared` | Σ yang benar-benar sampai (**bukan** klaim) |
| `production_job_items.qty_short_open` / `qty_short_resolved` | kewajiban vendor yang belum / sudah selesai |
| `buyer_shipment_items.qty_claimed_original` | klaim awal sebelum dikoreksi ke qty diterima buyer |
| `buyer_shipment_items.fg_issued_at` / `fg_issued_qty` | penanda idempotensi mutasi stok FG keluar |

## Endpoint
* `POST /api/prod/cmt-receipts/{id}/lines/{lid}/koreksi-hasil-qc` — koreksi qty lolos QC (stok FG ikut).
* `POST /api/prod/cmt-receipts/{id}/lines/{lid}/koreksi-deklarasi` — koreksi klaim vendor (+ rambatan + notifikasi).
* `GET /api/prod/short-shipments` · `POST /api/prod/short-shipments/{id}/resolve`
  (`dikirim_ulang` | `hilang_tanggungan_vendor` | `hilang_tanggungan_da` | `salah_input_dikoreksi`).
* `GET /api/buyer-shorts` · `POST /api/buyer-shorts/{id}/resolve`
  (`dikirim_ulang` | `tanggungan_cmt` | `tanggungan_da` | `dibatalkan`).
* `PUT /api/prod/cmt-receipts/{id}/lines/{lid}` → **409** setelah QC selesai (wajib pakai koreksi resmi).
* `POST /api/production-pos/{id}/close-short` → kini SAH juga dari status `Completed`.

## Invarian & alat
`INV-16` klaim = sampai + selisih terdokumentasi · `INV-17` tidak ada selisih tanpa dokumen ·
`INV-18` tiap dispatch buyer mengurangi stok FG.
Alat: `tests/scenario_selisih_ssot.py` (acceptance 43 cek) · `tests/backend_test_selisih_edge_cases.py` ·
`scripts/repair_selisih_ssot.py --dry-run|--apply` (perbaikan data lama) ·
`scripts/verify_produksi_maklon_invariants.py --audit-only` (audit data nyata tanpa membuat data uji).


---

# SATUAN (UoM) DI TITIK MASUK/KELUAR STOK — 2026-08-05

## Masalah yang diselesaikan
Operator lapangan menghitung barang dalam satuan fisik yang mereka pegang (per **box / rol / pak /
gram / yard**), sementara sistem menyimpan stok dalam **satuan dasar** (INV-UOM-2). Backend sudah
menerima satuan sejak Juli, tetapi LAYARNYA belum punya pemilih satuan sehingga satu-satunya cara
adalah mengetik angka dalam satuan dasar — sumber salah hitung (mis. "3 pak" tercatat 3 pcs).

## Perilaku sekarang
| Layar | Endpoint | Field satuan |
|---|---|---|
| Gudang → Scan Gudang (Scan In) | `POST /api/wms/pending/{id}/scan-in` | `input_uom` |
| Gudang → Penyimpanan (Put-away) | `POST /api/wms/putaway/place` | `input_uom` |
| Gudang → Opname Scan | `POST /api/wms/opname3/scan` | `input_uom` |
| Gudang → Pengeluaran Material | `POST/PUT /api/rahaza/material-issues` | `items[].qty_uom` |
| Aksesoris → Master & Stok (terima/keluarkan) | `POST /api/acc/stock/{receive,issue}` | `input_unit` (base \| pack \| kode satuan) |
| Aksesoris → Stok Opname | `PUT /api/acc/opname/{id}/count` | `counted_uom` |
| Cutting → Input Progres | `POST /api/cutting/orders/{id}/progress` | `input_uom` |

* Daftar satuan yang ditawarkan layar = **kemampuan server**, dari satu endpoint:
  `GET /api/rahaza/materials/uom-options?material_ids=a,b,c`
  (kemasan master + satuan sedimensi global + kain m⇄kg via gramasi & lebar; alias ganda disembunyikan).
* Konversi dieksekusi SATU helper: `core/bom_uom.factor_to_base(material, unit)`; jejaknya
  (`input_qty`, `input_uom`, `uom_factor`, `uom_source`) dibekukan di baris ledger.
* Layar SELALU menampilkan pratinjau ("2 rol → 50 kg") sebelum disimpan, dan peringatan bila satuan
  belum punya faktor. Tanpa memilih satuan, perilakunya sama seperti sebelumnya (satuan dasar).
* Satuan yang tidak bisa dikonversi ditolak **400** dengan pesan yang mengarahkan ke Master Material —
  tidak pernah diam-diam dihitung 1:1 pada jalur stok.
* Komponen UI: `frontend/src/components/erp/uom/UomPicker.jsx` + `frontend/src/hooks/useUomOptions.js`.
* Uji: `tests/flow_uom_entry_points_ui_test.py` (38 cek) · `scripts/poc_uom_entry_points.py` (11 cek).
* Data demo: `scripts/seed_uom_ui_demo.py` (`--cleanup` untuk membuang).

# PENOMORAN DOKUMEN — TAHAP 2 (2026-08-05)
Owner mengatur format nomor di **Portal Administrasi Sistem → Penomoran Dokumen** (`45 jenis`).
Token: `{YYYY} {YY} {MM} {DD} {SEQ:n}` + token khusus per jenis (`{TIPE}`, `{KLIEN}`, `{PREFIX}`,
`{STYLE}/{WARNA}/{SIZE}`). Satu-satunya generator tetap `utils.counters.gen_prefixed_number`
(race-safe lewat koleksi `counters`, lazy-init dari nomor tertinggi yang sudah ada).
* Tahap 2 memindahkan 11 penghasil nomor manual: PO pembelian · GR penerimaan · AP dari GR ·
  klaim biaya karyawan · perjalanan dinas · penyelesaian dinas · PO maklon · pengiriman maklon ·
  invoice maklon manual · invoice maklon otomatis (AR) · job vendor.
* `config_key=` dipakai bila dua jenis nomor menumpang satu koleksi+field
  (`rahaza_ar_invoices.invoice_number`: AR Finance vs invoice maklon).
* Perubahan format hanya berlaku untuk dokumen BARU. Menurunkan nomor urut ditolak bila sudah ada
  dokumen memakai awalan yang sama (mencegah nomor kembar — INV-CNT-1).
* Uji: `tests/flow_doc_numbering_phase2_test.py` (19 cek, termasuk 25 permintaan bersamaan → unik).

# DASHBOARD MAKLON — ALUR PRODUKSI (2026-08-05)
Portal Maklon → Monitoring Progress → **Alur Produksi** (`#maklon-alur-produksi`) menampilkan
perjalanan barang maklon dari `GET /api/prod/dashboard?business_type=maklon`:
Rencana PO → Cutting → Di Vendor CMT → Terima & QC → Permak → **Dispatch ke Buyer**, plus KPI
(PO berjalan, di vendor, menunggu periksa, tingkat cacat) dan pemilih periode 7/30/90 hari.
Komponennya SAMA dengan Portal Produksi (`ProductionDashboardOverview`, beda `businessType`) sehingga
tidak ada dua sumber angka.

# ADDENDUM — RBAC SATU TEMPAT (2026-08-06)

**Masalah owner:** ada DUA tempat mengatur akses (dialog "Edit Role" + "Matriks Role & Permission"),
membingungkan; matriksnya terlalu besar untuk dikonfigurasi.

**Keadaan sekarang (SSOT tunggal):**
* **Katalog izin**: `backend/data/permission_catalog.py` — 129 izin, tersusun portal → modul → izin,
  tiap izin bermetadata `action` (`view/input/manage/approve/run/export`).
  `GET /api/permissions` (datar) · `GET /api/permissions?grouped=1` (bersarang).
* **Satu layar konfigurasi**: `frontend/src/components/erp/RoleManagementModule.jsx`
  ("Peran & Hak Akses", master–detail 5 bagian). `RoleMatrixModule.jsx` DIHAPUS.
  Hub Kontrol Akses: **Pengguna | Peran & Hak Akses** (2 tab).
* **Satu jalur simpan**: `POST /api/roles` & `PUT /api/roles/{id}` (name, description, portals,
  hidden_modules, permissions). `PUT /api/roles/{id}/permissions` dan `POST /api/roles/matrix/bulk`
  DIHAPUS.
* **Satu mesin penegakan**: `backend/routes/shared.py` → `has_perm` / `can_act` / `require_perm` /
  `require_perm_dep`, model **FALLBACK AMAN**:
  super role atau `*` → izin yang diminta → (bila izin peran masih kosong) daftar role legacy
  / `legacy_any=True` → selain itu 403. **Konsekuensi disengaja:** begitu owner mencentang izin,
  daftar izin itulah yang berlaku untuk peran tersebut.
* Cache izin proses TTL 20 detik + `auth.bump_rbac_cache()` saat peran/pengguna berubah.
* Titik aksi/approval yang sudah dipusatkan: MI approve, Cutting, CMT (intake/belanja/kejar/permak),
  Penomoran Dokumen, approval Opname Gudang, approval ubah Invoice, Inbox Approval SDM, Put-away.
  Sisa penjaga hardcode (±80 berkas) tetap jalan dan dimigrasi bertahap.
* Rincian: `memory/RBAC_KONSOLIDASI_2026-08-06.md`.

## Sesi 2026-08-07 (RnD: foto desain, banding revisi, tahap lengkap, rapor mingguan,
ambang peringatan) — rinciannya dipindah ke `memory/CHANGELOG.md` agar PRD tetap ringkas.
