import React, { useState, useEffect, useMemo } from 'react';
import type { Facility, User } from '../types';
import { api } from '../services/api';
import { exportToCSV } from '../utils/export';

interface ShelterInventoryProps {
  isOpen: boolean;
  onClose: () => void;
  user: User | null;
  offlineMode: boolean;
  onStockModeChanged?: (mode: 'configured' | 'entered') => void;
}

export const ShelterInventory: React.FC<ShelterInventoryProps> = ({
  isOpen,
  onClose,
  user,
  offlineMode,
  onStockModeChanged,
}) => {
  const isOperator = user?.role === 'operator';
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterType, setFilterType] = useState<'all' | 'routable' | 'unroutable'>('all');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const hasEnteredStock = facilities.some((facility) => facility.stock?.some((item) => item.mode === 'entered'));

  // Edit stock modal/inline state
  const [editingFacilityId, setEditingFacilityId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<{ food: number; water: number; medical: number }>({
    food: 0,
    water: 0,
    medical: 0,
  });

  const loadFacilities = async () => {
    try {
      const data = await api.getFacilities();
      // This project considers three event-confirmed relief-site records.
      // DDMP-listed candidates without event confirmation are not presented as
      // operational facilities in the student demo.
      const consideredIds = new Set([
        'svs_kannada_medium_school_bantwal',
        'mini_town_hall_mangaluru',
        'panemangaluru_sharada_relief_centre',
      ]);
      const consideredSites = data.filter((facility) =>
        consideredIds.has(facility.id) && facility.source === 'event-confirmed',
      );
      setFacilities(consideredSites);
    } catch (err) {
      console.error('Failed to load facilities:', err);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadFacilities();
    }
  }, [isOpen]);

  // Filter facilities
  const filteredFacilities = useMemo(() => {
    const list = Array.isArray(facilities) ? facilities : [];
    return list.filter((f) => {
      const matchesSearch =
        f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        f.id.toLowerCase().includes(searchQuery.toLowerCase());
      if (!matchesSearch) return false;

      if (filterType === 'routable') return f.is_routable;
      if (filterType === 'unroutable') return !f.is_routable;
      return true;
    });
  }, [facilities, searchQuery, filterType]);

  const handleStartEdit = (f: Facility) => {
    if (!isOperator || offlineMode) return;
    setEditingFacilityId(f.id);
    const food = f.stock?.find((s) => s.resource === 'food_rations')?.quantity || 0;
    const water = f.stock?.find((s) => s.resource === 'water_liters')?.quantity || 0;
    const medical = f.stock?.find((s) => s.resource === 'medical_kits')?.quantity || 0;
    setEditValues({ food, water, medical });
  };

  const handleSaveStock = async (facilityId: string) => {
    try {
      await api.updateFacilityStock(facilityId, [
        { resource: 'food_rations', quantity: editValues.food, unit: 'rations' },
        { resource: 'water_liters', quantity: editValues.water, unit: 'liters' },
        { resource: 'medical_kits', quantity: editValues.medical, unit: 'kits' },
      ]);
      setStatusMessage(`Stock updated for ${facilityId} (marked ENTERED, UNVERIFIED)`);
      setEditingFacilityId(null);
      await loadFacilities();
      if (onStockModeChanged) onStockModeChanged('entered');
      setTimeout(() => setStatusMessage(null), 3500);
    } catch (err: any) {
      setStatusMessage(`Error updating stock: ${err.message}`);
    }
  };

  const handleResetToAssumed = async () => {
    if (!isOperator || offlineMode) return;
    if (!window.confirm('Reset all facility stock to baseline assumed values?')) return;
    try {
      await api.resetStockToAssumed();
      setStatusMessage('All facility inventory reset to assumed baseline.');
      await loadFacilities();
      if (onStockModeChanged) onStockModeChanged('configured');
      setTimeout(() => setStatusMessage(null), 3500);
    } catch (err: any) {
      setStatusMessage(`Reset error: ${err.message}`);
    }
  };

  const handleExportCSV = () => {
    const flatRows = facilities.map((f) => {
      const food = f.stock?.find((s) => s.resource === 'food_rations');
      const water = f.stock?.find((s) => s.resource === 'water_liters');
      const medical = f.stock?.find((s) => s.resource === 'medical_kits');
      return {
        facility_id: f.id,
        name: f.name,
        type: f.type,
        lat: f.lat ?? '',
        lon: f.lon ?? '',
        routable: f.is_routable ? 'YES' : 'NO',
        food_rations: food?.quantity ?? 0,
        food_mode: food?.mode ?? 'assumed',
        water_liters: water?.quantity ?? 0,
        water_mode: water?.mode ?? 'assumed',
        medical_kits: medical?.quantity ?? 0,
        medical_mode: medical?.mode ?? 'assumed',
      };
    });
    exportToCSV('resq_shelter_inventory', flatRows);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col overflow-hidden text-slate-100">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/70">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold tracking-tight text-white">Event-Confirmed Relief Sites</h2>
              <span className={`px-2.5 py-0.5 rounded text-xs font-semibold border ${hasEnteredStock ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-violet-500/15 text-violet-200 border-violet-400/30'}`}>
                {hasEnteredStock ? 'ENTERED, UNVERIFIED' : 'ASSUMED INVENTORY'}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Only relief sites named in event reports are shown. Stock remains assumed or manually entered, not live.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Shelter Inventory"
            className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition"
          >
            ✕
          </button>
        </div>

        {/* Amber Advisory Banner */}
        <div className={`${offlineMode ? 'bg-indigo-950/50 border-indigo-700/50 text-indigo-200' : 'bg-amber-950/40 border-amber-800/60 text-amber-200'} border-b px-6 py-2.5 text-xs flex items-center justify-between gap-4`}>
          <div className="flex items-center gap-2">
            <span>⚠️</span>
            <span>
              {offlineMode
                ? <><strong>Offline snapshot is read-only.</strong> Connect the API to edit stock or recalculate allocations.</>
                : hasEnteredStock
                  ? <><strong>Operator-entered stock, unverified, no live sync.</strong> These are manual inputs, not live facility telemetry.</>
                  : <><strong>Assumed stock values.</strong> Demo quantities are illustrative and are not verified facility inventory.</>}
            </span>
          </div>
          {isOperator && !offlineMode && (
            <button
              onClick={handleResetToAssumed}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] shrink-0 font-medium"
            >
              Reset to Assumed Stock
            </button>
          )}
        </div>

        {/* Toolbar */}
        <div className="bg-slate-950/40 px-6 py-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3">
            <input
              type="text"
              placeholder="Filter by facility name or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-64 focus:outline-none focus:border-indigo-500"
            />
            <div className="flex items-center gap-1 bg-slate-850 p-0.5 rounded-lg border border-slate-750">
              {(['all', 'routable', 'unroutable'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setFilterType(t)}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium capitalize transition ${
                    filterType === t ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleExportCSV}
              className="px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-200 text-xs font-medium transition flex items-center gap-1.5"
            >
              📥 Export CSV
            </button>
          </div>
        </div>

        {statusMessage && (
          <div className="bg-indigo-950/60 border-b border-indigo-800 px-6 py-2 text-xs text-indigo-200">
            {statusMessage}
          </div>
        )}

        {/* Facilities Table */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="sticky top-0 bg-slate-900 border-b border-slate-700 text-slate-400 uppercase font-medium">
              <tr>
                <th className="py-2 px-3">Facility</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3 text-right">Food Rations</th>
                <th className="py-2 px-3 text-right">Water (L)</th>
                <th className="py-2 px-3 text-right">Medical Kits</th>
                <th className="py-2 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredFacilities.map((f) => {
                const food = f.stock?.find((s) => s.resource === 'food_rations');
                const water = f.stock?.find((s) => s.resource === 'water_liters');
                const medical = f.stock?.find((s) => s.resource === 'medical_kits');
                const isEditing = editingFacilityId === f.id;

                return (
                  <tr key={f.id} className="hover:bg-slate-800/40 transition">
                    <td className="py-2.5 px-3 font-sans">
                      <div className="font-semibold text-slate-200">{f.name}</div>
                      <div className="text-[11px] text-slate-500 font-mono">
                        {f.id} • {f.source}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 font-sans">
                      {f.is_routable ? (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          Routable
                        </span>
                      ) : (
                        <span
                          title={f.unroutable_reason || 'Unverified coordinates'}
                          className="px-2 py-0.5 rounded text-[10px] bg-red-500/20 text-red-300 border border-red-500/30 cursor-help"
                        >
                          Unroutable Candidate
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editValues.food}
                          onChange={(e) => setEditValues({ ...editValues, food: parseInt(e.target.value) || 0 })}
                          className="w-20 px-1 py-0.5 bg-slate-800 border border-slate-700 text-right rounded"
                        />
                      ) : (
                        <span className={food?.mode === 'entered' ? 'text-amber-300 font-bold' : 'text-slate-300'}>
                          {food?.quantity.toLocaleString() ?? '—'}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editValues.water}
                          onChange={(e) => setEditValues({ ...editValues, water: parseInt(e.target.value) || 0 })}
                          className="w-20 px-1 py-0.5 bg-slate-800 border border-slate-700 text-right rounded"
                        />
                      ) : (
                        <span className={water?.mode === 'entered' ? 'text-amber-300 font-bold' : 'text-slate-300'}>
                          {water?.quantity.toLocaleString() ?? '—'}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editValues.medical}
                          onChange={(e) => setEditValues({ ...editValues, medical: parseInt(e.target.value) || 0 })}
                          className="w-16 px-1 py-0.5 bg-slate-800 border border-slate-700 text-right rounded"
                        />
                      ) : (
                        <span className={medical?.mode === 'entered' ? 'text-amber-300 font-bold' : 'text-slate-300'}>
                          {medical?.quantity.toLocaleString() ?? '—'}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right font-sans">
                      {isOperator && !offlineMode && (
                        isEditing ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => handleSaveStock(f.id)}
                              className="px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-medium"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingFacilityId(null)}
                              className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px]"
                            >
                              ✕
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleStartEdit(f)}
                            className="px-2 py-1 rounded bg-slate-850 hover:bg-slate-750 text-slate-300 border border-slate-700 text-[11px]"
                          >
                            Edit
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between text-xs text-slate-400">
          <div>
            Showing {filteredFacilities.length} of {facilities.length} event-confirmed sites; {facilities.filter((facility) => facility.is_routable).length} have mapped coordinates.
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
