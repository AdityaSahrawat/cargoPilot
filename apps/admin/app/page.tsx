"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";

const API_BASE = "http://localhost:8000/api/v1";

type ActiveTab = "OVERVIEW" | "FLEET_OPERATIONS" | "EQUIPMENT_INVENTORY" | "USER_MANAGEMENT";
type EnvironmentMode = "TEST_LAB" | "PRODUCTION";

export default function AdminHomePage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("OVERVIEW");
  const [envMode, setEnvMode] = useState<EnvironmentMode>("PRODUCTION");
  const [loading, setLoading] = useState<boolean>(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [summaryData, setSummaryData] = useState<any>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/simulation/world-1/summary`);
      if (!res.ok) throw new Error("API disconnected");
      const data = await res.json();
      setSummaryData(data);
      setApiError(null);
    } catch (err: any) {
      setApiError("Backend API unreachable on localhost:8000. Ensure 'uv run main.py' is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased">
      {/* Top Header & Global App Navigation */}
      <header className="border-b border-slate-200 bg-white/95 backdrop-blur-md sticky top-0 z-50 px-6 py-3 shadow-xs">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          
          {/* Logo & Brand */}
          <div className="flex items-center space-x-3">
            <Link
              href="/"
              className="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center text-white font-black text-lg shadow-md shadow-indigo-500/20"
            >
              🚢
            </Link>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-base font-bold tracking-tight text-slate-900">CargoPilot</span>
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                  Enterprise Platform
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                Container Logistics Optimization & Simulation Command Center
              </p>
            </div>
          </div>

          {/* Navigation Bar Tabs */}
          <nav className="hidden md:flex items-center space-x-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600">
            <button
              onClick={() => setActiveTab("OVERVIEW")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === "OVERVIEW"
                  ? "bg-white text-indigo-700 shadow-xs font-bold"
                  : "hover:text-slate-900"
              }`}
            >
              📊 Executive Overview
            </button>
            <Link
              href="/test"
              className="px-3 py-1.5 rounded-lg transition-all hover:text-slate-900 hover:bg-white/60"
            >
              🧪 Test Worlds Hub
            </Link>
            <Link
              href="/test/world1"
              className="px-3 py-1.5 rounded-lg transition-all text-indigo-600 font-bold bg-indigo-50/70 border border-indigo-200/50 hover:bg-indigo-100/70"
            >
              🕹️ World 1 Lab
            </Link>
            <Link
              href="/test/world2"
              className="px-3 py-1.5 rounded-lg transition-all text-violet-700 font-bold bg-violet-50/70 border border-violet-200/50 hover:bg-violet-100/70"
            >
              🌐 World 2 Lab
            </Link>
            <button
              onClick={() => setActiveTab("FLEET_OPERATIONS")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === "FLEET_OPERATIONS"
                  ? "bg-white text-indigo-700 shadow-xs font-bold"
                  : "hover:text-slate-900"
              }`}
            >
              🚢 Fleet & Network
            </button>
            <button
              onClick={() => setActiveTab("EQUIPMENT_INVENTORY")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === "EQUIPMENT_INVENTORY"
                  ? "bg-white text-indigo-700 shadow-xs font-bold"
                  : "hover:text-slate-900"
              }`}
            >
              📦 Inventory Barometer
            </button>
            <button
              onClick={() => setActiveTab("USER_MANAGEMENT")}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === "USER_MANAGEMENT"
                  ? "bg-white text-indigo-700 shadow-xs font-bold"
                  : "hover:text-slate-900"
              }`}
            >
              👥 Team & Access
            </button>
          </nav>

          {/* Environment & Status Indicator */}
          <div className="flex items-center space-x-3">
            <div className="flex bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-[11px] font-medium">
              <button
                onClick={() => setEnvMode("TEST_LAB")}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  envMode === "TEST_LAB"
                    ? "bg-amber-500 text-white font-bold shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                🧪 Test Lab
              </button>
              <button
                onClick={() => setEnvMode("PRODUCTION")}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  envMode === "PRODUCTION"
                    ? "bg-emerald-600 text-white font-bold shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                🟢 Production
              </button>
            </div>

            <div className="flex items-center space-x-1.5 text-xs bg-slate-50 px-2.5 py-1 rounded-lg border border-slate-200">
              <span className={`h-2 w-2 rounded-full ${apiError ? "bg-rose-500" : "bg-emerald-500 animate-pulse"}`} />
              <span className="font-mono text-[11px] text-slate-700">
                {apiError ? "API Offline" : "HiGHS / CBC Active"}
              </span>
            </div>
          </div>

        </div>
      </header>

      {/* Main Container Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        
        {/* Error Alert */}
        {apiError && (
          <div className="bg-rose-50 border border-rose-200 p-4 rounded-xl text-rose-800 text-xs flex items-center justify-between shadow-xs">
            <div>
              <span className="font-bold">⚠️ Connection Notice: </span>
              <span>{apiError}</span>
            </div>
            <button
              onClick={fetchSummary}
              className="bg-rose-700 hover:bg-rose-800 text-white px-3 py-1 rounded-lg font-semibold text-xs shadow-xs"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 1: EXECUTIVE OVERVIEW                                                 */}
        {/* ========================================================================= */}
        {activeTab === "OVERVIEW" && (
          <div className="space-y-6">
            
            {/* Top KPI Ribbon */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                <div className="flex justify-between items-center text-slate-500 text-xs">
                  <span>Global Fleet Capacity</span>
                  <span className="text-indigo-600 font-bold">🚢 Active</span>
                </div>
                <div className="text-2xl font-bold text-slate-900 mt-1 font-mono">2,700 TEU</div>
                <div className="text-[11px] text-slate-500 mt-1 flex justify-between">
                  <span>2 Vessels in Rotation</span>
                  <span className="text-emerald-600 font-semibold">100% On-Schedule</span>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                <div className="flex justify-between items-center text-slate-500 text-xs">
                  <span>Port Network Coverage</span>
                  <span className="text-cyan-600 font-bold">🗺️ Hubs</span>
                </div>
                <div className="text-2xl font-bold text-slate-900 mt-1 font-mono">4 Strategic Ports</div>
                <div className="text-[11px] text-slate-500 mt-1 flex justify-between">
                  <span>Shanghai, Singapore, Chennai, Dubai</span>
                  <span className="text-indigo-600 font-semibold">13,500 TEU Cap</span>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                <div className="flex justify-between items-center text-slate-500 text-xs">
                  <span>Booking Commitments</span>
                  <span className="text-emerald-600 font-bold">📋 Bookings</span>
                </div>
                <div className="text-2xl font-bold text-slate-900 mt-1 font-mono">8 Confirmed</div>
                <div className="text-[11px] text-slate-500 mt-1 flex justify-between">
                  <span>300 TEU Volume Demand</span>
                  <span className="text-emerald-600 font-semibold">0% Shortage Rate</span>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                <div className="flex justify-between items-center text-slate-500 text-xs">
                  <span>Mathematical Optimality</span>
                  <span className="text-amber-600 font-bold">⚡ HiGHS / CBC</span>
                </div>
                <div className="text-2xl font-bold text-emerald-600 mt-1 font-mono">0.0% Gap</div>
                <div className="text-[11px] text-slate-500 mt-1 flex justify-between">
                  <span>Coupled Master MILP</span>
                  <span className="text-slate-600 font-mono font-semibold">$30.3k Plan Cost</span>
                </div>
              </div>
            </div>

            {/* Test Worlds Directory & Live Simulation Monitor */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* Test Worlds Hub Quick Card */}
              <div className="lg:col-span-8 bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">🧪 Progressive Test Worlds Catalog</h2>
                    <p className="text-xs text-slate-500">
                      Isolated testing environments to mathematically prove and stress-test logistics algorithms.
                    </p>
                  </div>
                  <Link
                    href="/test"
                    className="text-xs text-indigo-600 hover:text-indigo-700 font-bold flex items-center space-x-1"
                  >
                    <span>View All Worlds ➔</span>
                  </Link>
                </div>

                <div className="space-y-3">
                  {/* World 1 Card */}
                  <div className="border border-indigo-100 bg-indigo-50/40 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-sm text-slate-900">World 1 — Mathematical Validation Benchmark</span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          🟢 Active & Verified
                        </span>
                      </div>
                      <p className="text-xs text-slate-600">
                        4 Ports (CNSHA, SGSIN, INMAA, AEDXB) • 6 Scheduled Voyages (18 Legs) • 3 Container Types • 8 Bookings • 40-Day Rolling Simulation
                      </p>
                      <div className="flex items-center space-x-4 text-[11px] font-mono text-slate-500 pt-1">
                        <span>Horizon: <strong className="text-slate-800">40 Days</strong></span>
                        <span>Optimality Gap: <strong className="text-emerald-700">0.0%</strong></span>
                        <span>Shortage Penalty: <strong className="text-emerald-700">$0</strong></span>
                      </div>
                    </div>

                    <Link
                      href="/test/world1"
                      className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs py-2 px-4 rounded-xl shadow-xs transition-all whitespace-nowrap text-center block"
                    >
                      🕹️ Launch World 1 Lab Workbench
                    </Link>
                  </div>

                  {/* World 2 Card (Planned) */}
                  <div className="border border-slate-200 bg-white rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-sm text-slate-800">World 2 — Regional Feeder & Transshipment Mesh</span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                          🟡 Configured
                        </span>
                      </div>
                      <p className="text-xs text-slate-500">
                        15 Ports across Asia-Pacific • 24 Voyages • 120 Multi-Tier Bookings • 60-Day Horizon with Rail/Barge Intermodal
                      </p>
                    </div>
                    <button
                      disabled
                      className="bg-slate-100 text-slate-400 font-semibold text-xs py-2 px-4 rounded-xl cursor-not-allowed border border-slate-200"
                    >
                      Configure Simulation
                    </button>
                  </div>

                  {/* World 3 Card (Roadmap) */}
                  <div className="border border-slate-200 bg-slate-50/60 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-sm text-slate-700">World 3 — Global Industry-Scale Hub-and-Spoke Grid</span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                          ⚪ Roadmap Scale
                        </span>
                      </div>
                      <p className="text-xs text-slate-500">
                        50 Global Ports • 110 Voyages • 800 Multi-Commodity Bookings • 90-Day Rolling Simulation
                      </p>
                    </div>
                    <span className="text-xs text-slate-400 font-mono">Phase 2 Target</span>
                  </div>
                </div>
              </div>

              {/* Live Simulation Feed & Alert Ticker */}
              <div className="lg:col-span-4 bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <h3 className="text-sm font-bold text-slate-900">📡 System Health & Engine Status</h3>
                    <span className="text-[10px] font-mono bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full border border-emerald-200">
                      Normal
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mb-3">
                    FastAPI solver engine active on localhost:8000 with HiGHS & Coin-OR CBC solvers loaded.
                  </p>

                  <div className="space-y-2 text-xs font-mono">
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-slate-700">
                      ✓ Master MILP Mathematical Model: <strong>Coupled</strong>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-slate-700">
                      ✓ Time-Expanded Network: <strong>18 Legs / 40 Days</strong>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-slate-700">
                      ✓ Inventory Balance Continuity: <strong>Strict 0-Tolerance</strong>
                    </div>
                  </div>
                </div>

                <Link
                  href="/test/world1"
                  className="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs py-2.5 px-4 rounded-xl shadow-xs transition-all text-center block"
                >
                  Open World 1 Simulation Scrubber ➔
                </Link>
              </div>

            </div>

            {/* Production Operations & Fleet Intelligence Quick Links */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              
              <div
                onClick={() => setActiveTab("FLEET_OPERATIONS")}
                className="bg-white border border-slate-200 hover:border-indigo-300 p-5 rounded-2xl shadow-xs hover:shadow-md transition-all cursor-pointer space-y-2"
              >
                <div className="text-xl">🚢</div>
                <div className="font-bold text-sm text-slate-900">Fleet & Vessel Allocations</div>
                <p className="text-xs text-slate-500">
                  Inspect vessel rotations, deadweight utilization, TEU slot constraints, and voyage schedules.
                </p>
                <div className="text-xs font-semibold text-indigo-600 pt-1">Explore Fleet Operations ➔</div>
              </div>

              <div
                onClick={() => setActiveTab("EQUIPMENT_INVENTORY")}
                className="bg-white border border-slate-200 hover:border-indigo-300 p-5 rounded-2xl shadow-xs hover:shadow-md transition-all cursor-pointer space-y-2"
              >
                <div className="text-xl">📦</div>
                <div className="font-bold text-sm text-slate-900">Equipment & Depot Barometers</div>
                <p className="text-xs text-slate-500">
                  Track empty container stock, safety stock thresholds, devanning queues, and regional deficits.
                </p>
                <div className="text-xs font-semibold text-indigo-600 pt-1">View Inventory Levels ➔</div>
              </div>

              <div
                onClick={() => setActiveTab("USER_MANAGEMENT")}
                className="bg-white border border-slate-200 hover:border-indigo-300 p-5 rounded-2xl shadow-xs hover:shadow-md transition-all cursor-pointer space-y-2"
              >
                <div className="text-xl">👥</div>
                <div className="font-bold text-sm text-slate-900">User Access & Audit Logs</div>
                <p className="text-xs text-slate-500">
                  Manage team roles (Planners, Port Ops, Alliance Partners) and review verified optimization audit logs.
                </p>
                <div className="text-xs font-semibold text-indigo-600 pt-1">Manage Permissions ➔</div>
              </div>

            </div>

          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: FLEET & NETWORK OPERATIONS                                        */}
        {/* ========================================================================= */}
        {activeTab === "FLEET_OPERATIONS" && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs flex justify-between items-center">
              <div>
                <h2 className="text-lg font-bold text-slate-900">🚢 Global Fleet & Voyage Operations</h2>
                <p className="text-xs text-slate-500 mt-1">
                  Monitor vessel deadweight utilization, TEU container capacity, and scheduled rotation loops.
                </p>
              </div>
              <Link
                href="/test/world1"
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs py-2 px-4 rounded-xl shadow-xs transition-all"
              >
                Simulate Fleet in World 1 ➔
              </Link>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-bold text-base text-slate-900">MV Pacific Trader</h3>
                    <span className="text-xs text-slate-500 font-mono">IMO: 9812345 • Container Vessel</span>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Active Rotation
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <div className="text-slate-500">Container Capacity</div>
                    <div className="text-base font-bold text-slate-900 mt-1">1,200 TEU</div>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <div className="text-slate-500">Deadweight Capacity</div>
                    <div className="text-base font-bold text-slate-900 mt-1">18,000 MT</div>
                  </div>
                </div>
                <div className="text-xs text-slate-600">
                  <strong>Assigned Rotations:</strong> Loop A (VOY_A1, VOY_A3) and Loop B (VOY_B2)
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-bold text-base text-slate-900">MV Eastern Pioneer</h3>
                    <span className="text-xs text-slate-500 font-mono">IMO: 9823456 • Container Vessel</span>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Active Rotation
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <div className="text-slate-500">Container Capacity</div>
                    <div className="text-base font-bold text-slate-900 mt-1">1,500 TEU</div>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-200">
                    <div className="text-slate-500">Deadweight Capacity</div>
                    <div className="text-base font-bold text-slate-900 mt-1">22,500 MT</div>
                  </div>
                </div>
                <div className="text-xs text-slate-600">
                  <strong>Assigned Rotations:</strong> Loop B (VOY_B1, VOY_B3) and Loop A (VOY_A2)
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: EQUIPMENT & INVENTORY BAROMETER                                    */}
        {/* ========================================================================= */}
        {activeTab === "EQUIPMENT_INVENTORY" && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs flex justify-between items-center">
              <div>
                <h2 className="text-lg font-bold text-slate-900">📦 Container Equipment & Multi-Depot Barometers</h2>
                <p className="text-xs text-slate-500 mt-1">
                  Regional empty container balance, turn-around devanning flows, and short-term leasing buffers.
                </p>
              </div>
              <Link
                href="/test/world1"
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs py-2 px-4 rounded-xl shadow-xs transition-all"
              >
                Inspect Live Barometers in World 1 ➔
              </Link>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3">
                <h3 className="font-bold text-sm text-slate-900">🇨🇳 Port of Shanghai (CNSHA)</h3>
                <p className="text-xs text-slate-500">Major Origin Hub with High Export Surplus</p>
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs font-mono space-y-1">
                  <div className="flex justify-between"><span>Initial Stock:</span><strong>310 Units (500 TEU)</strong></div>
                  <div className="flex justify-between"><span>Safety Stock Target:</span><strong>20 TEU</strong></div>
                  <div className="flex justify-between"><span>Turnaround Lead Time:</span><strong>2 Days</strong></div>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3">
                <h3 className="font-bold text-sm text-slate-900">🇸🇬 Port of Singapore (SGSIN)</h3>
                <p className="text-xs text-slate-500">Strategic Transshipment & Hub Hub</p>
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs font-mono space-y-1">
                  <div className="flex justify-between"><span>Initial Stock:</span><strong>95 Units (150 TEU)</strong></div>
                  <div className="flex justify-between"><span>Safety Stock Target:</span><strong>15 TEU</strong></div>
                  <div className="flex justify-between"><span>Turnaround Lead Time:</span><strong>2 Days</strong></div>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3">
                <h3 className="font-bold text-sm text-slate-900">🇮🇳 Port of Chennai (INMAA)</h3>
                <p className="text-xs text-slate-500">Regional Gateway Port with Balanced Import Flows</p>
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs font-mono space-y-1">
                  <div className="flex justify-between"><span>Initial Stock:</span><strong>35 Units (55 TEU)</strong></div>
                  <div className="flex justify-between"><span>Safety Stock Target:</span><strong>10 TEU</strong></div>
                  <div className="flex justify-between"><span>Turnaround Lead Time:</span><strong>2 Days</strong></div>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3">
                <h3 className="font-bold text-sm text-slate-900">🇦🇪 Port of Jebel Ali, Dubai (AEDXB)</h3>
                <p className="text-xs text-slate-500">High Inbound Consumption with Repositioning Requirements</p>
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs font-mono space-y-1">
                  <div className="flex justify-between"><span>Initial Stock:</span><strong>50 Units (80 TEU)</strong></div>
                  <div className="flex justify-between"><span>Safety Stock Target:</span><strong>10 TEU</strong></div>
                  <div className="flex justify-between"><span>Turnaround Lead Time:</span><strong>2 Days</strong></div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: USER & ACCESS MANAGEMENT                                          */}
        {/* ========================================================================= */}
        {activeTab === "USER_MANAGEMENT" && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs flex justify-between items-center">
              <div>
                <h2 className="text-lg font-bold text-slate-900">👥 Team, Access Control & Audit Log</h2>
                <p className="text-xs text-slate-500 mt-1">
                  Manage operational role permissions and inspect enterprise audit logs.
                </p>
              </div>
              <button className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs py-2 px-4 rounded-xl shadow-xs transition-all">
                + Invite User
              </button>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
              <h3 className="text-sm font-bold text-slate-900">Active Team Members</h3>
              <div className="divide-y divide-slate-100 text-xs">
                {[
                  { name: "Aditya Sahrawat", email: "aditya@cargopilot.io", role: "Super Administrator", status: "Active" },
                  { name: "Operations Lead (Asia-Pacific)", email: "ops.apac@cargopilot.io", role: "Logistics Planner", status: "Active" },
                  { name: "Equipment Controller (Middle East)", email: "depot.dxb@cargopilot.io", role: "Depot Manager", status: "Active" },
                  { name: "Alliance Slot Auditor", email: "alliance@cargopilot.io", role: "Auditor (Read-Only)", status: "Active" },
                ].map((user) => (
                  <div key={user.email} className="py-3 flex justify-between items-center">
                    <div>
                      <div className="font-bold text-slate-900">{user.name}</div>
                      <div className="text-slate-500 text-[11px]">{user.email}</div>
                    </div>
                    <div className="flex items-center space-x-3">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[11px] font-semibold border border-slate-200">
                        {user.role}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200">
                        {user.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
