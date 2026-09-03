"use client";

import React from "react";
import Link from "next/link";

export default function TestWorldsHubPage() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased">
      {/* Top Header */}
      <header className="border-b border-slate-200 bg-white/95 backdrop-blur-md sticky top-0 z-50 px-6 py-3 shadow-xs">
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
                <span className="text-sm font-bold text-indigo-600">Test Worlds Hub</span>
              </div>
              <p className="text-[11px] text-slate-500">
                Multi-tier Progressive Test Worlds & Mathematical Benchmarks Catalog
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <Link
              href="/"
              className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-3.5 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold transition-all flex items-center space-x-1"
            >
              <span>← Command Center</span>
            </Link>
            <Link
              href="/test/world1"
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs flex items-center space-x-1.5"
            >
              <span>🕹️ Open World 1 Workbench</span>
            </Link>
          </div>

        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        
        {/* Banner */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
          <h1 className="text-xl font-bold text-slate-900">🧪 Progressive Test Worlds Catalog</h1>
          <p className="text-xs text-slate-500 mt-1 max-w-3xl leading-relaxed">
            CargoPilot uses isolated synthetic test environments to mathematically validate our master MILP solver, time-expanded space-time networks, and 40-day rolling horizon simulations before enterprise fleet deployment.
          </p>
        </div>

        {/* Worlds Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* World 1 Card */}
          <div className="bg-white border-2 border-indigo-600 rounded-2xl p-6 shadow-md space-y-4 relative flex flex-col justify-between">
            <div className="space-y-4">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-base font-bold text-slate-900">World 1: 4-Port Mathematical Benchmark</h2>
                  <div className="text-xs text-indigo-600 font-semibold">Mathematical Validation & 40-Day Simulator</div>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  🟢 Active & Verified
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                The canonical 4-port liner network used to mathematically validate exact capacity coupling, multi-period daily inventory conservation, turnaround devanning flows, and priority tiers.
              </p>

              <ul className="text-xs text-slate-600 space-y-2 border-t border-slate-100 pt-3">
                <li>• <strong>4 Ports:</strong> Shanghai, Singapore, Chennai, Dubai</li>
                <li>• <strong>6 Scheduled Voyages:</strong> 18 Legs (2 Recurring Loops)</li>
                <li>• <strong>3 Container Types:</strong> 20DC, 40DC, 40HC</li>
                <li>• <strong>8 Multi-Tier Bookings:</strong> Critical, High, Normal, Low</li>
                <li>• <strong>40-Day Horizon:</strong> Day-by-Day Progression ($D_0 \to D_{40}$)</li>
                <li>• <strong>HiGHS Optimality:</strong> Proven Global Optimum (0.0% Gap)</li>
              </ul>
            </div>

            <Link
              href="/test/world1"
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs py-2.5 px-4 rounded-xl shadow-xs transition-all text-center block mt-4"
            >
              🕹️ Launch World 1 Lab Workbench
            </Link>
          </div>

          {/* World 2 Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4 flex flex-col justify-between">
            <div className="space-y-4">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-base font-bold text-slate-900">World 2: 15-Port Regional Mesh</h2>
                  <div className="text-xs text-slate-500 font-semibold">Transshipment Hubs & Feeders</div>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                  🟡 Configured
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Regional feeder and transshipment network testing hub connections, intermodal rail transfers, and multi-vessel slot swaps.
              </p>

              <ul className="text-xs text-slate-600 space-y-2 border-t border-slate-100 pt-3">
                <li>• <strong>15 Ports:</strong> Asia-Pacific Main Ports + Inland Depots</li>
                <li>• <strong>24 Scheduled Voyages:</strong> Feeder & Mainline Loops</li>
                <li>• <strong>120 Bookings:</strong> Multi-Commodity Demands</li>
                <li>• <strong>60-Day Horizon:</strong> Rolling lookahead evaluation</li>
              </ul>
            </div>

            <button
              disabled
              className="w-full bg-slate-100 text-slate-400 font-semibold text-xs py-2.5 px-4 rounded-xl border border-slate-200 cursor-not-allowed text-center block mt-4"
            >
              Configure & Seed World 2
            </button>
          </div>

          {/* World 3 Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4 flex flex-col justify-between">
            <div className="space-y-4">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-base font-bold text-slate-900">World 3: 50-Port Global Grid</h2>
                  <div className="text-xs text-slate-500 font-semibold">Enterprise Production Scale</div>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                  ⚪ Roadmap
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Global industry-scale benchmark across East Asia, Middle East, Europe, and Americas evaluating multi-carrier alliance slot sharing.
              </p>

              <ul className="text-xs text-slate-600 space-y-2 border-t border-slate-100 pt-3">
                <li>• <strong>50 Global Ports:</strong> Worldwide container terminals</li>
                <li>• <strong>110 Voyages:</strong> Alliance rotations</li>
                <li>• <strong>800 Bookings:</strong> High-frequency demand</li>
                <li>• <strong>90-Day Horizon:</strong> Enterprise stress test</li>
              </ul>
            </div>

            <button
              disabled
              className="w-full bg-slate-100 text-slate-400 font-semibold text-xs py-2.5 px-4 rounded-xl border border-slate-200 cursor-not-allowed text-center block mt-4"
            >
              Phase 2 Scale Target
            </button>
          </div>

        </div>

      </main>
    </div>
  );
}
