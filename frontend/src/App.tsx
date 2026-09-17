import { NavLink, Route, Routes } from 'react-router-dom';
import { NewAudit } from './pages/NewAudit';
import { About, AuditReportPage, Experiments, History } from './pages/StaticPages';

function Home() {
  return <main className="page"><History /></main>;
}

/** The application shell intentionally uses plain React links and semantic navigation. */
export default function App() {
  return <div className="app-shell">
    <header className="app-header">
      <NavLink className="brand" to="/"><span aria-hidden="true" className="brand-mark">✦</span>Memory Auditor</NavLink>
      <nav aria-label="Primary navigation">
        <NavLink to="/">Dashboard</NavLink>
        <NavLink to="/new-audit">New audit</NavLink>
        <NavLink to="/history">History</NavLink>
        <NavLink to="/experiments">Experiments</NavLink>
        <NavLink to="/about">About</NavLink>
      </nav>
    </header>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/new-audit" element={<NewAudit />} />
      <Route path="/history" element={<main className="page"><History /></main>} />
      <Route path="/audits/:runId" element={<main className="page"><AuditReportPage /></main>} />
      <Route path="/experiments" element={<main className="page"><Experiments /></main>} />
      <Route path="/about" element={<main className="page"><About /></main>} />
    </Routes>
  </div>;
}
