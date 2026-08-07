import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Calculator, Plus, Trash2, Pencil, ChevronRight, RefreshCw,
  TrendingUp, PackageOpen, Scissors, Package, Settings2, Save, X, Wand2
} from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL || '';

const fmt = (n) => n != null ? formatRupiah(n) : '—';

const emptyAcc = { name: '', unit_cost: 0, qty: 1 };

const emptyForm = {
  hpp_code: '', style_id: '', style_code: '', style_name: '',
  fabric_usage_per_pcs: 0,
  fabric_price_per_meter: 0,
  fabric_source: 'manual', fabric_size: '',
  accessories_cost: [{ name: 'Label / Tag', unit_cost: 500, qty: 1 }],
  cmt_cost_per_pcs: 0,
  cutting_cost_per_pcs: 0,
  packaging_cost_per_pcs: 0,
  overhead_pct: 10,
  margin_pct: 30,
  use_bom: false,
  notes: '', status: 'draft',
};

const PREVIEW_INIT = {
  fabric_cost: 0, accessories_total: 0, cmt_cost: 0, cutting_cost: 0,
  packaging_cost: 0, direct_cost: 0, overhead_value: 0,
  hpp_total: 0, selling_price_proposal: 0,
  margin_pct: 30, overhead_pct: 10,
};

