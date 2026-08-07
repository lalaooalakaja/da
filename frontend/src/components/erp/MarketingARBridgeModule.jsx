/**
 * MarketingARBridgeModule — DINONAKTIFKAN (KEPUTUSAN #1)
 *
 * Jalur otomatis "Sales Marketing → AR Finance" telah dimatikan. Pendapatan
 * marketplace kini dicatat oleh Finance melalui Jurnal Manual (Manual Journal
 * Entry). Input sales harian tetap tersedia untuk dashboard marketing (analitik)
 * dan TIDAK lagi memicu pembuatan invoice AR / jurnal GL.
 *
 * Menu "Buat Invoice" sudah disembunyikan dari Portal Marketing. Komponen ini
 * dipertahankan hanya untuk menampilkan pesan jelas jika halaman diakses via
 * tautan lama (deep-link/redirect).
 */
import React from 'react';
import { Info, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function MarketingARBridgeModule() {
  return (
    <div className="p-6 max-w-3xl mx-auto" data-testid="marketing-ar-disabled">
      <Card className="border-amber-300 bg-amber-50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-amber-900">
            <Info className="w-5 h-5" />
            Fitur "Buat Invoice AR dari Sales" dinonaktifkan
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-amber-900">
          <p>
            Sesuai kebijakan terbaru (Keputusan #1), pembuatan <b>Invoice AR otomatis
            dari data Sales Marketing</b> telah <b>dimatikan</b>. Angka penjualan harian
            tidak lagi menjadi piutang/jurnal secara otomatis.
          </p>
          <div className="rounded-lg bg-white border border-amber-200 p-4 space-y-2">
            <p className="font-semibold">Alur pencatatan pendapatan sekarang:</p>
            <ul className="list-disc pl-5 space-y-1">
              <li>
                <b>Input Sales harian</b> tetap berjalan — dipakai untuk
                <b> dashboard &amp; analitik marketing</b> (target, ROI, budget).
              </li>
              <li>
                Pendapatan marketplace dicatat oleh <b>Finance</b> melalui
                <b> Jurnal Manual (Manual Journal Entry)</b> di Portal Finance.
              </li>
            </ul>
          </div>
          <div className="flex items-center gap-2 text-amber-800">
            <ArrowRight className="w-4 h-4" />
            <span>
              Gunakan menu <b>Input Sales</b> untuk analitik, dan Portal <b>Finance →
              Jurnal</b> untuk pencatatan pendapatan.
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
