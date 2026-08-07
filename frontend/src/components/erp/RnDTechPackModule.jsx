import { useState, useEffect, useRef } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  FileText, Plus, Trash2, Pencil, Search, CheckCircle2,
  ExternalLink, X, BookOpen, Upload, Layers, Scissors, Ruler, ListChecks, AlertTriangle,
} from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import RnDUnitSelect, { UOM_STATUS } from './RnDUnitSelect';

const API = process.env.REACT_APP_BACKEND_URL || '';

const STATUS_CONF = {
  draft:      { label: 'Draft',       cls: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30' },
  approved:   { label: 'Disetujui',   cls: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 border-emerald-400 dark:border-emerald-500/30' },
  superseded: { label: 'Digantikan',  cls: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground/60 dark:text-zinc-400 border-border dark:border-zinc-500/30' },
};

const emptyBOM = { material: '', spec: '', qty: 0, unit: 'meter', supplier: '' };
const emptyCP = { seq: 0, title: '', description: '' };
const emptyFab = { name: '', role: 'main' };
const emptyCons = { size: '', fabric_role: 'main', length_cm: '', width_cm: '', yield_pcs: '' };
const DEFAULT_SIZE_COLS = ['S', 'M', 'L', 'XL', 'XXL'];

const emptyForm = {
  style_id: '', style_code: '', style_name: '',
  version: 'v1', title: '', description: '',
  doc_url: '', doc_type: 'pdf',
  bom_items: [{ ...emptyBOM }],
  fabrics: [{ ...emptyFab }],
  fabric_consumption: [],
  construction_points: [],
  construction_notes: '', stitch_type: '', seam_allowance_mm: 10,
  size_grading_notes: '', base_size: 'M', size_range: 'S-XL',
  size_columns: [...DEFAULT_SIZE_COLS],
  fit_categories: [],
  measurements: [],
  status: 'draft',
};

// Normalise measurements to the flexible {point, values:{col:val}} shape.
// Backward-compat: legacy rows {point, S, M, L, XL, XXL} → values map.
function normMeasurements(rows, sizeCols) {
  const cols = (sizeCols && sizeCols.length) ? sizeCols : DEFAULT_SIZE_COLS;
  return (rows || []).map(m => {
    if (m && m.values && typeof m.values === 'object') return { point: m.point || '', values: { ...m.values } };
    const values = {};
    cols.forEach(c => { if (m && m[c] != null && m[c] !== '') values[c] = m[c]; });
    return { point: (m && m.point) || '', values };
  });
}

export default function RnDTechPackModule({ token }) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  const hMultipart = { Authorization: `Bearer ${token}` }; // no Content-Type → browser sets boundary
  const [techPacks, setTechPacks] = useState([]);
  const [styles,    setStyles]    = useState([]);
  const [matOpts,   setMatOpts]   = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [search,    setSearch]    = useState('');
  const [filterStyle, setFilterStyle] = useState('');
  const [showForm,  setShowForm]  = useState(false);
  const [editing,   setEditing]   = useState(null);
  const [form,      setForm]      = useState({ ...emptyForm });
  const [delId,     setDelId]     = useState(null);
  const [expanded,  setExpanded]  = useState(null);
  const [tab,       setTab]       = useState('info'); // info | konstruksi | bahan | bom | measurements

  // Import Excel state
  const [showImport, setShowImport] = useState(false);
  const [importPreview, setImportPreview] = useState(null);
  const [importSummary, setImportSummary] = useState(null);
  const [importBusy, setImportBusy] = useState(false);
  const fileRef = useRef(null);
  const [pickedFileName, setPickedFileName] = useState('');

  const f = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const loadTechPacks = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStyle) qs.set('style_id', filterStyle);
      if (search) qs.set('search', search);
      const res = await fetch(`${API}/api/dewi/rnd/tech-packs?${qs}`, { headers: h });
      setTechPacks(await res.json());
    } catch { toast.error('Gagal memuat tech pack'); }
    finally { setLoading(false); }
  };

  const loadStyles = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles`, { headers: h });
      if (res.ok) setStyles(await res.json());
    } catch { /* ignore */ }
  };

  // Master material untuk MENAUTKAN baris BOM → tanpa tautan ini satuan tidak
  // bisa dikonversi (faktor kemasan/gramasi ada di master material).
  const loadMatOpts = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/material-options`, { headers: h });
      if (res.ok) setMatOpts(await res.json());
    } catch { /* ignore */ }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadTechPacks(); }, [filterStyle]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadStyles(); loadMatOpts(); }, []);

  const setStyleField = sid => {
    const sel = styles.find(s => s.id === sid);
    setForm(p => ({ ...p, style_id: sid, style_code: sel?.style_code || '', style_name: sel?.style_name || '' }));
  };

  // BOM helpers
  const setBOM = (i, k, v) => { const items = [...form.bom_items]; items[i] = { ...items[i], [k]: k === 'qty' ? Number(v) : v }; f('bom_items', items); };
  const addBOM = () => f('bom_items', [...form.bom_items, { ...emptyBOM }]);
  const removeBOM = i => f('bom_items', form.bom_items.filter((_, j) => j !== i));

  // Construction point helpers (b)
  const setCP = (i, k, v) => { const items = [...(form.construction_points || [])]; items[i] = { ...items[i], [k]: v }; f('construction_points', items); };
  const addCP = () => f('construction_points', [...(form.construction_points || []), { ...emptyCP }]);
  const removeCP = i => f('construction_points', (form.construction_points || []).filter((_, j) => j !== i));
  const moveCP = (i, dir) => {
    const items = [...(form.construction_points || [])];
    const j = i + dir; if (j < 0 || j >= items.length) return;
    [items[i], items[j]] = [items[j], items[i]];
    f('construction_points', items);
  };

  // Fabric helpers (c)
  const setFab = (i, k, v) => { const items = [...(form.fabrics || [])]; items[i] = { ...items[i], [k]: v }; f('fabrics', items); };
  const addFab = () => f('fabrics', [...(form.fabrics || []), { ...emptyFab }]);
  const removeFab = i => f('fabrics', (form.fabrics || []).filter((_, j) => j !== i));

  // Consumption helpers (c)
  const setCons = (i, k, v) => { const items = [...(form.fabric_consumption || [])]; items[i] = { ...items[i], [k]: v }; f('fabric_consumption', items); };
  const addCons = () => f('fabric_consumption', [...(form.fabric_consumption || []), { ...emptyCons }]);
  const removeCons = i => f('fabric_consumption', (form.fabric_consumption || []).filter((_, j) => j !== i));

  // Dynamic size columns
  const setSizeCol = (i, v) => { const c = [...(form.size_columns || [])]; c[i] = v; f('size_columns', c); };
  const addSizeCol = () => f('size_columns', [...(form.size_columns || []), '']);
  const removeSizeCol = i => f('size_columns', (form.size_columns || []).filter((_, j) => j !== i));

  // Measurements (dynamic columns)
  const setMeasPoint = (i, v) => { const items = [...(form.measurements || [])]; items[i] = { ...items[i], point: v }; f('measurements', items); };
  const setMeasVal = (i, col, v) => { const items = [...(form.measurements || [])]; const values = { ...(items[i].values || {}) }; values[col] = v; items[i] = { ...items[i], values }; f('measurements', items); };
  const addMeas = () => f('measurements', [...(form.measurements || []), { point: '', values: {} }]);
  const removeMeas = i => f('measurements', (form.measurements || []).filter((_, j) => j !== i));

  const openNew = () => {
    const sel = styles.find(s => s.id === filterStyle);
    setForm({ ...emptyForm, style_id: sel?.id || '', style_code: sel?.style_code || '', style_name: sel?.style_name || '' });
    setEditing(null); setTab('info'); setShowForm(true);
  };

  const openEdit = tp => {
    const sizeCols = (tp.size_columns && tp.size_columns.length) ? tp.size_columns : DEFAULT_SIZE_COLS;
    setForm({
      style_id: tp.style_id || '', style_code: tp.style_code || '', style_name: tp.style_name || '',
      version: String(tp.version || 'v1'), title: tp.title || '', description: tp.description || '',
      doc_url: tp.doc_url || '', doc_type: tp.doc_type || 'pdf',
      bom_items: tp.bom_items?.length ? tp.bom_items : [{ ...emptyBOM }],
      fabrics: tp.fabrics?.length ? tp.fabrics : [{ ...emptyFab }],
      fabric_consumption: tp.fabric_consumption || [],
      construction_points: (tp.construction_points && tp.construction_points.length)
        ? tp.construction_points
        : (tp.construction_notes
            ? tp.construction_notes.split('\n').filter(Boolean).map((d, i) => ({ seq: i + 1, title: '', description: d }))
            : []),
      construction_notes: tp.construction_notes || '',
      stitch_type: tp.stitch_type || '',
      seam_allowance_mm: tp.seam_allowance_mm ?? 10,
      size_grading_notes: tp.size_grading_notes || '',
      base_size: tp.base_size || 'M',
      size_range: tp.size_range || 'S-XL',
      size_columns: [...sizeCols],
      fit_categories: tp.fit_categories || [],
      measurements: normMeasurements(tp.measurements, sizeCols),
      status: tp.status || 'draft',
    });
    setEditing(tp.id); setTab('info'); setShowForm(true);
  };

  const handleApprove = async id => {
    try {
      await fetch(`${API}/api/dewi/rnd/tech-packs/${id}/approve`, { method: 'POST', headers: h });
      toast.success('Tech pack disetujui');
      loadTechPacks();
    } catch { toast.error('Gagal approve'); }
  };

  const handleSave = async () => {
    if (!form.style_id) return toast.error('Pilih style terlebih dahulu');
    if (!form.version.trim()) return toast.error('Versi wajib diisi');
    // keep construction_notes synced from structured points (backward-compat)
    const payload = {
      ...form,
      construction_points: (form.construction_points || []).map((cp, i) => ({ ...cp, seq: i + 1 })),
      construction_notes: (form.construction_points || []).map(cp => cp.description).filter(Boolean).join('\n') || form.construction_notes,
      size_columns: (form.size_columns || []).filter(Boolean),
    };
    try {
      const method = editing ? 'PUT' : 'POST';
      const url = editing ? `${API}/api/dewi/rnd/tech-packs/${editing}` : `${API}/api/dewi/rnd/tech-packs`;
      await fetch(url, { method, headers: h, body: JSON.stringify(payload) });
      toast.success(editing ? 'Tech pack diperbarui' : 'Tech pack ditambahkan');
      setShowForm(false);
      loadTechPacks();
    } catch { toast.error('Gagal menyimpan tech pack'); }
  };

  const handleDelete = async () => {
    try {
      await fetch(`${API}/api/dewi/rnd/tech-packs/${delId}`, { method: 'DELETE', headers: h });
      toast.success('Tech pack dihapus');
      setDelId(null); loadTechPacks();
    } catch { toast.error('Gagal menghapus'); }
  };

  // ── Import Excel ──
  const openImport = () => { setImportPreview(null); setImportSummary(null); setPickedFileName(''); if (fileRef.current) fileRef.current.value = ''; setShowImport(true); };

  const doImport = async (mode) => {
    const file = fileRef.current?.files?.[0];
    if (!file) return toast.error('Pilih file Excel (.xlsx) terlebih dahulu');
    const fd = new FormData();
    fd.append('file', file);
    setImportBusy(true);
    try {
      const url = `${API}/api/dewi/rnd/techpack/import/${mode}`;
      const res = await fetch(url, { method: 'POST', headers: hMultipart, body: fd });
      const data = await res.json();
      if (!res.ok) { toast.error(data?.detail || 'Import gagal'); return; }
      if (mode === 'preview') {
        setImportPreview(data); setImportSummary(null);
        toast.success(`Preview: ${data.total} produk terbaca (${data.errors?.length || 0} error)`);
      } else {
        setImportSummary(data); setImportPreview(null);
        toast.success(`Import selesai: ${data.styles_created} baru, ${data.styles_updated} update, ${data.techpacks} techpack`);
        loadTechPacks(); loadStyles();
      }
    } catch { toast.error('Import gagal (koneksi)'); }
    finally { setImportBusy(false); }
  };

  const filtered = techPacks.filter(tp => {
    if (!search) return true;
    const q = search.toLowerCase();
    return String(tp.title || '').toLowerCase().includes(q)
      || String(tp.style_code || '').toLowerCase().includes(q)
      || String(tp.style_name || '').toLowerCase().includes(q)
      || String(tp.version || '').toLowerCase().includes(q);
  });
  const filteredPg = useClientPagination(filtered, 10);

  const detailSizeCols = (tp) => (tp.size_columns && tp.size_columns.length) ? tp.size_columns : DEFAULT_SIZE_COLS;

  return (
    <div className="p-6 space-y-5" data-testid="rnd-techpack-module">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <FileText className="w-5 h-5 text-violet-500" /> Tech Pack
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">BOM, konstruksi per-poin, penggunaan bahan per-size, & ukuran per kategori</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={openImport} className="gap-2" data-testid="techpack-import-btn">
            <Upload className="w-4 h-4" /> Import Excel
          </Button>
          <Button onClick={openNew} className="gap-2" data-testid="techpack-add-btn">
            <Plus className="w-4 h-4" /> Buat Tech Pack
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadTechPacks()}
            placeholder="Cari style / judul..." className="pl-9" />
        </div>
        <SmartNativeSelect value={filterStyle} onChange={e => setFilterStyle(e.target.value)}
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[200px]">
          <option value="">Semua Style</option>
          {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
        </SmartNativeSelect>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <FileText className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada tech pack.</p>
          <div className="flex gap-2 justify-center mt-3">
            <Button variant="outline" onClick={openImport} className="gap-2"><Upload className="w-4 h-4" /> Import Excel</Button>
            <Button variant="outline" onClick={openNew}>+ Buat Tech Pack Pertama</Button>
          </div>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {filteredPg.paged.map(tp => {
            const sc = STATUS_CONF[tp.status] || STATUS_CONF.draft;
            const cols = detailSizeCols(tp);
            return (
              <GlassCard key={tp.id} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-foreground">{tp.title || `Tech Pack ${tp.version}`}</span>
                      <span className="text-xs font-mono text-foreground/40">{tp.version}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${sc.cls}`}>{sc.label}</span>
                      {tp.is_latest && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400 border border-violet-400 dark:border-violet-500/30">Latest</span>
                      )}
                      {tp.source === 'excel_import' && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-sky-100 dark:bg-sky-500/20 text-sky-700 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30">Import Excel</span>
                      )}
                    </div>
                    <div className="text-xs text-foreground/50 mt-1">
                      {tp.style_code} — {tp.style_name} · Base: {tp.base_size} · Range: {tp.size_range}
                      {(tp.fit_categories || []).length > 0 && <span> · Fit: {tp.fit_categories.join(' / ')}</span>}
                    </div>
                    {tp.description && <p className="text-xs text-foreground/40 mt-1">{tp.description}</p>}
                  </div>
                  <div className="flex gap-1 ml-3 flex-shrink-0">
                    {tp.doc_url && (
                      <a href={tp.doc_url} target="_blank" rel="noreferrer"
                        className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-foreground/[0.08] text-foreground/50 hover:text-foreground">
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                    <Button variant="ghost" size="sm"
                      onClick={() => setExpanded(expanded === tp.id ? null : tp.id)}
                      className="h-8 px-2 text-xs text-foreground/50">
                      <BookOpen className="w-3.5 h-3.5 mr-1" /> {expanded === tp.id ? 'Tutup' : 'Detail'}
                    </Button>
                    {tp.status !== 'approved' && (
                      <Button variant="ghost" size="sm" onClick={() => handleApprove(tp.id)}
                        className="h-8 px-2 text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:bg-emerald-500/10"
                        data-testid={`techpack-approve-${tp.id}`}>
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Setujui
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => openEdit(tp)}
                      className="h-8 w-8 p-0"><Pencil className="w-3.5 h-3.5" /></Button>
                    <Button variant="ghost" size="sm" onClick={() => setDelId(tp.id)}
                      className="h-8 w-8 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:bg-red-500/10">
                      <Trash2 className="w-3.5 h-3.5" /></Button>
                  </div>
                </div>

                {/* Expanded detail */}
                {expanded === tp.id && (
                  <div className="mt-4 pt-4 border-t border-foreground/10 space-y-4">
                    {/* Fabrics */}
                    {tp.fabrics?.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-foreground/40 uppercase tracking-wider mb-1 flex items-center gap-1"><Layers className="w-3 h-3" /> Material / Kain</div>
                        <div className="flex flex-wrap gap-2">
                          {tp.fabrics.map((fb, i) => (
                            <span key={i} className={`text-xs px-2 py-0.5 rounded-full border ${fb.role === 'main' ? 'bg-violet-100 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-500/30' : 'bg-muted text-foreground/60 border-border'}`}>
                              {fb.name} · {fb.role === 'main' ? 'Utama' : 'Kombinasi'}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Construction points */}
                    {tp.construction_points?.length > 0 ? (
                      <div>
                        <div className="text-xs font-semibold text-foreground/40 uppercase tracking-wider mb-1 flex items-center gap-1"><Scissors className="w-3 h-3" /> Tipe Jahitan / Konstruksi ({tp.construction_points.length} poin)</div>
                        <ol className="list-decimal list-inside space-y-0.5 text-sm text-foreground/70">
                          {tp.construction_points.map((cp, i) => (
                            <li key={i}>{cp.title ? <span className="font-medium">{cp.title}: </span> : null}{cp.description}</li>
                          ))}
                        </ol>
                        {tp.stitch_type && <p className="text-xs text-foreground/40 mt-1">Stitch: {tp.stitch_type} · Seam allowance: {tp.seam_allowance_mm}mm</p>}
                      </div>
                    ) : tp.construction_notes ? (
                      <div>
                        <div className="text-xs font-semibold text-foreground/40 uppercase tracking-wider mb-1">Konstruksi</div>
                        <p className="text-sm text-foreground/70 whitespace-pre-line">{tp.construction_notes}</p>
                      </div>
                    ) : null}
                    {/* Fabric consumption */}
                    {tp.fabric_consumption?.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-foreground/40 uppercase tracking-wider mb-2">Penggunaan Bahan (per size)</div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead><tr className="border-b border-foreground/10">
                              {['Size', 'Kain', 'Panjang (cm)', 'Lebar (cm)', 'Hasil (pcs)'].map(c => (
                                <th key={c} className="text-left px-2 py-1.5 text-foreground/40 font-medium">{c}</th>
                              ))}
                            </tr></thead>
                            <tbody>
                              {tp.fabric_consumption.map((e, i) => (
                                <tr key={i} className="border-b border-foreground/5">
                                  <td className="px-2 py-1.5 font-medium text-foreground">{e.size}</td>
                                  <td className="px-2 py-1.5 text-foreground/60">{e.fabric_role === 'main' ? 'Utama' : 'Kombinasi'}</td>
                                  <td className="px-2 py-1.5 text-foreground/70">{e.length_cm ?? '—'}</td>
                                  <td className="px-2 py-1.5 text-foreground/60">{e.width_cm ?? '—'}</td>
                                  <td className="px-2 py-1.5 text-foreground/70">{e.yield_pcs ?? '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {/* BOM */}
                    {tp.bom_items?.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-foreground/40 uppercase tracking-wider mb-2">Bill of Materials</div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead><tr className="border-b border-foreground/10">
                              {['Material', 'Spec', 'Qty', 'Satuan', 'Qty satuan dasar', 'Supplier'].map(c => (
                                <th key={c} className="text-left px-2 py-1.5 text-foreground/40 font-medium">{c}</th>
                              ))}
                            </tr></thead>
                            <tbody>
                              {tp.bom_items.map((b, i) => (
                                <tr key={i} className="border-b border-foreground/5">
                                  <td className="px-2 py-1.5 font-medium text-foreground">{b.material}</td>
                                  <td className="px-2 py-1.5 text-foreground/60">{b.spec}</td>
                                  <td className="px-2 py-1.5 text-foreground/70">{b.qty}</td>
                                  <td className="px-2 py-1.5 text-foreground/60">{b.unit}</td>
                                  <td className={`px-2 py-1.5 ${(UOM_STATUS[b.uom_status] || {}).warn ? 'text-red-600 dark:text-red-400' : 'text-foreground/70'}`}>
                                    {b.qty_base != null
                                      ? <>{b.qty_base} {b.unit_base}{(UOM_STATUS[b.uom_status] || {}).warn ? ` · ${UOM_STATUS[b.uom_status].label}` : ''}</>
                                      : '—'}
                                  </td>
                                  <td className="px-2 py-1.5 text-foreground/50">{b.supplier || '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {/* Measurements (dynamic cols) */}
                    {tp.measurements?.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-foreground/40 uppercase tracking-wider mb-2 flex items-center gap-1"><Ruler className="w-3 h-3" /> Ukuran Detail (cm)</div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead><tr className="border-b border-foreground/10">
                              <th className="text-left px-2 py-1.5 text-foreground/40 font-medium">Titik Ukur</th>
                              {cols.map(c => <th key={c} className="text-left px-2 py-1.5 text-foreground/40 font-medium">{c}</th>)}
                            </tr></thead>
                            <tbody>
                              {normMeasurements(tp.measurements, cols).map((m, i) => (
                                <tr key={i} className="border-b border-foreground/5">
                                  <td className="px-2 py-1.5 font-medium text-foreground">{m.point}</td>
                                  {cols.map(c => <td key={c} className="px-2 py-1.5 text-foreground/70">{m.values[c] || '—'}</td>)}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </GlassCard>
            );
          })}
          {filteredPg.total > 0 && <PaginationLite page={filteredPg.page} totalPages={filteredPg.totalPages} total={filteredPg.total} pageSize={filteredPg.pageSize} onPageChange={filteredPg.setPage} />}
        </div>
      )}

      {/* ── Import Excel Modal ── */}
      <Modal open={showImport} onClose={() => setShowImport(false)} title="Import Techpack dari Excel (V5)" size="xl">
        <div className="space-y-4" data-testid="techpack-import-modal">
          <div className="text-sm text-foreground/60">
            Upload file <b>"Data Techpack Ringkasan Produk"</b> (.xlsx). Sistem akan membuat/memperbarui
            Style, Varian (per warna), dan Tech Pack (konstruksi per-poin, penggunaan bahan per-size, ukuran per kategori).
          </div>
          <div className="flex items-center gap-3">
            <input ref={fileRef} type="file" accept=".xlsx" data-testid="techpack-import-file"
              onChange={e => { setPickedFileName(e.target.files?.[0]?.name || ''); setImportPreview(null); setImportSummary(null); }}
              className="text-sm text-foreground file:mr-3 file:rounded-md file:border-0 file:bg-violet-100 dark:file:bg-violet-500/20 file:text-violet-700 dark:file:text-violet-300 file:px-3 file:py-1.5 file:text-sm" />
            {pickedFileName && <span className="text-xs text-foreground/50 truncate max-w-[200px]">{pickedFileName}</span>}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" disabled={importBusy} onClick={() => doImport('preview')} data-testid="techpack-import-preview-btn" className="gap-2">
              <Search className="w-4 h-4" /> Preview
            </Button>
            <Button disabled={importBusy} onClick={() => doImport('commit')} data-testid="techpack-import-commit-btn" className="gap-2">
              <Upload className="w-4 h-4" /> {importBusy ? 'Memproses...' : 'Import Sekarang'}
            </Button>
          </div>

          {importPreview && (
            <div className="mt-2">
              <div className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1">
                <ListChecks className="w-4 h-4 text-violet-500" /> {importPreview.total} produk terbaca
                {importPreview.errors?.length > 0 && <span className="text-amber-600 text-xs ml-2 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> {importPreview.errors.length} baris bermasalah</span>}
              </div>
              <div className="max-h-[320px] overflow-auto border border-border rounded-md">
                <table className="w-full text-xs">
                  <thead className="bg-foreground/5 sticky top-0"><tr>
                    {['Kode', 'Nama', 'Kategori', 'Warna', 'Size', 'Poin Jahit', 'Kain', 'Kategori Ukuran'].map(c => (
                      <th key={c} className="text-left px-2 py-1.5 text-foreground/50 font-medium">{c}</th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {importPreview.products.map((p, i) => (
                      <tr key={i} className="border-t border-foreground/5">
                        <td className="px-2 py-1.5 font-mono text-blue-700 dark:text-blue-400">{p.style_code}</td>
                        <td className="px-2 py-1.5 font-medium text-foreground">{p.style_name}</td>
                        <td className="px-2 py-1.5 text-foreground/60">{p.category}</td>
                        <td className="px-2 py-1.5 text-foreground/60">{(p.colors || []).length}</td>
                        <td className="px-2 py-1.5 text-foreground/60">{(p.sizes || []).join(', ')}</td>
                        <td className="px-2 py-1.5 text-foreground/60">{(p.construction_points || []).length}</td>
                        <td className="px-2 py-1.5 text-foreground/60">{(p.fabrics || []).map(f => f.name).join(' + ')}</td>
                        <td className="px-2 py-1.5 text-foreground/60">{(p.measurement_categories || []).join(', ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {importSummary && (
            <div className="mt-2 p-4 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30" data-testid="techpack-import-summary">
              <div className="text-sm font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1 mb-2">
                <CheckCircle2 className="w-4 h-4" /> Import Berhasil
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                {[['Style Baru', importSummary.styles_created], ['Style Update', importSummary.styles_updated], ['Varian', importSummary.variants], ['Tech Pack', importSummary.techpacks]].map(([lbl, val]) => (
                  <div key={lbl} className="bg-background/60 rounded-md py-2">
                    <div className="text-lg font-bold text-foreground">{val}</div>
                    <div className="text-xs text-foreground/50">{lbl}</div>
                  </div>
                ))}
              </div>
              {importSummary.errors?.length > 0 && (
                <div className="text-xs text-amber-600 mt-2">{importSummary.errors.length} baris bermasalah (dilewati).</div>
              )}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowImport(false)}>Tutup</Button>
        </div>
      </Modal>

      {/* Form Modal */}
      <Modal open={showForm} onClose={() => setShowForm(false)}
        title={editing ? 'Edit Tech Pack' : 'Buat Tech Pack'} size="xl">
        <div className="flex gap-1 border-b border-foreground/10 mb-5 flex-wrap">
          {[['info', 'Informasi'], ['konstruksi', 'Konstruksi'], ['bahan', 'Bahan'], ['bom', 'BOM'], ['measurements', 'Ukuran']].map(([id, lbl]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`px-4 pb-3 text-sm font-medium border-b-2 transition-all ${
                tab === id ? 'border-violet-500 text-violet-600 dark:text-violet-400' : 'border-transparent text-foreground/50 hover:text-foreground'
              }`}>{lbl}</button>
          ))}
        </div>

        {tab === 'info' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Style <span className="text-red-700 dark:text-red-400">*</span></Label>
                <SmartNativeSelect value={form.style_id} onChange={e => setStyleField(e.target.value)}
                  className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                  <option value="">-- Pilih Style --</option>
                  {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
                </SmartNativeSelect>
              </div>
              <div>
                <Label>Versi <span className="text-red-700 dark:text-red-400">*</span></Label>
                <Input className="mt-1 font-mono" value={form.version} onChange={e => f('version', e.target.value)} placeholder="v1" />
              </div>
            </div>
            <div>
              <Label>Judul Tech Pack</Label>
              <Input className="mt-1" value={form.title} onChange={e => f('title', e.target.value)} placeholder="Contoh: JENIFER Blouse TP v1" />
            </div>
            <div>
              <Label>Deskripsi</Label>
              <textarea value={form.description} onChange={e => f('description', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-16 resize-none" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>URL Dokumen (PDF/Gambar)</Label>
                <Input className="mt-1" value={form.doc_url} onChange={e => f('doc_url', e.target.value)} placeholder="https://..." />
              </div>
              <div>
                <Label>Tipe Dokumen</Label>
                <select value={form.doc_type} onChange={e => f('doc_type', e.target.value)}
                  className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                  <option value="pdf">PDF</option>
                  <option value="image">Gambar</option>
                  <option value="link">Link Eksternal</option>
                  <option value="excel_import">Import Excel</option>
                </select>
              </div>
            </div>
            <GlassCard className="p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3">Size Grading</h3>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Base Size</Label>
                  <Input className="mt-1" value={form.base_size} onChange={e => f('base_size', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Size Range</Label>
                  <Input className="mt-1" value={form.size_range} onChange={e => f('size_range', e.target.value)} placeholder="M - XL (Standar & Jumbo)" />
                </div>
                <div className="col-span-3">
                  <Label className="text-xs">Catatan Grading</Label>
                  <Input className="mt-1" value={form.size_grading_notes} onChange={e => f('size_grading_notes', e.target.value)} />
                </div>
                <div className="col-span-3">
                  <Label className="text-xs">Kategori Fit (info, mis. Standar, Jumbo) — tidak mengubah SKU/varian</Label>
                  <Input className="mt-1" value={(form.fit_categories || []).join(', ')}
                    onChange={e => f('fit_categories', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    placeholder="Standar, Jumbo" data-testid="techpack-fit-categories" />
                </div>
              </div>
            </GlassCard>
          </div>
        )}

        {tab === 'konstruksi' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1"><Scissors className="w-4 h-4" /> Tipe Jahitan / Konstruksi (per poin)</Label>
              <Button type="button" variant="outline" size="sm" onClick={addCP} className="h-7 text-xs gap-1"><Plus className="w-3 h-3" /> Tambah Poin</Button>
            </div>
            {(form.construction_points || []).length === 0 && (
              <div className="text-center py-6 text-foreground/40 text-sm">Belum ada poin konstruksi. Klik "Tambah Poin".</div>
            )}
            {(form.construction_points || []).map((cp, i) => (
              <div key={i} className="flex items-start gap-2 bg-foreground/[0.03] rounded-md p-2">
                <div className="w-6 text-center text-sm font-semibold text-violet-500 pt-2">{i + 1}</div>
                <div className="flex-1 space-y-2">
                  <Input value={cp.title || ''} onChange={e => setCP(i, 'title', e.target.value)} placeholder="Judul (opsional, mis. Kepala Lengan)" className="text-sm h-8" />
                  <textarea value={cp.description || ''} onChange={e => setCP(i, 'description', e.target.value)}
                    placeholder="Deskripsi poin jahitan..." className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-14 resize-none" />
                </div>
                <div className="flex flex-col gap-1">
                  <button type="button" onClick={() => moveCP(i, -1)} className="text-xs text-foreground/40 hover:text-foreground px-1">▲</button>
                  <button type="button" onClick={() => moveCP(i, 1)} className="text-xs text-foreground/40 hover:text-foreground px-1">▼</button>
                  <Button variant="ghost" size="sm" onClick={() => removeCP(i)} className="h-7 w-7 p-0 text-red-700 dark:text-red-500"><X className="w-3.5 h-3.5" /></Button>
                </div>
              </div>
            ))}
            <div className="grid grid-cols-3 gap-3 pt-2 border-t border-foreground/10">
              <div className="col-span-2">
                <Label className="text-xs">Tipe Stitch (umum)</Label>
                <Input className="mt-1" value={form.stitch_type} onChange={e => f('stitch_type', e.target.value)} placeholder="Overlock / single needle..." />
              </div>
              <div>
                <Label className="text-xs">Seam Allowance (mm)</Label>
                <Input className="mt-1" type="number" value={form.seam_allowance_mm} onChange={e => f('seam_allowance_mm', Number(e.target.value))} />
              </div>
            </div>
          </div>
        )}

        {tab === 'bahan' && (
          <div className="space-y-5">
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label className="flex items-center gap-1"><Layers className="w-4 h-4" /> Material / Kain (Utama + Kombinasi)</Label>
                <Button type="button" variant="outline" size="sm" onClick={addFab} className="h-7 text-xs gap-1"><Plus className="w-3 h-3" /> Tambah Kain</Button>
              </div>
              {(form.fabrics || []).map((fb, i) => (
                <div key={i} className="grid grid-cols-[1fr_140px_28px] gap-2 mb-2">
                  <Input value={fb.name} onChange={e => setFab(i, 'name', e.target.value)} placeholder="Nama kain (mis. CONDRU)" className="text-sm" />
                  <select value={fb.role} onChange={e => setFab(i, 'role', e.target.value)}
                    className="border border-input bg-background rounded-md px-2 py-2 text-sm text-foreground">
                    <option value="main">Utama</option>
                    <option value="combination">Kombinasi</option>
                  </select>
                  <Button variant="ghost" size="sm" onClick={() => removeFab(i)} className="h-9 w-7 p-0 text-red-700 dark:text-red-500"><X className="w-3.5 h-3.5" /></Button>
                </div>
              ))}
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>Penggunaan Bahan (per size)</Label>
                <Button type="button" variant="outline" size="sm" onClick={addCons} className="h-7 text-xs gap-1"><Plus className="w-3 h-3" /> Tambah Baris</Button>
              </div>
              {(form.fabric_consumption || []).length === 0 && (
                <div className="text-center py-4 text-foreground/40 text-sm">Belum ada data konsumsi. Contoh: M / Utama / 463 cm / 150 / 5 pcs.</div>
              )}
              {(form.fabric_consumption || []).map((e, i) => (
                <div key={i} className="grid grid-cols-[90px_120px_1fr_1fr_1fr_28px] gap-2 mb-2">
                  <Input value={e.size || ''} onChange={ev => setCons(i, 'size', ev.target.value.toUpperCase())} placeholder="Size" className="text-sm" />
                  <select value={e.fabric_role || 'main'} onChange={ev => setCons(i, 'fabric_role', ev.target.value)}
                    className="border border-input bg-background rounded-md px-2 py-2 text-sm text-foreground">
                    <option value="main">Utama</option>
                    <option value="combination">Kombinasi</option>
                  </select>
                  <Input type="number" value={e.length_cm ?? ''} onChange={ev => setCons(i, 'length_cm', ev.target.value)} placeholder="Panjang cm" className="text-sm" />
                  <Input type="number" value={e.width_cm ?? ''} onChange={ev => setCons(i, 'width_cm', ev.target.value)} placeholder="Lebar cm" className="text-sm" />
                  <Input type="number" value={e.yield_pcs ?? ''} onChange={ev => setCons(i, 'yield_pcs', ev.target.value)} placeholder="Hasil pcs" className="text-sm" />
                  <Button variant="ghost" size="sm" onClick={() => removeCons(i)} className="h-9 w-7 p-0 text-red-700 dark:text-red-500"><X className="w-3.5 h-3.5" /></Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'bom' && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <Label>Bill of Materials</Label>
              <Button type="button" variant="outline" size="sm" onClick={addBOM} className="h-7 text-xs gap-1"><Plus className="w-3 h-3" /> Tambah Item</Button>
            </div>
            <div className="text-[11px] text-foreground/50 bg-foreground/5 rounded-md px-3 py-2 mb-3">
              Tautkan setiap baris ke <b>master material</b> supaya satuannya bisa dikonversi
              (gram→kg, lusin→pcs, meter↔kg untuk kain lewat gramasi &amp; lebar). Tanpa tautan,
              qty dipakai apa adanya dan biaya HPP dari BOM bisa salah.
            </div>
            {form.bom_items.map((b, i) => {
              const st = UOM_STATUS[b.uom_status] || {};
              return (
                <div key={i} className="grid grid-cols-[1fr_150px_1fr_70px_90px_1fr_28px] gap-2 mb-2">
                  <Input value={b.material} onChange={e => setBOM(i, 'material', e.target.value)} placeholder="Material" className="text-sm" data-testid={`tp-bom-material-${i}`} />
                  <SmartNativeSelect value={b.material_id || ''} onChange={e => setBOM(i, 'material_id', e.target.value)}
                    data-testid={`tp-bom-master-${i}`} className="w-full text-sm">
                    <option value="">Tautkan master…</option>
                    {matOpts.map(m => <option key={m.material_id} value={m.material_id}>{m.code} — {m.name} ({m.base_unit})</option>)}
                  </SmartNativeSelect>
                  <Input value={b.spec} onChange={e => setBOM(i, 'spec', e.target.value)} placeholder="Spec" className="text-sm" />
                  <Input type="number" value={b.qty} onChange={e => setBOM(i, 'qty', e.target.value)} placeholder="Qty" className="text-sm" data-testid={`tp-bom-qty-${i}`} />
                  <RnDUnitSelect value={b.unit} onChange={e => setBOM(i, 'unit', e.target.value)} testId={`tp-bom-unit-${i}`} />
                  <Input value={b.supplier} onChange={e => setBOM(i, 'supplier', e.target.value)} placeholder="Supplier" className="text-sm" />
                  <Button variant="ghost" size="sm" onClick={() => removeBOM(i)} className="h-9 w-7 p-0 text-red-700 dark:text-red-500"><X className="w-3.5 h-3.5" /></Button>
                  {b.uom_status && (
                    <div className={`col-span-full -mt-1 mb-1 text-[11px] ${st.warn ? 'text-red-600 dark:text-red-400' : 'text-foreground/50'}`}>
                      {st.warn && <AlertTriangle className="inline w-3 h-3 mr-1 -mt-0.5" />}
                      {b.qty} {b.unit} = <b>{b.qty_base}</b> {b.unit_base} · {b.uom_note || st.label}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {tab === 'measurements' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1"><Ruler className="w-4 h-4" /> Ukuran Detail (per kategori, cm)</Label>
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" onClick={addSizeCol} className="h-7 text-xs gap-1"><Plus className="w-3 h-3" /> Kategori Size</Button>
                <Button type="button" variant="outline" size="sm" onClick={addMeas} className="h-7 text-xs gap-1"><Plus className="w-3 h-3" /> Titik Ukur</Button>
              </div>
            </div>
            {/* Editable size-category headers */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-foreground/50">Kategori Size:</span>
              {(form.size_columns || []).map((c, i) => (
                <div key={i} className="flex items-center gap-1">
                  <Input value={c} onChange={e => setSizeCol(i, e.target.value.toUpperCase())} className="h-7 text-xs w-24" placeholder="STANDAR" />
                  <button type="button" onClick={() => removeSizeCol(i)} className="text-red-500"><X className="w-3 h-3" /></button>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-foreground/5">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs text-foreground/50">Titik Ukur</th>
                    {(form.size_columns || []).map(c => <th key={c} className="text-center px-2 py-2 text-xs text-foreground/50 w-24">{c || '—'}</th>)}
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.measurements || []).map((m, i) => (
                    <tr key={i} className="border-t border-foreground/5">
                      <td className="px-3 py-1.5">
                        <Input value={m.point} onChange={e => setMeasPoint(i, e.target.value)} placeholder="Contoh: LD" className="h-7 text-xs" />
                      </td>
                      {(form.size_columns || []).map(col => (
                        <td key={col} className="px-2 py-1.5">
                          <Input value={(m.values && m.values[col]) || ''} onChange={e => setMeasVal(i, col, e.target.value)} className="h-7 text-xs text-center" placeholder="0" />
                        </td>
                      ))}
                      <td className="py-1.5 px-1">
                        <Button variant="ghost" size="sm" onClick={() => removeMeas(i)} className="h-7 w-7 p-0 text-red-700 dark:text-red-500"><X className="w-3 h-3" /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(form.measurements || []).length === 0 && (
              <div className="text-center py-8 text-foreground/40 text-sm">Belum ada titik ukur. Klik "Titik Ukur" untuk mulai.</div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button onClick={handleSave} data-testid="techpack-save-btn">Simpan</Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus Tech Pack?"
          message="Tech pack ini akan dihapus permanen."
        />
      )}
    </div>
  );
}
