"use client";

import React, { useState, useCallback } from "react";
import Link from "next/link";

const API = "http://localhost:8000/api/v1/simulation";

type Tab = "OVERVIEW" | "NETWORK" | "BOOKINGS" | "VOYAGES" | "MILP_SOLVER" | "HISTORY";
type RegionFilter = "ALL" | "ASIA" | "EUROPE" | "AMERICAS" | "MIDEAST" | "AFRICA" | "SOUTH_ASIA" | "OCEANIA";

const REGION_COLORS: Record<string, string> = {
  ASIA:       "bg-blue-100 text-blue-800 border-blue-200",
  EUROPE:     "bg-purple-100 text-purple-800 border-purple-200",
  AMERICAS:   "bg-green-100 text-green-800 border-green-200",
  MIDEAST:    "bg-amber-100 text-amber-800 border-amber-200",
  AFRICA:     "bg-orange-100 text-orange-800 border-orange-200",
  SOUTH_ASIA: "bg-pink-100 text-pink-800 border-pink-200",
  OCEANIA:    "bg-cyan-100 text-cyan-800 border-cyan-200",
};

const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800 border-red-200",
  HIGH:     "bg-orange-100 text-orange-800 border-orange-200",
  NORMAL:   "bg-blue-100 text-blue-800 border-blue-200",
  LOW:      "bg-slate-100 text-slate-600 border-slate-200",
};

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${color}`}>
      {label}
    </span>
  );
}

function StatCard({ icon, label, value, sub }: { icon: string; label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-1">
      <div className="text-lg">{icon}</div>
      <div className="text-xl font-black text-slate-900">{typeof value === "number" ? value.toLocaleString() : value}</div>
      <div className="text-[11px] font-semibold text-slate-700">{label}</div>
      {sub && <div className="text-[10px] text-slate-400">{sub}</div>}
    </div>
  );
}

export default function World2WorkbenchPage() {
  const [activeTab, setActiveTab] = useState<Tab>("OVERVIEW");
  const [summary, setSummary] = useState<any>(null);
  const [solution, setSolution] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [voyageData, setVoyageData] = useState<any>(null);
  const [solving, setSolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("ALL");
  const [timeLimit, setTimeLimit] = useState(120);
  const [solveProgress, setSolveProgress] = useState("");
  const [expandedVoyages, setExpandedVoyages] = useState<Set<string>>(new Set());
  const [serviceFilter, setServiceFilter] = useState<string>("ALL");

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sumRes, voyRes] = await Promise.all([
        fetch(`${API}/world-2/summary`),
        fetch(`${API}/world-2/voyages`),
      ]);
      if (!sumRes.ok) throw new Error(`HTTP ${sumRes.status}`);
      const data = await sumRes.json();
      setSummary(data);
      if (voyRes.ok) {
        const vd = await voyRes.json();
        setVoyageData(vd);
      }
    } catch (e: any) {
      setError("Failed to load World 2 data. Is the API running?");
    } finally {
      setLoading(false);
    }
  }, []);

  const runSolver = useCallback(async () => {
    setSolving(true);
    setSolveProgress("Building 55-port network graph…");
    setSolution(null);
    try {
      setSolveProgress(`Running HiGHS MILP (20 equation families, ${timeLimit}s limit)…`);
      const res = await fetch(`${API}/world-2/solve-milp?time_limit=${timeLimit}`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSolution(data);
      // Merge post-solve voyage utilization back into voyageData
      if (data.voyage_utilization) {
        setVoyageData((prev: any) => ({
          ...prev,
          status: "post_solve",
          voyages: data.voyage_utilization,
        }));
      }
      setSolveProgress("");
    } catch (e: any) {
      setError("Solver failed. Check API logs.");
      setSolveProgress("");
    } finally {
      setSolving(false);
    }
  }, [timeLimit]);

  const toggleVoyage = (vn: string) => {
    setExpandedVoyages(prev => {
      const next = new Set(prev);
      if (next.has(vn)) next.delete(vn); else next.add(vn);
      return next;
    });
  };

  React.useEffect(() => { loadSummary(); }, [loadSummary]);

  const filteredPorts = summary?.ports?.filter((p: any) =>
    regionFilter === "ALL" || p.region?.replace(/ /g, "_").toUpperCase() === regionFilter
  ) ?? [];

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "OVERVIEW",    label: "Overview",       icon: "📊" },
    { id: "NETWORK",     label: "Global Network", icon: "🌍" },
    { id: "BOOKINGS",    label: "Bookings",        icon: "📦" },
    { id: "VOYAGES",     label: "Voyages & Capacity", icon: "⚓" },
    { id: "MILP_SOLVER", label: "MILP Solver",     icon: "⚡" },
    { id: "HISTORY",     label: "Historical Data", icon: "📈" },
  ];

  // Unique service codes from voyage data
  const serviceCodes = React.useMemo(() => {
    if (!voyageData?.voyages) return [];
    const codes = new Set<string>(voyageData.voyages.map((v: any) => v.service_code));
    return ["ALL", ...Array.from(codes).sort()];
  }, [voyageData]);

  const filteredVoyages = React.useMemo(() => {
    if (!voyageData?.voyages) return [];
    return serviceFilter === "ALL"
      ? voyageData.voyages
      : voyageData.voyages.filter((v: any) => v.service_code === serviceFilter);
  }, [voyageData, serviceFilter]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="border-b border-slate-200 bg-white/95 backdrop-blur-md sticky top-0 z-50 px-6 py-3 shadow-xs">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Link href="/" className="h-9 w-9 rounded-xl bg-gradient-to-tr from-violet-600 to-fuchsia-500 flex items-center justify-center text-white font-black text-lg shadow-md shadow-violet-500/20 hover:opacity-90 transition-all">
              🌐
            </Link>
            <div>
              <div className="flex items-center space-x-2">
                <Link href="/" className="text-sm font-bold text-slate-600 hover:text-slate-900 transition-colors">CargoPilot</Link>
                <span className="text-slate-400 text-xs">/</span>
                <Link href="/test" className="text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors">Test Worlds</Link>
                <span className="text-slate-400 text-xs">/</span>
                <span className="text-sm font-bold text-violet-700">World 2 Lab Workbench</span>
              </div>
              <p className="text-[11px] text-slate-500">Full-Scale Global MILP — 55 Ports · 18 Vessels · 84-Day Horizon · All 20 Equation Families</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-violet-100 text-violet-800 border border-violet-200">
              🟣 World 2 Active
            </span>
            <Link href="/test/world1" className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold transition-all">
              ← World 1
            </Link>
            <button
              onClick={loadSummary}
              disabled={loading}
              className="bg-violet-600 hover:bg-violet-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs disabled:opacity-50"
            >
              {loading ? "Loading…" : "↺ Refresh"}
            </button>
          </div>
        </div>
      </header>

      {/* ── Error Banner ─────────────────────────────────────────────── */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-3 text-sm text-red-700 font-medium text-center">
          ⚠️ {error}
        </div>
      )}

      {/* ── Tab Bar ──────────────────────────────────────────────────── */}
      <div className="border-b border-slate-200 bg-white px-6">
        <div className="max-w-7xl mx-auto flex items-center space-x-1 overflow-x-auto">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`px-4 py-3 text-xs font-semibold whitespace-nowrap border-b-2 transition-all ${
                activeTab === t.id
                  ? "border-violet-600 text-violet-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      </div>

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

        {/* ══════════════════════════════════════════════════════════════
            OVERVIEW TAB
        ══════════════════════════════════════════════════════════════ */}
        {activeTab === "OVERVIEW" && (
          <div className="space-y-6">
            {/* Hero banner */}
            <div className="bg-gradient-to-r from-violet-600 via-fuchsia-600 to-indigo-600 rounded-2xl p-6 text-white shadow-lg shadow-violet-500/20">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-2xl font-black tracking-tight">World 2: Full-Scale Global MILP</h1>
                  <p className="text-violet-200 text-xs mt-1 max-w-2xl leading-relaxed">
                    The CargoPilot reference benchmark implementing all 20 equation families from the master MILP spec.
                    55 global ports, 18 vessels with recurring rotations, 193 bookings, and 12 weeks of historical data.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-3">
                    {["20 Eq Families", "All 5 Container Types", "3-Hop Transshipment", "Dynamic Safety Stocks",
                      "Long-Term Leasing", "Delay Penalties", "Handling Costs", "Forecast Pipeline"].map(tag => (
                      <span key={tag} className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-white/20 border border-white/30">
                        ✓ {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <span className="text-5xl opacity-80">🌐</span>
              </div>
            </div>

            {/* Scale stats */}
            {loading ? (
              <div className="text-center py-12 text-slate-400 text-sm">Loading World 2 dataset…</div>
            ) : summary ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  <StatCard icon="🗺️" label="Global Ports"      value={summary.scale?.ports}           sub="6 world regions" />
                  <StatCard icon="🚢" label="Vessels"           value={summary.scale?.vessels}          sub="ULCV → Feeder" />
                  <StatCard icon="⚓" label="Voyage Legs"       value={summary.scale?.voyage_legs}      sub="recurring rotations" />
                  <StatCard icon="🔄" label="Unique Voyages"    value={summary.scale?.unique_voyages}   sub="67 service rotations" />
                  <StatCard icon="📦" label="Bookings"          value={summary.scale?.bookings}         sub="18 trade lanes" />
                  <StatCard icon="📅" label="Horizon"           value={`${summary.horizon_days}d`}      sub="12-week window" />
                </div>

                {/* MILP features row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <StatCard icon="📡" label="Demand Forecast D[i,k,t]"  value={summary.new_milp_features?.demand_forecast_entries?.toLocaleString()} sub="55×5×85 entries" />
                  <StatCard icon="🔙" label="Return Forecast R[i,k,t]"  value={summary.new_milp_features?.return_forecast_entries?.toLocaleString()} sub="lagged 21 days" />
                  <StatCard icon="🛳️" label="In-Transit Pipeline G"     value={summary.new_milp_features?.in_transit_pipeline_entries} sub="pre-sim arrivals" />
                  <StatCard icon="🛡️" label="Safety Stocks SS[i,k,t]"  value={summary.new_milp_features?.precomputed_safety_stocks?.toLocaleString()} sub="ECO formula" />
                </div>

                {/* Forecast & Historical sample */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                    <h3 className="text-sm font-bold text-slate-900 mb-3">📡 Forecast Parameter Sample</h3>
                    <table className="w-full text-xs">
                      <tbody className="divide-y divide-slate-100">
                        {Object.entries(summary.forecast_sample ?? {}).map(([k, v]) => (
                          <tr key={k}>
                            <td className="py-1.5 text-slate-500 font-mono text-[10px]">{k.replace(/_/g, " ")}</td>
                            <td className="py-1.5 text-right font-bold text-violet-700">{typeof v === "number" ? v.toFixed(3) : String(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                    <h3 className="text-sm font-bold text-slate-900 mb-3">📈 Historical Data Sample (12 weeks)</h3>
                    <table className="w-full text-xs">
                      <tbody className="divide-y divide-slate-100">
                        {Object.entries(summary.historical_sample ?? {}).map(([k, v]) => (
                          <tr key={k}>
                            <td className="py-1.5 text-slate-500 font-mono text-[10px]">{k.replace(/_/g, " ")}</td>
                            <td className="py-1.5 text-right font-bold text-violet-700">{typeof v === "number" ? v.toFixed(2) : String(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="mt-3 p-2 bg-violet-50 rounded-lg border border-violet-100 text-[10px] text-violet-700">
                      Historical data covers <strong>weeks -12 to -1</strong> (before simulation start). Used to calibrate
                      forecast error stats (μ, σ) and precompute safety stocks SS[i,k,t].
                    </div>
                  </div>
                </div>

                {/* Equation families grid */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                  <h3 className="text-sm font-bold text-slate-900 mb-3">📐 All 20 MILP Equation Families — Active in World 2</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      ["Eq 1",  "Master Inventory Balance",        "W1+W2", "violet"],
                      ["Eq 2",  "Empty Flow at Vessel Calls",      "W2",    "fuchsia"],
                      ["Eq 3",  "Booking Demand Fulfillment",      "W1+W2", "violet"],
                      ["Eq 4",  "Origin Equipment Bound",          "W2",    "fuchsia"],
                      ["Eq 5",  "Voyage TEU Capacity",             "W1+W2", "violet"],
                      ["Eq 6",  "Vessel Deadweight Capacity",      "W1+W2", "violet"],
                      ["Eq 7",  "Dynamic Safety Stocks SS[i,k,t]", "W2",    "fuchsia"],
                      ["Eq 8",  "Repositioning Authorization",     "W2",    "fuchsia"],
                      ["Eq 9",  "Booking Timing Windows (ET/LT)",  "W2",    "fuchsia"],
                      ["Eq 10", "Path Feasibility (3-Hop)",        "W1+W2", "violet"],
                      ["Eq 11", "Short-Term Lease Cap",            "W2",    "fuchsia"],
                      ["Eq 12", "Long-Term Lease Integration",     "W2",    "fuchsia"],
                      ["Eq 13", "Devanning Return Flow",           "W1+W2", "violet"],
                      ["Eq 14", "Storage Capacity Limit",          "W2",    "fuchsia"],
                      ["Eq 15", "Dual Shortage (U_b + S_ss)",      "W1+W2", "violet"],
                      ["Eq 16", "Delay Penalties (linearised)",    "W2",    "fuchsia"],
                      ["Eq 17", "Repositioning Cost",              "W1+W2", "violet"],
                      ["Eq 18", "Inventory Holding Cost",          "W1+W2", "violet"],
                      ["Eq 19", "Leasing Cost (short + long)",     "W2",    "fuchsia"],
                      ["Eq 20", "Terminal Handling (UP + DOWN)",   "W2",    "fuchsia"],
                    ].map(([eq, label, world, color]) => (
                      <div key={eq} className={`p-2 rounded-lg border ${color === "fuchsia" ? "bg-fuchsia-50 border-fuchsia-200" : "bg-violet-50 border-violet-200"}`}>
                        <div className={`text-[10px] font-black ${color === "fuchsia" ? "text-fuchsia-700" : "text-violet-700"}`}>{eq}</div>
                        <div className="text-[10px] text-slate-700 font-medium leading-tight">{label}</div>
                        <div className={`text-[9px] mt-0.5 font-bold ${color === "fuchsia" ? "text-fuchsia-600" : "text-violet-500"}`}>{world}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            NETWORK TAB
        ══════════════════════════════════════════════════════════════ */}
        {activeTab === "NETWORK" && summary && (
          <div className="space-y-4">
            {/* Region filter */}
            <div className="flex flex-wrap gap-2">
              {(["ALL","ASIA","EUROPE","AMERICAS","MIDEAST","AFRICA","SOUTH_ASIA","OCEANIA"] as RegionFilter[]).map(r => (
                <button
                  key={r}
                  onClick={() => setRegionFilter(r)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all ${
                    regionFilter === r ? "bg-violet-600 text-white border-violet-600" : "bg-white text-slate-600 border-slate-200 hover:border-violet-400"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>

            {/* Ports table */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
                <span className="text-sm font-bold text-slate-900">🗺️ Global Port Network ({filteredPorts.length} ports)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-100">
                    <tr>
                      {["UNLOCODE","Port Name","Country","Region","Storage TEU","SS TEU","Devan Days","Lift-On $","Lift-Off $"].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {filteredPorts.map((p: any) => (
                      <tr key={p.unlocode} className="hover:bg-violet-50/30 transition-colors">
                        <td className="px-3 py-2 font-mono font-bold text-violet-700">{p.unlocode}</td>
                        <td className="px-3 py-2 font-medium text-slate-800 whitespace-nowrap">{p.name}</td>
                        <td className="px-3 py-2 text-slate-500">{p.country}</td>
                        <td className="px-3 py-2">
                          <Badge label={p.region ?? "?"} color={REGION_COLORS[p.region?.replace(/ /g,"_").toUpperCase()] ?? "bg-slate-100 text-slate-600 border-slate-200"} />
                        </td>
                        <td className="px-3 py-2 text-right font-semibold text-slate-700">{p.storage_capacity_teu?.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right text-violet-700 font-bold">{p.safety_stock_teu}</td>
                        <td className="px-3 py-2 text-right text-slate-500">{p.devanning_lead_time_days}d</td>
                        <td className="px-3 py-2 text-right text-emerald-700 font-semibold">${p.lift_on_cost}</td>
                        <td className="px-3 py-2 text-right text-rose-700 font-semibold">${p.lift_off_cost}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Vessels table */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <span className="text-sm font-bold text-slate-900">🚢 Fleet — 18 Vessels with Recurring Rotations</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-100">
                    <tr>
                      {["IMO","Vessel Name","Type","Capacity TEU","DWT (mt)","Reefer Plugs"].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {(summary.vessels ?? []).map((v: any) => (
                      <tr key={v.imo_number} className="hover:bg-violet-50/30 transition-colors">
                        <td className="px-3 py-2 font-mono text-[10px] text-slate-400">{v.imo_number}</td>
                        <td className="px-3 py-2 font-bold text-slate-800">{v.name}</td>
                        <td className="px-3 py-2"><Badge label={v.vessel_type} color="bg-blue-50 text-blue-800 border-blue-200" /></td>
                        <td className="px-3 py-2 text-right font-black text-violet-700">{v.capacity_teu?.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right text-slate-600">{v.deadweight_mt?.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right text-cyan-700 font-semibold">{v.reefer_plugs}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            BOOKINGS TAB
        ══════════════════════════════════════════════════════════════ */}
        {activeTab === "BOOKINGS" && summary && (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              {(["CRITICAL","HIGH","NORMAL","LOW"] as const).map(p => {
                const count = (summary.bookings ?? []).filter((b: any) => b.priority === p).length;
                const colors: Record<string, string> = { CRITICAL:"from-red-500 to-rose-600", HIGH:"from-orange-500 to-amber-600", NORMAL:"from-blue-500 to-indigo-600", LOW:"from-slate-400 to-slate-500" };
                return (
                  <div key={p} className={`bg-gradient-to-br ${colors[p]} rounded-xl p-4 text-white shadow-md`}>
                    <div className="text-2xl font-black">{count}</div>
                    <div className="text-xs font-bold opacity-90">{p} Priority</div>
                  </div>
                );
              })}
            </div>

            <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <span className="text-sm font-bold text-slate-900">📦 All {summary.bookings?.length} World 2 Bookings</span>
              </div>
              <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-100 sticky top-0">
                    <tr>
                      {["Booking ID","Origin","Destination","Type","Qty","Priority","Cargo Ready","Cutoff","Deadline","Weight MT"].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {(summary.bookings ?? []).map((b: any) => (
                      <tr key={b.booking_id} className="hover:bg-violet-50/30 transition-colors">
                        <td className="px-3 py-2 font-mono font-bold text-violet-700 text-[10px]">{b.booking_id}</td>
                        <td className="px-3 py-2 font-mono font-bold text-slate-700">{b.origin}</td>
                        <td className="px-3 py-2 font-mono font-bold text-slate-700">{b.destination}</td>
                        <td className="px-3 py-2"><Badge label={b.container_type} color="bg-slate-100 text-slate-700 border-slate-200" /></td>
                        <td className="px-3 py-2 text-right font-black text-slate-900">{b.quantity}</td>
                        <td className="px-3 py-2"><Badge label={b.priority} color={PRIORITY_COLORS[b.priority] ?? ""} /></td>
                        <td className="px-3 py-2 text-center text-slate-500">D{b.cargo_ready_day}</td>
                        <td className="px-3 py-2 text-center text-amber-700 font-semibold">D{b.cutoff_day}</td>
                        <td className="px-3 py-2 text-center text-violet-700 font-bold">D{b.delivery_deadline_day}</td>
                        <td className="px-3 py-2 text-right text-slate-500">{b.cargo_weight_mt}mt</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            MILP SOLVER TAB
        ══════════════════════════════════════════════════════════════ */}
        {activeTab === "MILP_SOLVER" && (
          <div className="space-y-5">
            {/* Solver controls */}
            <div className="bg-white border border-violet-200 rounded-xl p-5 shadow-xs space-y-4">
              <h2 className="text-sm font-bold text-slate-900">⚡ World 2 Full MILP — All 20 Equation Families</h2>
              <p className="text-xs text-slate-500 leading-relaxed">
                Launches the CargoPilot HiGHS MILP solver with all World 2 variables activated: 
                L_long (long-term leases), Delay_b (delivery delays), UP/DOWN (terminal handling), 
                dynamic safety stocks SS[i,k,t], and all 8 objective cost terms.
              </p>
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2">
                  <label className="text-xs font-semibold text-slate-700">Time limit (seconds):</label>
                  <input
                    type="number"
                    value={timeLimit}
                    onChange={e => setTimeLimit(Number(e.target.value))}
                    min={30} max={600} step={30}
                    className="w-20 text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-center font-bold"
                  />
                </div>
                <button
                  onClick={runSolver}
                  disabled={solving}
                  className="bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white font-bold text-xs px-5 py-2 rounded-xl shadow-md shadow-violet-500/20 disabled:opacity-50 transition-all"
                >
                  {solving ? "⏳ Solving…" : "▶ Run World 2 MILP"}
                </button>
                {solveProgress && (
                  <span className="text-xs text-violet-600 font-medium animate-pulse">{solveProgress}</span>
                )}
              </div>
            </div>

            {/* Solution display */}
            {solution && (
              <div className="space-y-4">
                {/* Status banner */}
                <div className={`rounded-xl p-4 border ${solution.solver_status === "Optimal" ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className={`text-base font-black ${solution.solver_status === "Optimal" ? "text-emerald-800" : "text-amber-800"}`}>
                        {solution.solver_status === "Optimal" ? "✅ Optimal Solution Found" : `⚠️ ${solution.solver_status}`}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {solution.solver_name} · {solution.solve_time_seconds?.toFixed(2)}s · 
                        Gap: {(solution.optimality_gap * 100)?.toFixed(3)}% · 
                        {solution.num_variables?.toLocaleString()} variables · {solution.num_constraints?.toLocaleString()} constraints
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-black text-slate-900">${solution.objective_value?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                      <div className="text-[10px] text-slate-500">Total Objective Cost</div>
                    </div>
                  </div>
                </div>

                {/* Cost breakdown */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                  <h3 className="text-sm font-bold text-slate-900 mb-3">💰 Complete 8-Term Cost Breakdown (World 2)</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { label: "Repositioning", key: "repositioning_cost",   icon: "🔀", color: "text-blue-700" },
                      { label: "Lease Short",   key: "leasing_short_cost",  icon: "📋", color: "text-amber-700" },
                      { label: "Lease Long",    key: "leasing_long_cost",   icon: "📑", color: "text-orange-700", w2: true },
                      { label: "Holding",       key: "holding_cost",        icon: "🏭", color: "text-slate-700" },
                      { label: "Handling",      key: "handling_cost",       icon: "⚙️", color: "text-cyan-700",  w2: true },
                      { label: "Delay Penalty", key: "delay_penalty",       icon: "⏰", color: "text-rose-700",  w2: true },
                      { label: "Shortage",      key: "shortage_penalty",    icon: "⚠️", color: "text-red-700" },
                      { label: "SS Shortfall",  key: "safety_stock_penalty",icon: "🛡️", color: "text-violet-700" },
                    ].map(({ label, key, icon, color, w2 }) => (
                      <div key={key} className={`p-3 rounded-lg border ${w2 ? "bg-fuchsia-50 border-fuchsia-200" : "bg-slate-50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-base">{icon}</span>
                          {w2 && <span className="text-[9px] font-bold text-fuchsia-600 bg-fuchsia-100 px-1 rounded">W2</span>}
                        </div>
                        <div className={`text-base font-black ${color}`}>
                          ${(solution.cost_breakdown?.[key] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </div>
                        <div className="text-[10px] text-slate-500 font-medium">{label}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Summary stats */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <StatCard icon="✅" label="Fully Served"      value={solution.summary?.bookings_fully_served} sub="bookings" />
                  <StatCard icon="⚠️" label="Partial/Unserved" value={solution.summary?.bookings_partial}      sub="bookings" />
                  <StatCard icon="🔀" label="Reposition Moves"  value={solution.summary?.total_repositioning_moves} sub="empty moves" />
                  <StatCard icon="📑" label="Long Lease Injects" value={solution.summary?.total_long_lease_injections} sub="L_long decisions" />
                  <StatCard icon="⏰" label="Delayed Bookings"  value={solution.summary?.delayed_bookings}    sub="Delay_b > 0" />
                </div>

                {/* Booking decisions table */}
                {solution.booking_decisions?.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
                    <div className="px-4 py-3 border-b border-slate-100">
                      <span className="text-sm font-bold text-slate-900">📦 Booking Decisions ({solution.booking_decisions.length})</span>
                    </div>
                    <div className="overflow-x-auto max-h-80 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-50 border-b border-slate-100 sticky top-0">
                          <tr>
                            {["Booking","Type","Owned","Leased","Unserved","Dep Day","Arr Day","Delay d","Cost $"].map(h => (
                              <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {solution.booking_decisions.map((bd: any) => (
                            <tr key={bd.booking_id + bd.path_id} className="hover:bg-violet-50/30">
                              <td className="px-3 py-1.5 font-mono text-violet-700 font-bold text-[10px]">{bd.booking_id}</td>
                              <td className="px-3 py-1.5 text-[10px]">{bd.container_type}</td>
                              <td className="px-3 py-1.5 text-right font-bold text-emerald-700">{bd.owned_qty}</td>
                              <td className="px-3 py-1.5 text-right font-bold text-amber-700">{bd.leased_qty}</td>
                              <td className="px-3 py-1.5 text-right font-bold text-red-700">{bd.unserved_qty}</td>
                              <td className="px-3 py-1.5 text-center text-slate-500">D{bd.departure_day}</td>
                              <td className="px-3 py-1.5 text-center text-slate-500">D{bd.arrival_day}</td>
                              <td className={`px-3 py-1.5 text-right font-bold ${bd.delay_days > 0.5 ? "text-rose-700" : "text-slate-400"}`}>{bd.delay_days?.toFixed(1)}</td>
                              <td className="px-3 py-1.5 text-right text-slate-700">${bd.cost?.toLocaleString(undefined,{maximumFractionDigits:0})}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Long-term lease decisions (W2 only) */}
                {solution.long_lease_decisions?.length > 0 && (
                  <div className="bg-fuchsia-50 border border-fuchsia-200 rounded-xl p-4 shadow-xs">
                    <h3 className="text-sm font-bold text-fuchsia-900 mb-3">📑 Long-Term Lease Decisions L_long (World 2 Exclusive)</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {solution.long_lease_decisions.slice(0, 20).map((ll: any, i: number) => (
                        <div key={i} className="bg-white border border-fuchsia-200 rounded-lg p-2">
                          <div className="font-mono font-bold text-fuchsia-700 text-[10px]">{ll.port}</div>
                          <div className="text-[10px] text-slate-600">{ll.container_type} · Day {ll.day}</div>
                          <div className="text-sm font-black text-fuchsia-900">{Math.round(ll.quantity)} units</div>
                          <div className="text-[10px] text-slate-400">${ll.cost?.toFixed(0)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            VOYAGES TAB — per-voyage capacity accordion
        ══════════════════════════════════════════════════════════════ */}
        {activeTab === "VOYAGES" && (
          <div className="space-y-4">
            {/* Status banner */}
            <div className={`rounded-xl px-4 py-3 border text-xs font-medium flex items-center justify-between ${
              voyageData?.status === "post_solve"
                ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                : "bg-amber-50 border-amber-200 text-amber-800"
            }`}>
              <span>
                {voyageData?.status === "post_solve"
                  ? "✅ Showing post-solve capacity (laden + empty from MILP solution)"
                  : "⚠️ Pre-solve view — run the MILP solver to see laden/empty/free breakdown"}
              </span>
              <span className="text-[10px] opacity-70">
                {voyageData?.total_voyages} voyages · {voyageData?.total_legs} legs
              </span>
            </div>

            {/* Service filter chips */}
            <div className="flex flex-wrap gap-1.5">
              {serviceCodes.map(code => (
                <button
                  key={code}
                  onClick={() => setServiceFilter(code)}
                  className={`px-3 py-1 rounded-full text-[11px] font-bold border transition-all ${
                    serviceFilter === code
                      ? "bg-violet-600 text-white border-violet-600"
                      : "bg-white text-slate-600 border-slate-200 hover:border-violet-400 hover:text-violet-700"
                  }`}
                >
                  {code}
                </button>
              ))}
              <button
                onClick={() => setExpandedVoyages(new Set(filteredVoyages.map((v: any) => v.voyage_number)))}
                className="px-3 py-1 rounded-full text-[11px] font-bold border bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 transition-all ml-2"
              >
                Expand All
              </button>
              <button
                onClick={() => setExpandedVoyages(new Set())}
                className="px-3 py-1 rounded-full text-[11px] font-bold border bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 transition-all"
              >
                Collapse All
              </button>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-[11px] font-semibold">
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-slate-400 inline-block"/><span className="text-slate-600">Pre-booked (3rd party)</span></span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-indigo-500 inline-block"/><span className="text-slate-600">Laden (CargoPilot bookings)</span></span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-amber-400 inline-block"/><span className="text-slate-600">Empty reposition</span></span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-emerald-400 inline-block"/><span className="text-slate-600">Free space</span></span>
            </div>

            {/* Voyage accordions */}
            <div className="space-y-2">
              {filteredVoyages.map((voyage: any) => {
                const isOpen = expandedVoyages.has(voyage.voyage_number);
                // Compute summary stats across all legs
                const totalCapTeu = voyage.legs.reduce((s: number, l: any) => s + (l.capacity_teu ?? 0), 0);
                const totalUsedTeu = voyage.legs.reduce((s: number, l: any) => {
                  const pre   = l.pre_booked_teu ?? 0;
                  const laden = l.laden_booking_teu ?? 0;
                  const empty = l.empty_reposition_teu ?? 0;
                  return s + pre + laden + empty;
                }, 0);
                const avgUtil = totalCapTeu > 0 ? Math.round(totalUsedTeu / totalCapTeu * 100) : 0;
                const isSolved = voyage.legs[0]?.laden_booking_teu !== null && voyage.legs[0]?.laden_booking_teu !== undefined;

                return (
                  <div key={voyage.voyage_number} className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
                    {/* Accordion header (click to expand) */}
                    <button
                      onClick={() => toggleVoyage(voyage.voyage_number)}
                      className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-50 transition-colors text-left"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-base">{isOpen ? "▼" : "▶"}</span>
                        <div>
                          <span className="font-bold text-slate-900 text-sm">{voyage.voyage_number}</span>
                          <span className="ml-2 text-[10px] text-slate-400 font-mono">{voyage.vessel_name}</span>
                        </div>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet-100 text-violet-700 border border-violet-200">
                          {voyage.service_code} · {voyage.rotation}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {voyage.legs.length} leg{voyage.legs.length !== 1 ? "s" : ""}
                        </span>
                      </div>
                      <div className="flex items-center gap-4">
                        {/* Mini utilisation bar */}
                        <div className="hidden sm:flex items-center gap-2">
                          <div className="w-28 h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                avgUtil > 85 ? "bg-red-400" : avgUtil > 60 ? "bg-amber-400" : "bg-emerald-400"
                              }`}
                              style={{ width: `${Math.min(avgUtil, 100)}%` }}
                            />
                          </div>
                          <span className={`text-[11px] font-bold ${
                            avgUtil > 85 ? "text-red-600" : avgUtil > 60 ? "text-amber-600" : "text-emerald-600"
                          }`}>{avgUtil}%</span>
                        </div>
                        <span className="text-[10px] text-slate-500 font-medium">{Math.round(totalUsedTeu)}/{totalCapTeu} TEU</span>
                      </div>
                    </button>

                    {/* Expanded legs */}
                    {isOpen && (
                      <div className="border-t border-slate-100">
                        <table className="w-full text-xs">
                          <thead className="bg-slate-50">
                            <tr>
                              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">Leg</th>
                              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">Route</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-slate-500 uppercase tracking-wide">Days</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-slate-500 uppercase tracking-wide">Cap TEU</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-slate-400 uppercase tracking-wide">Pre-booked</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-indigo-400 uppercase tracking-wide">Laden</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-amber-400 uppercase tracking-wide">Empty</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-emerald-500 uppercase tracking-wide">Free</th>
                              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide w-40">Capacity Bar</th>
                              <th className="px-3 py-2 text-center text-[10px] font-bold text-slate-500 uppercase tracking-wide">Wt. Util%</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-50">
                            {voyage.legs.map((leg: any) => {
                              const preTeu   = leg.pre_booked_teu ?? 0;
                              const ladenTeu = leg.laden_booking_teu ?? 0;
                              const emptyTeu = leg.empty_reposition_teu ?? 0;
                              const freeTeu  = leg.free_teu ?? (leg.capacity_teu - preTeu);
                              const cap      = leg.capacity_teu || 1;

                              const preW   = Math.min((preTeu   / cap) * 100, 100);
                              const ladenW = Math.min((ladenTeu / cap) * 100, 100);
                              const emptyW = Math.min((emptyTeu / cap) * 100, 100);
                              const freeW  = Math.max(0, 100 - preW - ladenW - emptyW);

                              const util = leg.utilization_pct ?? leg.pre_utilization_pct ?? 0;

                              return (
                                <tr key={leg.leg_id} className="hover:bg-violet-50/20 transition-colors">
                                  <td className="px-3 py-2 font-mono text-[10px] text-slate-400">{leg.leg_id.split("_").slice(-2).join("_")}</td>
                                  <td className="px-3 py-2">
                                    <span className="font-bold text-violet-700">{leg.from_port}</span>
                                    <span className="text-slate-400 mx-1">→</span>
                                    <span className="font-bold text-violet-700">{leg.to_port}</span>
                                  </td>
                                  <td className="px-3 py-2 text-center text-slate-500">D{leg.departure_day}→D{leg.arrival_day}</td>
                                  <td className="px-3 py-2 text-center font-black text-slate-800">{leg.capacity_teu}</td>
                                  <td className="px-3 py-2 text-center text-slate-500 font-semibold">{preTeu}</td>
                                  <td className={`px-3 py-2 text-center font-bold ${isSolved ? "text-indigo-700" : "text-slate-300"}`}>
                                    {isSolved ? ladenTeu : "—"}
                                  </td>
                                  <td className={`px-3 py-2 text-center font-bold ${isSolved ? "text-amber-600" : "text-slate-300"}`}>
                                    {isSolved ? emptyTeu : "—"}
                                  </td>
                                  <td className={`px-3 py-2 text-center font-bold ${isSolved ? "text-emerald-600" : "text-slate-300"}`}>
                                    {isSolved ? Math.round(freeTeu) : "—"}
                                  </td>
                                  <td className="px-3 py-2 w-40">
                                    <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden flex">
                                      {/* Pre-booked (grey) */}
                                      {preW > 0 && (
                                        <div className="h-full bg-slate-400 transition-all" style={{ width: `${preW}%` }} title={`Pre-booked: ${preTeu} TEU`}/>
                                      )}
                                      {/* Laden (indigo) */}
                                      {ladenW > 0 && (
                                        <div className="h-full bg-indigo-500 transition-all" style={{ width: `${ladenW}%` }} title={`Laden: ${ladenTeu} TEU`}/>
                                      )}
                                      {/* Empty (amber) */}
                                      {emptyW > 0 && (
                                        <div className="h-full bg-amber-400 transition-all" style={{ width: `${emptyW}%` }} title={`Empty: ${emptyTeu} TEU`}/>
                                      )}
                                      {/* Free (emerald) */}
                                      {freeW > 0 && (
                                        <div className="h-full bg-emerald-400 transition-all" style={{ width: `${freeW}%` }} title={`Free: ${Math.round(freeTeu)} TEU`}/>
                                      )}
                                    </div>
                                    <div className="text-[9px] text-slate-400 mt-0.5 text-center">{util}%</div>
                                  </td>
                                  <td className={`px-3 py-2 text-center text-[11px] font-bold ${
                                    (leg.weight_utilization_pct ?? 0) > 85 ? "text-red-600" :
                                    (leg.weight_utilization_pct ?? 0) > 60 ? "text-amber-600" : "text-slate-500"
                                  }`}>
                                    {leg.weight_utilization_pct !== null && leg.weight_utilization_pct !== undefined
                                      ? `${leg.weight_utilization_pct}%`
                                      : `${leg.pre_utilization_pct}%`
                                    }
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>

                        {/* Leg weight detail summary */}
                        {isSolved && (
                          <div className="px-4 py-2 bg-slate-50 border-t border-slate-100 flex flex-wrap gap-4 text-[11px] text-slate-600">
                            <span><strong className="text-slate-400">Pre-booked:</strong> {voyage.legs.reduce((s: number, l: any) => s + (l.pre_booked_mt ?? 0), 0).toFixed(0)} MT</span>
                            <span><strong className="text-indigo-500">Laden:</strong> {voyage.legs.reduce((s: number, l: any) => s + (l.laden_booking_mt ?? 0), 0).toFixed(0)} MT</span>
                            <span><strong className="text-amber-500">Empty:</strong> {voyage.legs.reduce((s: number, l: any) => s + (l.empty_reposition_mt ?? 0), 0).toFixed(0)} MT</span>
                            <span><strong className="text-emerald-500">Free:</strong> {voyage.legs.reduce((s: number, l: any) => s + (l.free_mt ?? 0), 0).toFixed(0)} MT</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {filteredVoyages.length === 0 && (
              <div className="text-center py-12 text-slate-400 text-sm">No voyages found for this service.</div>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            HISTORY TAB
        ══════════════════════════════════════════════════════════════ */}
        {activeTab === "HISTORY" && summary && (
          <div className="space-y-4">
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
              <h2 className="text-sm font-bold text-slate-900 mb-3">📈 12-Week Historical Data Structure</h2>
              <p className="text-xs text-slate-500 mb-4 leading-relaxed">
                World 2 seeds 12 weeks of pre-simulation data across all 55 ports × 5 container types. 
                This historical data is used to compute forecast error statistics (μ^D, σ^D, μ^R, σ^R) 
                and calibrate dynamic safety stocks SS[i,k,t] via the ECO/Neely formula.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { label: "Historical Demand", key: "hist_demand_CNSHA_40DC_week_neg12", weeks: "Week -12 to -1", desc: "D[i,k,t] pre-simulation", icon: "📊" },
                  { label: "Historical Returns", key: "hist_inv_NLRTM_40HC_week_neg4", weeks: "Week -12 to -1", desc: "R[i,k,t] pre-simulation", icon: "🔙" },
                ].map(item => (
                  <div key={item.key} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                    <div className="text-lg mb-1">{item.icon}</div>
                    <div className="text-sm font-bold text-slate-900">{item.label}</div>
                    <div className="text-xs text-slate-500">{item.weeks}</div>
                    <div className="text-xs text-slate-400 mt-1">{item.desc}</div>
                    <div className="mt-2 text-xl font-black text-violet-700">
                      {typeof summary.historical_sample?.[item.key] === "number"
                        ? summary.historical_sample[item.key].toFixed(2)
                        : "—"}
                    </div>
                    <div className="text-[10px] text-slate-400">sample value (containers/week)</div>
                  </div>
                ))}
                <div className="bg-violet-50 border border-violet-200 rounded-xl p-4">
                  <div className="text-lg mb-1">🛡️</div>
                  <div className="text-sm font-bold text-violet-900">Safety Stock Formula</div>
                  <div className="text-[10px] text-violet-600 mt-2 font-mono leading-relaxed">
                    SS[i,k,t] = z_α · √(lt · σ_D² + μ_D² · σ_v² + σ_R²)
                  </div>
                  <div className="text-[10px] text-slate-500 mt-2">
                    z_α = 1.645 (95% service level)<br/>
                    σ_v = 1.5d vessel arrival uncertainty<br/>
                    lt = region lead-time (5–15 days)
                  </div>
                </div>
              </div>

              {/* Records count */}
              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
                  <div className="text-lg font-black text-slate-900">{summary.new_milp_features?.historical_records?.toLocaleString()}</div>
                  <div className="text-[10px] text-slate-500">Historical demand records</div>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
                  <div className="text-lg font-black text-slate-900">12</div>
                  <div className="text-[10px] text-slate-500">weeks covered (t = -84 to -7)</div>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
                  <div className="text-lg font-black text-slate-900">55 × 5</div>
                  <div className="text-[10px] text-slate-500">port × container type pairs</div>
                </div>
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
