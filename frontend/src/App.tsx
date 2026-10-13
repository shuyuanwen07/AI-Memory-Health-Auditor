import { lazy, Suspense, useEffect, useState } from 'react';
import { Button, Menu, Spin } from 'antd';
import { AccessBoundary } from './components/AccessBoundary';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
const NewAudit = lazy(() => import('./pages/NewAudit').then(module => ({default:module.NewAudit})));
const AuditorComparisonPage = lazy(() => import('./pages/AuditorComparison').then(module => ({default:module.AuditorComparisonPage})));
const AssessorComparisonPage = lazy(() => import('./pages/AssessorComparison').then(module => ({default:module.AssessorComparisonPage})));
const GeneratorComparisonPage = lazy(() => import('./pages/GeneratorComparison').then(module => ({default:module.GeneratorComparisonPage})));
const ExtractionComparisonPage = lazy(() => import('./pages/ExtractionComparison').then(module => ({default:module.ExtractionComparisonPage})));
const AuditComparisonPage = lazy(() => import('./pages/AuditComparison').then(module => ({default:module.AuditComparisonPage})));
const BlindReviewPage = lazy(() => import('./pages/BlindReview').then(module => ({default:module.BlindReviewPage})));
const AuditorQualityPage = lazy(() => import('./pages/AuditorQuality').then(module => ({default:module.AuditorQualityPage})));
const History = lazy(() => import('./pages/StaticPages').then(module => ({default:module.History})));
const About = lazy(() => import('./pages/StaticPages').then(module => ({default:module.About})));
const AuditReportPage = lazy(() => import('./pages/StaticPages').then(module => ({default:module.AuditReportPage})));
const Experiments = lazy(() => import('./pages/StaticPages').then(module => ({default:module.Experiments})));

const Dashboard = lazy(() => import('./pages/Dashboard').then(module => ({default:module.Dashboard})));
function Home() {
  return <main className="page"><Dashboard /></main>;
}

/** One component library and theme for the application shell and controls. */
function AppShell({signOut,signingOut}:{signOut:(()=>Promise<void>)|null;signingOut:boolean}) {
  const { pathname } = useLocation();
  const [navigationOpenKeys, setNavigationOpenKeys] = useState<string[]>([]);
  useEffect(() => { setNavigationOpenKeys([]); }, [pathname]);
  const links = [['/', 'Dashboard'], ['/new-audit', 'New audit'], ['/history', 'History'],
    ['/compare', 'Before & after'], ['/audit-methods', 'Audit methods'], ['/assessor-models', 'AI assessors'], ['/generator-models', 'Test generators'], ['/extraction-models','Memory extractors'], ['/quality', 'Auditor reliability'], ['/experiments', 'Experiments'], ['/about', 'About']];
  return <div className="app-shell">
    <header className="app-header">
      <NavLink className="brand" to="/"><span aria-hidden="true" className="brand-mark">✦</span>Memory Auditor</NavLink>
      <nav aria-label="Primary navigation">
        <Menu mode="horizontal" triggerSubMenuAction="click" openKeys={navigationOpenKeys}
          onOpenChange={setNavigationOpenKeys} onClick={() => setNavigationOpenKeys([])} selectedKeys={[pathname.startsWith('/audits/') ? '/history' : pathname]}
          items={links.map(([to, label]) => ({ key: to, label: <NavLink to={to}>{label}</NavLink> }))} />
      </nav>
      {signOut&&<Button onClick={()=>void signOut()} className="workspace-signout" loading={signingOut}>Sign out</Button>}
    </header>
    <Suspense fallback={<main className="page" role="status"><Spin/> Loading page…</main>}><Routes>
      <Route path="/" element={<Home />} />
      <Route path="/new-audit" element={<NewAudit />} />
      <Route path="/history" element={<main className="page"><History /></main>} />
      <Route path="/compare" element={<main className="page"><AuditComparisonPage /></main>} />
      <Route path="/audit-methods" element={<main className="page"><AuditorComparisonPage /></main>} />
      <Route path="/assessor-models" element={<main className="page"><AssessorComparisonPage /></main>} />
      <Route path="/generator-models" element={<main className="page"><GeneratorComparisonPage /></main>} />
      <Route path="/extraction-models" element={<main className="page"><ExtractionComparisonPage /></main>} />
      <Route path="/audits/:runId" element={<main className="page"><AuditReportPage /></main>} />
      <Route path="/experiments" element={<main className="page"><Experiments /></main>} />
      <Route path="/blind-review/:runId" element={<BlindReviewPage/>}/>
      <Route path="/quality" element={<AuditorQualityPage/>}/>
      <Route path="/about" element={<main className="page"><About /></main>} />
      <Route path="*" element={<main className="page"><section className="empty"><h1>Page not found</h1><p>This link does not lead to an available page. Choose where to continue.</p><div className="actions"><NavLink className="secondary" to="/history">Open Audit History</NavLink><NavLink className="secondary" to="/new-audit">Start a new audit</NavLink></div></section></main>} />
    </Routes></Suspense>
  </div>;
}

export default function App(){return <AccessBoundary>{(signOut,signingOut)=><AppShell signOut={signOut} signingOut={signingOut}/>}</AccessBoundary>;}
