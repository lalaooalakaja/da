# Development Plan — Perbaiki Rantai Approval Procurement (UI Inbox + SoD + Threshold Nilai + Notifikasi)

> **STATUS AKHIR SESI 2026-08-07: SEMUA FASE SELESAI & TERVERIFIKASI ✅**
>
> Titik berhenti sesi lalu (“approval chain dead-ends in the UI — fix inbox role mapping”) **sudah diverifikasi hijau lebih dulu**,
> lalu seluruh dead-end di UI ditutup sampai end-to-end (dept → finance → final) + konfigurasi ambang nilai + notifikasi + audit override.
>
> Bukti: `scripts/poc_approval_chain.py` **73/73 PASS** · `scripts/verify_pr_inbox_roles.py` **LULUS** · `bash scripts/gate.sh` **13/13 HIJAU**
> · testing agent iteration_26/27/28 **0 bug**.

---

## 1) Objectives

### 1.1 Objective awal (sudah tercapai)
- Menghidupkan kembali rantai persetujuan PR procurement end-to-end (tidak dead-end di UI). ✅
- Menjadikan backend sebagai **SSOT izin**: list/detail/inbox mengembalikan `can_approve/can_reject`, `blocked_reason`, `stage_label`, `next_approver_label`, `chain`. ✅
- Menerapkan **Segregation of Duties ketat**:
  - Hanya role tahap terkait boleh approve/reject. ✅
  - Requester tidak boleh menyetujui PR miliknya sendiri. ✅
  - Satu aktor tidak boleh menyetujui 2 tahap pada PR yang sama. ✅
  - Admin/owner boleh **override** semua tahap, dan override harus tercatat di approval_steps. ✅
- Approval depth berbasis nilai PR dengan ambang yang bisa diatur owner (editable di **Ringkasan Bisnis**), disimpan di `dewi_mgmt_alert_config`. ✅
- Notifikasi “next approver” muncul di bel (SSOT `notifications`) dan bisa membuka modul `proc-requests`. ✅

### 1.2 Objective tambahan yang muncul dari verifikasi (juga sudah tercapai)
- Menutup bug lingkungan/RBAC yang membuat aturan departemen selalu mati: `department` kini ikut JWT + fallback DB (`_with_department`). ✅
- Menutup bug audit: izin `*` admin membuat override tidak pernah tercatat. ✅
- Menutup lubang data demo: bootstrap sekarang men-seed **Master Supplier** agar UI Portal Pengadaan tidak tampak “kosong/rusak” dan alur PR→PO tidak mentok. ✅
- Menutup bug UI staleness: detail PR refresh setelah PO dibuat sehingga nomor PO tampil dan tombol “Buat PO” hilang. ✅

---

## 2) Implementation Steps

### Phase 1 — POC Core Approval Chain (WAJIB HIJAU sebelum UI)
**Output:** `scripts/poc_approval_chain.py`

**STATUS: SELESAI ✅**

Yang dilakukan (dan hasilnya):
1) Ambang nilai PR ditambah ke dokumen SSOT `dewi_mgmt_alert_config` dan disajikan endpoint lama:
   - File: `backend/services/management_alerts.py`, route tetap `GET/PUT /api/rahaza/management/alert-config`.
   - Keys: `pr_1_stage_max` (default Rp 1.000.000), `pr_2_stage_max` (default Rp 25.000.000), validasi `pr_1 <= pr_2`.
   - Validator dipisah dari ambang hari (hari 0..60 vs rupiah 0..100 miliar). ✅

2) Rantai persetujuan dibekukan saat submit:
   - Field `approval_chain` disimpan di PR saat `/submit` sehingga perubahan ambang tidak menggeser PR yang sudah berjalan. ✅

3) Mesin tunggal `_eval_approval` di backend menjadi SSOT izin untuk:
   - `/inbox`, list PR, detail PR, timeline, gerbang `/approve` & `/reject`, `my_pending_approval`, dan lencana TopBar. ✅

4) SoD ketat + override admin tercatat:
   - Peran tiap tahap SALING LEPAS; `manager_keuangan` dikeluarkan dari tahap final.
   - Larangan self-approval + larangan satu orang menyetujui dua tahap.
   - Admin/owner override boleh, tetapi dicatat (`override: true`, `override_reasons`, label “(override admin)”). ✅

5) Notifikasi:
   - Next approver diberi notifikasi via `notif_insert` SSOT (type=rahaza, subtype=procurement_approval) dengan `meta.link_module='proc-requests'`.
   - Pemohon diberi notifikasi saat disetujui penuh/ditolak. ✅

6) Akun approver final:
   - Ditambah `direktur@dewiaditya.id` role `director` di `backend/scripts/seed_role_accounts.py` (sebelumnya tidak ada akun director/cfo/ceo/owner, PR 3 tahap tidak bisa selesai tanpa override admin). ✅

7) POC menemukan 3 bug nyata yang tidak terlihat dari pembacaan kode (semua sudah difix):
   - (a) rantai persetujuan tidak tampil di draft karena perubahan endpoint detail sempat tertimpa edit paralel.
   - (b) `department` tidak masuk JWT → aturan departemen mati → inbox lama bisa kosong total untuk approver bergantung-departemen.
   - (c) izin `*` membuat override admin tidak pernah tercatat.

