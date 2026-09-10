"use client";

import Link from "next/link";

const worlds = [
  {
    href: "/test/world1",
    emoji: "🕹️",
    label: "Test World 1",
    description: "API & integration test environment — World 1 fixture data",
    gradient: "from-indigo-600 to-cyan-500",
    glow: "shadow-indigo-500/30",
    border: "border-indigo-500/30",
    hover: "hover:border-indigo-400/60",
    badge: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40",
    badgeText: "TEST",
  },
  {
    href: "/test/world2",
    emoji: "🌐",
    label: "Test World 2",
    description: "Extended test lab — 55 ports, 18 vessels, 6 trade regions",
    gradient: "from-violet-600 to-purple-500",
    glow: "shadow-violet-500/30",
    border: "border-violet-500/30",
    hover: "hover:border-violet-400/60",
    badge: "bg-violet-500/20 text-violet-300 border-violet-500/40",
    badgeText: "TEST",
  },
  {
    href: "/simulation/world1",
    emoji: "🗺️",
    label: "Simulation World 1",
    description: "Live interactive world map — real-time vessel & port simulation",
    gradient: "from-emerald-600 to-teal-500",
    glow: "shadow-emerald-500/30",
    border: "border-emerald-500/30",
    hover: "hover:border-emerald-400/60",
    badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    badgeText: "LIVE",
  },
];

export default function HomePage() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "radial-gradient(ellipse at 60% 0%, #0f172a 0%, #020617 60%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Inter', 'Segoe UI', sans-serif",
        padding: "40px 24px",
      }}
    >
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: "64px" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "14px",
            marginBottom: "20px",
          }}
        >
          <div
            style={{
              width: "52px",
              height: "52px",
              borderRadius: "16px",
              background: "linear-gradient(135deg, #4f46e5, #06b6d4)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "26px",
              boxShadow: "0 8px 32px rgba(79,70,229,0.4)",
            }}
          >
            🚢
          </div>
          <div style={{ textAlign: "left" }}>
            <div
              style={{
                fontSize: "28px",
                fontWeight: 800,
                color: "#f1f5f9",
                letterSpacing: "-0.5px",
                lineHeight: 1,
              }}
            >
              CargoPilot
            </div>
            <div style={{ fontSize: "13px", color: "#64748b", marginTop: "4px" }}>
              Container Logistics & Simulation Command Center
            </div>
          </div>
        </div>
        <h1
          style={{
            fontSize: "42px",
            fontWeight: 800,
            color: "#f8fafc",
            letterSpacing: "-1px",
            margin: 0,
          }}
        >
          Choose Your World
        </h1>
        <p style={{ color: "#64748b", fontSize: "16px", marginTop: "12px" }}>
          Select an environment to explore
        </p>
      </div>

      {/* World Cards */}
      <div
        style={{
          display: "flex",
          gap: "28px",
          flexWrap: "wrap",
          justifyContent: "center",
          maxWidth: "1100px",
          width: "100%",
        }}
      >
        {worlds.map((w) => (
          <Link
            key={w.href}
            href={w.href}
            style={{ textDecoration: "none", flex: "1 1 300px", maxWidth: "340px" }}
          >
            <div
              style={{
                background: "rgba(15, 23, 42, 0.85)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "24px",
                padding: "40px 36px",
                cursor: "pointer",
                transition: "all 0.25s ease",
                backdropFilter: "blur(16px)",
                position: "relative",
                overflow: "hidden",
                height: "100%",
                boxSizing: "border-box",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.transform = "translateY(-6px)";
                (e.currentTarget as HTMLDivElement).style.boxShadow = `0 24px 64px rgba(0,0,0,0.4)`;
                (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.18)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
                (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
                (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.08)";
              }}
            >
              {/* Gradient glow top */}
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  height: "2px",
                  background: `linear-gradient(90deg, ${
                    w.gradient.includes("indigo")
                      ? "#4f46e5, #06b6d4"
                      : w.gradient.includes("violet")
                      ? "#7c3aed, #a855f7"
                      : "#059669, #14b8a6"
                  })`,
                  borderRadius: "24px 24px 0 0",
                }}
              />

              {/* Badge */}
              <div
                style={{
                  display: "inline-block",
                  fontSize: "10px",
                  fontWeight: 700,
                  letterSpacing: "1.5px",
                  padding: "3px 10px",
                  borderRadius: "6px",
                  border: "1px solid",
                  marginBottom: "24px",
                  color:
                    w.badgeText === "LIVE"
                      ? "#34d399"
                      : w.gradient.includes("indigo")
                      ? "#818cf8"
                      : "#a78bfa",
                  background:
                    w.badgeText === "LIVE"
                      ? "rgba(52,211,153,0.1)"
                      : w.gradient.includes("indigo")
                      ? "rgba(129,140,248,0.1)"
                      : "rgba(167,139,250,0.1)",
                  borderColor:
                    w.badgeText === "LIVE"
                      ? "rgba(52,211,153,0.3)"
                      : w.gradient.includes("indigo")
                      ? "rgba(129,140,248,0.3)"
                      : "rgba(167,139,250,0.3)",
                }}
              >
                {w.badgeText === "LIVE" ? "● " : ""}{w.badgeText}
              </div>

              {/* Emoji */}
              <div style={{ fontSize: "52px", marginBottom: "20px", lineHeight: 1 }}>
                {w.emoji}
              </div>

              {/* Title */}
              <div
                style={{
                  fontSize: "22px",
                  fontWeight: 700,
                  color: "#f1f5f9",
                  marginBottom: "10px",
                  letterSpacing: "-0.3px",
                }}
              >
                {w.label}
              </div>

              {/* Description */}
              <div style={{ fontSize: "14px", color: "#64748b", lineHeight: 1.6 }}>
                {w.description}
              </div>

              {/* Arrow */}
              <div
                style={{
                  marginTop: "28px",
                  fontSize: "13px",
                  fontWeight: 600,
                  color:
                    w.badgeText === "LIVE"
                      ? "#34d399"
                      : w.gradient.includes("indigo")
                      ? "#818cf8"
                      : "#a78bfa",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                Open world <span style={{ fontSize: "16px" }}>→</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
