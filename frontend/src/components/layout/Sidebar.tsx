import {
  Activity, Car, Eye, LayoutDashboard, ListChecks, Moon, Scan, Search,
  Server, Settings, ShieldAlert, Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";

const primaryLinks = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/analysis", label: "Analysis", icon: Scan },
  { to: "/jobs", label: "Jobs", icon: ListChecks },
  { to: "/events", label: "Events", icon: Activity },
  { to: "/anpr-search", label: "ANPR Search", icon: Search },
];

// These all deep-link into the Analysis page's module selection (via
// ?open=<key>) rather than separate pages - "Human Detection" and "Vehicle
// Detection" have no standalone backend endpoint of their own (person/vehicle
// detection is the shared tracker every module already uses under the
// hood), so routing them to a fake dedicated page would misrepresent what
// the backend actually offers. The Analysis page surfaces a note for those
// two explaining that instead of pretending they're independent modules.
const moduleLinks = [
  { to: "/analysis?open=person_id", label: "Target Person ID", icon: Eye },
  { to: "/analysis?open=human_detection", label: "Human Detection", icon: Users },
  { to: "/analysis?open=vehicle_detection", label: "Vehicle Detection", icon: Car },
  { to: "/analysis?open=anpr", label: "ANPR / Plate OCR", icon: Search },
  { to: "/analysis?open=zone", label: "Zone Intrusion", icon: ShieldAlert },
  { to: "/analysis?open=behavior", label: "Behavioral Analytics", icon: Activity },
  { to: "/analysis?open=lowlight", label: "Low-Light Enhancement", icon: Moon },
];

const systemLinks = [
  { to: "/system", label: "System Status", icon: Server },
  { to: "/settings", label: "Settings", icon: Settings },
];

function NavGroup({ links }: { links: typeof primaryLinks }) {
  return (
    <nav className="flex flex-col gap-px px-3">
      {links.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded px-3 py-[9px] text-[13.5px] border-l-2 transition-colors ${
              isActive
                ? "bg-accent-blue/10 text-text-primary border-accent-blue"
                : "text-text-secondary border-transparent hover:bg-bg-3 hover:text-text-primary"
            }`
          }
        >
          <Icon size={16} className="shrink-0 opacity-85" />
          <span className="truncate">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 h-screen w-[248px] shrink-0 overflow-y-auto border-r border-border-1 bg-bg-0 py-5 max-[1366px]:w-[220px]">
      <div className="mb-4 border-b border-border-1 px-5 pb-5">
        <div className="flex items-center gap-2 text-lg font-bold tracking-wide text-text-primary">
          <span className="h-2 w-2 shrink-0 rounded-full bg-accent-blue shadow-[0_0_8px_var(--color-accent-blue)]" />
          BORDERWATCH
        </div>
        <div className="mt-1 pl-4 text-[11px] tracking-[1.5px] text-text-tertiary">AI VIDEO INTELLIGENCE</div>
      </div>

      <NavGroup links={primaryLinks} />

      <div className="px-5 pb-1 pt-4 text-[10px] font-semibold tracking-[1.2px] text-text-disabled">
        ANALYSIS MODULES
      </div>
      <NavGroup links={moduleLinks} />

      <div className="px-5 pb-1 pt-4 text-[10px] font-semibold tracking-[1.2px] text-text-disabled">SYSTEM</div>
      <NavGroup links={systemLinks} />

      <div className="mx-5 mt-4 flex items-center gap-2 border-t border-border-1 pt-4 text-[11px] tracking-wide text-text-tertiary">
        <span className="h-[6px] w-[6px] rounded-full bg-accent-green" />
        SYSTEM ONLINE
      </div>
    </aside>
  );
}
