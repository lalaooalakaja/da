import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Plus, Edit2, Trash2, X, Upload, Camera, FileText, Video, Image as ImageIcon,
  ArrowUp, ArrowDown, Link2, ListChecks, BookOpen, Info,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import { DataTable } from './DataTableV2';
import { PageHeader } from './moduleAtoms';
import ImportExportToolbar from './ImportExportToolbar';
import { toast } from 'sonner';
import { readField, readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

const CATEGORIES = ['Sweater', 'Cardigan', 'Vest', 'Polo', 'Other'];
const DEFAULT_FORM = { code: '', name: '', category: 'Sweater', material_kg_per_pcs: 0, bundle_size: 30, description: '' };
const MAX_PHOTOS = 8;

const IMAGE_FALLBACK = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24' fill='none' stroke='%23cbd5e1' stroke-width='1.5'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Ccircle cx='8.5' cy='8.5' r='1.5'/%3E%3Cpath d='M21 15l-5-5L5 21'/%3E%3C/svg%3E`;

const fileUrl = (path, token) => `/api/files/${path}?auth=${encodeURIComponent(token)}`;

function ytId(url) {
  const m = String(url || '').match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([\w-]{11})/);
  return m ? m[1] : null;
}

function ImageThumb({ path, token, onDelete, large = false }) {
  const url = useMemo(() => fileUrl(path, token), [path, token]);
  const sz = large ? 'w-24 h-24' : 'w-12 h-12';
  return (
    <div className={`relative group ${sz} rounded-lg overflow-hidden border border-[var(--glass-border)] bg-[var(--glass-bg)]`}>
      <img src={url} alt="model" className="w-full h-full object-cover"
        onError={(e) => { e.target.src = IMAGE_FALLBACK; e.target.style.objectFit = 'contain'; e.target.style.padding = '6px'; }} />
      {onDelete && (
        <button onClick={onDelete}
          className="absolute top-0.5 right-0.5 p-1 rounded-full bg-red-500/90 text-white opacity-0 group-hover:opacity-100 transition-opacity"
          data-testid="model-image-delete" title="Hapus foto">
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PANDUAN PRODUKSI DIALOG — Foto Produk + SOP langkah + Video/Referensi
// ════════════════════════════════════════════════════════════════════════════
function PanduanProduksiDialog({ model, token, onClose, onUpdated }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [tab, setTab] = useState('foto');
  const [paths, setPaths] = useState(model.image_paths || []);
  const [steps, setSteps] = useState(() =>
    (model.sop_steps || []).map((s) => ({
      id: s.id || crypto.randomUUID(), title: s.title || '', description: s.description || '', image_path: s.image_path || '',
    }))
  );
  const [videos, setVideos] = useState(() => (model.reference_videos || []).map((v) => ({ url: v.url || '', title: v.title || '' })));
  const [refImages, setRefImages] = useState(() => (model.reference_images || []).map((v) => ({ url: v.url || '', caption: v.caption || '' })));
  const [uploading, setUploading] = useState(false);
  const [stepUploading, setStepUploading] = useState(null);
  const [saving, setSaving] = useState(false);

  // ── Foto Produk ────────────────────────────────────────────────────────────
  const handleUploadPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (paths.length >= MAX_PHOTOS) { toast.error(`Maksimal ${MAX_PHOTOS} foto per model`); return; }
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch(`/api/rahaza/models/${model.id}/images`, { method: 'POST', headers, body: fd });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Upload gagal'); return; }
      const data = await r.json();
      setPaths(data.image_paths || []);
      toast.success('Foto diupload');
      onUpdated && onUpdated();
    } finally { setUploading(false); e.target.value = ''; }
  };

  const handleDeletePhoto = async (path) => {
    if (!window.confirm('Hapus foto ini?')) return;
    const r = await fetch(`/api/rahaza/models/${model.id}/images`, {
      method: 'DELETE', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ storage_path: path }),
    });
    if (r.ok) { const data = await r.json(); setPaths(data.image_paths || []); toast.success('Foto dihapus'); onUpdated && onUpdated(); }
    else toast.error('Gagal menghapus foto');
  };

  // ── SOP langkah ──────────────────────────────────────────────────────────────
  const addStep = () => setSteps((s) => [...s, { id: crypto.randomUUID(), title: '', description: '', image_path: '' }]);
  const removeStep = (idx) => setSteps((s) => s.filter((_, i) => i !== idx));
  const updateStep = (idx, patch) => setSteps((s) => s.map((st, i) => (i === idx ? { ...st, ...patch } : st)));
  const moveStep = (idx, dir) => setSteps((s) => {
    const j = idx + dir; if (j < 0 || j >= s.length) return s;
    const c = [...s]; [c[idx], c[j]] = [c[j], c[idx]]; return c;
  });

  const uploadStepPhoto = async (idx, file) => {
    if (!file) return;
    setStepUploading(idx);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch(`/api/rahaza/models/${model.id}/sop-image`, { method: 'POST', headers, body: fd });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Upload gagal'); return; }
      const data = await r.json();
      updateStep(idx, { image_path: data.storage_path });
      toast.success('Foto langkah diupload');
    } finally { setStepUploading(null); }
  };

  // ── Video & Referensi ─────────────────────────────────────────────────────────
  const addVideo = () => setVideos((v) => [...v, { url: '', title: '' }]);
  const removeVideo = (idx) => setVideos((v) => v.filter((_, i) => i !== idx));
  const updateVideo = (idx, patch) => setVideos((v) => v.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const addRefImage = () => setRefImages((v) => [...v, { url: '', caption: '' }]);
  const removeRefImage = (idx) => setRefImages((v) => v.filter((_, i) => i !== idx));
  const updateRefImage = (idx, patch) => setRefImages((v) => v.map((it, i) => (i === idx ? { ...it, ...patch } : it)));

  const saveSop = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/rahaza/models/${model.id}/sop`, {
        method: 'PUT', headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ sop_steps: steps, reference_videos: videos, reference_images: refImages }),
      });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Gagal menyimpan'); return; }
      toast.success('Panduan Produksi tersimpan');
      onUpdated && onUpdated();
      onClose();
    } finally { setSaving(false); }
  };

  const TabBtn = ({ id, icon: Icon, label, count }) => (
    <button onClick={() => setTab(id)}
      className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors ${
        tab === id ? 'bg-primary/10 border-primary/40 text-foreground' : 'border-[var(--glass-border)] text-muted-foreground hover:bg-[var(--glass-bg-hover)]'}`}
      data-testid={`panduan-tab-${id}`}>
      <Icon className="w-4 h-4" /> {label}
      {count != null && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-foreground/10">{count}</span>}
    </button>
  );

  return (
    <Modal onClose={onClose} title={`Panduan Produksi · ${model.code} — ${model.name}`} size="lg">
      <div className="space-y-4" data-testid="panduan-produksi-dialog">
        <div className="flex items-center gap-2 flex-wrap">
          <TabBtn id="foto" icon={Camera} label="Foto Produk" count={paths.length} />
          <TabBtn id="sop" icon={ListChecks} label="SOP Produksi" count={steps.length} />
          <TabBtn id="video" icon={Video} label="Video & Referensi" count={videos.length + refImages.length} />
        </div>

        {/* ── FOTO ── */}
        {tab === 'foto' && (
          <div className="space-y-3" data-testid="panduan-foto-tab">
            <p className="text-sm text-muted-foreground">
              Upload sampai <b>{MAX_PHOTOS} foto jadi / referensi</b> (max 5MB). Tampil di LKP & Portal Vendor CMT.
            </p>
            <div className="grid grid-cols-4 sm:grid-cols-6 gap-3">
              {paths.map((p) => <ImageThumb key={p} path={p} token={token} large onDelete={() => handleDeletePhoto(p)} />)}
              {paths.length < MAX_PHOTOS && (
                <label className="w-24 h-24 rounded-lg border-2 border-dashed border-[var(--glass-border)] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-primary hover:bg-[var(--glass-bg-hover)] transition-colors"
                  data-testid="model-image-upload-label">
                  {uploading ? <span className="text-xs text-muted-foreground">Uploading...</span> : (<>
                    <Upload className="w-5 h-5 text-muted-foreground" />
                    <span className="text-[10px] text-muted-foreground">Tambah foto</span>
                  </>)}
                  <input type="file" accept="image/*" className="hidden" disabled={uploading} onChange={handleUploadPhoto} data-testid="model-image-upload-input" />
                </label>
              )}
            </div>
            <div className="text-xs text-muted-foreground">{paths.length}/{MAX_PHOTOS} foto · JPG, PNG, WebP. (Tersimpan otomatis)</div>
          </div>
        )}

        {/* ── SOP ── */}
        {tab === 'sop' && (
          <div className="space-y-3" data-testid="panduan-sop-tab">
            <p className="text-sm text-muted-foreground">
              Tata cara pembuatan model — langkah berurutan. Vendor CMT membaca ini untuk tahu cara produksi.
            </p>
            <div className="space-y-3 max-h-[45vh] overflow-y-auto pr-1">
              {steps.map((st, idx) => (
                <div key={st.id} className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3" data-testid={`sop-step-${idx}`}>
                  <div className="flex items-start gap-3">
                    <div className="flex flex-col items-center gap-1 pt-1">
                      <span className="w-6 h-6 rounded-full bg-primary/15 text-primary text-xs font-bold flex items-center justify-center">{idx + 1}</span>
                      <button onClick={() => moveStep(idx, -1)} disabled={idx === 0} className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" title="Naik"><ArrowUp className="w-3.5 h-3.5" /></button>
                      <button onClick={() => moveStep(idx, 1)} disabled={idx === steps.length - 1} className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" title="Turun"><ArrowDown className="w-3.5 h-3.5" /></button>
                    </div>
                    <div className="flex-1 space-y-2">
                      <GlassInput value={st.title} onChange={(e) => updateStep(idx, { title: e.target.value })}
                        placeholder="Judul langkah (cth: Potong kain sesuai pola)" data-testid={`sop-step-${idx}-title`} />
                      <textarea value={st.description} onChange={(e) => updateStep(idx, { description: e.target.value })}
                        placeholder="Deskripsi / instruksi detail..." rows={2}
                        className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-sm text-foreground resize-y"
                        data-testid={`sop-step-${idx}-desc`} />
                      <div className="flex items-center gap-3">
                        {st.image_path ? (
                          <div className="relative group">
                            <img src={fileUrl(st.image_path, token)} alt="step" className="w-20 h-20 rounded-lg object-cover border border-[var(--glass-border)]"
                              onError={(e) => { e.target.src = IMAGE_FALLBACK; }} />
                            <button onClick={() => updateStep(idx, { image_path: '' })}
                              className="absolute -top-1.5 -right-1.5 p-1 rounded-full bg-red-500/90 text-white" title="Hapus foto langkah"><X className="w-3 h-3" /></button>
                          </div>
                        ) : (
                          <label className="w-20 h-20 rounded-lg border-2 border-dashed border-[var(--glass-border)] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-primary text-muted-foreground"
                            data-testid={`sop-step-${idx}-photo-label`}>
                            {stepUploading === idx ? <span className="text-[9px]">...</span> : (<><ImageIcon className="w-4 h-4" /><span className="text-[9px]">Foto</span></>)}
                            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadStepPhoto(idx, e.target.files?.[0])} />
                          </label>
                        )}
                        <button onClick={() => removeStep(idx)} className="ml-auto flex items-center gap-1 text-xs text-red-400 hover:text-red-300" data-testid={`sop-step-${idx}-remove`}>
                          <Trash2 className="w-3.5 h-3.5" /> Hapus langkah
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {steps.length === 0 && (
                <div className="text-center py-6 text-sm text-muted-foreground border border-dashed border-[var(--glass-border)] rounded-lg">
                  Belum ada langkah. Klik "Tambah Langkah".
                </div>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={addStep} data-testid="sop-add-step-btn"><Plus className="w-4 h-4 mr-1" /> Tambah Langkah</Button>
          </div>
        )}

        {/* ── VIDEO & REFERENSI ── */}
        {tab === 'video' && (
          <div className="space-y-5" data-testid="panduan-video-tab">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Video className="w-4 h-4 text-primary" /> Referensi Video</span>
                <Button variant="outline" size="sm" onClick={addVideo} data-testid="ref-add-video-btn"><Plus className="w-4 h-4 mr-1" /> Video</Button>
              </div>
              <div className="space-y-2">
                {videos.map((v, idx) => {
                  const yid = ytId(v.url);
                  return (
                    <div key={idx} className="flex items-center gap-3 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2" data-testid={`ref-video-${idx}`}>
                      {yid ? <img src={`https://img.youtube.com/vi/${yid}/default.jpg`} alt="yt" className="w-16 h-12 rounded object-cover" />
                           : <div className="w-16 h-12 rounded bg-foreground/10 flex items-center justify-center"><Video className="w-5 h-5 text-muted-foreground" /></div>}
                      <div className="flex-1 space-y-1">
                        <GlassInput value={v.title} onChange={(e) => updateVideo(idx, { title: e.target.value })} placeholder="Judul video" data-testid={`ref-video-${idx}-title`} />
                        <GlassInput value={v.url} onChange={(e) => updateVideo(idx, { url: e.target.value })} placeholder="https://youtu.be/... atau link Drive" data-testid={`ref-video-${idx}-url`} />
                      </div>
                      <button onClick={() => removeVideo(idx)} className="p-1.5 text-red-400 hover:text-red-300" data-testid={`ref-video-${idx}-remove`}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  );
                })}
                {videos.length === 0 && <div className="text-xs text-muted-foreground py-2">Belum ada video referensi.</div>}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Link2 className="w-4 h-4 text-primary" /> Gambar Referensi (link)</span>
                <Button variant="outline" size="sm" onClick={addRefImage} data-testid="ref-add-image-btn"><Plus className="w-4 h-4 mr-1" /> Gambar</Button>
              </div>
              <div className="space-y-2">
                {refImages.map((v, idx) => (
                  <div key={idx} className="flex items-center gap-3 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2" data-testid={`ref-image-${idx}`}>
                    <img src={v.url || IMAGE_FALLBACK} alt="ref" className="w-14 h-14 rounded object-cover bg-foreground/5" onError={(e) => { e.target.src = IMAGE_FALLBACK; e.target.style.objectFit = 'contain'; e.target.style.padding = '4px'; }} />
                    <div className="flex-1 space-y-1">
                      <GlassInput value={v.caption} onChange={(e) => updateRefImage(idx, { caption: e.target.value })} placeholder="Keterangan" data-testid={`ref-image-${idx}-caption`} />
                      <GlassInput value={v.url} onChange={(e) => updateRefImage(idx, { url: e.target.value })} placeholder="https://.../gambar.jpg" data-testid={`ref-image-${idx}-url`} />
                    </div>
                    <button onClick={() => removeRefImage(idx)} className="p-1.5 text-red-400 hover:text-red-300" data-testid={`ref-image-${idx}-remove`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
                {refImages.length === 0 && <div className="text-xs text-muted-foreground py-2">Belum ada gambar referensi.</div>}
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t border-[var(--glass-border)]">
          <Button variant="ghost" onClick={onClose} data-testid="panduan-close">Tutup</Button>
          <Button onClick={saveSop} disabled={saving} data-testid="panduan-save">
            {saving ? 'Menyimpan...' : 'Simpan Panduan (SOP + Video)'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function RahazaModelsModule({ token }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [panduanModel, setPanduanModel] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/models', { headers });
      if (r.ok) setRows(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const openCreate = () => { setEditing(null); setForm(DEFAULT_FORM); setModalOpen(true); };
  const openEdit = (row) => {
    setEditing(row);
    setForm({
      code: row.code || '', name: row.name || '', category: row.category || 'Sweater',
      material_kg_per_pcs: readNumber(row, FIELD.materialKgPerPcs), bundle_size: row.bundle_size || 30, description: row.description || '',
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.code || !form.name) { toast.error('Kode & nama wajib diisi'); return; }
    setSaving(true);
    try {
      const url = editing ? `/api/rahaza/models/${editing.id}` : '/api/rahaza/models';
      const method = editing ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers, body: JSON.stringify(form) });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || `HTTP ${r.status}`); return; }
      toast.success(editing ? 'Model diperbarui' : 'Model dibuat');
      setModalOpen(false);
      fetchRows();
    } finally { setSaving(false); }
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`Nonaktifkan model ${row.code}?`)) return;
    const r = await fetch(`/api/rahaza/models/${row.id}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Model dinonaktifkan'); fetchRows(); }
    else toast.error('Gagal menonaktifkan');
  };

  const columns = [
    { key: 'code', label: 'Kode', sortable: true },
    { key: 'name', label: 'Nama Model', sortable: true },
    { key: 'category', label: 'Kategori' },
    {
      key: 'image_paths', label: 'Foto',
      render: (row) => {
        const arr = Array.isArray(row?.image_paths) ? row.image_paths : [];
        return (
          <div className="flex items-center gap-1.5" data-testid={`model-images-${row.code}`}>
            {arr.slice(0, 3).map((p) => <ImageThumb key={p} path={p} token={token} />)}
            {arr.length > 3 && <span className="text-[10px] text-muted-foreground">+{arr.length - 3}</span>}
          </div>
        );
      },
    },
    {
      key: 'sop_steps', label: 'Panduan',
      render: (row) => {
        const nSop = (row?.sop_steps || []).length;
        const nVid = (row?.reference_videos || []).length;
        return (
          <button
            onClick={(e) => { e.stopPropagation(); setPanduanModel(row); }}
            className="px-2 py-1 rounded text-xs border border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] flex items-center gap-1 text-muted-foreground hover:text-foreground"
            data-testid={`model-panduan-${row.code}`} title="Panduan Produksi (SOP + Foto + Video)">
            <BookOpen className="w-3.5 h-3.5" />
            <span>{nSop} SOP · {nVid} video</span>
          </button>
        );
      },
    },
    { key: 'material_kg_per_pcs', label: 'Bahan utama/pcs (kg)', render: (row) => { const v = readNumber(row, FIELD.materialKgPerPcs); return v ? Number(v).toFixed(3) : '-'; } },
    { key: 'bundle_size', label: 'Bundle', render: (row, v) => `${v || 30} pcs` },
    {
      key: 'actions', label: 'Aksi',
      render: (row) => (
        <div className="flex items-center gap-1">
          <button onClick={(e) => { e.stopPropagation(); openEdit(row); }}
            className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground" title="Edit" data-testid={`model-edit-${row.code}`}>
            <Edit2 className="w-3.5 h-3.5" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); handleDelete(row); }}
            className="p-1.5 rounded hover:bg-red-100 dark:bg-red-500/20 text-muted-foreground hover:text-red-700 dark:text-red-400" title="Nonaktifkan" data-testid={`model-deactivate-${row.code}`}>
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4" data-testid="rahaza-models-module">
      <PageHeader
        title="Model Produk (Internal)"
        subtitle="Master model produksi + Panduan Produksi (SOP, foto jadi, video) yang dibaca Vendor CMT."
        actions={
          <>
            <ImportExportToolbar collectionKey="models" label="Model Produk" onImported={fetchRows} />
            <Button onClick={openCreate} className="gap-1.5" data-testid="model-create-btn">
              <Plus className="w-4 h-4" /> Tambah Model
            </Button>
          </>
        }
      />

      <GlassCard>
        <DataTable tableId="rahaza-models" columns={columns} rows={rows} loading={loading}
          emptyTitle="Belum ada model" emptyDescription="Model internal idealnya lahir dari R&D. Klik Tambah Model untuk input manual." rowKey="id" />
      </GlassCard>

      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)} title={editing ? 'Edit Model' : 'Tambah Model Baru'} size="md">
          <div className="space-y-3" data-testid="model-form">
            {!editing && (
              <div className="flex items-start gap-2 text-[11px] text-amber-700 dark:text-amber-300 bg-amber-500/10 border border-amber-400/30 rounded-lg p-2" data-testid="model-rnd-hint">
                <Info className="w-4 h-4 shrink-0 mt-0.5" />
                <span><b>Disarankan lewat R&D:</b> produk internal idealnya lahir dari modul R&D (publish style → otomatis jadi master + bawa foto desain). Input manual ini untuk kasus khusus.</span>
              </div>
            )}
            <div>
              <label className="text-xs text-muted-foreground">Kode <span className="text-red-700 dark:text-red-400">*</span></label>
              <GlassInput value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="Contoh: SW-VN-A" data-testid="model-form-code" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Nama Model <span className="text-red-700 dark:text-red-400">*</span></label>
              <GlassInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Contoh: Sweater V-Neck Classic" data-testid="model-form-name" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Kategori</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-sm text-foreground" data-testid="model-form-category">
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Ukuran Bundle (pcs)</label>
                <GlassInput type="number" value={form.bundle_size}
                  onChange={(e) => setForm({ ...form, bundle_size: parseInt(e.target.value) || 30 })} data-testid="model-form-bundle-size" />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Deskripsi</label>
              <GlassInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Opsional" data-testid="model-form-description" />
            </div>
            {editing && (
              <p className="text-[11px] text-muted-foreground bg-[var(--glass-bg)] p-2 rounded border border-[var(--glass-border)]">
                💡 <b>Panduan Produksi</b> (SOP, foto jadi, video) dikelola lewat tombol <BookOpen className="inline w-3 h-3" /> di kolom Panduan pada tabel.
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
              <Button variant="ghost" onClick={() => setModalOpen(false)} data-testid="model-form-cancel">Batal</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="model-form-save">{saving ? 'Menyimpan...' : 'Simpan'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {panduanModel && (
        <PanduanProduksiDialog model={panduanModel} token={token} onClose={() => setPanduanModel(null)} onUpdated={fetchRows} />
      )}
    </div>
  );
}
