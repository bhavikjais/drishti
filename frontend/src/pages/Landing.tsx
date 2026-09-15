import {
  Activity, Car, CloudFog, Crosshair, Eye, LayoutDashboard, Lock, Radar, ScanEye,
  ShieldAlert, ShieldCheck, TextSearch, UserSearch, type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import "./Landing.css";

const signalBars: { label: string; pct: number }[] = [
  { label: "Person tracking", pct: 92 },
  { label: "Vehicle detection", pct: 78 },
  { label: "Plate recognition", pct: 65 },
  { label: "Zone monitoring", pct: 88 },
  { label: "Low-light clarity", pct: 54 },
];

const trustItems: { icon: LucideIcon; label: string }[] = [
  { icon: ShieldCheck, label: "Built for public agencies" },
  { icon: Radar, label: "Real-time detection" },
  { icon: Lock, label: "Secure & auditable" },
  { icon: Eye, label: "24/7 monitoring" },
];

const capabilities: { icon: LucideIcon; title: string; desc: string }[] = [
  { icon: UserSearch, title: "Target person identification", desc: "Lock onto a person of interest and track them across every camera and frame." },
  { icon: ScanEye, title: "Human & vehicle detection", desc: "Every person and vehicle in the frame, detected and tracked automatically." },
  { icon: TextSearch, title: "ANPR / plate OCR", desc: "Read license plates in real time, even in motion or at low resolution." },
  { icon: ShieldAlert, title: "Zone intrusion alerts", desc: "Draw a boundary once. Get notified the instant it's crossed." },
  { icon: CloudFog, title: "Low-light / haze enhancement", desc: "Recover clear detail from dark, hazy, or fog-degraded footage." },
  { icon: Activity, title: "Real-time event feed", desc: "Every crossing, entry, and detection logged the moment it happens." },
  { icon: LayoutDashboard, title: "Job & analysis dashboard", desc: "Track every analysis job, from upload to insight, in one place." },
];

const workflowSteps = [
  { num: "01", title: "Connect your feeds", desc: "Bring in live camera streams or archived footage from any source." },
  { num: "02", title: "Run the right module", desc: "Choose detection, tracking, ANPR, or enhancement — or run them together." },
  { num: "03", title: "Act on what matters", desc: "Alerts, tracks, and plates surface the moment they're found." },
];

const eventFeed: { icon: LucideIcon; title: string; meta: string; time: string }[] = [
  { icon: Crosshair, title: "Crossing predicted — Zone 3", meta: "Track #227", time: "00:51.2" },
  { icon: Car, title: "Vehicle detected — Gate 2", meta: "Track #224", time: "00:50.8" },
  { icon: TextSearch, title: "Plate read — Lot A", meta: "Track #212", time: "00:48.1" },
  { icon: UserSearch, title: "Target match — Entrance 1", meta: "Track #227", time: "00:46.2" },
  { icon: ShieldAlert, title: "Zone entry — Perimeter B", meta: "Track #223", time: "00:44.9" },
];

const dashboardStats = [
  { label: "Feeds live", value: "15" },
  { label: "Events today", value: "273" },
  { label: "Plates read", value: "40" },
];

const scenarios = [
  { title: "Perimeter security", desc: "Zone intrusion and human detection flag unauthorized crossings before they become incidents." },
  { title: "Traffic & access control", desc: "ANPR reads plates at checkpoints in real time, day or night, in any weather." },
  { title: "Investigations", desc: "Search archived footage for a specific person or vehicle across days of footage in minutes." },
];

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

export function Landing() {
  return (
    <div className="drishti-landing">
      <header className="dl-header">
        <div className="dl-brand">
          <div className="dl-brand-mark">
            <Eye size={18} color="#fdfbf7" />
          </div>
          <span className="dl-brand-name">Drishti</span>
        </div>
        <nav className="dl-nav">
          <a href="#capabilities" onClick={(e) => { e.preventDefault(); scrollToId("capabilities"); }}>
            Capabilities
          </a>
          <a href="#how-it-works" onClick={(e) => { e.preventDefault(); scrollToId("how-it-works"); }}>
            How it works
          </a>
          <a href="#in-the-field" onClick={(e) => { e.preventDefault(); scrollToId("in-the-field"); }}>
            In the field
          </a>
          <Link to="/" className="dl-btn dl-btn-outline" style={{ padding: "9px 18px" }}>
            Open dashboard
          </Link>
        </nav>
      </header>

      <section className="dl-hero">
        <div className="dl-container dl-hero-inner">
          <div className="dl-hero-copy">
            <span className="dl-badge">AI video intelligence for public safety</span>
            <h1 className="dl-h1">See everything that matters, the instant it happens.</h1>
            <p className="dl-lede">
              Drishti turns raw camera feeds into instant answers — who crossed a line, which vehicle passed, what
              needs attention right now. Built for agencies who can't afford to miss the moment.
            </p>
            <div className="dl-cta-row">
              <button className="dl-btn dl-btn-primary" onClick={() => scrollToId("capabilities")}>
                Explore capabilities
              </button>
              <button className="dl-btn dl-btn-outline" onClick={() => scrollToId("how-it-works")}>
                See how it works
              </button>
            </div>
          </div>

          <div className="dl-hero-card-wrap">
            <div className="dl-signal-card">
              <div className="dl-signal-head">
                <span className="dl-signal-label">Live signal</span>
                <span className="dl-signal-status">
                  <span className="dl-pulse-dot" />
                  analysing
                </span>
              </div>
              {signalBars.map((bar) => (
                <div className="dl-signal-bar-row" key={bar.label}>
                  <span className="dl-signal-bar-label">{bar.label}</span>
                  <div className="dl-signal-track">
                    <div className="dl-signal-fill" style={{ width: `${bar.pct}%` }} />
                  </div>
                </div>
              ))}
              <div className="dl-signal-foot">Abstract representation of real-time multi-module analysis.</div>
            </div>
          </div>
        </div>
      </section>

      <section className="dl-trust">
        <div className="dl-container dl-trust-row">
          {trustItems.map((item) => (
            <div className="dl-trust-item" key={item.label}>
              <item.icon size={20} />
              {item.label}
            </div>
          ))}
        </div>
      </section>

      <section id="capabilities" className="dl-capabilities">
        <div className="dl-container">
          <div className="dl-section-head">
            <span className="dl-eyebrow">Capabilities</span>
            <h2 className="dl-h2">One platform, every analysis module you need.</h2>
          </div>
          <div className="dl-cap-grid">
            {capabilities.map((cap) => (
              <div className="dl-card" key={cap.title}>
                <div className="dl-card-icon">
                  <cap.icon size={22} />
                </div>
                <div className="dl-card-title">{cap.title}</div>
                <div className="dl-card-body">{cap.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className="dl-how">
        <div className="dl-container">
          <div className="dl-section-head">
            <span className="dl-eyebrow">How it works</span>
            <h2 className="dl-h2">From raw footage to actionable insight.</h2>
          </div>
          <div className="dl-steps">
            {workflowSteps.map((step) => (
              <div key={step.num}>
                <div className="dl-step-num">{step.num}</div>
                <div className="dl-step-title">{step.title}</div>
                <div className="dl-step-body">{step.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="dl-preview">
        <div className="dl-container">
          <div className="dl-section-head">
            <span className="dl-eyebrow dl-eyebrow-inverse">Command center</span>
            <h2 className="dl-h2 dl-h2-inverse">Every job, every event, one live view.</h2>
          </div>
          <div className="dl-preview-grid">
            <div className="dl-preview-feed">
              <div className="dl-preview-feed-title">Recent security events</div>
              {eventFeed.map((ev, i) => (
                <div className="dl-feed-row" key={i}>
                  <div className="dl-feed-left">
                    <ev.icon size={18} />
                    <div>
                      <div className="dl-feed-title">{ev.title}</div>
                      <div className="dl-feed-meta">{ev.meta}</div>
                    </div>
                  </div>
                  <div className="dl-feed-time">{ev.time}</div>
                </div>
              ))}
            </div>
            <div className="dl-preview-stats">
              {dashboardStats.map((stat) => (
                <div className="dl-stat-card" key={stat.label}>
                  <div className="dl-stat-label">{stat.label}</div>
                  <div className="dl-stat-value">{stat.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="in-the-field" className="dl-field">
        <div className="dl-container">
          <div className="dl-section-head">
            <span className="dl-eyebrow">In the field</span>
            <h2 className="dl-h2">Where Drishti earns its place.</h2>
          </div>
          <div className="dl-field-grid">
            {scenarios.map((sc) => (
              <div className="dl-card" key={sc.title}>
                <div className="dl-card-title">{sc.title}</div>
                <div className="dl-card-body">{sc.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="dl-footer">
        <div className="dl-container dl-footer-top">
          <div className="dl-brand">
            <div className="dl-brand-mark" style={{ width: 30, height: 30, background: "rgba(255,255,255,0.12)" }}>
              <Eye size={16} color="#fdfbf7" />
            </div>
            <span className="dl-brand-name" style={{ fontSize: "1.75rem" }}>Drishti</span>
          </div>
          <div className="dl-footer-desc">AI video intelligence for public safety and security operations.</div>
        </div>
        <div className="dl-container dl-footer-bottom">© {new Date().getFullYear()} Drishti.</div>
      </footer>
    </div>
  );
}
