"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";

const API_BASE = "http://localhost:8000/api/v1";

interface PortInventory {
  [ctype: string]: number;
}

interface PortHorizonInsight {
  port_unlocode: string;
  port_name: string;
  initial_stock_teu: number;
  min_stock_teu: number;
  min_stock_day: number;
  max_stock_teu: number;
  max_stock_day: number;
  safety_stock_teu: number;
  deficit_status: "CRITICAL_DEFICIT_RISK" | "TIGHT_BUFFER" | "SURPLUS_STABLE" | string;
  explanation: string;
}

interface EmptyRepositionDirective {
  port_unlocode: string;
  port_name: string;
  should_load_empties: boolean;
  voyage_number: string | null;
  destination_port: string | null;
  total_reposition_teu: number;
  action_instruction: string;
}

interface BookingDispatchDirective {
  booking_id: string;
  origin_port: string;
  destination_port: string;
  container_type: string;
  total_quantity: number;
  owned_quantity: number;
  leased_quantity: number;
  assigned_voyage: string;
  departure_day: number;
  arrival_day: number;
  urgency: string;
  action_instruction: string;
}

interface AssignedBookingDetail {
  booking_id: string;
  origin: string;
  destination: string;
  container_type: string;
  quantity: number;
  teu_load: number;
  owned_qty: number;
  leased_qty: number;
}

interface EmptyRepositionDetail {
  from_port: string;
  to_port: string;
  container_type: string;
  quantity: number;
  teu_load: number;
}

interface PortVesselCall {
  voyage_number: string;
  vessel_name: string;
  call_type: string;
  arrival_day: number | null;
  departure_day: number | null;
  berth_stay_duration_days: number;
  destination_port: string;
  vessel_capacity_teu: number;
  deadweight_capacity_mt: number;
  laden_bookings_teu: number;
  laden_bookings_count: number;
  laden_bookings_list: AssignedBookingDetail[];
  empty_reposition_teu: number;
  empty_reposition_list: EmptyRepositionDetail[];
  total_onboard_teu: number;
  remaining_free_teu: number;
  utilization_pct: number;
  inbound_discharging_laden_teu?: number;
  inbound_discharging_empty_teu?: number;
}

interface PortVesselSchedule {
  port_unlocode: string;
  port_name: string;
  total_calls_count: number;
  vessel_calls: PortVesselCall[];
}

interface RawDBBooking {
  id: string;
  booking_code: string;
  origin: string;
  destination: string;
  container_type: string;
  quantity: number;
  cargo_weight_mt: number;
  cargo_ready_day: number;
  cutoff_day: number;
  delivery_deadline_day: number;
  priority: string;
  status: string;
}

interface OptimizedBooking {
  booking_id: string;
  origin: string;
  destination: string;
  container_type: string;
  quantity: number;
  priority: string;
  status: string;
  voyage: string | null;
  departure_day: number | null;
  arrival_day: number | null;
  actual_delivery_day: number | null;
}

interface PortActionSummary {
  port_unlocode: string;
  port_name: string;
  current_stock: PortInventory;
  total_stock_teu: number;
  safety_stock_teu: number;
  safety_status: string;
  outbound_laden_units: number;
  empty_reposition_load_units: number;
  inbound_devanning_units: number;
  leased_units: number;
  recommended_action: string;
}

interface SolverMetrics {
  solver_status: string;
  optimality_gap: number;
  objective_value: number;
  solve_time_seconds: number;
  cost_breakdown: {
    repositioning_cost: number;
    leasing_cost: number;
    holding_cost: number;
    shortage_penalty: number;
    safety_stock_penalty: number;
  };
}

interface VoyageScheduleItem {
  voyage_id: string;
  voyage_number: string;
  service_name: string;
  vessel_name: string;
  vessel_assignment_status: string;
  is_blank_sailing: boolean;
  status: string;
  legs: Array<{
    leg_id: string;
    from_port: string;
    to_port: string;
    departure_day: number;
    arrival_day: number;
    capacity_teu: number;
    deadweight_capacity_mt: number;
  }>;
}

interface DBStatus {
  database: string;
  status: string;
  counts: {
    ports: number;
    vessels: number;
    services: number;
    voyages: number;
    voyage_legs: number;
    bookings: number;
    containers: number;
  };
}