**Bukti:** `scripts/poc_approval_chain.py` = **73/73 PASS**.

---

### Phase 2 — V1 App (Backend + Frontend) untuk menutup dead-end UI

**STATUS: SELESAI ✅**

1) Inbox jadi TAB di ProcurementRequestModule:
   - File: `frontend/src/components/erp/ProcurementRequestModule.jsx`
   - 3 tab: “Semua Permintaan” · “Menunggu Persetujuan Saya” (lencana jumlah + total nilai) · “Permintaan Saya”. ✅

2) Hapus role-gate hardcoded di frontend:
   - Tombol Setujui/Tolak kini murni mengikuti `can_approve`/`can_reject` dari server.
   - Jika tidak berhak, `blocked_reason` ditampilkan (bukan tombol hilang tanpa penjelasan). ✅

3) Stepper rantai persetujuan:
   - Stepper penuh di detail modal + stepper ringkas di kartu list.
   - Menampilkan siapa yang memutuskan, kapan, dan penanda override. ✅

4) Ringkasan Bisnis: ambang persetujuan PR:
   - File: `frontend/src/components/erp/ManagementOverviewModule.jsx`
   - Blok “Ambang Persetujuan PR” (2 input rupiah + pratinjau + penjelasan “dibekukan saat diajukan”). ✅

5) Bundle statis di-rebuild:
   - `scripts/rebuild_frontend.sh` → “Compiled successfully”, frontend HTTP 200. ✅

6) Pengujian:
   - testing agent iteration_26: backend 26/26 PASS.
   - testing agent iteration_27: UI inti (tombol approve finance@ = accounting, stepper, validasi reject, blocked_reason, gudang@ approve dept) PASS.
   - testing agent iteration_28: UI lanjutan (2 tahap selesai oleh finance, 3 tahap → direktur, override tercatat, ambang + validasi) PASS. ✅

---

### Phase 3 — Polish + Regression + Dokumentasi

**STATUS: SELESAI ✅**

1) Perbaikan UI tambahan yang ditemukan saat verifikasi:
   - Detail PR refresh setelah PO dibuat (nomor PO tampil, tombol “Buat PO” hilang).
   - GateNotice “tidak ada persetujuan yang menunggu” disenyapkan untuk PR yang sudah selesai (kebisingan). ✅

2) Lubang data demo ditutup:
   - `scripts/bootstrap.sh` sebelumnya tidak men-seed `rahaza_suppliers` → Portal Pengadaan tampak “kosong” + alur PR→PO mentok.
   - Ditambah `scripts/seed_procurement_suppliers_demo.py` (idempoten, `--cleanup`, hanya master supplier + price list) dan dipanggil oleh bootstrap. ✅

3) Verifikasi script lama diselaraskan:
   - `scripts/verify_pr_inbox_roles.py` diupdate: nilai PR uji dinaikkan ke Rp 50 jt supaya tahap keuangan benar-benar ada; cleanup dipastikan lewat Mongo di finally.

4) Dokumentasi:
   - `memory/CHANGELOG.md` (entri teratas)
   - `memory/test_credentials.md`
   - `test_result.md`

5) Final gates:
   - `bash scripts/gate.sh` → **13/13 HIJAU**.

---

## 3) Next Actions (Sesi berikutnya / backlog)

> **Catatan:** di sesi ini, semua target approval procurement sudah selesai. Berikutnya adalah backlog prioritas repo (dari HANDOFF_NEXT_AGENT.md + temuan sesi ini).

1) **PRIORITAS 1 — Hilangkan `except Exception: pass` (17 titik; 6 di jalur stok & uang)**
   - Lokasi contoh: `core/stock_service.py:334`, `core/quarantine.py` ×3,
     `core/accessory_stock.py:46`, `core/stock_reconcile.py:198`.
   - Risiko: mutasi stok bisa gagal tanpa log/error ⇒ angka salah tanpa jejak.

2) **Race numbering**: 44 titik `count_documents()+1` → nomor dokumen kembar saat concurrency.
   - SSOT `utils/counters.py` sudah ada; tinggal adopsi.

3) **Datetime naive**: 27 titik → batas hari laporan/absen bisa bergeser.

4) **Frontend tests**: nol Jest/RTL test di `frontend/`.

5) **Approval PO** (`rahaza_po.py`) belum memakai mesin SSOT seperti `_eval_approval`.
   - Risiko: kelas bug yang sama (role list ganda di UI/BE) bisa terulang di PO.

6) **SLA reminder PR**: notifikasi pengingat PR yang menunggu terlalu lama
   - Ambang bisa memakai pola `dewi_mgmt_alert_config` yang sudah ada.

---

## 4) Success Criteria (Status)

- Phase 1: `python3 scripts/poc_approval_chain.py` PASS 100% (**73/73**) ✅
- Phase 2: UI `proc-requests` punya tab inbox; tombol approve/reject mengikuti flag backend; stepper tampil; ambang rupiah editable; notif bell membuka PR ✅
- Phase 3: `bash scripts/gate.sh` HIJAU; skrip verifikasi tersimpan; regresi portal pengadaan lulus; CHANGELOG/test_credentials/test_result ter-update ✅
