import { BlindReviewPage } from "./pages/BlindReview";
import { AuditorQualityPage } from "./pages/AuditorQuality";
import { Button, Menu } from 'antd';
import { AccessBoundary } from './components/AccessBoundary';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { NewAudit } from './pages/NewAudit';
import { AuditComparisonPage } from './pages/AuditComparison';
import { About, AuditReportPage, Experiments, History } from './pages/StaticPages';

function Home() {
  return <main className="page"><History /></main>;
}

/** One component library and theme for the application shell and controls. */
function AppShell({signOut,signingOut}:{signOut:(()=>Promise<void>)|null;signingOut:boolean}) {
  const { pathname } = useLocation();
  const links = [['/', 'Dashboard'], ['/new-audit', 'New audit'], ['/history', 'History'],
    ['/compare', 'Before & after'], ['/quality', 'Auditor reliability'], ['/experiments', 'Experiments'], ['/about', 'About']];
  return <div className="app-shell">
    <header className="app-header">
      <NavLink className="brand" to="/"><span aria-hidden="true" className="brand-mark">✦</span>Memory Auditor</NavLink>
      <nav aria-label="Primary navigation">
        <Menu mode="horizontal" selectedKeys={[pathname.startsWith('/audits/') ? '/history' : pathname]}
          items={links.map(([to, label]) => ({ key: to, label: <NavLink to={to}>{label}</NavLink> }))} />
      </nav>
      {signOut&&<Button onClick={()=>void signOut()} className="workspace-signout" loading={signingOut}>Sign out</Button>}
    </header>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/new-audit" element={<NewAudit />} />
      <Route path="/history" element={<main className="page"><History /></main>} />
      <Route path="/compare" element={<main className="page"><AuditComparisonPage /></main>} />
      <Route path="/audits/:runId" element={<main className="page"><AuditReportPage /></main>} />
      <Route path="/experiments" element={<main className="page"><Experiments /></main>} />
      <Route path="/blind-review/:runId" element={<BlindReviewPage/>}/>
      <Route path="/quality" element={<AuditorQualityPage/>}/>
      <Route path="/about" element={<main className="page"><About /></main>} />
      <Route path="*" element={<main className="page"><section className="empty"><h1>Page not found</h1><p>This link does not lead to an available page. Choose where to continue.</p><div className="actions"><NavLink className="secondary" to="/history">Open Audit History</NavLink><NavLink className="secondary" to="/new-audit">Start a new audit</NavLink></div></section></main>} />
    </Routes>
  </div>;
}

export default function App(){return <AccessBoundary>{(signOut,signingOut)=><AppShell signOut={signOut} signingOut={signingOut}/>}</AccessBoundary>;}
