"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import type LType from "leaflet";
import "leaflet/dist/leaflet.css";

const SIM_API = "http://localhost:8001/api/v1/simulation";
const REFRESH_MS = 6000;

interface SimStatus {
  status: string;
  simulation_time: string | null;
  run_id: string | null;
  world_id: string | null;
}

interface SimState {
  run_id: string;
  world_id: string;
  simulation_time: string;
  vessels_count: number;
  ports_count: number;
  voyages_count: number;
  containers_count: number;
  bookings_count: number;
  leases_count: number;
  equipment_balances_count: number;
  demand_forecast_count: number;
  active_disruptions_count: number;
  kpis: {
    total_cost: number;
    vessels_delayed: number;
    delay_hours: number;
    equipment_shortages: number;
  };
}

interface Port {
  port_id: string;
  unlocode: string;
  name: string;
  latitude: number;
  longitude: number;
  berths_total: number;
  berths_occupied: number;
  berths_available: number;
  vessel_queue_count: number;
  vessel_queue: string[];
  congestion_index: number;
  is_strike_active: boolean;
  is_closed: boolean;
}

interface Vessel {
  vessel_id: string;
  name: string;
  status: string;
  current_voyage_id: string | null;
  current_port_id: string | null;
  origin_port_id: string | null;
  destination_port_id: string | null;
  position_fraction: number;
  distance_remaining_nm: number;
  current_speed_knots: number;
  eta: string | null;
  schedule_variance_hours: number;
  condition: string;
}

interface Voyage {
  voyage_id: string;
  vessel_id: string;
  origin_port_id: string;
  destination_port_id: string;
  scheduled_departure: string | null;
  scheduled_arrival: string | null;
  actual_departure: string | null;
  estimated_arrival: string | null;
  actual_arrival: string | null;
  status: string;
  route_distance_nm: number;
  capacity_teu: number;
  booked_teu: number;
}

interface Container {
  container_id: string;
  equipment_type: string;
  status: string;
  condition: string;
  location_id: string | null;
  voyage_id: string | null;
  booking_id: string | null;
}

interface Booking {
  booking_id: string;
  origin_port_id: string;
  destination_port_id: string;
  equipment_type: string;
  quantity: number;
  status: string;
  lock_status: string;
  cutoff_time: string | null;
}

interface Disruption {
  disruption_id: string;
  disruption_type: string;
  status: string;
  severity: number;
  start_time: string | null;
  end_time: string | null;
  affected_entity_ids: string[] | null;
}

interface EquipmentBalance {
  location_id: string;
  equipment_type: string;
  available: number;
  allocated: number;
  in_transit: number;
  unavailable: number;
  target: number;
  total: number;
  shortage: number;
  surplus: number;
  deficit: number;
}

interface SimEvent {
  event_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  simulation_time: string;
  source: string;
  payload: Record<string, unknown>;
  caused_by_event_id: string | null;
}

interface Scenario {
  id: string;
  name: string;
  description: string;
}

type SelectedEntity = { type: "port"; data: Port } | { type: "vessel"; data: Vessel } | null;

function fmtSimTime(iso: string | null) {
  if (!iso) return { date: "—", time: "—", day: "—" };
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return { date, time, day: `Day ${Math.max(1, Math.floor((d.getTime() - new Date("2026-09-01").getTime()) / 86400000) + 1)}` };
}

function fmtNum(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(Math.round(n));
}

