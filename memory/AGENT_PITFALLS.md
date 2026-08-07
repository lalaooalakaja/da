# Catatan kerja agen — jangan diulangi

## 2026-08-05 · JANGAN kirim beberapa `search_replace` untuk FILE YANG SAMA dalam satu batch paralel
Gejala: tool melaporkan "Edit was successful" untuk semua panggilan, tetapi hanya
SEBAGIAN perubahan benar-benar ada di file (write terakhir menimpa hasil write
sebelumnya). Efek samping yang sempat terjadi:
- `rahaza_inventory_materials.py`: patch `gsm`/`width_cm` pada POST hilang (hanya PUT yang ada)
  → 9 assertion uji gagal padahal kodenya "sudah ditulis".
- `RnDMaterialsTab.jsx`: patch `openEdit` hilang + sisa potongan `);}` di akhir file
  → parsing error eslint.

Aturan: edit paralel hanya untuk file BERBEDA. Untuk beberapa perubahan pada satu file:
lakukan berurutan, atau tulis ulang file dengan `create_file overwrite=true`.
Selalu verifikasi dengan `grep -n` setelah batch edit.

## 2026-08-05 · Cakupan konversi satuan: `core.uom` ≠ `core.bom_uom`
`core/uom.py::factor_of` HANYA tahu kemasan resmi material (`uoms`/`pack_*`). Satuan sedimensi
global (gram↔kg, cm↔m, lusin↔pcs) dan kain m⇄kg (via gsm & lebar) hanya dikenal `core/bom_uom.py`.
Akibatnya titik masuk stok yang memakai `factor_of` menolak "gram"/"yard" padahal BOM & Costing
sudah lama bisa mengonversinya — dan dropdown satuan di layar akan menawarkan satuan yang server
tolak. Sejak sesi ini pakai **`core.bom_uom.factor_to_base(material, unit)`** (satu helper, melempar
`UomError` bila benar-benar tak bisa dikonversi) untuk SEMUA jalur stok, dan bangun dropdown dari
`GET /api/rahaza/materials/uom-options` supaya daftar di layar = kemampuan server.

## 2026-08-05 · `gen_prefixed_number` memakai kunci konfigurasi `<koleksi>.<field>`
Dua jenis dokumen yang menumpang SATU koleksi+field (mis. `rahaza_ar_invoices.invoice_number`
dipakai AR Finance `AR-…` DAN invoice maklon otomatis `INV-MKL-…`) akan saling menimpa formatnya.
Pakai parameter **`config_key=`** + entri registry dengan `collection`/`field` eksplisit
(`data/doc_number_registry.py::target_of`). Jangan membuat generator kedua.

## 2026-08-05 · Seeder demo membuat dokumen dispatch tanpa mutasi stok FG
`tests/seed_demo_produksi_maklon.py` menulis `buyer_shipments`/`buyer_shipment_items` LANGSUNG ke DB,
jadi INV-18 ("setiap dispatch sudah mengurangi stok FG") selalu MERAH di container segar. Penutupnya:
`scripts/repair_selisih_ssot.py --apply --topup-fg` (sudah dipanggil `seed_demo_all.sh`).
`--topup-fg` HANYA untuk data demo — pada data nyata owner, stok kurang = ada QC/dokumen yang belum
diselesaikan dan harus diperiksa manusia.