export default function RnDHPPCalculatorModule({ token }) {
  const hdr = useMemo(() => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }), [token]);
  const [records, setRecords]   = useState([]);
  const [styles,  setStyles]    = useState([]);
  const [loading, setLoading]   = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing,  setEditing]  = useState(null);
  const [form,     setForm]     = useState({ ...emptyForm });
  const [preview,  setPreview]  = useState(PREVIEW_INIT);
  const [prevLoading, setPrevLoading] = useState(false);
  const [bomBreakdown, setBomBreakdown] = useState([]);
  const [delId,    setDelId]    = useState(null);

  const f = (name, val) => setForm(prev => ({ ...prev, [name]: val }));

  // #1 HPP otomatis — estimasi biaya kain dari fabric_consumption techpack
  const [fabricEst, setFabricEst] = useState(null);
  const [fabricEstLoading, setFabricEstLoading] = useState(false);

  const loadFabricEstimate = async () => {
    if (!form.style_id) { toast.error('Pilih Style dulu untuk menghitung kain dari techpack'); return; }
    setFabricEstLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp/fabric-estimate?style_id=${form.style_id}`, { headers: hdr });
      const data = await res.json();
      if (!res.ok) { toast.error(data?.detail || 'Techpack belum ada untuk style ini'); setFabricEst(null); return; }
      if (!data.sizes || data.sizes.length === 0) { toast.error('Techpack belum punya data Penggunaan Bahan'); setFabricEst(null); return; }
      setFabricEst(data);
      if (data.has_unresolved_price) toast.warning('Sebagian harga kain belum diset di Riset Material (dianggap Rp0).');
      else toast.success('Estimasi kain dimuat dari techpack');
    } catch { toast.error('Gagal memuat estimasi kain'); }
    finally { setFabricEstLoading(false); }
  };

  const applyFabricSize = (sz) => {
    setForm(prev => ({ ...prev,
      fabric_usage_per_pcs: sz.meters_per_pcs,
      fabric_price_per_meter: sz.weighted_price_per_meter,
      fabric_source: 'techpack', fabric_size: sz.size,
    }));
    toast.success(`Kain size ${sz.size} diterapkan`);
  };

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator`, { headers: hdr });
      setRecords(await res.json());
    } catch { toast.error('Gagal memuat HPP'); }
    finally { setLoading(false); }
  }, [hdr]);

  const loadStyles = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles`, { headers: hdr });
      const data = await res.json();
      setStyles(Array.isArray(data) ? data : (data.items || []));
    } catch { /* ignore */ }
  }, [hdr]);

  useEffect(() => { loadRecords(); loadStyles(); }, [loadRecords, loadStyles]);

  const fetchPreview = useCallback(async (formData) => {
    setPrevLoading(true);
    try {
      // Mode BOM: biaya material dihitung server dari BOM Tech Pack dengan
      // KONVERSI SATUAN (mis. 250 gram ≠ 250 kg), bukan input manual kain.
      const useBom = !!formData.use_bom;
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator/${useBom ? 'compute-from-bom' : 'preview'}`, {
        method: 'POST', headers: hdr, body: JSON.stringify(formData),
      });
      if (res.ok) {
        const data = await res.json();
        setPreview(data);
        if (useBom) setBomBreakdown(data.material_breakdown || []);
      }
    } catch { /* ignore */ }
    finally { setPrevLoading(false); }
  }, [hdr]);

  // Debounced live preview
  useEffect(() => {
    if (!showForm) return;
    const t = setTimeout(() => fetchPreview(form), 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    form.fabric_usage_per_pcs, form.fabric_price_per_meter,
    form.accessories_cost, form.cmt_cost_per_pcs, form.cutting_cost_per_pcs,
    form.packaging_cost_per_pcs, form.overhead_pct, form.margin_pct,
    form.use_bom, form.style_id, showForm, fetchPreview,
  ]);

  const openNew = () => {
    setForm({ ...emptyForm, hpp_code: `HPP-${Date.now().toString(36).toUpperCase()}` });
    setPreview(PREVIEW_INIT);
    setBomBreakdown([]);
    setEditing(null);
    setShowForm(true);
  };

  const openEdit = (rec) => {
    setForm({
      hpp_code: rec.hpp_code || '',
      style_id: rec.style_id || '',
      style_code: rec.style_code || '',
      style_name: rec.style_name || '',
      fabric_usage_per_pcs: rec.fabric_usage_per_pcs || 0,
      fabric_price_per_meter: rec.fabric_price_per_meter || 0,
      fabric_source: rec.fabric_source || 'manual',
      fabric_size: rec.fabric_size || '',
      accessories_cost: rec.accessories_cost?.length ? rec.accessories_cost : [{ ...emptyAcc }],
      cmt_cost_per_pcs: rec.cmt_cost_per_pcs || 0,
      cutting_cost_per_pcs: rec.cutting_cost_per_pcs || 0,
      packaging_cost_per_pcs: rec.packaging_cost_per_pcs || 0,
      overhead_pct: rec.overhead_pct ?? 10,
      margin_pct: rec.margin_pct ?? 30,
      use_bom: !!rec.use_bom,
      notes: rec.notes || '',
      status: rec.status || 'draft',
    });
    setBomBreakdown(rec.bom_breakdown || []);
    setPreview({
      fabric_cost: rec.fabric_cost, accessories_total: rec.accessories_total,
      cmt_cost: rec.cmt_cost, cutting_cost: rec.cutting_cost,
      packaging_cost: rec.packaging_cost, direct_cost: rec.direct_cost,
      overhead_value: rec.overhead_value, hpp_total: rec.hpp_total,
      selling_price_proposal: rec.selling_price_proposal,
      margin_pct: rec.margin_pct, overhead_pct: rec.overhead_pct,
    });
    setEditing(rec.id);
    setShowForm(true);
  };

  const setStyleField = (styleId) => {
    const sel = styles.find(s => s.id === styleId);
    setForm(prev => ({ ...prev, style_id: styleId, style_code: sel?.style_code || '', style_name: sel?.style_name || '' }));
    setFabricEst(null);
  };

  const setAcc = (idx, field, val) => {
    const acc = [...form.accessories_cost];
    acc[idx] = { ...acc[idx], [field]: ['unit_cost', 'qty'].includes(field) ? Number(val) : val };
    f('accessories_cost', acc);
  };

  const addAcc = () => f('accessories_cost', [...form.accessories_cost, { ...emptyAcc }]);
  const removeAcc = (idx) => f('accessories_cost', form.accessories_cost.filter((_, i) => i !== idx));

  const handleSave = async (statusOverride) => {
    if (!form.hpp_code) return toast.error('Isi kode HPP');
    const payload = { ...form, ...(statusOverride ? { status: statusOverride } : {}) };
    try {
      const method = editing ? 'PUT' : 'POST';
      const url = editing
        ? `${API}/api/dewi/rnd/hpp-calculator/${editing}`
        : `${API}/api/dewi/rnd/hpp-calculator`;
      await fetch(url, { method, headers: hdr, body: JSON.stringify(payload) });
      toast.success(editing ? 'HPP diperbarui' : 'HPP disimpan');
      setShowForm(false);
      loadRecords();
    } catch { toast.error('Gagal menyimpan HPP'); }
  };

  const handleDelete = async () => {
    try {
      await fetch(`${API}/api/dewi/rnd/hpp-calculator/${delId}`, { method: 'DELETE', headers: hdr });
      toast.success('HPP dihapus');
      setDelId(null);
      loadRecords();
    } catch { toast.error('Gagal menghapus'); }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(records, 10);
  return (
    <div className="p-6" data-testid="rnd-hpp-module">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Calculator className="w-5 h-5 text-violet-500" /> HPP Calculator
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">Kalkulasi Harga Pokok Produksi → Proposal Harga Jual</p>
        </div>
        <Button onClick={openNew} className="gap-2" data-testid="rnd-hpp-add-btn">
          <Plus className="w-4 h-4" /> Hitung HPP Baru
        </Button>
      </div>

      {/* Saved records */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : records.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Calculator className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada kalkulasi HPP.</p>
          <Button variant="outline" className="mt-3" onClick={openNew}>+ Hitung HPP Pertama</Button>
        </GlassCard>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 border-b border-foreground/10">
              <tr>
                {['Kode HPP', 'Style', 'Direct Cost', 'Overhead', 'HPP/pcs', 'Harga Jual Proposal', 'Margin', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map(rec => (
                <tr key={rec.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03] last:border-0">
                  <td className="px-4 py-3 font-mono text-xs text-foreground/70">{rec.hpp_code}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium">{rec.style_code || '—'}</div>
                    <div className="text-xs text-foreground/50">{rec.style_name}</div>
                  </td>
                  <td className="px-4 py-3 text-foreground/70">{fmt(rec.direct_cost)}</td>
                  <td className="px-4 py-3 text-foreground/70">{fmt(rec.overhead_value)}</td>
                  <td className="px-4 py-3 font-semibold text-foreground">{fmt(rec.hpp_total)}</td>
                  <td className="px-4 py-3 font-bold text-emerald-500">{fmt(rec.selling_price_proposal)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/15 text-emerald-500 border border-emerald-500/25">
                      {rec.margin_pct}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(rec)}
                        className="h-7 w-7 p-0" data-testid={`rnd-hpp-edit-${rec.id}`}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setDelId(rec.id)}
                        className="h-7 w-7 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:bg-red-500/10"
                        data-testid={`rnd-hpp-del-${rec.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}

      {/* HPP Form Modal */}
      <Modal open={showForm} onClose={() => setShowForm(false)}
        title={editing ? 'Edit HPP' : 'Hitung HPP Baru'} size="xl">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left: Inputs */}
          <div className="lg:col-span-3 space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Kode HPP <span className="text-red-700 dark:text-red-400">*</span></Label>
                <Input className="mt-1 font-mono" value={form.hpp_code}
                  onChange={e => f('hpp_code', e.target.value)} />
              </div>
              <div>
                <Label>Style (Opsional)</Label>
                <SmartNativeSelect value={form.style_id} onChange={e => setStyleField(e.target.value)}
                  className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                  <option value="">-- Pilih Style --</option>
                  {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
                </SmartNativeSelect>
              </div>
            </div>

            {/* Material dari BOM Tech Pack (sadar satuan) */}
            <GlassCard className="p-4" data-testid="hpp-bom-card">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <PackageOpen className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Material dari BOM Tech Pack
                  {form.use_bom && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300">
                      aktif — input kain &amp; aksesoris manual diabaikan
                    </span>
                  )}
                </h3>
                <Button type="button" variant={form.use_bom ? 'default' : 'outline'} size="sm"
                  onClick={() => f('use_bom', !form.use_bom)} className="h-7 text-xs gap-1"
                  data-testid="hpp-use-bom-toggle">
                  <Wand2 className="w-3 h-3" /> {form.use_bom ? 'Pakai input manual' : 'Hitung dari BOM'}
                </Button>
              </div>
              {!form.use_bom ? (
                <p className="text-xs text-foreground/50">
                  Aktifkan untuk memakai BOM Tech Pack terbaru dari style terpilih. Qty tiap baris BOM
                  dikonversi otomatis ke satuan harga materialnya (gram→kg, lusin→pcs, meter↔kg untuk kain).
                </p>
              ) : bomBreakdown.length === 0 ? (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  BOM belum ditemukan untuk style ini — pilih Style yang punya Tech Pack berisi BOM.
                </p>
              ) : (
                <div className="overflow-x-auto" data-testid="hpp-bom-breakdown">
                  <table className="w-full text-xs">
                    <thead><tr className="border-b border-foreground/10">
                      {['Material', 'Qty BOM', 'Qty dihitung', 'Harga', 'Biaya', 'Sumber harga'].map(c => (
                        <th key={c} className="text-left px-2 py-1.5 text-foreground/40 font-medium">{c}</th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {bomBreakdown.map((b, i) => {
                        const warn = ['mismatch', 'unlinked'].includes(b.uom_status) || b.cost_source === 'unresolved';
                        return (
                          <tr key={i} className="border-b border-foreground/5">
                            <td className="px-2 py-1.5 font-medium text-foreground">
                              {b.material_name || b.material_code || '—'}
                              {warn && <span className="block text-[10px] text-red-600 dark:text-red-400">{b.uom_note || 'harga/satuan belum lengkap'}</span>}
                            </td>
                            <td className="px-2 py-1.5 text-foreground/60">{b.qty} {b.unit || '—'}</td>
                            <td className="px-2 py-1.5 text-foreground/70">{b.qty_costed} {b.cost_unit}</td>
                            <td className="px-2 py-1.5 text-foreground/70">{fmt(b.unit_cost)}</td>
                            <td className="px-2 py-1.5 font-semibold text-foreground">{fmt(b.line_cost)}</td>
                            <td className="px-2 py-1.5 text-foreground/40">{b.cost_source}</td>
                          </tr>
                        );
                      })}
                      <tr>
                        <td colSpan="4" className="px-2 py-1.5 text-right text-foreground/60">Total material dari BOM</td>
                        <td className="px-2 py-1.5 font-bold text-violet-600 dark:text-violet-400" data-testid="hpp-bom-total">
                          {fmt(preview.material_cost)}
                        </td>
                        <td />
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </GlassCard>

            {/* Bahan Kain */}
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <PackageOpen className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Bahan Kain
                  {form.fabric_source === 'techpack' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300">
                      dari Techpack{form.fabric_size ? ` · ${form.fabric_size}` : ''}
                    </span>
                  )}
                </h3>
                <Button type="button" variant="outline" size="sm" onClick={loadFabricEstimate}
                  disabled={fabricEstLoading} className="h-7 text-xs gap-1" data-testid="hpp-fabric-from-techpack">
                  <Wand2 className="w-3 h-3" /> {fabricEstLoading ? 'Memuat...' : 'Hitung dari Techpack'}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Pemakaian kain/pcs (meter)</Label>
                  <Input className="mt-1" type="number" step="0.01" value={form.fabric_usage_per_pcs}
                    onChange={e => { f('fabric_usage_per_pcs', Number(e.target.value)); f('fabric_source', 'manual'); }} />
                </div>
                <div>
                  <Label className="text-xs">Harga kain/meter (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.fabric_price_per_meter}
                    onChange={e => { f('fabric_price_per_meter', Number(e.target.value)); f('fabric_source', 'manual'); }} />
                </div>
              </div>
              <div className="mt-2 text-xs text-foreground/50">
                Biaya kain = {form.fabric_usage_per_pcs} m × Rp {Number(form.fabric_price_per_meter).toLocaleString('id-ID')} = <strong className="text-foreground">{fmt(form.fabric_usage_per_pcs * form.fabric_price_per_meter)}</strong>
              </div>

              {fabricEst && fabricEst.sizes?.length > 0 && (
                <div className="mt-3 border-t border-foreground/10 pt-3" data-testid="hpp-fabric-estimate-panel">
                  <div className="text-xs font-medium text-foreground/60 mb-2">
                    Estimasi techpack <b>{fabricEst.style_code}</b> — klik size untuk pakai:
                    {fabricEst.has_unresolved_price && <span className="text-amber-600 ml-1">(sebagian harga Rp0 — set di Riset Material)</span>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {fabricEst.sizes.map(sz => (
                      <button key={sz.size} type="button" onClick={() => applyFabricSize(sz)}
                        className={`text-xs px-2 py-1 rounded-md border transition-colors ${form.fabric_size === sz.size && form.fabric_source === 'techpack'
                          ? 'bg-violet-100 dark:bg-violet-500/20 border-violet-400 text-violet-700 dark:text-violet-300'
                          : 'bg-background border-border text-foreground/70 hover:border-violet-400'}`}>
                        <b>{sz.size}</b>: {sz.meters_per_pcs}m × Rp{Number(sz.weighted_price_per_meter).toLocaleString('id-ID')} = {fmt(sz.fabric_cost_per_pcs)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </GlassCard>

            {/* Aksesoris */}
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Package className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Aksesoris & Bahan Tambahan
                </h3>
                <Button type="button" variant="outline" size="sm" onClick={addAcc} className="h-7 text-xs gap-1">
                  <Plus className="w-3 h-3" /> Tambah
                </Button>
              </div>
              {form.accessories_cost.map((acc, i) => (
                <div key={i} className="grid grid-cols-[1fr_110px_70px_32px] gap-2 mb-2">
                  <Input value={acc.name} onChange={e => setAcc(i, 'name', e.target.value)}
                    placeholder="Nama item" className="text-sm" />
                  <Input type="number" value={acc.unit_cost}
                    onChange={e => setAcc(i, 'unit_cost', e.target.value)}
                    placeholder="Harga/unit" className="text-sm" />
                  <Input type="number" value={acc.qty} min="1"
                    onChange={e => setAcc(i, 'qty', e.target.value)}
                    placeholder="Qty" className="text-sm" />
                  <Button variant="ghost" size="sm" onClick={() => removeAcc(i)}
                    className="h-9 w-8 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:bg-red-500/10">
                    <X className="w-3.5 h-3.5" />
                  </Button>
                </div>
              ))}
            </GlassCard>

            {/* Biaya Proses */}
            <GlassCard className="p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <Scissors className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Biaya Proses /pcs
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Ongkos CMT (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.cmt_cost_per_pcs}
                    onChange={e => f('cmt_cost_per_pcs', Number(e.target.value))} />
                </div>
                <div>
                  <Label className="text-xs">Biaya Cutting (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.cutting_cost_per_pcs}
                    onChange={e => f('cutting_cost_per_pcs', Number(e.target.value))} />
                </div>
                <div>
                  <Label className="text-xs">Packaging/pcs (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.packaging_cost_per_pcs}
                    onChange={e => f('packaging_cost_per_pcs', Number(e.target.value))} />
                </div>
              </div>
            </GlassCard>

            {/* Overhead & Margin */}
            <GlassCard className="p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Overhead & Target Margin
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Overhead (%)</Label>
                  <Input className="mt-1" type="number" step="0.5" value={form.overhead_pct}
                    onChange={e => f('overhead_pct', Number(e.target.value))} />
                  <div className="text-xs text-foreground/40 mt-1">dari total direct cost</div>
                </div>
                <div>
                  <Label className="text-xs">Target Margin (%)</Label>
                  <Input className="mt-1" type="number" step="0.5" value={form.margin_pct}
                    onChange={e => f('margin_pct', Number(e.target.value))} />
                  <div className="text-xs text-foreground/40 mt-1">dari harga jual</div>
                </div>
              </div>
            </GlassCard>

            <div>
              <Label>Catatan</Label>
              <textarea value={form.notes} onChange={e => f('notes', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-16 resize-none" />
            </div>
          </div>

          {/* Right: Live Preview */}
          <div className="lg:col-span-2">
            <div className="sticky top-0">
              <GlassCard className="p-5 border-violet-300 dark:border-violet-500/20 bg-gradient-to-br from-violet-500/5 to-purple-500/5">
                <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-violet-500" />
                  Hasil Kalkulasi
                  {prevLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-foreground/40" />}
                </h3>

                <div className="space-y-2.5 text-sm">
                  {[
                    { label: 'Biaya Kain',         val: preview.fabric_cost,         color: '' },
                    { label: 'Biaya Aksesoris',     val: preview.accessories_total,   color: '' },
                    { label: 'Ongkos CMT',          val: preview.cmt_cost,            color: '' },
                    { label: 'Biaya Cutting',       val: preview.cutting_cost,        color: '' },
                    { label: 'Packaging',           val: preview.packaging_cost,      color: '' },
                  ].map(row => (
                    <div key={row.label} className="flex items-center justify-between">
                      <span className="text-foreground/60">{row.label}</span>
                      <span className="font-mono text-foreground">{fmt(row.val)}</span>
                    </div>
                  ))}

                  <div className="border-t border-foreground/10 pt-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-foreground/70 font-medium">Direct Cost</span>
                      <span className="font-mono font-semibold text-foreground">{fmt(preview.direct_cost)}</span>
                    </div>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-foreground/60">Overhead ({preview.overhead_pct}%)</span>
                      <span className="font-mono text-foreground/70">{fmt(preview.overhead_value)}</span>
                    </div>
                  </div>

                  <div className="border-t border-violet-400 dark:border-violet-500/30 pt-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">HPP / pcs</span>
                      <span className="font-mono font-bold text-foreground text-base">{fmt(preview.hpp_total)}</span>
                    </div>
                  </div>

                  <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-500/25 rounded-xl p-3 mt-3">
                    <div className="text-xs text-emerald-500/70 mb-1">Harga Jual Proposal</div>
                    <div className="text-xl font-bold text-emerald-500">{fmt(preview.selling_price_proposal)}</div>
                    <div className="text-xs text-emerald-500/60 mt-1">Margin {preview.margin_pct}% dari harga jual</div>
                  </div>
                </div>
              </GlassCard>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button variant="outline" onClick={() => handleSave('draft')} className="gap-2">
            <Save className="w-4 h-4" /> Simpan Draft
          </Button>
          <Button onClick={() => handleSave('approved')} className="gap-2" data-testid="rnd-hpp-save-btn">
            <CheckCircle2_Icon /> Simpan & Setujui
          </Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus HPP?"
          message="Data kalkulasi HPP akan dihapus permanen."
        />
      )}
    </div>
  );
}

function CheckCircle2_Icon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

