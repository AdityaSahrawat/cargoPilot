"use client";

import React, { useState, useEffect, useCallback } from "react";

const API_BASE = "http://localhost:8000/api/v1";

interface ScenarioInfo {
  id: string;
  name: string;
  description: string;
}

interface LocationItem {
  id: string;
  name: string;
  unlocode: string;
  locationType: string;
  latitude: number | null;
  longitude: number | null;
  operationalStatus: string;
}

interface VesselItem {
  id: string;
  name: string;
  containerCapacity: number;
  status: string;
}

interface PlanResponse {
  runId: string;
  totalCost: number;
  repositioning: {
    week: string;
    voyageLegId: string;
    fromLocationId?: string;
    toLocationId?: string;
    containerType: string;
    quantity: number;
    cost: number;
  }[];
  leasing: {
    week: string;
    locationId: string;
    containerType: string;
    quantity: number;
    cost: number;
  }[];
  inventory: {
    week: string;
    locationId: string;
    containerType: string;
    quantity: number;
  }[];
  demand: {
    week: string;
    locationId: string;
    containerType: string;
    confirmedDemand: number;
    confirmedServed: number;
    forecastDemand: number;
    forecastServed: number;
    forecastBacklog: number;
    confirmedShortage: number;
  }[];
}

export default function ScenarioLab() {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("baseline");
  const [loading, setLoading] = useState<boolean>(true);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Live Backend Entity Data
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [vessels, setVessels] = useState<VesselItem[]>([]);
  const [metrics, setMetrics] = useState({
    ports: 0,
    vessels: 0,
    containers: 0,
    bookings: 0,
    voyages: 0,
  });
  const [dashboardOverview, setDashboardOverview] = useState<any>(null);
  const [activePlan, setActivePlan] = useState<PlanResponse | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<LocationItem | null>(null);

  // 1. Fetch available scenarios from Backend API
  const fetchScenarios = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/scenarios`);
      if (!res.ok) throw new Error("Backend API unreachable");
      const data = await res.json();
      setScenarios(data);
      setApiError(null);
    } catch (err: any) {
      setApiError("Backend API disconnected. Please start the Python backend (uvicorn main:app --reload).");
    }
  }, []);

  // 2. Fetch live data from Backend API
  const fetchLiveData = useCallback(async () => {
    setLoading(true);
    try {
      const [locRes, vesRes, cntRes, bokRes, voyRes, ovRes] = await Promise.all([
        fetch(`${API_BASE}/locations`),
        fetch(`${API_BASE}/vessels`),
        fetch(`${API_BASE}/containers`),
        fetch(`${API_BASE}/bookings`),
        fetch(`${API_BASE}/voyages`),
        fetch(`${API_BASE}/dashboard/overview`),
      ]);

      const locs = locRes.ok ? await locRes.json() : [];
      const ves = vesRes.ok ? await vesRes.json() : [];
      const cnt = cntRes.ok ? await cntRes.json() : { total: 0 };
      const bok = bokRes.ok ? await bokRes.json() : { data: [] };
      const voy = voyRes.ok ? await voyRes.json() : [];
      const ov = ovRes.ok ? await ovRes.json() : null;

      setLocations(locs);
      setVessels(ves);
      setDashboardOverview(ov);
      setMetrics({
        ports: locs.length,
        vessels: ves.length,
        containers: cnt.total || 0,
        bookings: bok.data?.length || 0,
        voyages: voy.length,
      });
      setApiError(null);
    } catch (err: any) {
      setApiError("Failed to fetch live database state from Backend API.");
    } finally {
      setLoading(false);
    }
  }, []);

  // 3. Reset scenario on Backend
  const handleResetScenario = async (scenarioId: string) => {
    setLoading(true);
    setActivePlan(null);
    try {
      const res = await fetch(`${API_BASE}/scenarios/${scenarioId}/reset`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Reset failed");
      await fetchLiveData();
    } catch (err: any) {
      setApiError(`Failed to reset scenario '${scenarioId}' on Backend API.`);
      setLoading(false);
    }
  };

  // 4. Trigger Optimization Run on Backend API
  const handleRunOptimization = async () => {
    setIsRunning(true);
    try {
      const runRes = await fetch(`${API_BASE}/optimization/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          startWeek: "2026-W36",
          horizonWeeks: 8,
        }),
      });

      if (!runRes.ok) throw new Error("Failed to start optimization run");
      const runData = await runRes.json();

      // Fetch plan result
      const planRes = await fetch(`${API_BASE}/optimization/runs/${runData.runId}/plan`);
      if (!planRes.ok) throw new Error("Failed to fetch plan from Backend API");
      const planData = await planRes.json();
      setActivePlan(planData);
    } catch (err: any) {
      setApiError("Optimization solver execution failed on Backend API.");
    } finally {
      setIsRunning(false);
    }
  };

  useEffect(() => {
    fetchScenarios();
    fetchLiveData();
  }, [fetchScenarios, fetchLiveData]);

  const handleScenarioChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    setSelectedScenario(id);
    handleResetScenario(id);
  };

  const currentScenarioObj = scenarios.find((s) => s.id === selectedScenario);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col grid-pattern">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur-md sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white font-black text-xl shadow-lg shadow-cyan-500/20">
            🚢
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-tight text-white">CargoPilot</h1>
              <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-xs font-semibold">
                Scenario Lab (Backend 100% Dependent)
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Live Database & API Driven Optimization Workbench
            </p>
          </div>
        </div>

        {/* API Connection Indicator */}
        <div className="flex items-center space-x-2 text-xs bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800">
          <span className={`h-2.5 w-2.5 rounded-full ${apiError ? "bg-rose-500" : "bg-emerald-500 animate-pulse"}`} />
          <span className="font-mono font-medium text-slate-300">
            {apiError ? "Backend Disconnected" : "Backend Connected (localhost:8000)"}
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        
        {/* Error Alert */}
        {apiError && (
          <div className="bg-rose-950/80 border border-rose-800 p-4 rounded-xl text-rose-200 text-xs flex items-center justify-between">
            <div>
              <span className="font-bold">⚠️ Connection Error: </span>
              <span>{apiError}</span>
            </div>
            <button
              onClick={() => { fetchScenarios(); fetchLiveData(); }}
              className="bg-rose-900 hover:bg-rose-800 px-3 py-1 rounded font-semibold text-white"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Scenario Selection & Controls */}
        <div className="glass-panel rounded-2xl p-6 border border-slate-800 relative overflow-hidden">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
            
            {/* Dropdown */}
            <div className="lg:col-span-5 space-y-2">
              <label className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                Select Backend Logistics Scenario
              </label>
              <select
                value={selectedScenario}
                onChange={handleScenarioChange}
                disabled={loading}
                className="w-full bg-slate-900 border border-slate-700 text-slate-100 rounded-xl px-4 py-3 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-cyan-500 cursor-pointer"
              >
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              <p className="text-xs text-slate-400">
                {currentScenarioObj?.description || "Select a scenario to reset backend database state."}
              </p>
            </div>

            {/* Live DB Summary Counters */}
            <div className="lg:col-span-4 bg-slate-900/60 rounded-xl p-4 border border-slate-800">
              <div className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">
                Live Backend DB Summary
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="text-slate-400">Ports</div>
                  <div className="text-base font-bold text-cyan-400">{metrics.ports}</div>
                </div>
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="text-slate-400">Vessels</div>
                  <div className="text-base font-bold text-blue-400">{metrics.vessels}</div>
                </div>
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="text-slate-400">Containers</div>
                  <div className="text-base font-bold text-emerald-400">{metrics.containers}</div>
                </div>
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="text-slate-400">Bookings</div>
                  <div className="text-base font-bold text-indigo-400">{metrics.bookings}</div>
                </div>
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="text-slate-400">Voyages</div>
                  <div className="text-base font-bold text-violet-400">{metrics.voyages}</div>
                </div>
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="text-slate-400">Active Bookings</div>
                  <div className="text-base font-bold text-amber-400">{dashboardOverview?.activeBookings || 0}</div>
                </div>
              </div>
            </div>

            {/* Controls */}
            <div className="lg:col-span-3 flex flex-col gap-2">
              <button
                onClick={handleRunOptimization}
                disabled={isRunning || loading}
                className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold py-3 px-5 rounded-xl shadow-lg shadow-cyan-500/20 transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
              >
                {isRunning ? (
                  <>
                    <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                    <span>Executing Solver...</span>
                  </>
                ) : (
                  <span>⚡ Run Optimization</span>
                )}
              </button>

              <button
                onClick={() => handleResetScenario(selectedScenario)}
                disabled={loading}
                className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold py-2 px-4 rounded-xl border border-slate-700 text-xs"
              >
                🔄 Reset Backend DB Scenario
              </button>
            </div>

          </div>
        </div>

        {/* Live Plan KPIs */}
        {activePlan && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="glass-panel p-4 rounded-2xl border border-slate-800">
              <div className="text-xs text-slate-400 uppercase">Run ID</div>
              <div className="text-xs font-mono font-bold text-cyan-400 truncate mt-1">{activePlan.runId}</div>
            </div>
            <div className="glass-panel p-4 rounded-2xl border border-slate-800">
              <div className="text-xs text-slate-400 uppercase">Repositioning Actions</div>
              <div className="text-2xl font-bold text-white mt-1">{activePlan.repositioning.length} Legs</div>
            </div>
            <div className="glass-panel p-4 rounded-2xl border border-slate-800">
              <div className="text-xs text-slate-400 uppercase">Local Leases</div>
              <div className="text-2xl font-bold text-amber-400 mt-1">{activePlan.leasing.length} Actions</div>
            </div>
            <div className="glass-panel p-4 rounded-2xl border border-slate-800">
              <div className="text-xs text-slate-400 uppercase">Total Solver Cost</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">${activePlan.totalCost.toLocaleString()}</div>
            </div>
          </div>
        )}

        {/* Spatial Ports Map & Live Database Nodes */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          <div className="lg:col-span-8 glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
            <h2 className="text-base font-bold text-white">🗺️ Live Port Nodes & Database Locations</h2>
            <div className="relative w-full h-[380px] bg-slate-950 rounded-xl border border-slate-800 overflow-hidden p-4">
              <div className="absolute inset-0 grid-pattern opacity-30" />

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 relative z-10">
                {locations.map((loc) => (
                  <div
                    key={loc.id}
                    onClick={() => setSelectedLocation(loc)}
                    className="bg-slate-900/90 border border-slate-800 hover:border-cyan-500/50 p-3 rounded-xl cursor-pointer transition-all space-y-1"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-mono font-bold text-cyan-400 text-xs">{loc.unlocode}</span>
                      <span className="text-[10px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-300">{loc.locationType}</span>
                    </div>
                    <div className="font-semibold text-white text-xs">{loc.name}</div>
                    <div className="text-[10px] text-slate-400">Lat: {loc.latitude || "N/A"} | Long: {loc.longitude || "N/A"}</div>
                  </div>
                ))}
              </div>

              {selectedLocation && (
                <div className="absolute bottom-4 right-4 bg-slate-900 border border-slate-700 p-4 rounded-xl text-xs space-y-1 max-w-xs z-20">
                  <div className="font-bold text-white">Location Details: {selectedLocation.name}</div>
                  <div className="text-slate-300">UN/LOCODE: <span className="font-mono">{selectedLocation.unlocode}</span></div>
                  <div className="text-slate-300">Status: <span className="text-emerald-400 font-bold">{selectedLocation.operationalStatus}</span></div>
                  <button onClick={() => setSelectedLocation(null)} className="text-slate-400 text-[10px] underline mt-1">Close</button>
                </div>
              )}
            </div>
          </div>

          {/* Vessels List */}
          <div className="lg:col-span-4 glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
            <h2 className="text-base font-bold text-white">🚢 Live Vessels Fleet</h2>
            <div className="space-y-3">
              {vessels.map((v) => (
                <div key={v.id} className="bg-slate-900 border border-slate-800 p-3 rounded-xl space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-bold text-white">{v.name}</span>
                    <span className="text-xs font-mono text-cyan-400">{v.containerCapacity} TEU</span>
                  </div>
                  <div className="text-[10px] text-slate-400 flex justify-between">
                    <span>ID: {v.id.substring(0, 8)}...</span>
                    <span className="text-emerald-400 font-semibold">{v.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>

      </main>
    </div>
  );
}