function fmtCurrency(n: number) {
  if (n >= 1_000_000) return "$" + (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return "$" + (n / 1_000).toFixed(0) + "k";
  return "$" + Math.round(n);
}

const EMPTY_STATUSES = new Set(["EMPTY_AVAILABLE", "EMPTY"]);

function DonutChart({ total, label, segments }: {
  total: number;
  label: string;
  segments: { value: number; color: string; name: string }[];
}) {
  const r = 44, cx = 60, cy = 60;
  const circumference = 2 * Math.PI * r;
  let cumulative = 0;
  const totalVal = segments.reduce((a, s) => a + s.value, 0) || 1;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <svg width={120} height={120} viewBox="0 0 120 120">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#F3F4F6" strokeWidth={14} />
        {segments.map((seg, i) => {
          const pct = seg.value / totalVal;
          const dashArray = pct * circumference;
          const offset = circumference - cumulative * circumference;
          cumulative += pct;
          return (
            <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={seg.color} strokeWidth={14}
              strokeDasharray={`${dashArray} ${circumference - dashArray}`}
              strokeDashoffset={offset} strokeLinecap="butt" transform="rotate(-90 60 60)" />
          );
        })}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize={15} fontWeight={700} fill="#111827">{fmtNum(total)}</text>
        <text x={cx} y={cy + 10} textAnchor="middle" fontSize={9} fill="#6B7280">{label}</text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, width: "100%" }}>
        {segments.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#374151" }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
            <span style={{ flex: 1 }}>{s.name}</span>
            <span style={{ fontWeight: 600 }}>{fmtNum(s.value)}</span>
            <span style={{ color: "#9CA3AF" }}>({Math.round((s.value / totalVal) * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BarChart({ data }: { data: { label: string; available: number; required: number }[] }) {
  const maxVal = Math.max(...data.flatMap((d) => [d.available, d.required]), 1);
  const chartH = 80;
  const barW = 18;
  const gap = 6;
  const groupW = barW * 2 + gap + 14;
  const totalW = data.length * groupW + 30;
  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={totalW} height={chartH + 44} viewBox={`0 0 ${totalW} ${chartH + 44}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
          const y = chartH - t * chartH + 10;
          const val = Math.round(t * maxVal);
          return (
            <g key={i}>
              <line x1={14} x2={totalW - 5} y1={y} y2={y} stroke="#F3F4F6" strokeWidth={1} />
              <text x={12} y={y + 3} textAnchor="end" fontSize={8} fill="#9CA3AF">
                {val >= 1000 ? (val / 1000).toFixed(0) + "k" : val}
              </text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const x = i * groupW + 22;
          const avH = (d.available / maxVal) * chartH;
          const reqH = (d.required / maxVal) * chartH;
          return (
            <g key={i}>
              <rect x={x} y={chartH - avH + 10} width={barW} height={avH} fill="#3B82F6" rx={2} />
              <rect x={x + barW + gap} y={chartH - reqH + 10} width={barW} height={reqH} fill="#F97316" rx={2} />
              <text x={x + barW + gap / 2} y={chartH + 22} textAnchor="middle" fontSize={9} fill="#374151">{d.label}</text>
            </g>
          );
        })}
        <rect x={18} y={chartH + 30} width={10} height={8} fill="#3B82F6" rx={1} />
        <text x={31} y={chartH + 38} fontSize={9} fill="#374151">Available</text>
        <rect x={80} y={chartH + 30} width={10} height={8} fill="#F97316" rx={1} />
        <text x={93} y={chartH + 38} fontSize={9} fill="#374151">Required</text>
      </svg>
    </div>
  );
}

function PortDetail({ port, vessels }: { port: Port; vessels: Vessel[] }) {
  const dockedVessels = vessels.filter((v) => v.current_port_id === port.port_id);
  const utilPct = port.berths_total > 0 ? Math.round((port.berths_occupied / port.berths_total) * 100) : 0;
  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>{port.name}</div>
          <div style={{ color: "#6B7280" }}>{port.unlocode}</div>
        </div>
        {port.congestion_index > 1.5 && (
          <span style={{ padding: "3px 8px", background: "#FEF2F2", color: "#DC2626", borderRadius: 10, fontSize: 11, fontWeight: 600 }}>
            {port.is_strike_active ? "Strike" : "Congested"}
          </span>
        )}
      </div>
      {[
        { label: "Congestion Index", value: port.congestion_index.toFixed(2), bar: true, val: Math.min(port.congestion_index / 3, 1), color: port.congestion_index > 2 ? "#EF4444" : port.congestion_index > 1.5 ? "#F97316" : "#10B981" },
        { label: "Waiting Vessels", value: String(port.vessel_queue_count), bar: false, val: 0, color: "" },
        { label: "Berths (Total / Free)", value: `${port.berths_total} / ${port.berths_available}`, bar: false, val: 0, color: "" },
        { label: "Yard Utilization", value: `${utilPct}%`, bar: true, val: utilPct / 100, color: utilPct > 80 ? "#EF4444" : utilPct > 60 ? "#F97316" : "#10B981" },
      ].map((row) => (
        <div key={row.label} style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: "#6B7280" }}>{row.label}</span>
            <span style={{ fontWeight: 600, color: "#111827" }}>{row.value}</span>
          </div>
          {row.bar && (
            <div style={{ height: 5, background: "#F3F4F6", borderRadius: 3 }}>
              <div style={{ width: `${row.val * 100}%`, height: "100%", background: row.color, borderRadius: 3 }} />
            </div>
          )}
        </div>
      ))}
      {dockedVessels.length > 0 && (
        <div>
          <div style={{ color: "#6B7280", marginBottom: 4 }}>Vessels at Dock ({dockedVessels.length})</div>
          {dockedVessels.slice(0, 3).map((v) => (
            <div key={v.vessel_id} style={{ padding: "4px 8px", background: "#F8FAFC", borderRadius: 5, marginBottom: 3, fontSize: 11 }}>
              {v.name} — <span style={{ color: "#6B7280" }}>{v.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function VesselDetail({ vessel: v, ports }: { vessel: Vessel; ports: Port[] }) {
  const portById = Object.fromEntries(ports.map((p) => [p.port_id, p]));
  const originPort = v.origin_port_id ? portById[v.origin_port_id] : null;
  const destPort = v.destination_port_id ? portById[v.destination_port_id] : null;
  const etaStr = v.eta ? new Date(v.eta).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
  const isDelayed = v.schedule_variance_hours > 2;
  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>{v.name}</div>
          <div style={{ color: "#6B7280" }}>{v.vessel_id.slice(-8)}</div>
        </div>
        <span style={{ padding: "3px 8px", borderRadius: 10, fontSize: 11, fontWeight: 600, background: isDelayed ? "#FFF7ED" : "#F0FDF4", color: isDelayed ? "#C2410C" : "#166534" }}>
          {isDelayed ? "Delayed" : v.status}
        </span>
      </div>
      {[
        { label: "Status", value: v.status, color: undefined },
        { label: "Voyage", value: v.current_voyage_id?.slice(-8) ?? "—", color: undefined },
        { label: "Origin", value: originPort?.name ?? "—", color: undefined },
        { label: "Destination", value: destPort?.name ?? "—", color: undefined },
        { label: "ETA", value: etaStr, color: undefined },
        { label: "Schedule Variance", value: `${v.schedule_variance_hours > 0 ? "+" : ""}${v.schedule_variance_hours.toFixed(1)}h`, color: isDelayed ? "#DC2626" : "#16A34A" },
        { label: "Speed", value: v.current_speed_knots ? `${v.current_speed_knots.toFixed(1)} kn` : "—", color: undefined },
        { label: "Distance Left", value: v.distance_remaining_nm ? `${Math.round(v.distance_remaining_nm).toLocaleString()} nm` : "—", color: undefined },
        { label: "Condition", value: v.condition, color: undefined },
      ].map((row) => (
        <div key={row.label} style={{ display: "flex", justifyContent: "space-between", marginBottom: 7, paddingBottom: 7, borderBottom: "1px solid #F9FAFB" }}>
          <span style={{ color: "#6B7280" }}>{row.label}</span>
          <span style={{ fontWeight: 600, color: row.color ?? "#111827" }}>{row.value}</span>
        </div>
      ))}
      {v.position_fraction != null && (
        <div style={{ marginTop: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: "#6B7280" }}>Voyage Progress</span>
            <span style={{ fontWeight: 600, color: "#111827" }}>{Math.round((v.position_fraction ?? 0) * 100)}%</span>
          </div>
          <div style={{ height: 6, background: "#F3F4F6", borderRadius: 3 }}>
            <div style={{ width: `${(v.position_fraction ?? 0) * 100}%`, height: "100%", background: "#2563EB", borderRadius: 3 }} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function SimulationWorld1Page() {
  const [simStatus, setSimStatus] = useState<SimStatus | null>(null);
  const [simState, setSimState] = useState<SimState | null>(null);
  const [ports, setPorts] = useState<Port[]>([]);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [voyages, setVoyages] = useState<Voyage[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [disruptions, setDisruptions] = useState<Disruption[]>([]);
  const [equipment, setEquipment] = useState<EquipmentBalance[]>([]);
  const [events, setEvents] = useState<SimEvent[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("NORMAL");
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntity>(null);
  const [entityTab, setEntityTab] = useState<"port" | "vessel" | "container">("port");
  const [activeTab, setActiveTab] = useState("overview");
  const [simNote, setSimNote] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [disruptionType, setDisruptionType] = useState("STORM");
  const [showDisruptionModal, setShowDisruptionModal] = useState(false);
  const [disruptionSeverity, setDisruptionSeverity] = useState(0.5);
  const [disruptionDuration, setDisruptionDuration] = useState(24);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mapReady, setMapReady] = useState(false);

  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<LType.Map | null>(null);
  const portMarkersRef = useRef<LType.CircleMarker[]>([]);
  const vesselMarkersRef = useRef<LType.Marker[]>([]);
  const routeLinesRef = useRef<LType.Polyline[]>([]);

  const fetchAll = useCallback(async () => {
    try {
      const [s1, s2, s3, s4] = await Promise.all([
        fetch(`${SIM_API}/status`),
        fetch(`${SIM_API}/state`),
        fetch(`${SIM_API}/state/ports`),
        fetch(`${SIM_API}/state/vessels`),
      ]);
      if (s1.ok) setSimStatus(await s1.json());
      if (s2.ok) setSimState(await s2.json());
      if (s3.ok) setPorts(await s3.json());
      if (s4.ok) setVessels(await s4.json());
    } catch { /* server not ready */ }
  }, []);

  const fetchSecondary = useCallback(async () => {
    try {
      const [r1, r2, r3, r4, r5, r6] = await Promise.all([
        fetch(`${SIM_API}/state/voyages`),
        fetch(`${SIM_API}/state/containers?limit=500`),
        fetch(`${SIM_API}/state/bookings`),
        fetch(`${SIM_API}/state/disruptions`),
        fetch(`${SIM_API}/state/equipment`),
        fetch(`${SIM_API}/state/events`),
      ]);
      if (r1.ok) setVoyages(await r1.json());
      if (r2.ok) setContainers(await r2.json());
      if (r3.ok) setBookings(await r3.json());
      if (r4.ok) setDisruptions(await r4.json());
      if (r5.ok) setEquipment(await r5.json());
      if (r6.ok) setEvents(await r6.json());
    } catch { /* ok */ }
  }, []);

  useEffect(() => {
    fetchAll();
    fetchSecondary();
    fetch(`${SIM_API}/config/scenarios`).then((r) => { if (r.ok) r.json().then(setScenarios); }).catch(() => {});
    const id1 = setInterval(fetchAll, REFRESH_MS);
    const id2 = setInterval(fetchSecondary, REFRESH_MS * 3);
    return () => { clearInterval(id1); clearInterval(id2); };
  }, [fetchAll, fetchSecondary]);

  useEffect(() => {
    if (!mapRef.current) return;
    let isCancelled = false;

    import("leaflet").then((mod) => {
      if (isCancelled) return;
      if (!mapRef.current) return;

      // Clean up previous instance if already existing on this element
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }

      const container = mapRef.current;
      if ((container as unknown as { _leaflet_id?: number })._leaflet_id) {
        delete (container as unknown as { _leaflet_id?: number })._leaflet_id;
      }

      const L = mod.default;
      delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const map = L.map(container, { center: [20, 10], zoom: 2, zoomControl: true });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap",
        maxZoom: 18,
      }).addTo(map);

      leafletMap.current = map;
      setMapReady(true);
    });

    return () => {
      isCancelled = true;
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }
      if (mapRef.current && (mapRef.current as unknown as { _leaflet_id?: number })._leaflet_id) {
        delete (mapRef.current as unknown as { _leaflet_id?: number })._leaflet_id;
      }
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    if (!leafletMap.current || !mapReady) return;
    import("leaflet").then((mod) => {
      const L = mod.default;
      const map = leafletMap.current;
      if (!map) return;
      portMarkersRef.current.forEach((m) => m.remove());
      vesselMarkersRef.current.forEach((m) => m.remove());
      routeLinesRef.current.forEach((l) => l.remove());
      portMarkersRef.current = [];
      vesselMarkersRef.current = [];
      routeLinesRef.current = [];
      const portById: Record<string, Port> = {};
      ports.forEach((p) => { portById[p.port_id] = p; });

      vessels.forEach((v) => {
        if (v.origin_port_id && v.destination_port_id) {
          const o = portById[v.origin_port_id], d = portById[v.destination_port_id];
          if (o && d) {
            const line = L.polyline([[o.latitude, o.longitude], [d.latitude, d.longitude]],
              { color: "#94A3B8", weight: 1.2, dashArray: "6 4", opacity: 0.5 }).addTo(map);
            routeLinesRef.current.push(line);
          }
        }
      });

      ports.forEach((p) => {
        const color = p.is_strike_active ? "#7C3AED" : p.congestion_index > 1.5 ? "#EF4444" : "#2563EB";
        const m = L.circleMarker([p.latitude, p.longitude], { radius: 7, fillColor: color, color: "#fff", weight: 2, fillOpacity: 0.95 })
          .bindTooltip(p.name, { className: "cargo-tooltip" }).addTo(map);
        m.on("click", () => { setSelectedEntity({ type: "port", data: p }); setEntityTab("port"); });
        portMarkersRef.current.push(m);
      });

      vessels.forEach((v) => {
        let lat = 0, lng = 0;
        const inPort = v.current_port_id ? portById[v.current_port_id] : null;
        if (inPort) { lat = inPort.latitude + (Math.random() - 0.5) * 0.8; lng = inPort.longitude + (Math.random() - 0.5) * 0.8; }
        else if (v.origin_port_id && v.destination_port_id) {
          const o = portById[v.origin_port_id], d = portById[v.destination_port_id];
          if (o && d) { const f = v.position_fraction ?? 0.5; lat = o.latitude + (d.latitude - o.latitude) * f; lng = o.longitude + (d.longitude - o.longitude) * f; }
        }
        if (!lat && !lng) return;
        const isDelayed = v.schedule_variance_hours > 2;
        const isAtPort = ["IN_PORT", "ARRIVED", "WAITING_FOR_BERTH"].includes(v.status);
        const color = isDelayed ? "#F97316" : isAtPort ? "#10B981" : "#16A34A";
        const icon = L.divIcon({
          className: "",
          html: `<div style="width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-bottom:12px solid ${color};filter:drop-shadow(0 1px 2px rgba(0,0,0,0.3));"></div>`,
          iconSize: [12, 12], iconAnchor: [6, 6],
        });
        const m = L.marker([lat, lng], { icon }).bindTooltip(v.name, { className: "cargo-tooltip" }).addTo(map);
        m.on("click", () => { setSelectedEntity({ type: "vessel", data: v }); setEntityTab("vessel"); });
        vesselMarkersRef.current.push(m);
      });
    });
  }, [ports, vessels, mapReady]);

  const showMsg = (msg: string) => { setActionMsg(msg); setTimeout(() => setActionMsg(""), 3500); };

  const doControl = async (path: string, body?: object) => {
    try {
      const res = await fetch(`${SIM_API}/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      const data = await res.json();
      if (res.ok) { showMsg(data.message || "Done"); await fetchAll(); }
      else showMsg(`Error: ${data.detail ?? "Unknown"}`);
    } catch { showMsg("Connection error"); }
  };

  const doAdvance = async (hours: number) => {
    setIsAdvancing(true);
    await doControl("advance", { delta_hours: hours });
    await fetchSecondary();
    setIsAdvancing(false);
  };

  const doInjectDisruption = async () => {
    await doControl("inject-disruption", { disruption_type: disruptionType, severity: disruptionSeverity, duration_hours: disruptionDuration });
    setShowDisruptionModal(false);
  };

  const ladenC = containers.filter((c) => !EMPTY_STATUSES.has(c.status)).length;
  const emptyC = containers.filter((c) => EMPTY_STATUSES.has(c.status)).length;
  const totalCForChart = ladenC + emptyC || 1;
  const congestedPorts = ports.filter((p) => p.congestion_index > 1.5).length;
  const atPortV = vessels.filter((v) => ["IN_PORT", "ARRIVED", "WAITING_FOR_BERTH"].includes(v.status)).length;
  const enRouteV = vessels.filter((v) => ["IN_TRANSIT", "SCHEDULED", "DEPARTED"].includes(v.status)).length;
  const delayedV = vessels.filter((v) => v.schedule_variance_hours > 2).length;
  const underRepairV = vessels.filter((v) => v.condition === "UNDER_REPAIR").length;
  const openBok = bookings.filter((b) => b.lock_status === "OPEN").length;
  const lockedBok = bookings.filter((b) => b.lock_status === "SEVEN_DAY_LOCK").length;
  const cancelledBok = bookings.filter((b) => b.status === "CANCELLED").length;
  const onTimeVoy = voyages.filter((v) => v.status === "IN_PROGRESS").length;
  const delayedVoy = voyages.filter((v) => v.status === "DELAYED").length;
  const activeDisruptions = disruptions.filter((d) => d.status === "ACTIVE");
  const stormDis = activeDisruptions.filter((d) => d.disruption_type === "STORM").length;
  const strikeDis = activeDisruptions.filter((d) => d.disruption_type === "PORT_STRIKE").length;
  const eqByType: Record<string, { available: number; target: number }> = {};
  equipment.forEach((eq) => { if (!eqByType[eq.equipment_type]) eqByType[eq.equipment_type] = { available: 0, target: 0 }; eqByType[eq.equipment_type].available += eq.available; eqByType[eq.equipment_type].target += eq.target; });
  const eqChartData = Object.entries(eqByType).slice(0, 4).map(([type, d]) => ({ label: type.replace(/_/g, " ").slice(0, 6), available: d.available, required: d.target }));
  const top5 = [...ports].filter((p) => p.congestion_index > 0).sort((a, b) => b.congestion_index - a.congestion_index).slice(0, 5);

  const isRunning = simStatus?.status === "RUNNING";
  const isPaused = simStatus?.status === "PAUSED";
  const isIdle = !simStatus || ["IDLE", "CREATED", "COMPLETED", "RESET", "ERROR"].includes(simStatus.status ?? "IDLE");
  const simTime = fmtSimTime(simStatus?.simulation_time ?? null);
  const progressPct = simState ? Math.min(Math.round(((new Date(simState.simulation_time).getTime() - new Date("2026-09-01").getTime()) / (60 * 86400000)) * 100), 100) : 0;
  const TABS = ["Overview", "Map", "Vessels", "Ports", "Containers", "Bookings", "Equipment", "Disruptions", "Costs"];

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        body{font-family:'Inter',sans-serif;background:#F8FAFC;color:#111827;}
        .cargo-tooltip{background:#1F2937!important;color:#fff!important;border:none!important;border-radius:4px!important;font-size:12px!important;padding:4px 8px!important;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-track{background:#F1F5F9;}
        ::-webkit-scrollbar-thumb{background:#CBD5E1;border-radius:3px;}
        .sc:hover{box-shadow:0 4px 16px rgba(37,99,235,.12);transform:translateY(-1px);}
        .sc{transition:all .18s ease;cursor:default;}
        .ni:hover{background:#EFF6FF!important;color:#2563EB!important;}
        .tb:hover{background:#F1F5F9;color:#1D4ED8;}
        .cb{transition:opacity .15s;cursor:pointer;border:none;}
        .cb:hover{opacity:.82;}
        .cb:disabled{opacity:.45;cursor:not-allowed;}
        .at{animation:slideUp .3s ease;}
        @keyframes slideUp{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}
        .pl{animation:pulse 2s infinite;}
        @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.45;}}
        .pb{transition:width .6s ease;}
      `}</style>

      <div style={{ display: "flex", height: "100vh", overflow: "hidden", fontFamily: "'Inter',sans-serif" }}>

        {/* Sidebar */}
        <aside style={{ width: sidebarCollapsed ? 56 : 216, background: "#fff", borderRight: "1px solid #E5E7EB", display: "flex", flexDirection: "column", flexShrink: 0, transition: "width .25s ease", overflow: "hidden" }}>
          <div style={{ padding: "14px 12px", borderBottom: "1px solid #F3F4F6", display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ width: 30, height: 30, background: "linear-gradient(135deg,#2563EB,#1D4ED8)", borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <span style={{ fontSize: 15, color: "#fff" }}>⚓</span>
            </div>
            {!sidebarCollapsed && <span style={{ fontWeight: 700, fontSize: 14, color: "#111827", whiteSpace: "nowrap" }}>CargoPilot</span>}
          </div>
          <nav style={{ flex: 1, padding: "6px 0", overflowY: "auto" }}>
            <a href="/" className="ni" style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px", textDecoration: "none", color: "#6B7280", fontSize: 13, fontWeight: 500, borderRadius: 6, margin: "1px 5px" }}>
              <span style={{ fontSize: 14, flexShrink: 0 }}>⊞</span>{!sidebarCollapsed && "Dashboard"}
            </a>
            <div style={{ margin: "3px 5px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px", fontSize: 13, fontWeight: 600, color: "#2563EB", background: "#EFF6FF", borderRadius: 6 }}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>🌐</span>{!sidebarCollapsed && "Simulation"}
              </div>
              {!sidebarCollapsed && (
                <div style={{ paddingLeft: 14, marginTop: 2 }}>
                  {[
                    { label: "World 1", href: "/simulation/world1", active: true },
                    { label: "World 2", href: "/simulation/world2" },
                    { label: "Scenarios", href: "#" },
                    { label: "Parameters", href: "#" },
                  ].map((s) => (
                    <a key={s.label} href={s.href} style={{ display: "block", padding: "5px 12px", fontSize: 12.5, color: s.active ? "#2563EB" : "#6B7280", fontWeight: s.active ? 600 : 400, textDecoration: "none", borderLeft: `2px solid ${s.active ? "#2563EB" : "transparent"}`, marginBottom: 1 }}>
                      {s.label}
                    </a>
                  ))}
                </div>
              )}
            </div>
            {[{ icon: "📦", label: "CargoPilot" }, { icon: "📊", label: "Reports" }, { icon: "⚙️", label: "Settings" }].map((item) => (
              <a key={item.label} href="#" className="ni" style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px", textDecoration: "none", color: "#6B7280", fontSize: 13, fontWeight: 500, borderRadius: 6, margin: "1px 5px" }}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>{item.icon}</span>{!sidebarCollapsed && item.label}
              </a>
            ))}
          </nav>
          <button onClick={() => setSidebarCollapsed((p) => !p)} style={{ margin: "6px", padding: "6px", background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: 6, cursor: "pointer", fontSize: 11, color: "#6B7280" }}>
            {sidebarCollapsed ? "→" : "← Collapse"}
          </button>
        </aside>

        {/* Main */}
        <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>

          {/* Header */}
          <header style={{ background: "#fff", borderBottom: "1px solid #E5E7EB", padding: "10px 20px", flexShrink: 0 }}>
            <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 6 }}>
              Simulation <span style={{ margin: "0 4px" }}>›</span><span style={{ color: "#374151" }}>World 1</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 180 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <h1 style={{ fontSize: 20, fontWeight: 700, color: "#111827" }}>World 1</h1>
                  <span style={{ padding: "2px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: isRunning ? "#DCFCE7" : isPaused ? "#FEF9C3" : "#F3F4F6", color: isRunning ? "#166534" : isPaused ? "#854D0E" : "#6B7280", display: "flex", alignItems: "center", gap: 4 }}>
                    {isRunning && <span className="pl" style={{ width: 6, height: 6, borderRadius: "50%", background: "#16A34A", display: "inline-block" }} />}
                    {simStatus?.status ?? "IDLE"}
                  </span>
                </div>
                <p style={{ fontSize: 11.5, color: "#6B7280", marginTop: 1 }}>Live simulation environment with real-time world state and controls.</p>
              </div>
              {simState && (
                <div style={{ background: "#F8FAFC", border: "1px solid #E5E7EB", borderRadius: 10, padding: "7px 14px", minWidth: 210 }}>
                  <div style={{ fontSize: 9, color: "#9CA3AF", marginBottom: 3 }}>Simulation Time (T_sim)</div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: "#111827" }}>{simTime.date} &nbsp; {simTime.time}</div>
                  <div style={{ fontSize: 10, color: "#6B7280", margin: "3px 0" }}>{simTime.day} of 60 ({progressPct}% complete)</div>
                  <div style={{ height: 5, background: "#E5E7EB", borderRadius: 3, overflow: "hidden" }}>
                    <div className="pb" style={{ width: `${progressPct}%`, height: "100%", background: "linear-gradient(90deg,#2563EB,#7C3AED)", borderRadius: 3 }} />
                  </div>
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11.5, color: "#374151" }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#16A34A", display: "inline-block" }} />Real Time</span>
                <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11.5, color: "#374151" }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#2563EB", display: "inline-block" }} />Connected</span>
              </div>
              <button style={{ padding: "7px 14px", background: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: 7, fontSize: 12, fontWeight: 600, color: "#1D4ED8", cursor: "pointer" }}>View Timeline →</button>
            </div>
          </header>

          {/* Tabs */}
          <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB", padding: "0 20px", flexShrink: 0, display: "flex", gap: 0, overflowX: "auto" }}>
            {TABS.map((tab) => {
              const key = tab.toLowerCase();
              return (
                <button key={key} className="tb" onClick={() => setActiveTab(key)} style={{ padding: "9px 14px", background: "none", border: "none", borderBottom: activeTab === key ? "2.5px solid #2563EB" : "2.5px solid transparent", color: activeTab === key ? "#2563EB" : "#6B7280", fontWeight: activeTab === key ? 600 : 400, fontSize: 12.5, cursor: "pointer", whiteSpace: "nowrap" }}>
                  {tab}
                </button>
              );
            })}
            <button className="tb" style={{ padding: "9px 10px", background: "none", border: "none", borderBottom: "2.5px solid transparent", color: "#6B7280", fontSize: 12.5, cursor: "pointer" }}>More ▾</button>
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflowY: "auto", padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Stats Row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", gap: 10 }}>
              {[
                { icon: "⚓", bg: "#EFF6FF", main: fmtNum(simState?.ports_count ?? ports.length), label: "Ports", sub: congestedPorts > 0 ? `${congestedPorts} congested` : "All clear", subColor: congestedPorts > 0 ? "#EF4444" : "#16A34A" },
                { icon: "🚢", bg: "#ECFEFF", main: fmtNum(simState?.vessels_count ?? vessels.length), label: "Vessels", sub: `${atPortV} at port`, subColor: "#6B7280" },
                { icon: "📦", bg: "#F5F3FF", main: fmtNum(simState?.containers_count ?? containers.length), label: "Containers", sub: `${fmtNum(ladenC)} laden · ${fmtNum(emptyC)} empty`, subColor: "#6B7280" },
                { icon: "📋", bg: "#F0FDFA", main: fmtNum(simState?.bookings_count ?? bookings.length), label: "Bookings", sub: `${fmtNum(lockedBok)} in 7-day lock`, subColor: "#6B7280" },
                { icon: "🗺️", bg: "#FFFBEB", main: fmtNum(simState?.voyages_count ?? voyages.length), label: "Active Voyages", sub: `${onTimeVoy} on time · ${delayedVoy} delayed`, subColor: delayedVoy > 0 ? "#F97316" : "#6B7280" },
                { icon: "⚠️", bg: "#FEF2F2", main: String(simState?.active_disruptions_count ?? activeDisruptions.length), label: "Active Disruptions", sub: `${strikeDis} port strike · ${stormDis} storm`, subColor: activeDisruptions.length > 0 ? "#EF4444" : "#6B7280" },
              ].map((card, i) => (
                <div key={i} className="sc" style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "13px 14px" }}>
                  <div style={{ width: 30, height: 30, borderRadius: 7, background: card.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, marginBottom: 8 }}>{card.icon}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#111827", lineHeight: 1 }}>{card.main}</div>
                  <div style={{ fontSize: 11.5, fontWeight: 500, color: "#374151", marginTop: 3 }}>{card.label}</div>
                  <div style={{ fontSize: 10.5, color: card.subColor, marginTop: 4, lineHeight: 1.3 }}>{card.sub}</div>
                </div>
              ))}
            </div>

            {/* Map + Entity Panel */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 14 }}>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, overflow: "hidden" }}>
                <div style={{ padding: "11px 14px", borderBottom: "1px solid #F3F4F6" }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5, color: "#111827" }}>World Map</div>
                  <div style={{ fontSize: 11, color: "#6B7280" }}>Global view of ports, vessels and current conditions.</div>
                </div>
                <div ref={mapRef} style={{ height: 360, width: "100%" }} />
                <div style={{ padding: "9px 14px", borderTop: "1px solid #F3F4F6", display: "flex", gap: 14, flexWrap: "wrap" }}>
                  {[
                    { color: "#2563EB", shape: "circle", label: "Port" },
                    { color: "#EF4444", shape: "circle", label: "Congested Port" },
                    { color: "#16A34A", shape: "tri", label: "Vessel (En Route)" },
                    { color: "#10B981", shape: "tri", label: "Vessel (At Port)" },
                    { color: "#F97316", shape: "tri", label: "Vessel (Delayed)" },
                    { color: "#94A3B8", shape: "dash", label: "Route" },
                  ].map((l) => (
                    <span key={l.label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10.5, color: "#374151" }}>
                      {l.shape === "circle" ? <span style={{ width: 9, height: 9, borderRadius: "50%", background: l.color, display: "inline-block" }} /> : l.shape === "tri" ? <span style={{ display: "inline-block", width: 0, height: 0, borderLeft: "4px solid transparent", borderRight: "4px solid transparent", borderBottom: `8px solid ${l.color}` }} /> : <span style={{ width: 14, height: 2, background: l.color, display: "inline-block", borderRadius: 1 }} />}
                      {l.label}
                    </span>
                  ))}
                </div>
              </div>

              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, display: "flex", flexDirection: "column" }}>
                <div style={{ padding: "11px 14px", borderBottom: "1px solid #F3F4F6" }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5, color: "#111827", marginBottom: 7 }}>Selected Entity</div>
                  <div style={{ display: "flex", gap: 3 }}>
                    {(["port", "vessel", "container"] as const).map((t) => (
                      <button key={t} onClick={() => setEntityTab(t)} style={{ padding: "3px 10px", borderRadius: 5, border: "none", fontSize: 11.5, fontWeight: entityTab === t ? 600 : 400, background: entityTab === t ? "#EFF6FF" : "#F9FAFB", color: entityTab === t ? "#2563EB" : "#6B7280", cursor: "pointer" }}>
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>
                <div style={{ flex: 1, padding: "12px 14px", overflowY: "auto" }}>
                  {!selectedEntity && entityTab !== "container" && (
                    <div style={{ textAlign: "center", color: "#9CA3AF", fontSize: 12, marginTop: 30 }}>
                      <div style={{ fontSize: 28, marginBottom: 6 }}>🗺️</div>
                      Click a port or vessel<br />on the map to see details
                    </div>
                  )}
                  {selectedEntity?.type === "port" && entityTab === "port" && <PortDetail port={selectedEntity.data} vessels={vessels} />}
                  {selectedEntity?.type === "vessel" && entityTab === "vessel" && <VesselDetail vessel={selectedEntity.data} ports={ports} />}
                  {entityTab === "container" && (
                    <div style={{ fontSize: 12 }}>
                      <div style={{ fontWeight: 600, color: "#111827", marginBottom: 8 }}>Container Summary</div>
                      {Object.entries(containers.slice(0, 200).reduce<Record<string, number>>((acc, c) => { acc[c.status] = (acc[c.status] ?? 0) + 1; return acc; }, {})).map(([status, count]) => (
                        <div key={status} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #F9FAFB", fontSize: 11 }}>
                          <span style={{ color: "#6B7280" }}>{status}</span>
                          <span style={{ fontWeight: 600, color: "#111827" }}>{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {selectedEntity && (
                  <div style={{ padding: "8px 14px", borderTop: "1px solid #F3F4F6" }}>
                    <button onClick={() => setSelectedEntity(null)} style={{ fontSize: 11.5, color: "#2563EB", background: "none", border: "none", cursor: "pointer" }}>View Full Details →</button>
                  </div>
                )}
              </div>
            </div>

            {/* Controls + Scenario + Quick Links */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 13.5, color: "#111827", marginBottom: 3 }}>Simulation Controls</div>
                <div style={{ fontSize: 11, color: "#6B7280", marginBottom: 12 }}>Control the simulation engine for World 1.</div>
                {actionMsg && <div className="at" style={{ marginBottom: 9, padding: "6px 10px", background: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 5, fontSize: 11.5, color: "#166534" }}>{actionMsg}</div>}
                <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                  {isIdle ? (
                    <button className="cb" onClick={() => doControl("start", { scenario_id: selectedScenario, seed: 42, world_id: "world-1" })} style={{ padding: "7px 16px", background: "#16A34A", color: "#fff", borderRadius: 7, fontSize: 12, fontWeight: 600 }}>▶ Start</button>
                  ) : isRunning ? (
                    <button className="cb" onClick={() => doControl("pause")} style={{ padding: "7px 16px", background: "#F59E0B", color: "#fff", borderRadius: 7, fontSize: 12, fontWeight: 600 }}>⏸ Pause</button>
                  ) : (
                    <button className="cb" onClick={() => doControl("resume")} style={{ padding: "7px 16px", background: "#16A34A", color: "#fff", borderRadius: 7, fontSize: 12, fontWeight: 600 }}>▶ Resume</button>
                  )}
                  {[1, 6, 12, 24].map((h) => (
                    <button key={h} className="cb" onClick={() => doAdvance(h)} disabled={isAdvancing || isIdle} style={{ padding: "7px 11px", background: isIdle ? "#F3F4F6" : "#EFF6FF", color: isIdle ? "#9CA3AF" : "#1D4ED8", border: `1px solid ${isIdle ? "#E5E7EB" : "#BFDBFE"}`, borderRadius: 7, fontSize: 11.5, fontWeight: 500 }}>
                      {isAdvancing ? "…" : `Advance +${h}h`}
                    </button>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <button className="cb" onClick={() => doControl("reset")} style={{ padding: "6px 10px", background: "#FEF2F2", color: "#DC2626", border: "1px solid #FECACA", borderRadius: 6, fontSize: 11 }}>🔄 Reset World</button>
                  <button className="cb" onClick={() => setShowDisruptionModal(true)} style={{ padding: "6px 10px", background: "#FFF7ED", color: "#C2410C", border: "1px solid #FED7AA", borderRadius: 6, fontSize: 11 }}>⚡ Inject Disruption</button>
                  <button className="cb" onClick={() => showMsg("Snapshot saved")} style={{ padding: "6px 10px", background: "#F5F3FF", color: "#6D28D9", border: "1px solid #DDD6FE", borderRadius: 6, fontSize: 11 }}>💾 Save Snapshot</button>
                </div>
              </div>

              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 13.5, color: "#111827", marginBottom: 3 }}>Scenario & Parameters</div>
                <div style={{ fontSize: 11, color: "#6B7280", marginBottom: 12 }}>Manage scenario and key simulation parameters.</div>
                <div style={{ fontSize: 10.5, color: "#6B7280", marginBottom: 5 }}>Current Scenario</div>
                <div style={{ display: "flex", gap: 7, marginBottom: 12 }}>
                  <select value={selectedScenario} onChange={(e) => setSelectedScenario(e.target.value)} style={{ flex: 1, padding: "7px 9px", border: "1px solid #D1D5DB", borderRadius: 6, fontSize: 12, background: "#fff", color: "#111827" }}>
                    {scenarios.length === 0 && <option value="NORMAL">Normal (No Disruptions)</option>}
                    {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}{s.description ? ` — ${s.description.slice(0, 24)}` : ""}</option>)}
                  </select>
                  <button className="cb" onClick={() => doControl("start", { scenario_id: selectedScenario, seed: 42, world_id: "world-1" })} style={{ padding: "7px 11px", background: "#2563EB", color: "#fff", borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Change</button>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <button className="cb" style={{ padding: "6px 10px", background: "#F8FAFC", border: "1px solid #E5E7EB", borderRadius: 6, fontSize: 11, color: "#374151" }}>⚙️ View/Edit Parameters</button>
                  <button className="cb" style={{ padding: "6px 10px", background: "#F8FAFC", border: "1px solid #E5E7EB", borderRadius: 6, fontSize: 11, color: "#374151" }}>🎲 Random Seed: {simState?.run_id?.slice(-5) ?? "—"}</button>
                </div>
              </div>

              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 13.5, color: "#111827", marginBottom: 12 }}>Quick Links</div>
                {[
                  { icon: "🚢", label: "Vessel List", count: vessels.length, tab: "vessels" },
                  { icon: "⚓", label: "Port List", count: ports.length, tab: "ports" },
                  { icon: "📦", label: "Container Inventory", count: simState?.containers_count ?? containers.length, tab: "containers" },
                  { icon: "📋", label: "Booking List", count: simState?.bookings_count ?? bookings.length, tab: "bookings" },
                  { icon: "⚠️", label: "Active Disruptions", count: activeDisruptions.length, tab: "disruptions" },
                  { icon: "💰", label: "Cost Summary", count: simState ? fmtCurrency(simState.kpis.total_cost) : "—", tab: "costs" },
                ].map((link) => (
                  <div key={link.label} className="ni" onClick={() => setActiveTab(link.tab)} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 4px", borderBottom: "1px solid #F3F4F6", cursor: "pointer", borderRadius: 4 }}>
                    <span style={{ fontSize: 12, color: "#374151", display: "flex", alignItems: "center", gap: 6 }}><span>{link.icon}</span>{link.label}</span>
                    <span style={{ fontSize: 11, color: "#6B7280", display: "flex", alignItems: "center", gap: 3 }}>{link.count} →</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Charts Row */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 14 }}>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 12.5, color: "#111827", marginBottom: 12 }}>Vessel Status</div>
                <DonutChart total={vessels.length || 1} label="Vessels" segments={[
                  { value: enRouteV, color: "#2563EB", name: "En Route" },
                  { value: atPortV, color: "#10B981", name: "At Port" },
                  { value: delayedV, color: "#F97316", name: "Delayed" },
                  { value: underRepairV, color: "#EF4444", name: "Under Repair" },
                ]} />
              </div>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 12.5, color: "#111827", marginBottom: 12 }}>Container Distribution</div>
                <DonutChart total={totalCForChart} label="Containers" segments={[
                  { value: ladenC, color: "#2563EB", name: "Laden" },
                  { value: emptyC, color: "#10B981", name: "Empty" },
                ]} />
              </div>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 12.5, color: "#111827", marginBottom: 12 }}>Booking Status</div>
                <DonutChart total={bookings.length || 1} label="Bookings" segments={[
                  { value: openBok, color: "#16A34A", name: "Open" },
                  { value: lockedBok, color: "#F59E0B", name: "7-Day Lock" },
                  { value: cancelledBok, color: "#EF4444", name: "Cancelled" },
                ]} />
              </div>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
                <div style={{ fontWeight: 600, fontSize: 12.5, color: "#111827", marginBottom: 12 }}>Equipment Balance (by Type)</div>
                {eqChartData.length > 0 ? <BarChart data={eqChartData} /> : <div style={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: "#9CA3AF" }}>No equipment data</div>}
              </div>
            </div>

            {/* Events + Congested Ports */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, overflow: "hidden" }}>
                <div style={{ padding: "12px 14px", borderBottom: "1px solid #F3F4F6", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 600, fontSize: 13.5, color: "#111827" }}>Recent Events</span>
                  <span style={{ fontSize: 11.5, color: "#2563EB", cursor: "pointer" }}>View All</span>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                    <thead>
                      <tr style={{ background: "#F8FAFC" }}>
                        {["Time (T_sim)", "Event", "Entity", "Details"].map((h) => (
                          <th key={h} style={{ padding: "7px 12px", textAlign: "left", color: "#6B7280", fontWeight: 500, fontSize: 10.5, borderBottom: "1px solid #F3F4F6" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {events.length === 0 ? (
                        <tr><td colSpan={4} style={{ padding: "20px", textAlign: "center", color: "#9CA3AF", fontSize: 12 }}>
                          {isIdle ? "Start the simulation to see events" : "No events yet — advance the simulation"}
                        </td></tr>
                      ) : events.slice(0, 8).map((e) => {
                        const t = new Date(e.simulation_time);
                        const tStr = `${t.toLocaleDateString("en-GB", { day: "2-digit", month: "short" })} ${t.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
                        const evColor = e.event_type.includes("DISRUPTION") ? "#EF4444" : e.event_type.includes("DELAY") ? "#F97316" : e.event_type.includes("BOOKING") ? "#2563EB" : "#10B981";
                        const payloadStr = Object.entries(e.payload).map(([k, v]) => `${k}: ${v}`).join(", ").slice(0, 45);
                        return (
                          <tr key={e.event_id} style={{ borderBottom: "1px solid #F9FAFB" }}>
                            <td style={{ padding: "7px 12px", color: "#6B7280", whiteSpace: "nowrap" }}>{tStr}</td>
                            <td style={{ padding: "7px 12px", whiteSpace: "nowrap" }}>
                              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                <span style={{ width: 7, height: 7, borderRadius: "50%", background: evColor, display: "inline-block", flexShrink: 0 }} />
                                {e.event_type.replace(/_/g, " ")}
                              </span>
                            </td>
                            <td style={{ padding: "7px 12px", fontWeight: 500, color: "#111827" }}>{e.entity_id.slice(-10)}</td>
                            <td style={{ padding: "7px 12px", color: "#6B7280", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{payloadStr || "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, overflow: "hidden" }}>
                <div style={{ padding: "12px 14px", borderBottom: "1px solid #F3F4F6", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 600, fontSize: 13.5, color: "#111827" }}>Top 5 Congested Ports</span>
                  <span style={{ fontSize: 11.5, color: "#2563EB", cursor: "pointer" }}>View All</span>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                    <thead>
                      <tr style={{ background: "#F8FAFC" }}>
                        {["Port", "Congestion Index", "Status"].map((h) => (
                          <th key={h} style={{ padding: "7px 12px", textAlign: "left", color: "#6B7280", fontWeight: 500, fontSize: 10.5, borderBottom: "1px solid #F3F4F6" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {top5.length === 0 ? (
                        <tr><td colSpan={3} style={{ padding: "20px", textAlign: "center", color: "#9CA3AF", fontSize: 12 }}>No congested ports — great!</td></tr>
                      ) : top5.map((p) => {
                        const ci = p.congestion_index;
                        const sl = ci > 2 ? "High" : ci > 1.5 ? "Medium" : "Normal";
                        const sc2 = ci > 2 ? { bg: "#FEF2F2", text: "#DC2626" } : ci > 1.5 ? { bg: "#FFF7ED", text: "#C2410C" } : { bg: "#F0FDF4", text: "#16A34A" };
                        const bc = ci > 2 ? "#EF4444" : ci > 1.5 ? "#F97316" : "#10B981";
                        return (
                          <tr key={p.port_id} style={{ borderBottom: "1px solid #F9FAFB", cursor: "pointer" }} onClick={() => { setSelectedEntity({ type: "port", data: p }); setEntityTab("port"); }}>
                            <td style={{ padding: "9px 12px" }}>
                              <div style={{ fontWeight: 500, color: "#111827" }}>{p.name}</div>
                              <div style={{ fontSize: 9.5, color: "#9CA3AF" }}>{p.unlocode}</div>
                            </td>
                            <td style={{ padding: "9px 12px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                <div style={{ flex: 1, height: 5, background: "#F3F4F6", borderRadius: 3 }}>
                                  <div style={{ width: `${Math.min((ci / 3) * 100, 100)}%`, height: "100%", background: bc, borderRadius: 3 }} />
                                </div>
                                <span style={{ fontWeight: 600, color: "#111827", minWidth: 26, fontSize: 12 }}>{ci.toFixed(1)}</span>
                              </div>
                            </td>
                            <td style={{ padding: "9px 12px" }}>
                              <span style={{ padding: "2px 7px", borderRadius: 10, fontSize: 10.5, fontWeight: 600, background: sc2.bg, color: sc2.text }}>{sl}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Notes */}
            <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 11, padding: "14px" }}>
              <div style={{ fontWeight: 600, fontSize: 13.5, color: "#111827", marginBottom: 9 }}>Simulation Notes / Logs</div>
              <div style={{ display: "flex", gap: 10 }}>
                <textarea value={simNote} onChange={(e) => setSimNote(e.target.value)} placeholder="Add a note about this simulation run (optional)..." style={{ flex: 1, padding: "9px 12px", border: "1px solid #D1D5DB", borderRadius: 7, fontSize: 12.5, resize: "vertical", minHeight: 64, color: "#374151", fontFamily: "'Inter',sans-serif" }} />
                <button onClick={() => { setSavedNote(simNote); showMsg("Note saved"); }} style={{ padding: "9px 22px", background: "#2563EB", color: "#fff", border: "none", borderRadius: 7, fontSize: 12.5, fontWeight: 600, cursor: "pointer", alignSelf: "flex-end" }}>Save Note</button>
              </div>
              {savedNote && <div style={{ marginTop: 9, padding: "7px 10px", background: "#F0F4FF", borderRadius: 5, fontSize: 11.5, color: "#374151" }}><strong>Saved:</strong> {savedNote}</div>}
            </div>

          </div>

          {/* Footer */}
          <footer style={{ background: "#fff", borderTop: "1px solid #E5E7EB", padding: "9px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
            <span style={{ fontSize: 11.5, color: "#6B7280", display: "flex", alignItems: "center", gap: 5 }}>
              ⚓ CargoPilot · Simulation Engine · World 1 · <span style={{ color: isRunning ? "#16A34A" : "#9CA3AF" }}>{simStatus?.status ?? "IDLE"}</span>
            </span>
            <span style={{ fontSize: 11.5, color: "#9CA3AF" }}>
              Last updated: {simStatus?.simulation_time ? new Date(simStatus.simulation_time).toLocaleString("en-GB") : "—"} (T_sim)
            </span>
          </footer>
        </main>
      </div>

      {/* Inject Disruption Modal */}
      {showDisruptionModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999 }}>
          <div style={{ background: "#fff", borderRadius: 14, padding: 26, width: 400, boxShadow: "0 20px 60px rgba(0,0,0,.18)" }}>
            <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 3 }}>Inject Disruption</h3>
            <p style={{ fontSize: 12.5, color: "#6B7280", marginBottom: 18 }}>Inject an operational disruption into the live simulation.</p>
            <div style={{ marginBottom: 13 }}>
              <label style={{ fontSize: 11.5, fontWeight: 500, color: "#374151", display: "block", marginBottom: 4 }}>Disruption Type</label>
              <select value={disruptionType} onChange={(e) => setDisruptionType(e.target.value)} style={{ width: "100%", padding: "8px 11px", border: "1px solid #D1D5DB", borderRadius: 7, fontSize: 12.5, background: "#fff" }}>
                {["STORM", "PORT_STRIKE", "EQUIPMENT_SHORTAGE", "VESSEL_BREAKDOWN", "DEMAND_SPIKE"].map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 13 }}>
              <label style={{ fontSize: 11.5, fontWeight: 500, color: "#374151", display: "block", marginBottom: 4 }}>Severity: {disruptionSeverity.toFixed(2)}</label>
              <input type="range" min={0} max={1} step={0.05} value={disruptionSeverity} onChange={(e) => setDisruptionSeverity(Number(e.target.value))} style={{ width: "100%", accentColor: "#2563EB" }} />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#9CA3AF" }}><span>Mild (0)</span><span>Severe (1)</span></div>
            </div>
            <div style={{ marginBottom: 18 }}>
              <label style={{ fontSize: 11.5, fontWeight: 500, color: "#374151", display: "block", marginBottom: 4 }}>Duration (hours): {disruptionDuration}h</label>
              <input type="range" min={6} max={168} step={6} value={disruptionDuration} onChange={(e) => setDisruptionDuration(Number(e.target.value))} style={{ width: "100%", accentColor: "#2563EB" }} />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#9CA3AF" }}><span>6h</span><span>168h (1 week)</span></div>
            </div>
            <div style={{ display: "flex", gap: 9, justifyContent: "flex-end" }}>
              <button onClick={() => setShowDisruptionModal(false)} style={{ padding: "8px 18px", background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: 7, fontSize: 12.5, cursor: "pointer" }}>Cancel</button>
              <button onClick={doInjectDisruption} style={{ padding: "8px 18px", background: "#DC2626", color: "#fff", border: "none", borderRadius: 7, fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>Inject Disruption</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