export default function World1Page() {
  const [isOptimized, setIsOptimized] = useState<boolean>(false);
  const [solverMetrics, setSolverMetrics] = useState<SolverMetrics | null>(null);
  const [voyagesList, setVoyagesList] = useState<VoyageScheduleItem[]>([]);
  const [dbStatus, setDbStatus] = useState<DBStatus | null>(null);
  const [rawBookings, setRawBookings] = useState<RawDBBooking[]>([]);
  const [portInsights, setPortInsights] = useState<PortHorizonInsight[]>([]);
  const [portVesselSchedules, setPortVesselSchedules] = useState<PortVesselSchedule[]>([]);
  const [portActionSummaries, setPortActionSummaries] = useState<PortActionSummary[]>([]);
  const [emptyDirectives, setEmptyDirectives] = useState<EmptyRepositionDirective[]>([]);
  const [bookingDirectives, setBookingDirectives] = useState<BookingDispatchDirective[]>([]);
  const [optimizedBookings, setOptimizedBookings] = useState<OptimizedBooking[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [statusToast, setStatusToast] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"EXECUTIVE_REPORT" | "FLEET_SCHEDULE" | "DB_ADMIN" | "DATA_QA">("EXECUTIVE_REPORT");

  // Data QA state
  const [qaReport, setQaReport] = useState<any>(null);
  const [qaLoading, setQaLoading] = useState<boolean>(false);
  const [qaFilter, setQaFilter] = useState<"ALL" | "ERROR" | "WARNING" | "INFO">("ALL");
  const [qaCategory, setQaCategory] = useState<string>("ALL");

  const runQA = useCallback(async () => {
    setQaLoading(true);
    try {
      const res = await fetch(`${API_BASE}/simulation/world-1/validate`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setQaReport(data);
    } catch (e: any) {
      alert("QA error: " + e.message);
    } finally {
      setQaLoading(false);
    }
  }, []);

  // Dropdown states
  const [selectedPortFilter, setSelectedPortFilter] = useState<string>("ALL");
  const [expandedDropdowns, setExpandedDropdowns] = useState<Record<string, boolean>>({
    "CNSHA_vessel_calls": true,
    "CNSHA_bookings": true,
    "CNSHA_empties": true,
    "CNSHA_inventory": true,
    "SGSIN_vessel_calls": true,
    "SGSIN_bookings": true,
    "SGSIN_empties": true,
    "SGSIN_inventory": true,
    "INMAA_vessel_calls": true,
    "INMAA_bookings": true,
    "INMAA_empties": true,
    "INMAA_inventory": true,
    "AEDXB_vessel_calls": true,
    "AEDXB_bookings": true,
    "AEDXB_empties": true,
    "AEDXB_inventory": true,
  });

  const toggleDropdown = (key: string) => {
    setExpandedDropdowns((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const toggleAllForPort = (portCode: string, expand: boolean) => {
    setExpandedDropdowns((prev) => ({
      ...prev,
      [`${portCode}_vessel_calls`]: expand,
      [`${portCode}_bookings`]: expand,
      [`${portCode}_empties`]: expand,
      [`${portCode}_inventory`]: expand,
    }));
  };

  // Modals state
  const [showAddBookingModal, setShowAddBookingModal] = useState(false);
  const [showReassignVesselModal, setShowReassignVesselModal] = useState(false);
  const [showAdjustInventoryModal, setShowAdjustInventoryModal] = useState(false);

  // Form states
  const [newBooking, setNewBooking] = useState({
    origin_unlocode: "CNSHA",
    destination_unlocode: "AEDXB",
    container_type: "20FT_DRY",
    quantity: 20,
    cargo_weight_mt: 14.0,
    cargo_ready_day: 4,
    cutoff_day: 5,
    delivery_deadline_day: 24,
    priority: "HIGH",
  });

  const [reassignForm, setReassignForm] = useState({
    voyage_number: "VOY_A1",
    vessel_name: "MV Pacific Trader",
    vessel_assignment_status: "FIRM",
  });

  const [adjustInvForm, setAdjustInvForm] = useState({
    port_unlocode: "CNSHA",
    container_type: "20FT_DRY",
    quantity_change: 20,
  });

  const showToast = (msg: string) => {
    setStatusToast(msg);
    setTimeout(() => setStatusToast(null), 4000);
  };

  // 1. Fetch raw state from SQLite DB without solving
  const fetchRawDBState = useCallback(async () => {
    try {
      setLoading(true);
      setApiError(null);

      const [dbRes, rawBkRes, voyRes] = await Promise.all([
        fetch(`${API_BASE}/test-admin/db-status`),
        fetch(`${API_BASE}/test-admin/bookings`),
        fetch(`${API_BASE}/test-admin/voyages`),
      ]);

      if (!dbRes.ok || !rawBkRes.ok) {
        throw new Error("Failed to read test database at localhost:8000");
      }

      const dbData = await dbRes.json();
      const rawBkData = await rawBkRes.json();
      const voyData = await voyRes.json();

      setDbStatus(dbData);
      setRawBookings(rawBkData.bookings || []);
      setVoyagesList(voyData.voyages || []);
    } catch (err: any) {
      console.error("DB Fetch error:", err);
      setApiError(err.message || "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  }, []);

  // 2. Run HiGHS Solver & Simulation
  const runOptimization = async () => {
    try {
      setLoading(true);
      setApiError(null);

      const [runRes, milpRes, dbRes, voyRes] = await Promise.all([
        fetch(`${API_BASE}/simulation/world-1/run`, { method: "POST" }),
        fetch(`${API_BASE}/simulation/world-1/solve-milp`, { method: "POST" }),
        fetch(`${API_BASE}/test-admin/db-status`),
        fetch(`${API_BASE}/test-admin/voyages`),
      ]);

      if (!runRes.ok || !milpRes.ok) {
        throw new Error("Failed to execute HiGHS optimization run");
      }

      const runData = await runRes.json();
      const milpData = await milpRes.json();
      const dbData = await dbRes.json();
      const voyData = await voyRes.json();

      setSolverMetrics(milpData);
      setDbStatus(dbData);
      setVoyagesList(voyData.voyages || []);
      setPortInsights(runData.port_horizon_insights || []);
      setPortVesselSchedules(runData.port_vessel_schedules || []);

      if (runData.snapshots && runData.snapshots.length > 0) {
        const snap0 = runData.snapshots[0];
        setPortActionSummaries(snap0.port_action_summaries || []);
        setEmptyDirectives(snap0.empty_reposition_directives || []);
        setBookingDirectives(snap0.booking_dispatch_directives || []);
        setOptimizedBookings(snap0.bookings || []);
      }

      setIsOptimized(true);
      showToast("⚡ HiGHS MILP Solved! Port vessel calls & space allocations updated.");
    } catch (err: any) {
      console.error("Optimization error:", err);
      setApiError(err.message || "Optimization failed");
    } finally {
      setLoading(false);
    }
  };

  // Initial load: Only fetch raw DB state. Admin clicks "⚡ Run HiGHS Optimizer"
  useEffect(() => {
    fetchRawDBState();
  }, [fetchRawDBState]);

  // Reset database handler -> Clears solved state and shows raw DB
  const handleResetDatabase = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/test-admin/reset-db`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to reset database");

      setIsOptimized(false);
      setSolverMetrics(null);
      setOptimizedBookings([]);
      setPortInsights([]);
      setPortVesselSchedules([]);
      setPortActionSummaries([]);
      setEmptyDirectives([]);
      setBookingDirectives([]);

      await fetchRawDBState();
      showToast("🔄 Database reset to raw unoptimized state! Click '⚡ Run HiGHS Optimizer' to solve.");
    } catch (err: any) {
      alert("Error resetting DB: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  // Upstream Schedule & Vessel Assignment generator
  const handleGenerateSchedule = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/test-admin/generate-schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ horizon_days: 40, firm_horizon_days: 14 }),
      });
      if (!res.ok) throw new Error("Schedule generation failed");
      const data = await res.json();
      showToast(`🚢 Schedule Generated: ${data.generated_voyages} Voyages, ${data.generated_legs} Legs assigned to fleet!`);
      await runOptimization();
    } catch (err: any) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  // Reassign vessel handler
  const handleReassignVessel = async () => {
    try {
      const res = await fetch(`${API_BASE}/test-admin/reassign-vessel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reassignForm),
      });
      if (!res.ok) throw new Error("Vessel reassignment failed");
      setShowReassignVesselModal(false);
      showToast(`🚢 ${reassignForm.voyage_number} reassigned to ${reassignForm.vessel_name} (${reassignForm.vessel_assignment_status})!`);
      await runOptimization();
    } catch (err: any) {
      alert("Error: " + err.message);
    }
  };

  // Add booking handler
  const handleAddBooking = async () => {
    try {
      const res = await fetch(`${API_BASE}/test-admin/bookings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newBooking),
      });
      if (!res.ok) throw new Error("Booking creation failed");
      setShowAddBookingModal(false);
      showToast(`📦 New Booking created in cargo_pilot_test.db! Re-solving with HiGHS...`);
      await runOptimization();
    } catch (err: any) {
      alert("Error: " + err.message);
    }
  };

  // Adjust inventory handler
  const handleAdjustInventory = async () => {
    try {
      const res = await fetch(`${API_BASE}/test-admin/inventory/adjust`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(adjustInvForm),
      });
      if (!res.ok) throw new Error("Inventory adjustment failed");
      setShowAdjustInventoryModal(false);
      showToast(`📦 Inventory adjusted at ${adjustInvForm.port_unlocode}! Re-solving...`);
      await runOptimization();
    } catch (err: any) {
      alert("Error: " + err.message);
    }
  };

  // Filter port action summaries by selected dropdown
  const filteredPortSummaries = selectedPortFilter === "ALL"
    ? portActionSummaries
    : portActionSummaries.filter((p) => p.port_unlocode === selectedPortFilter);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased">
      {/* Toast Notification */}
      {statusToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-5 py-3 rounded-2xl shadow-2xl flex items-center space-x-3 border border-slate-700 animate-bounce">
          <span className="text-sm font-semibold">{statusToast}</span>
        </div>
      )}

      {/* Top Header Navigation */}
      <header className="border-b border-slate-200 bg-white/95 backdrop-blur-md sticky top-0 z-40 px-6 py-3 shadow-xs">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Link
              href="/"
              className="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center text-white font-black text-lg shadow-md shadow-indigo-500/20 hover:opacity-90 transition-all"
            >
              🚢
            </Link>
            <div>
              <div className="flex items-center space-x-2">
                <Link href="/" className="text-sm font-bold text-slate-600 hover:text-slate-900 transition-colors">
                  CargoPilot
                </Link>
                <span className="text-slate-400 text-xs">/</span>
                <Link href="/test" className="text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors">
                  Test Worlds
                </Link>
                <span className="text-slate-400 text-xs">/</span>
                <span className="text-sm font-bold text-indigo-600">World 1 Optimization & Port Directives</span>
              </div>
              <p className="text-[11px] text-slate-500">
                40-Day Lookahead Horizon ($H=40$ Days) Solved to Determine Vessel Call Space Allocations, Directives & Deficit Avoidance
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleResetDatabase}
              disabled={loading}
              className="bg-rose-50 hover:bg-rose-100 text-rose-700 px-3 py-1.5 rounded-xl border border-rose-200 text-xs font-bold transition-all flex items-center space-x-1"
              title="Clears and restores clean canonical World 1 dataset in SQLite"
            >
              <span>🔄 Reset DB</span>
            </button>
            <button
              onClick={runOptimization}
              disabled={loading}
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs flex items-center space-x-1.5 disabled:opacity-50"
            >
              <span>⚡ Run HiGHS Optimizer</span>
            </button>
            <div className="flex items-center space-x-1.5 text-xs bg-slate-50 px-2.5 py-1 rounded-lg border border-slate-200">
              <span
                className={`h-2 w-2 rounded-full ${
                  apiError ? "bg-rose-500" : isOptimized ? "bg-emerald-500 animate-pulse" : "bg-amber-500"
                }`}
              />
              <span className="font-mono text-[11px] text-slate-700">
                {apiError
                  ? "API Offline"
                  : isOptimized
                  ? `HiGHS Optimal (${solverMetrics?.optimality_gap.toFixed(1)}% Gap)`
                  : "Raw DB (Unsolved)"}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        
        {/* Navigation Tabs */}
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setActiveTab("EXECUTIVE_REPORT")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeTab === "EXECUTIVE_REPORT"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              📊 Executive Dispatch & Vessel Calls (Today)
            </button>
            <button
              onClick={() => setActiveTab("FLEET_SCHEDULE")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeTab === "FLEET_SCHEDULE"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              🚢 Upstream Service & Fleet Assignment
            </button>
            <button
              onClick={() => setActiveTab("DB_ADMIN")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeTab === "DB_ADMIN"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              🛠️ Live SQLite Data Editor
            </button>
            <button
              onClick={() => setActiveTab("DATA_QA")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeTab === "DATA_QA"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              🔍 Data Validation QA
            </button>
          </div>

          {/* DB Live Status Indicators */}
          {dbStatus && (
            <div className="flex items-center space-x-2 text-[11px] font-mono text-slate-500">
              <span className="bg-slate-100 px-2 py-0.5 rounded border border-slate-200 font-bold text-slate-700">
                DB: {dbStatus.database}
              </span>
              <span>{dbStatus.counts.ports} Ports</span>
              <span>•</span>
              <span>{dbStatus.counts.vessels} Vessels</span>
              <span>•</span>
              <span>{dbStatus.counts.voyages} Voyages</span>
              <span>•</span>
              <span>{dbStatus.counts.bookings} Bookings</span>
            </div>
          )}
        </div>

        {/* ========================================================================= */}
        {/* TAB 1: EXECUTIVE DISPATCH & PORT VESSEL CALLS */}
        {/* ========================================================================= */}
        {activeTab === "EXECUTIVE_REPORT" && (
          <div className="space-y-6">
            
            {/* Optimization Status Banner */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  {isOptimized ? (
                    <>
                      <span className="bg-emerald-100 text-emerald-800 text-xs px-2.5 py-0.5 rounded-full font-bold border border-emerald-200">
                        🟢 HiGHS MILP Global Optimum
                      </span>
                      <span className="bg-indigo-50 text-indigo-700 text-xs px-2.5 py-0.5 rounded-full font-bold border border-indigo-200">
                        40-Day Lookahead Planning Horizon
                      </span>
                    </>
                  ) : (
                    <span className="bg-amber-100 text-amber-900 text-xs px-2.5 py-0.5 rounded-full font-bold border border-amber-300">
                      ⚠️ Raw SQLite Database State (Pending Solver Execution)
                    </span>
                  )}
                </div>
                <h2 className="text-xl font-black text-slate-900 tracking-tight">
                  {isOptimized
                    ? "Operational Port Directives & Vessel Space Allocation"
                    : "Customer Booking Demands in Test DB (Unassigned)"}
                </h2>
                <p className="text-xs text-slate-500 max-w-3xl">
                  {isOptimized
                    ? "HiGHS solved the 40-day network to compute exact vessel call space allocations (laden TEU, empty TEU, free space), port holding windows, and equipment dispatch directives."
                    : "The database contains raw customer demands across all 4 ports. Click '⚡ Run HiGHS Optimizer' to execute the MILP model and compute optimal vessel loadings & container assignments."}
                </p>
              </div>

              {/* Action / High-Level Metrics */}
              {isOptimized && solverMetrics ? (
                <div className="flex items-center space-x-4 bg-slate-50 p-3 rounded-xl border border-slate-200 font-mono text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-bold block">Objective Cost</span>
                    <span className="text-sm font-black text-slate-900">
                      ${solverMetrics.objective_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="h-7 w-px bg-slate-200" />
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-bold block">MIP Gap</span>
                    <span className="text-sm font-black text-emerald-600">{solverMetrics.optimality_gap.toFixed(1)}%</span>
                  </div>
                  <div className="h-7 w-px bg-slate-200" />
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-bold block">Solve Time</span>
                    <span className="text-sm font-black text-slate-700">{solverMetrics.solve_time_seconds.toFixed(3)}s</span>
                  </div>
                </div>
              ) : (
                <button
                  onClick={runOptimization}
                  disabled={loading}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl font-bold text-xs shadow-md shadow-indigo-500/20 flex items-center space-x-2"
                >
                  <span>⚡ Run HiGHS Optimizer</span>
                </button>
              )}
            </div>

            {/* IF NOT OPTIMIZED: Show prominent Call To Action Banner */}
            {!isOptimized && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-amber-900 shadow-xs flex flex-col md:flex-row items-center justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="font-bold text-sm flex items-center space-x-2">
                    <span>⚠️ Database Reset: {rawBookings.length} Bookings Unassigned in SQLite</span>
                  </h3>
                  <p className="text-xs text-amber-800">
                    All customer booking requests exist in <code>cargo_pilot_test.db</code> as raw demands. Click the button to run HiGHS MILP optimization to bind them to voyages and generate port vessel space manifests.
                  </p>
                </div>
                <button
                  onClick={runOptimization}
                  className="bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-xl text-xs font-bold shadow-xs whitespace-nowrap"
                >
                  ⚡ Run HiGHS Optimizer
                </button>
              </div>
            )}

            {/* ========================================================================= */}
            {/* SECTION 1: PORT-BY-PORT DIRECTIVES & SCHEDULED VESSEL CALLS */}
            {/* ========================================================================= */}
            {isOptimized && (
              <div className="space-y-6">
                
                {/* Header with Port Filter Dropdown Selector */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
                  <div>
                    <h3 className="text-sm font-black text-slate-900 uppercase tracking-wider flex items-center space-x-2">
                      <span>🎯 Port-by-Port Vessel Manifests & Directives</span>
                    </h3>
                    <p className="text-xs text-slate-500">
                      Select a port from the dropdown or browse all ports. Click any section header to expand/collapse details.
                    </p>
                  </div>
                  
                  {/* Port Dropdown Filter */}
                  <div className="flex items-center space-x-2 shrink-0">
                    <label className="text-xs font-bold text-slate-700">Port Filter:</label>
                    <select
                      value={selectedPortFilter}
                      onChange={(e) => setSelectedPortFilter(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded-xl px-3 py-1.5 text-xs font-bold text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 font-mono shadow-2xs"
                    >
                      <option value="ALL">🌐 All 4 Strategic Hubs</option>
                      <option value="CNSHA">🇨🇳 CNSHA — Port of Shanghai</option>
                      <option value="SGSIN">🇸🇬 SGSIN — Port of Singapore</option>
                      <option value="INMAA">🇮🇳 INMAA — Port of Chennai</option>
                      <option value="AEDXB">🇦🇪 AEDXB — Port of Dubai</option>
                    </select>
                  </div>
                </div>

                {/* Grid of Port Cards */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {filteredPortSummaries.map((pas) => {
                    const portVesselData = portVesselSchedules.find((pvs) => pvs.port_unlocode === pas.port_unlocode);
                    const portEmpties = emptyDirectives.filter((erd) => erd.port_unlocode === pas.port_unlocode);
                    const portBookings = bookingDirectives.filter((bdd) => bdd.origin_port === pas.port_unlocode);

                    const isVesselCallsOpen = expandedDropdowns[`${pas.port_unlocode}_vessel_calls`] !== false;
                    const isBookingsOpen = expandedDropdowns[`${pas.port_unlocode}_bookings`] !== false;
                    const isEmptiesOpen = expandedDropdowns[`${pas.port_unlocode}_empties`] !== false;
                    const isInventoryOpen = expandedDropdowns[`${pas.port_unlocode}_inventory`] !== false;

                    return (
                      <div
                        key={pas.port_unlocode}
                        className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4 hover:shadow-md transition-all flex flex-col justify-between"
                      >
                        {/* 1. Port Header & Controls */}
                        <div>
                          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                            <div>
                              <div className="flex items-center space-x-2">
                                <span className="text-xs font-mono font-bold text-indigo-600 bg-indigo-50 px-2.5 py-0.5 rounded border border-indigo-100">
                                  {pas.port_unlocode}
                                </span>
                                <h4 className="text-base font-bold text-slate-900">{pas.port_name}</h4>
                              </div>
                              <p className="text-[11px] text-slate-500 font-mono mt-0.5">
                                Current Depot Stock: {pas.total_stock_teu} TEU (Safety Target: {pas.safety_stock_teu} TEU)
                              </p>
                            </div>
                            
                            <div className="flex items-center space-x-2">
                              <span
                                className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${
                                  pas.safety_status === "HEALTHY"
                                    ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                                    : "bg-amber-100 text-amber-800 border border-amber-200"
                                }`}
                              >
                                {pas.safety_status}
                              </span>
                              <button
                                onClick={() => toggleAllForPort(pas.port_unlocode, !isVesselCallsOpen)}
                                className="text-[10px] font-bold text-slate-500 hover:text-indigo-600 px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 transition-colors"
                                title="Toggle all dropdowns in this port"
                              >
                                {isVesselCallsOpen ? "Collapse" : "Expand"}
                              </button>
                            </div>
                          </div>

                          {/* 2. Scheduled Vessel / Voyage Calls Dropdown Accordion */}
                          <div className="mt-4 border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-2xs">
                            <button
                              onClick={() => toggleDropdown(`${pas.port_unlocode}_vessel_calls`)}
                              className="w-full p-3 bg-slate-50/90 hover:bg-slate-100/80 flex items-center justify-between text-left transition-colors border-b border-slate-200/60"
                            >
                              <div className="flex items-center space-x-2">
                                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                  🚢 Scheduled Vessel Calls & Space Allocation
                                </span>
                                <span className="text-[10px] font-mono bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-bold">
                                  {portVesselData?.vessel_calls.length || 0} Calls
                                </span>
                              </div>
                              <span className="text-xs font-bold text-slate-400">
                                {isVesselCallsOpen ? "▲" : "▼"}
                              </span>
                            </button>

                            {isVesselCallsOpen && (
                              <div className="p-3 space-y-3 bg-white">
                                {(!portVesselData || portVesselData.vessel_calls.length === 0) ? (
                                  <div className="text-xs text-slate-400 italic p-3 bg-slate-50 rounded-xl border border-slate-100 text-center">
                                    No vessel calls scheduled at this port.
                                  </div>
                                ) : (
                                  portVesselData.vessel_calls.map((call, cIdx) => (
                                    <div
                                      key={cIdx}
                                      className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-2.5 hover:bg-slate-100/70 transition-colors"
                                    >
                                      {/* Voyage & Vessel Heading */}
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-2">
                                          <span className="font-mono font-black text-indigo-700 bg-indigo-100/80 px-2 py-0.5 rounded text-[11px]">
                                            {call.voyage_number}
                                          </span>
                                          <span className="font-bold text-slate-900">{call.vessel_name}</span>
                                        </div>
                                        <span
                                          className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                                            call.call_type === "ORIGIN_DEPARTURE"
                                              ? "bg-cyan-100 text-cyan-800"
                                              : call.call_type === "INTERMEDIATE_TRANSIT_CALL"
                                              ? "bg-purple-100 text-purple-800"
                                              : "bg-emerald-100 text-emerald-800"
                                          }`}
                                        >
                                          {call.call_type.replace(/_/g, " ")}
                                        </span>
                                      </div>

                                      {/* Timing & Call Details */}
                                      <div className="text-[11px] font-mono text-slate-600 flex flex-wrap items-center gap-x-3 gap-y-1">
                                        {call.arrival_day !== null && (
                                          <span>Arrives: <strong>Day {call.arrival_day}</strong></span>
                                        )}
                                        {call.berth_stay_duration_days > 0 && (
                                          <span className="text-indigo-600 font-semibold">
                                            (Holds {call.berth_stay_duration_days}d in Berth)
                                          </span>
                                        )}
                                        {call.departure_day !== null ? (
                                          <span>
                                            Departs: <strong>Day {call.departure_day}</strong> → Next: <strong>{call.destination_port}</strong>
                                          </span>
                                        ) : (
                                          <span className="text-emerald-700 font-semibold">Turnaround Port (Discharge)</span>
                                        )}
                                      </div>

                                      {/* Vessel Capacity & Space Allocation Matrix */}
                                      <div className="bg-white p-2.5 rounded-lg border border-slate-200/80 space-y-2 font-mono">
                                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-[10px]">
                                          <div className="bg-slate-50 p-1.5 rounded">
                                            <span className="text-slate-400 block font-semibold">Total Capacity</span>
                                            <span className="font-black text-slate-800">{call.vessel_capacity_teu} TEU</span>
                                          </div>
                                          <div className="bg-indigo-50/70 p-1.5 rounded">
                                            <span className="text-indigo-600 block font-semibold">Laden Bookings</span>
                                            <span className="font-black text-indigo-900">{call.laden_bookings_teu} TEU</span>
                                          </div>
                                          <div className="bg-emerald-50/70 p-1.5 rounded">
                                            <span className="text-emerald-600 block font-semibold">Empty Placed</span>
                                            <span className="font-black text-emerald-900">{call.empty_reposition_teu} TEU</span>
                                          </div>
                                          <div className="bg-slate-100 p-1.5 rounded">
                                            <span className="text-slate-500 block font-semibold">Free Space</span>
                                            <span className="font-black text-slate-700">{call.remaining_free_teu} TEU</span>
                                          </div>
                                        </div>

                                        {/* Visual Capacity Utilization Bar */}
                                        <div>
                                          <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                                            <span>Capacity Utilization</span>
                                            <span className="font-bold text-slate-800">{call.utilization_pct}% Used ({call.total_onboard_teu} / {call.vessel_capacity_teu} TEU)</span>
                                          </div>
                                          <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden flex">
                                            <div
                                              className="bg-indigo-600 h-full"
                                              style={{ width: `${(call.laden_bookings_teu / call.vessel_capacity_teu) * 100}%` }}
                                              title={`Laden: ${call.laden_bookings_teu} TEU`}
                                            />
                                            <div
                                              className="bg-emerald-500 h-full"
                                              style={{ width: `${(call.empty_reposition_teu / call.vessel_capacity_teu) * 100}%` }}
                                              title={`Empty: ${call.empty_reposition_teu} TEU`}
                                            />
                                          </div>
                                        </div>

                                        {/* Assigned Bookings List */}
                                        {call.laden_bookings_list && call.laden_bookings_list.length > 0 && (
                                          <div className="pt-1.5 border-t border-slate-100">
                                            <span className="text-[10px] text-slate-400 uppercase font-bold block mb-1">
                                              Assigned Bookings Placed on this Voyage:
                                            </span>
                                            <div className="flex flex-wrap gap-1.5">
                                              {call.laden_bookings_list.map((bk, bIdx) => (
                                                <span
                                                  key={bIdx}
                                                  className="bg-indigo-50 border border-indigo-200 text-indigo-800 px-2 py-0.5 rounded text-[10px] font-bold"
                                                >
                                                  {bk.booking_id}: {bk.quantity}× {bk.container_type.replace("DRY_", "").replace("_DRY", "")} ({bk.teu_load} TEU) → {bk.destination}
                                                </span>
                                              ))}
                                            </div>
                                          </div>
                                        )}

                                        {/* Empty Repositions List */}
                                        {call.empty_reposition_list && call.empty_reposition_list.length > 0 && (
                                          <div className="pt-1 border-t border-slate-100">
                                            <span className="text-[10px] text-slate-400 uppercase font-bold block mb-1">
                                              Empty Container Loading Moves:
                                            </span>
                                            <div className="flex flex-wrap gap-1.5">
                                              {call.empty_reposition_list.map((em, eIdx) => (
                                                <span
                                                  key={eIdx}
                                                  className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-2 py-0.5 rounded text-[10px] font-bold"
                                                >
                                                  +{em.quantity}× {em.container_type.replace("DRY_", "").replace("_DRY", "")} ({em.teu_load} TEU) → {em.to_port}
                                                </span>
                                              ))}
                                            </div>
                                          </div>
                                        )}
                                      </div>

                                    </div>
                                  ))
                                )}
                              </div>
                            )}
                          </div>

                          {/* 3. Today's Commercial Bookings Dropdown Accordion */}
                          <div className="mt-3 border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-2xs">
                            <button
                              onClick={() => toggleDropdown(`${pas.port_unlocode}_bookings`)}
                              className="w-full p-3 bg-slate-50/90 hover:bg-slate-100/80 flex items-center justify-between text-left transition-colors border-b border-slate-200/60"
                            >
                              <div className="flex items-center space-x-2">
                                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                  📦 Commercial Bookings Directives (Originating Here)
                                </span>
                                <span className="text-[10px] font-mono bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-bold">
                                  {portBookings.length} Directives
                                </span>
                              </div>
                              <span className="text-xs font-bold text-slate-400">
                                {isBookingsOpen ? "▲" : "▼"}
                              </span>
                            </button>

                            {isBookingsOpen && (
                              <div className="p-3 space-y-2 bg-white">
                                {portBookings.length === 0 ? (
                                  <div className="text-xs text-slate-400 italic p-2 bg-slate-50 rounded-xl border border-slate-100 text-center">
                                    No outbound laden bookings originating today.
                                  </div>
                                ) : (
                                  portBookings.map((b, idx) => (
                                    <div
                                      key={idx}
                                      className="text-xs p-2.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2"
                                    >
                                      <div className="space-y-0.5">
                                        <div className="flex items-center space-x-2">
                                          <span className="font-bold text-indigo-700 font-mono">{b.booking_id}</span>
                                          <span className="text-slate-400">→</span>
                                          <span className="font-semibold text-slate-800">{b.destination_port}</span>
                                          <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded font-mono">
                                            {b.total_quantity}× {b.container_type.replace("DRY_", "").replace("_DRY", "")}
                                          </span>
                                        </div>
                                        <p className="text-[11px] text-slate-600">{b.action_instruction}</p>
                                      </div>
                                      <span
                                        className={`px-2 py-0.5 rounded text-[10px] font-bold shrink-0 font-mono ${
                                          b.urgency === "DISPATCH_NOW"
                                            ? "bg-amber-100 text-amber-900 border border-amber-300"
                                            : b.urgency === "LOAD_VESSEL_TODAY"
                                            ? "bg-indigo-100 text-indigo-900 border border-indigo-300"
                                            : "bg-slate-200 text-slate-700"
                                        }`}
                                      >
                                        {b.urgency}
                                      </span>
                                    </div>
                                  ))
                                )}
                              </div>
                            )}
                          </div>

                          {/* 4. Empty Repositioning Loading Orders Dropdown Accordion */}
                          <div className="mt-3 border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-2xs">
                            <button
                              onClick={() => toggleDropdown(`${pas.port_unlocode}_empties`)}
                              className="w-full p-3 bg-slate-50/90 hover:bg-slate-100/80 flex items-center justify-between text-left transition-colors border-b border-slate-200/60"
                            >
                              <div className="flex items-center space-x-2">
                                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                  🔁 Empty Container Loading Directives
                                </span>
                                <span className="text-[10px] font-mono bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded font-bold">
                                  {portEmpties.length} Directives
                                </span>
                              </div>
                              <span className="text-xs font-bold text-slate-400">
                                {isEmptiesOpen ? "▲" : "▼"}
                              </span>
                            </button>

                            {isEmptiesOpen && (
                              <div className="p-3 space-y-2 bg-white">
                                {portEmpties.length === 0 ? (
                                  <div className="text-xs text-slate-400 italic p-2 bg-slate-50 rounded-xl border border-slate-100 text-center">
                                    No vessel departure today requiring empty loading.
                                  </div>
                                ) : (
                                  portEmpties.map((erd, idx) => (
                                    <div
                                      key={idx}
                                      className={`text-xs p-2.5 rounded-xl border font-mono flex items-start justify-between ${
                                        erd.should_load_empties
                                          ? "bg-emerald-50 border-emerald-200 text-emerald-950"
                                          : "bg-slate-50 border-slate-200 text-slate-600"
                                      }`}
                                    >
                                      <div className="space-y-0.5">
                                        <span className="font-bold block">
                                          {erd.should_load_empties ? "✅ LOAD EMPTIES" : "⏸️ HOLD / DO NOT LOAD"}
                                        </span>
                                        <p className="text-[11px]">{erd.action_instruction}</p>
                                      </div>
                                      {erd.should_load_empties && (
                                        <span className="bg-emerald-600 text-white px-2 py-0.5 rounded text-[10px] font-bold shrink-0 ml-2">
                                          +{erd.total_reposition_teu} TEU
                                        </span>
                                      )}
                                    </div>
                                  ))
                                )}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* 5. Depot Stock Sub-Matrix Dropdown */}
                        <div className="mt-3 border-t border-slate-100 pt-3">
                          <button
                            onClick={() => toggleDropdown(`${pas.port_unlocode}_inventory`)}
                            className="w-full flex items-center justify-between text-[11px] font-mono text-slate-500 hover:text-slate-800 transition-colors"
                          >
                            <span>📦 Live Depot Breakdown Matrix</span>
                            <span className="font-bold text-indigo-600">
                              Total: {pas.total_stock_teu} TEU {isInventoryOpen ? "▲" : "▼"}
                            </span>
                          </button>
                          {isInventoryOpen && (
                            <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs font-mono bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                              <div>
                                <span className="text-[10px] text-slate-400 block font-semibold">20ft Dry</span>
                                <span className="font-bold text-slate-800">{pas.current_stock["20FT_DRY"] || 0}</span>
                              </div>
                              <div>
                                <span className="text-[10px] text-slate-400 block font-semibold">40ft Dry</span>
                                <span className="font-bold text-slate-800">{pas.current_stock["40FT_DRY"] || 0}</span>
                              </div>
                              <div>
                                <span className="text-[10px] text-slate-400 block font-semibold">40ft HC</span>
                                <span className="font-bold text-slate-800">{pas.current_stock["40FT_HIGH_CUBE"] || 0}</span>
                              </div>
                            </div>
                          )}
                        </div>

                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* SECTION 2: 40-DAY FORWARD-LOOKING DEFICIT & BOTTLENECK ANALYSIS */}
            {isOptimized && (
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div>
                    <h3 className="text-base font-black text-slate-900 flex items-center space-x-2">
                      <span>🔮 40-Day Lookahead Risk & Bottleneck Analysis</span>
                    </h3>
                    <p className="text-xs text-slate-500">
                      Projections across all 40 days computed by the optimizer to detect periods where port inventory drops near or below safety buffer.
                    </p>
                  </div>
                  <span className="text-xs bg-indigo-50 text-indigo-700 font-bold px-3 py-1 rounded-xl border border-indigo-100">
                    Deficit Prevention Active
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {portInsights.map((pi) => (
                    <div
                      key={pi.port_unlocode}
                      className={`p-4 rounded-xl border flex flex-col justify-between ${
                        pi.deficit_status === "CRITICAL_DEFICIT_RISK"
                          ? "bg-rose-50/70 border-rose-200"
                          : pi.deficit_status === "TIGHT_BUFFER"
                          ? "bg-amber-50/70 border-amber-200"
                          : "bg-slate-50 border-slate-200"
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center space-x-2">
                            <span className="font-mono font-bold text-xs text-slate-900">{pi.port_unlocode}</span>
                            <span className="text-xs font-semibold text-slate-700">{pi.port_name}</span>
                          </div>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              pi.deficit_status === "CRITICAL_DEFICIT_RISK"
                                ? "bg-rose-600 text-white"
                                : pi.deficit_status === "TIGHT_BUFFER"
                                ? "bg-amber-500 text-white"
                                : "bg-emerald-600 text-white"
                            }`}
                          >
                            {pi.deficit_status.replace(/_/g, " ")}
                          </span>
                        </div>

                        {/* Min / Max TEU Trajectory */}
                        <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono my-3 bg-white p-2.5 rounded-lg border border-slate-200/80">
                          <div>
                            <span className="text-[10px] text-slate-400 block font-bold">Initial (D0)</span>
                            <span className="font-bold text-slate-900">{pi.initial_stock_teu} TEU</span>
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400 block font-bold">Projected Low</span>
                            <span
                              className={`font-black ${
                                pi.min_stock_teu < pi.safety_stock_teu ? "text-rose-600" : "text-amber-600"
                              }`}
                            >
                              {pi.min_stock_teu.toFixed(0)} TEU (Day {pi.min_stock_day})
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400 block font-bold">Safety Stock</span>
                            <span className="font-bold text-indigo-700">{pi.safety_stock_teu} TEU</span>
                          </div>
                        </div>

                        <p className="text-xs text-slate-700 leading-relaxed font-sans">{pi.explanation}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* SECTION 3: COMMERCIAL BOOKINGS ASSIGNMENT LEDGER */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div>
                  <h3 className="text-base font-black text-slate-900">
                    📋 Customer Bookings → Equipment Assignment Ledger
                  </h3>
                  <p className="text-xs text-slate-500">
                    {isOptimized
                      ? "Every customer booking demand mapped to physical container allocation, assigned vessel voyage, departure day, and delivery milestone."
                      : "Raw customer booking demands currently stored in SQLite (cargo_pilot_test.db) awaiting HiGHS MILP optimization."}
                  </p>
                </div>
                <button
                  onClick={() => setShowAddBookingModal(true)}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs"
                >
                  ➕ Add Booking
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-100 text-slate-700 uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="p-3">Booking ID</th>
                      <th className="p-3">Route (Origin → Dest)</th>
                      <th className="p-3">Type & Quantity</th>
                      <th className="p-3">Priority</th>
                      <th className="p-3">Assigned Voyage</th>
                      <th className="p-3">Departure → Delivery</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {isOptimized ? (
                      optimizedBookings.map((b) => (
                        <tr key={b.booking_id} className="hover:bg-slate-50 transition-colors">
                          <td className="p-3 font-bold text-indigo-600">{b.booking_id}</td>
                          <td className="p-3 font-bold text-slate-900">
                            {b.origin} → {b.destination}
                          </td>
                          <td className="p-3 text-slate-700">
                            {b.quantity}× {b.container_type.replace("DRY_", "").replace("_DRY", "")}
                          </td>
                          <td className="p-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                b.priority === "CRITICAL"
                                  ? "bg-rose-100 text-rose-800"
                                  : b.priority === "HIGH"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-slate-100 text-slate-700"
                              }`}
                            >
                              {b.priority}
                            </span>
                          </td>
                          <td className="p-3 font-bold text-purple-700 bg-purple-50/50">{b.voyage || "—"}</td>
                          <td className="p-3 text-slate-600">
                            {b.departure_day !== null ? `Day ${b.departure_day} → Day ${b.arrival_day}` : "Pending"}
                          </td>
                          <td className="p-3">
                            <span className="bg-emerald-100 text-emerald-800 border border-emerald-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                              OPTIMIZED & ASSIGNED
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : (
                      rawBookings.map((rb) => (
                        <tr key={rb.id} className="hover:bg-slate-50 transition-colors">
                          <td className="p-3 font-bold text-indigo-600">{rb.booking_code}</td>
                          <td className="p-3 font-bold text-slate-900">
                            {rb.origin} → {rb.destination}
                          </td>
                          <td className="p-3 text-slate-700">
                            {rb.quantity}× {rb.container_type.replace("DRY_", "").replace("_DRY", "")}
                          </td>
                          <td className="p-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                rb.priority === "CRITICAL"
                                  ? "bg-rose-100 text-rose-800"
                                  : rb.priority === "HIGH"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-slate-100 text-slate-700"
                              }`}
                            >
                              {rb.priority}
                            </span>
                          </td>
                          <td className="p-3 text-slate-400 italic">
                            <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-[10px]">
                              — (Unassigned in DB)
                            </span>
                          </td>
                          <td className="p-3 text-slate-600">
                            Ready Day {rb.cargo_ready_day} → Deadline Day {rb.delivery_deadline_day}
                          </td>
                          <td className="p-3">
                            <span className="bg-amber-100 text-amber-800 border border-amber-300 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                              PENDING SOLVER RUN
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: UPSTREAM SERVICE ROTATIONS & FLEET ASSIGNMENT */}
        {/* ========================================================================= */}
        {activeTab === "FLEET_SCHEDULE" && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <div className="flex flex-col md:flex-row items-center justify-between gap-4 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="text-base font-black text-slate-900">
                    🚢 Upstream Liner Services & Fleet Assignment Engine
                  </h3>
                  <p className="text-xs text-slate-500">
                    Service Rotation Templates generate dated voyage instances. The Fleet Planner assigns available vessels (Firm within 14 days vs Provisional beyond 14 days) before CargoPilot optimizes.
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleGenerateSchedule}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold shadow-xs transition-all"
                  >
                    🔄 Run Upstream Fleet Planner
                  </button>
                  <button
                    onClick={() => setShowReassignVesselModal(true)}
                    className="bg-slate-800 hover:bg-slate-900 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold shadow-xs transition-all"
                  >
                    ✏️ Reassign Vessel
                  </button>
                </div>
              </div>

              {/* Service Rotations Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 my-6">
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-indigo-700 font-mono text-sm">LOOP_A</span>
                    <span className="text-[10px] bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-bold">
                      Every 14 Days
                    </span>
                  </div>
                  <h4 className="text-xs font-bold text-slate-800 mb-2">Asia-Middle East Express Loop A</h4>
                  <div className="text-xs font-mono text-slate-600 space-y-1">
                    <div>1. CNSHA (Shanghai) - Day 0 departure</div>
                    <div>2. SGSIN (Singapore) - Day 5 arrival, Day 6 departure</div>
                    <div>3. INMAA (Chennai) - Day 10 arrival, Day 11 departure</div>
                    <div>4. AEDXB (Dubai) - Day 16 arrival (Turnaround)</div>
                  </div>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-cyan-700 font-mono text-sm">LOOP_B</span>
                    <span className="text-[10px] bg-cyan-100 text-cyan-800 px-2 py-0.5 rounded font-bold">
                      Every 15 Days
                    </span>
                  </div>
                  <h4 className="text-xs font-bold text-slate-800 mb-2">Middle East-Asia Express Loop B</h4>
                  <div className="text-xs font-mono text-slate-600 space-y-1">
                    <div>1. AEDXB (Dubai) - Day 0 departure</div>
                    <div>2. INMAA (Chennai) - Day 5 arrival, Day 6 departure</div>
                    <div>3. SGSIN (Singapore) - Day 10 arrival, Day 11 departure</div>
                    <div>4. CNSHA (Shanghai) - Day 16 arrival (Turnaround)</div>
                  </div>
                </div>
              </div>

              {/* Generated Voyages Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-100 text-slate-700 uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="p-3">Voyage #</th>
                      <th className="p-3">Service</th>
                      <th className="p-3">Assigned Vessel</th>
                      <th className="p-3">Departure / Arrival</th>
                      <th className="p-3">Legs</th>
                      <th className="p-3">Capacity</th>
                      <th className="p-3">Assignment Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {voyagesList.map((v) => (
                      <tr key={v.voyage_id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-3 font-bold text-indigo-600">{v.voyage_number}</td>
                        <td className="p-3 text-slate-700">{v.service_name}</td>
                        <td className="p-3 font-bold text-slate-900">{v.vessel_name}</td>
                        <td className="p-3 text-slate-600">
                          {v.legs[0]?.departure_day !== undefined
                            ? `Day ${v.legs[0].departure_day} → Day ${v.legs[v.legs.length - 1]?.arrival_day}`
                            : "—"}
                        </td>
                        <td className="p-3">{v.legs.length} Legs</td>
                        <td className="p-3 text-slate-700">{v.legs[0]?.capacity_teu || 1200} TEU</td>
                        <td className="p-3">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                              v.vessel_assignment_status === "FIRM"
                                ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                                : "bg-amber-100 text-amber-800 border border-amber-200"
                            }`}
                          >
                            {v.vessel_assignment_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: LIVE DATABASE & TEST DATA EDITOR */}
        {/* ========================================================================= */}
        {activeTab === "DB_ADMIN" && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
              <div className="flex flex-col md:flex-row items-center justify-between gap-4 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="text-base font-black text-slate-900">
                    🛠️ Live SQLite Database & Scenario Editor (`cargo_pilot_test.db`)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Modify demand bookings, adjust container depot stocks, or reseed clean canonical fixtures. All changes persist in SQLite.
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setShowAddBookingModal(true)}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs"
                  >
                    ➕ Add Booking Demand
                  </button>
                  <button
                    onClick={() => setShowAdjustInventoryModal(true)}
                    className="bg-cyan-600 hover:bg-cyan-700 text-white px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs"
                  >
                    📦 Adjust Port Inventory
                  </button>
                  <button
                    onClick={handleResetDatabase}
                    className="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs"
                  >
                    🔄 Reset & Reseed DB
                  </button>
                </div>
              </div>

              {/* DB Statistics Matrix */}
              {dbStatus && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 my-6 font-mono text-center">
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <span className="text-[10px] text-slate-500">Ports</span>
                    <p className="text-lg font-black text-indigo-600">{dbStatus.counts.ports}</p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <span className="text-[10px] text-slate-500">Vessels</span>
                    <p className="text-lg font-black text-indigo-600">{dbStatus.counts.vessels}</p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <span className="text-[10px] text-slate-500">Services</span>
                    <p className="text-lg font-black text-indigo-600">{dbStatus.counts.services}</p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <span className="text-[10px] text-slate-500">Voyages</span>
                    <p className="text-lg font-black text-indigo-600">{dbStatus.counts.voyages}</p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <span className="text-[10px] text-slate-500">Bookings</span>
                    <p className="text-lg font-black text-indigo-600">{dbStatus.counts.bookings}</p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <span className="text-[10px] text-slate-500">Containers</span>
                    <p className="text-lg font-black text-indigo-600">{dbStatus.counts.containers}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: DATA VALIDATION QA */}
        {/* ========================================================================= */}
        {activeTab === "DATA_QA" && (
          <div className="space-y-4">
            {/* Run button */}
            {!qaReport && (
              <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-xs text-center space-y-3">
                <div className="text-3xl">🔍</div>
                <h2 className="text-sm font-bold text-slate-900">CargoPilot Data QA Engine — World 1</h2>
                <p className="text-xs text-slate-500 max-w-lg mx-auto leading-relaxed">
                  Runs 35+ logistics-aware validation rules across bookings, vessels, voyages, ports,
                  inventory, and costs for the 4-port 40-day World 1 scenario.
                </p>
                <button
                  onClick={runQA}
                  disabled={qaLoading}
                  className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white font-bold text-xs px-6 py-2.5 rounded-xl shadow-xs transition-all"
                >
                  {qaLoading ? "⏳ Running validation…" : "▶ Run Data Validation"}
                </button>
              </div>
            )}

            {qaReport && (() => {
              const summary = qaReport.summary;
              const issues: any[] = qaReport.issues ?? [];
              const catBreakdown = qaReport.category_breakdown ?? {};

              const filtered = issues.filter((iss: any) => {
                const sevOk  = qaFilter   === "ALL" || iss.severity === qaFilter;
                const catOk  = qaCategory === "ALL" || iss.category === qaCategory;
                return sevOk && catOk;
              });

              const sevColor = (s: string) =>
                s === "ERROR"   ? "text-red-700 bg-red-50 border-red-200" :
                s === "WARNING" ? "text-amber-700 bg-amber-50 border-amber-200" :
                                  "text-sky-700 bg-sky-50 border-sky-200";
              const sevDot = (s: string) =>
                s === "ERROR" ? "🔴" : s === "WARNING" ? "🟡" : "🔵";

              return (
                <div className="space-y-4">
                  {/* Re-run button */}
                  <div className="flex justify-end">
                    <button onClick={runQA} disabled={qaLoading}
                      className="bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-200 transition-all">
                      {qaLoading ? "⏳ Running…" : "↺ Re-run Validation"}
                    </button>
                  </div>

                  {/* ── QA Report Header ─────────────────────────────────────── */}
                  <div className={`rounded-xl border-2 p-5 ${qaReport.blocking ? "border-red-300 bg-red-50" : "border-emerald-300 bg-emerald-50"}`}>
                    <div className="flex items-start justify-between">
                      <div>
                        <h2 className="font-black text-lg text-slate-900">
                          {qaReport.blocking ? "🚨 Validation BLOCKING" : "✅ Validation Passed"}
                        </h2>
                        <p className="text-xs text-slate-600 mt-0.5">
                          {qaReport.blocking
                            ? "Dataset has ERRORs — do NOT send to optimizer until resolved."
                            : "No blocking errors. Dataset is safe to optimise."}
                        </p>
                      </div>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {new Date(qaReport.generated_at).toLocaleTimeString()}
                      </span>
                    </div>

                    {/* Big stats row */}
                    <div className="mt-4 grid grid-cols-5 gap-3">
                      {[
                        { label: "Records Processed", value: summary.total_records.toLocaleString(), color: "text-slate-900" },
                        { label: "Records OK",         value: summary.records_ok.toLocaleString(),   color: "text-emerald-700" },
                        { label: "Errors",             value: summary.errors,                        color: "text-red-700" },
                        { label: "Warnings",           value: summary.warnings,                      color: "text-amber-700" },
                        { label: "Info",               value: summary.infos,                         color: "text-sky-700" },
                      ].map(st => (
                        <div key={st.label} className="bg-white rounded-lg p-3 border border-slate-100 text-center shadow-xs">
                          <div className={`text-2xl font-black ${st.color}`}>{st.value}</div>
                          <div className="text-[10px] text-slate-500 mt-0.5 font-semibold">{st.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* ── Category Breakdown ───────────────────────────────────── */}
                  <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
                    <div className="px-4 py-3 border-b border-slate-100">
                      <h3 className="text-xs font-bold text-slate-700">Category Breakdown</h3>
                    </div>
                    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-px bg-slate-100">
                      {Object.entries(catBreakdown).map(([cat, info]: [string, any]) => (
                        <button
                          key={cat}
                          onClick={() => setQaCategory(qaCategory === cat ? "ALL" : cat)}
                          className={`bg-white p-3 text-left hover:bg-indigo-50 transition-colors ${qaCategory === cat ? "ring-2 ring-indigo-400 ring-inset" : ""}`}
                        >
                          <div className="text-[11px] font-bold text-slate-700">{cat}</div>
                          <div className="text-[10px] mt-1 space-x-2">
                            {info.errors > 0 && <span className="text-red-600 font-bold">{info.errors}E</span>}
                            {info.warnings > 0 && <span className="text-amber-600 font-bold">{info.warnings}W</span>}
                            {info.infos > 0 && <span className="text-sky-600">{info.infos}I</span>}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* ── Filter chips ─────────────────────────────────────────── */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-slate-500 font-semibold">Filter:</span>
                    {(["ALL", "ERROR", "WARNING", "INFO"] as const).map(sev => (
                      <button key={sev} onClick={() => setQaFilter(sev)}
                        className={`px-3 py-1 rounded-full text-[11px] font-bold border transition-all ${
                          qaFilter === sev
                            ? sev === "ERROR"   ? "bg-red-600 text-white border-red-600"
                            : sev === "WARNING" ? "bg-amber-500 text-white border-amber-500"
                            : sev === "INFO"    ? "bg-sky-600 text-white border-sky-600"
                            : "bg-indigo-600 text-white border-indigo-600"
                            : "bg-white text-slate-600 border-slate-200 hover:border-indigo-400"
                        }`}
                      >
                        {sev === "ALL" ? `All (${issues.length})` : `${sevDot(sev)} ${sev} (${issues.filter((i: any) => i.severity === sev).length})`}
                      </button>
                    ))}
                    {qaCategory !== "ALL" && (
                      <button onClick={() => setQaCategory("ALL")}
                        className="px-2 py-1 rounded-full text-[11px] text-indigo-700 border border-indigo-300 bg-indigo-50 font-semibold">
                        ✕ {qaCategory}
                      </button>
                    )}
                    <span className="text-[10px] text-slate-400 ml-2">{filtered.length} shown</span>
                  </div>

                  {/* ── Issue list ───────────────────────────────────────────── */}
                  <div className="space-y-1.5 max-h-[600px] overflow-y-auto pr-1">
                    {filtered.map((iss: any, idx: number) => (
                      <div key={idx} className={`rounded-xl border p-3.5 ${sevColor(iss.severity)}`}>
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="text-[10px] font-black tracking-widest uppercase">{iss.severity}</span>
                              <span className="text-[10px] font-bold bg-white/60 px-1.5 py-0.5 rounded border border-current/20">{iss.category}</span>
                              <span className="text-[10px] font-mono text-current/60">{iss.rule_id}</span>
                              <span className="text-[10px] font-mono bg-white/40 px-1.5 py-0.5 rounded">{iss.entity_id}</span>
                            </div>
                            <p className="text-xs font-medium leading-snug">{iss.message}</p>
                          </div>
                        </div>
                        {/* Context drilldown */}
                        {Object.keys(iss.context ?? {}).length > 0 && (
                          <div className="mt-2 pt-2 border-t border-current/10 flex flex-wrap gap-x-4 gap-y-0.5">
                            {Object.entries(iss.context).map(([k, v]: [string, any]) => (
                              <span key={k} className="text-[10px] font-mono">
                                <span className="opacity-60">{k}:</span>{" "}
                                <span className="font-bold">{typeof v === "number" ? v.toLocaleString() : String(v)}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                    {filtered.length === 0 && (
                      <div className="text-center py-8 text-slate-400 text-sm">
                        No issues match the current filter.
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>
        )}


      </main>

      {/* ========================================================================= */}
      {/* MODAL: ADD BOOKING DEMAND */}
      {/* ========================================================================= */}
      {showAddBookingModal && (
        <div className="fixed inset-0 bg-slate-950/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-200 space-y-4">
            <h3 className="text-sm font-black text-slate-900">➕ Add New Commercial Booking Demand</h3>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="font-bold text-slate-700">Origin Port</label>
                  <select
                    value={newBooking.origin_unlocode}
                    onChange={(e) => setNewBooking({ ...newBooking, origin_unlocode: e.target.value })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  >
                    <option value="CNSHA">CNSHA (Shanghai)</option>
                    <option value="SGSIN">SGSIN (Singapore)</option>
                    <option value="INMAA">INMAA (Chennai)</option>
                    <option value="AEDXB">AEDXB (Dubai)</option>
                  </select>
                </div>
                <div>
                  <label className="font-bold text-slate-700">Destination Port</label>
                  <select
                    value={newBooking.destination_unlocode}
                    onChange={(e) => setNewBooking({ ...newBooking, destination_unlocode: e.target.value })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  >
                    <option value="AEDXB">AEDXB (Dubai)</option>
                    <option value="INMAA">INMAA (Chennai)</option>
                    <option value="SGSIN">SGSIN (Singapore)</option>
                    <option value="CNSHA">CNSHA (Shanghai)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="font-bold text-slate-700">Container Type</label>
                  <select
                    value={newBooking.container_type}
                    onChange={(e) => setNewBooking({ ...newBooking, container_type: e.target.value })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  >
                    <option value="20FT_DRY">20ft Dry</option>
                    <option value="40FT_DRY">40ft Dry</option>
                    <option value="40FT_HIGH_CUBE">40ft High Cube</option>
                  </select>
                </div>
                <div>
                  <label className="font-bold text-slate-700">Quantity</label>
                  <input
                    type="number"
                    min="1"
                    value={newBooking.quantity}
                    onChange={(e) => setNewBooking({ ...newBooking, quantity: parseInt(e.target.value, 10) || 1 })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="font-bold text-slate-700">Ready Day</label>
                  <input
                    type="number"
                    min="0"
                    max="40"
                    value={newBooking.cargo_ready_day}
                    onChange={(e) => setNewBooking({ ...newBooking, cargo_ready_day: parseInt(e.target.value, 10) || 0 })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  />
                </div>
                <div>
                  <label className="font-bold text-slate-700">Cutoff Day</label>
                  <input
                    type="number"
                    min="0"
                    max="40"
                    value={newBooking.cutoff_day}
                    onChange={(e) => setNewBooking({ ...newBooking, cutoff_day: parseInt(e.target.value, 10) || 0 })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  />
                </div>
                <div>
                  <label className="font-bold text-slate-700">Deadline</label>
                  <input
                    type="number"
                    min="0"
                    max="50"
                    value={newBooking.delivery_deadline_day}
                    onChange={(e) => setNewBooking({ ...newBooking, delivery_deadline_day: parseInt(e.target.value, 10) || 0 })}
                    className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                  />
                </div>
              </div>

              <div>
                <label className="font-bold text-slate-700">Priority Tier</label>
                <select
                  value={newBooking.priority}
                  onChange={(e) => setNewBooking({ ...newBooking, priority: e.target.value })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                >
                  <option value="CRITICAL">Critical (High Shortage Penalty)</option>
                  <option value="HIGH">High</option>
                  <option value="NORMAL">Normal</option>
                  <option value="LOW">Low</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setShowAddBookingModal(false)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold"
              >
                Cancel
              </button>
              <button
                onClick={handleAddBooking}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-xs"
              >
                Save & Solve
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: REASSIGN VESSEL */}
      {/* ========================================================================= */}
      {showReassignVesselModal && (
        <div className="fixed inset-0 bg-slate-950/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-200 space-y-4">
            <h3 className="text-sm font-black text-slate-900">🚢 Reassign Vessel to Voyage</h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="font-bold text-slate-700">Select Voyage</label>
                <select
                  value={reassignForm.voyage_number}
                  onChange={(e) => setReassignForm({ ...reassignForm, voyage_number: e.target.value })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg font-mono"
                >
                  {voyagesList.map((v) => (
                    <option key={v.voyage_id} value={v.voyage_number}>
                      {v.voyage_number} ({v.service_name})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-bold text-slate-700">Assign Vessel</label>
                <select
                  value={reassignForm.vessel_name}
                  onChange={(e) => setReassignForm({ ...reassignForm, vessel_name: e.target.value })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg font-mono"
                >
                  <option value="MV Pacific Trader">MV Pacific Trader (1,200 TEU / 18,000 MT)</option>
                  <option value="MV Eastern Pioneer">MV Eastern Pioneer (1,500 TEU / 22,500 MT)</option>
                </select>
              </div>

              <div>
                <label className="font-bold text-slate-700">Assignment Horizon Status</label>
                <select
                  value={reassignForm.vessel_assignment_status}
                  onChange={(e) => setReassignForm({ ...reassignForm, vessel_assignment_status: e.target.value })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg font-mono"
                >
                  <option value="FIRM">FIRM (Near-Term Committed)</option>
                  <option value="PROVISIONAL">PROVISIONAL (Far-Term Adjustable)</option>
                  <option value="UNASSIGNED">UNASSIGNED</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setShowReassignVesselModal(false)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold"
              >
                Cancel
              </button>
              <button
                onClick={handleReassignVessel}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-xs"
              >
                Update Assignment
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: ADJUST DEPOT INVENTORY */}
      {/* ========================================================================= */}
      {showAdjustInventoryModal && (
        <div className="fixed inset-0 bg-slate-950/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-200 space-y-4">
            <h3 className="text-sm font-black text-slate-900">📦 Adjust Port Depot Inventory</h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="font-bold text-slate-700">Select Port</label>
                <select
                  value={adjustInvForm.port_unlocode}
                  onChange={(e) => setAdjustInvForm({ ...adjustInvForm, port_unlocode: e.target.value })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                >
                  <option value="CNSHA">Shanghai (CNSHA)</option>
                  <option value="SGSIN">Singapore (SGSIN)</option>
                  <option value="INMAA">Chennai (INMAA)</option>
                  <option value="AEDXB">Dubai (AEDXB)</option>
                </select>
              </div>

              <div>
                <label className="font-bold text-slate-700">Container Type</label>
                <select
                  value={adjustInvForm.container_type}
                  onChange={(e) => setAdjustInvForm({ ...adjustInvForm, container_type: e.target.value })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg"
                >
                  <option value="20FT_DRY">20ft Dry</option>
                  <option value="40FT_DRY">40ft Dry</option>
                  <option value="40FT_HIGH_CUBE">40ft High Cube</option>
                </select>
              </div>

              <div>
                <label className="font-bold text-slate-700">Quantity Change</label>
                <input
                  type="number"
                  value={adjustInvForm.quantity_change}
                  onChange={(e) => setAdjustInvForm({ ...adjustInvForm, quantity_change: parseInt(e.target.value, 10) || 0 })}
                  className="w-full mt-1 p-2 bg-slate-50 border border-slate-200 rounded-lg font-mono"
                  placeholder="+20 to add, -20 to remove"
                />
                <span className="text-[10px] text-slate-500">Positive number to add, negative number to remove units.</span>
              </div>
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setShowAdjustInventoryModal(false)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold"
              >
                Cancel
              </button>
              <button
                onClick={handleAdjustInventory}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-xs font-bold shadow-xs"
              >
                Apply & Solve
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
