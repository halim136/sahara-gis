import React, { useState, useRef } from 'react';
import {
  X,
  MapPin,
  Trash2,
  Download,
  Upload,
  Plus,
  FileCode,
  Tag,
  CheckCircle2,
  FolderOpen,
  Table,
  Search,
  FileSpreadsheet,
  FileUp,
  Eye,
  EyeOff
} from 'lucide-react';
import { MarkItem } from '../types';
import { DraggableWindow } from './DraggableWindow';

interface MarksManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  marks: MarkItem[];
  onAddMark: (mark: MarkItem) => void;
  onDeleteMark: (id: string) => void;
  onImportMarks: (marks: MarkItem[]) => void;
  onToggleMark?: (id: string) => void;
  onSetAllHidden?: (hidden: boolean) => void;
  onStyleMark?: (id: string, patch: Partial<MarkItem>) => void;
  lang: 'ar' | 'en';
}

export const MarksManagerModal: React.FC<MarksManagerModalProps> = ({
  isOpen,
  onClose,
  marks,
  onAddMark,
  onDeleteMark,
  onImportMarks,
  onToggleMark,
  onSetAllHidden,
  onStyleMark,
  lang
}) => {
  const isAr = lang === 'ar';
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [tableView, setTableView] = useState<boolean>(false);
  const [tableFilter, setTableFilter] = useState<string>('');
  const [importText, setImportText] = useState<string>('');
  const [isImporting, setIsImporting] = useState<boolean>(false);
  const [importMessage, setImportMessage] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const anyVisible = marks.some((m) => !m.hidden);

  // New Mark Form
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [newName, setNewName] = useState<string>('');
  const [newLat, setNewLat] = useState<string>('30.0444');
  const [newLon, setNewLon] = useState<string>('31.2357');
  const [newDesc, setNewDesc] = useState<string>('');
  const [newColor, setNewColor] = useState<string>('#ef4444');
  const [newCategory, setNewCategory] = useState<string>('POI');

  if (!isOpen) return null;

  const categories = Array.from(new Set(marks.map((m) => m.category || 'General')));

  const filteredMarks = activeCategory === 'all'
    ? marks
    : marks.filter((m) => (m.category || 'General') === activeCategory);

  const handleCreateMark = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName) return;
    const lat = parseFloat(newLat);
    const lon = parseFloat(newLon);
    if (isNaN(lat) || isNaN(lon)) return;

    const newMark: MarkItem = {
      id: 'mark_' + Date.now(),
      name: newName,
      type: 'point',
      coords: [lon, lat],
      description: newDesc,
      color: newColor,
      category: newCategory,
      timestamp: new Date().toISOString()
    };

    onAddMark(newMark);
    setNewName('');
    setNewDesc('');
    setShowAddForm(false);
  };

  const handleExport = async (format: 'gpx' | 'kml' | 'geojson' | 'dxf' | 'dxf_ns' | 'shapefile') => {
    try {
      const res = await fetch('/api/python/vector/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ marks, format })
      });
      const data = await res.json();
      if (data.success) {
        let blob: Blob, ext: string;
        if (format === 'shapefile') {
          const bin = Uint8Array.from(atob(String(data.content).trim()), (c) => c.charCodeAt(0));
          blob = new Blob([bin], { type: 'application/zip' });
          ext = 'zip';
        } else {
          blob = new Blob([data.content], { type: 'text/plain;charset=utf-8' });
          ext = format.startsWith('dxf') ? 'dxf' : format;
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `marks_export_${Date.now()}.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      alert(`Export error: ${e.message}`);
    }
  };

  // Attribute table: columns are the union of every mark's property keys.
  const attributeKeys = Array.from(new Set(filteredMarks.flatMap((m) => Object.keys(m.properties || {}).filter((k) => k !== 'holes'))));
  const cell = (mark: MarkItem, key: string): string => {
    const value = (mark.properties || {})[key];
    return value == null ? '' : String(value);
  };
  const tableRows = filteredMarks.filter((m) => {
    if (!tableFilter.trim()) return true;
    const needle = tableFilter.toLowerCase();
    return (m.name + ' ' + attributeKeys.map((k) => cell(m, k)).join(' ')).toLowerCase().includes(needle);
  });
  const zoomToMark = (mark: MarkItem) => {
    const map = (window as any).__SAS_MAP;
    if (!map) return;
    const pts: [number, number][] = mark.type === 'point' ? [mark.coords] : mark.coords;
    if (mark.type === 'point') { map.setView([pts[0][1], pts[0][0]], 16); return; }
    const lats = pts.map((p) => p[1]), lons = pts.map((p) => p[0]);
    map.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], { padding: [40, 40], maxZoom: 18 });
  };
  const exportCsv = () => {
    const columns = ['name', 'type', 'category', ...attributeKeys];
    const escape = (value: string) => '"' + value.replace(/"/g, '""') + '"';
    const header = columns.map(escape).join(',');
    const body = tableRows.map((m) => columns.map((c) =>
      escape(c === 'name' ? m.name || '' : c === 'type' ? m.type : c === 'category' ? (m.category || '') : cell(m, c))
    ).join(',')).join('\n');
    const blob = new Blob(['﻿' + header + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `marks_table_${Date.now()}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  // Binary/point·line·polygon file import (KML/KMZ/GPX/GeoJSON/Shapefile ZIP/SML/DB3).
  const handleFileImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setImportMessage(isAr ? 'جاري قراءة الملف…' : 'Reading file…');
    try {
      const res = await fetch('/api/studio/upload/vector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) },
        body: file
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Import failed');
      const imported: MarkItem[] = data.result?.marks || [];
      if (imported.length > 0) {
        onImportMarks(imported);
        setImportMessage(
          isAr
            ? `تم استيراد ${imported.length} عنصراً من ${file.name} (${data.result.format})`
            : `Imported ${imported.length} features from ${file.name} (${data.result.format})`
        );
      } else {
        setImportMessage(isAr ? 'لم يتم العثور على عناصر صالحة في الملف' : 'No valid features found in the file');
      }
    } catch (e: any) {
      setImportMessage(`${isAr ? 'خطأ الاستيراد:' : 'Import error:'} ${e.message}`);
    }
  };

  const handleImport = async () => {
    if (!importText) return;
    setImportMessage('');
    try {
      const res = await fetch('/api/python/vector/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: importText })
      });
      const data = await res.json();
      if (data.marks && data.marks.length > 0) {
        onImportMarks(data.marks);
        setImportMessage(
          isAr
            ? `تم استيراد ${data.marks.length} علامة بنجاح من صيغة (${data.format})!`
            : `Successfully imported ${data.marks.length} items from ${data.format}!`
        );
        setImportText('');
        setIsImporting(false);
      } else {
        setImportMessage(data.error || (isAr ? 'لم يتم العثور على علامات صالحة' : 'No valid marks found'));
      }
    } catch (e: any) {
      setImportMessage(`Import error: ${e.message}`);
    }
  };

  return (
    <DraggableWindow lang={lang}>
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden text-slate-200">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <MapPin className="w-5 h-5 text-rose-400" />
            <h2 className="text-sm font-bold text-white">
              {isAr ? 'مدير العلامات والتصنيفات (Marks & Categories Manager)' : 'Marks & Categories Manager'}
            </h2>
            <span className="text-[11px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
              {marks.length} {isAr ? 'علامة' : 'Marks'}
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Action Bar */}
        <div className="flex items-center justify-between px-4 py-2 bg-slate-950/60 border-b border-slate-800 flex-wrap gap-2 text-xs">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{isAr ? 'إضافة علامة جديدة' : 'Add New Mark'}</span>
            </button>

            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".kml,.kmz,.gpx,.geojson,.json,.zip,.sml,.db3"
              onChange={handleFileImport}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              title={isAr ? 'استيراد ملف نقطي أو خطي أو مساحي' : 'Import point / line / polygon file'}
            >
              <FileUp className="w-3.5 h-3.5 text-teal-400" />
              <span>{isAr ? 'استيراد ملف (KML·GPX·SML·DB3·SHP)' : 'Import file'}</span>
            </button>

            <button
              onClick={() => setIsImporting(!isImporting)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            >
              <Upload className="w-3.5 h-3.5 text-amber-400" />
              <span>{isAr ? 'لصق نص (GPX / KML / GeoJSON)' : 'Paste text'}</span>
            </button>

            {onSetAllHidden && marks.length > 0 && (
              <button
                onClick={() => onSetAllHidden(anyVisible)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
                title={isAr ? 'إظهار أو إخفاء كل العلامات على الخريطة' : 'Show or hide all marks on the map'}
              >
                {anyVisible ? <EyeOff className="w-3.5 h-3.5 text-slate-300" /> : <Eye className="w-3.5 h-3.5 text-emerald-400" />}
                <span>{anyVisible ? (isAr ? 'إخفاء الكل' : 'Hide all') : (isAr ? 'إظهار الكل' : 'Show all')}</span>
              </button>
            )}

            <button
              onClick={() => setTableView((v) => !v)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-semibold transition-colors ${tableView ? 'bg-teal-600 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-200'}`}
              title={isAr ? 'جدول الخصائص' : 'Attribute table'}
            >
              <Table className="w-3.5 h-3.5" />
              <span>{isAr ? 'جدول الخصائص' : 'Attribute table'}</span>
            </button>
          </div>

          {/* Export Buttons */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400 text-[11px] me-1">{isAr ? 'تصدير:' : 'Export:'}</span>
            <button onClick={() => handleExport('gpx')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-[11px]">GPX</button>
            <button onClick={() => handleExport('kml')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-[11px]">KML</button>
            <button onClick={() => handleExport('geojson')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-[11px]">GeoJSON</button>
            <button onClick={() => handleExport('dxf')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-[11px]" title={isAr ? 'DXF بإحداثيات WGS84' : 'DXF in WGS84 lon/lat'}>DXF</button>
            <button onClick={() => handleExport('dxf_ns')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 font-mono text-[11px]" title={isAr ? 'DXF مُسقط إلى Nord Sahara UTM (متر) للأوتوكاد' : 'DXF projected to Nord Sahara UTM (metres) for AutoCAD'}>DXF·NS</button>
            <button onClick={() => handleExport('shapefile')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-300 font-mono text-[11px]" title={isAr ? 'تصدير Shapefile داخل ملف ZIP (نقاط/خطوط/مساحات)' : 'Shapefile export in a ZIP (points/lines/polygons)'}>SHP</button>
          </div>
        </div>

        {/* Import Box */}
        {isImporting && (
          <div className="p-4 bg-slate-950/90 border-b border-slate-800 space-y-2 animate-in fade-in">
            <label className="block text-xs font-semibold text-slate-300">
              {isAr ? 'الصق محتوى ملف GPX أو KML أو GeoJSON هنا للاستيراد:' : 'Paste GPX, KML, or GeoJSON content here:'}
            </label>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              rows={4}
              placeholder="<gpx>... or <kml>... or { type: 'FeatureCollection' ... }"
              className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-xs font-mono text-slate-200 outline-none"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setIsImporting(false)}
                className="px-3 py-1 rounded bg-slate-800 text-slate-300 text-xs"
              >
                {isAr ? 'إلغاء' : 'Cancel'}
              </button>
              <button
                onClick={handleImport}
                className="px-4 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs"
              >
                {isAr ? 'بدء الاستيراد' : 'Import'}
              </button>
            </div>
          </div>
        )}

        {importMessage && (
          <div className="px-4 py-2 bg-emerald-950/40 border-b border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>{importMessage}</span>
          </div>
        )}

        {/* Add Form */}
        {showAddForm && (
          <form onSubmit={handleCreateMark} className="p-4 bg-slate-950/90 border-b border-slate-800 grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs animate-in fade-in">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">{isAr ? 'اسم العلامة:' : 'Mark Name:'}</label>
              <input
                type="text"
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={isAr ? 'مثال: نقطة أهرامات الجيزة' : 'e.g. Pyramids POI'}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-300 mb-1">{isAr ? 'خط العرض (Lat):' : 'Latitude:'}</label>
              <input
                type="text"
                required
                value={newLat}
                onChange={(e) => setNewLat(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-300 mb-1">{isAr ? 'خط الطول (Lon):' : 'Longitude:'}</label>
              <input
                type="text"
                required
                value={newLon}
                onChange={(e) => setNewLon(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-300 mb-1">{isAr ? 'اللون والتصنيف:' : 'Color & Category:'}</label>
              <div className="flex gap-2">
                <input
                  type="color"
                  value={newColor}
                  onChange={(e) => setNewColor(e.target.value)}
                  className="w-8 h-8 rounded border-0 bg-transparent cursor-pointer"
                />
                <input
                  type="text"
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  placeholder="POI"
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
                />
              </div>
            </div>
            <div className="sm:col-span-4 flex justify-end gap-2 mt-1">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-3 py-1 rounded bg-slate-800 text-slate-300"
              >
                {isAr ? 'إلغاء' : 'Cancel'}
              </button>
              <button
                type="submit"
                className="px-4 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold"
              >
                {isAr ? 'حفظ العلامة' : 'Save Mark'}
              </button>
            </div>
          </form>
        )}

        {/* Categories Bar */}
        <div className="flex items-center gap-1.5 px-4 py-1.5 bg-slate-950 text-xs border-b border-slate-800 overflow-x-auto">
          <button
            onClick={() => setActiveCategory('all')}
            className={`px-2.5 py-1 rounded transition-colors ${
              activeCategory === 'all' ? 'bg-blue-600 text-white font-semibold' : 'text-slate-400 hover:bg-slate-800'
            }`}
          >
            {isAr ? 'الكل' : 'All'} ({marks.length})
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeCategory === cat ? 'bg-blue-600 text-white font-semibold' : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Attribute Table */}
        {tableView ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2 bg-slate-950/60 border-b border-slate-800">
              <Search className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              <input
                value={tableFilter}
                onChange={(e) => setTableFilter(e.target.value)}
                placeholder={isAr ? 'تصفية حسب أي قيمة…' : 'Filter by any value…'}
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 outline-none"
              />
              <span className="text-[11px] text-slate-400 font-mono">{tableRows.length}/{filteredMarks.length}</span>
              <button onClick={exportCsv} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-[11px] font-semibold">
                <FileSpreadsheet className="w-3.5 h-3.5" />{isAr ? 'تصدير CSV' : 'Export CSV'}
              </button>
            </div>
            <div className="flex-1 overflow-auto">
              {tableRows.length === 0 ? (
                <div className="text-center py-10 text-slate-500 text-xs">{isAr ? 'لا توجد صفوف مطابقة.' : 'No matching rows.'}</div>
              ) : (
                <table className="w-max min-w-full text-[11px] border-collapse">
                  <thead className="sticky top-0 bg-slate-950 text-slate-400">
                    <tr className="text-start">
                      <th className="px-2 py-1.5 text-start font-semibold border-b border-slate-800">{isAr ? 'الاسم' : 'Name'}</th>
                      <th className="px-2 py-1.5 text-start font-semibold border-b border-slate-800">{isAr ? 'النوع' : 'Type'}</th>
                      {attributeKeys.map((key) => (
                        <th key={key} className="px-2 py-1.5 text-start font-semibold border-b border-slate-800 font-mono whitespace-nowrap">{key}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tableRows.map((mark) => (
                      <tr key={mark.id} onClick={() => zoomToMark(mark)} className="hover:bg-slate-800/50 cursor-pointer" title={isAr ? 'انقر للانتقال إلى العنصر' : 'Click to zoom to feature'}>
                        <td className="px-2 py-1.5 border-b border-slate-900 text-slate-200 font-semibold whitespace-nowrap">
                          <span className="inline-block w-2 h-2 rounded-full me-1.5 align-middle" style={{ backgroundColor: mark.color || '#ef4444' }} />{mark.name}
                        </td>
                        <td className="px-2 py-1.5 border-b border-slate-900 text-slate-500 font-mono">{mark.type}</td>
                        {attributeKeys.map((key) => (
                          <td key={key} className="px-2 py-1.5 border-b border-slate-900 text-slate-300 whitespace-nowrap" dir="ltr">{cell(mark, key)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {attributeKeys.length === 0 && (
              <div className="px-4 py-2 text-[11px] text-slate-500 border-t border-slate-800">{isAr ? 'لا حقول خصائص في هذه العلامات (استورد SML/DB3/Shapefile لرؤية الحقول).' : 'No attribute fields on these marks (import SML/DB3/Shapefile to see fields).'}</div>
            )}
          </div>
        ) : (
        /* Marks List */
        <div className="flex-1 overflow-y-auto p-4 divide-y divide-slate-800">
          {filteredMarks.length === 0 ? (
            <div className="text-center py-10 text-slate-500 text-xs">
              {isAr ? 'لا توجد علامات مسجلة حالياً.' : 'No marks in this category.'}
            </div>
          ) : (
            filteredMarks.map((mark) => (
              <div key={mark.id} className={`py-2.5 flex items-center justify-between gap-3 text-xs ${mark.hidden ? 'opacity-45' : ''}`}>
                <div className="flex items-center gap-3">
                  {onStyleMark ? (
                    <input type="color" value={/^#[0-9a-f]{6}$/i.test(mark.color || '') ? mark.color : '#ef4444'} onChange={(e) => onStyleMark(mark.id, { color: e.target.value })} className="w-4 h-4 rounded-full border-0 bg-transparent cursor-pointer shrink-0 p-0" title={isAr ? 'لون العنصر' : 'Feature color'} />
                  ) : (
                    <div className="w-3.5 h-3.5 rounded-full shrink-0 shadow-xs" style={{ backgroundColor: mark.color || '#ef4444' }} />
                  )}
                  <div>
                    <div className="font-semibold text-slate-200">{mark.name}</div>
                    {mark.description && <div className="text-[11px] text-slate-400">{mark.description}</div>}
                    <div className="text-[10px] text-slate-500 font-mono">
                      {mark.type.toUpperCase()} | {Array.isArray(mark.coords) && typeof mark.coords[0] === 'number'
                        ? `${mark.coords[1].toFixed(5)}°, ${mark.coords[0].toFixed(5)}°`
                        : `${mark.coords.length} Points`}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                    {mark.category || 'General'}
                  </span>
                  {onStyleMark && mark.type !== 'point' && (
                    <input type="number" min={1} max={12} step={0.5} value={mark.weight || (mark.type === 'polygon' ? 2.5 : 3.5)} onChange={(e) => onStyleMark(mark.id, { weight: Number(e.target.value) })} className="w-12 bg-slate-900 border border-slate-700 rounded px-1 py-0.5 text-[11px] text-slate-200" title={isAr ? 'سماكة الخط' : 'Line width'} />
                  )}
                  {onToggleMark && (
                    <button
                      onClick={() => onToggleMark(mark.id)}
                      className="p-1 rounded text-slate-500 hover:text-sky-300 hover:bg-sky-950/30 transition-colors"
                      title={mark.hidden ? (isAr ? 'إظهار على الخريطة' : 'Show on map') : (isAr ? 'إخفاء من الخريطة' : 'Hide from map')}
                    >
                      {mark.hidden ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  )}
                  <button
                    onClick={() => onDeleteMark(mark.id)}
                    className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
                    title={isAr ? 'حذف العلامة' : 'Delete Mark'}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
        )}
      </div>
    </DraggableWindow>
  );
};
