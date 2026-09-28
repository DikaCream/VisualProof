import { Link, NavLink, Route, Routes } from "react-router-dom";
import { VisualProofProvider, useVisualProof } from "./context/VisualProofContext";
import { ChainNotice, TxBanner, WalletButton } from "./components/Chrome";
import { Board } from "./pages/Board";
import { AttestationPage } from "./pages/AttestationPage";
import { NewAttestation } from "./pages/NewAttestation";
import { HowItWorks } from "./pages/HowItWorks";
import { formatGen } from "./config";

function Bar() {
  const { stats } = useVisualProof();
  return (
    <header className="bar">
      <Link to="/" className="brand">
        <span className="mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="22" height="22" fill="none">
            <rect x="4.5" y="8" width="23" height="16" rx="2.5" stroke="currentColor" strokeWidth="2.2" />
            <circle cx="16" cy="16" r="4.2" stroke="currentColor" strokeWidth="2.2" />
            <path d="M16 4.5v3M16 24.5v3" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
        </span>
        <span className="brand-text">
          <strong>VisualProof</strong>
          <em>what a page shows, decided by consensus</em>
        </span>
      </Link>

      <nav className="bar-nav" aria-label="Main">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "on" : "")}>
          Attestations
        </NavLink>
        <NavLink to="/new" className={({ isActive }) => (isActive ? "on" : "")}>
          Request
        </NavLink>
        <NavLink to="/how" className={({ isActive }) => (isActive ? "on" : "")}>
          How it works
        </NavLink>
      </nav>

      <div className="bar-meters">
        <span className="mini mono">{stats.attestations} requested</span>
        <span className="mini mono">{formatGen(stats.rewarded)} GEN paid to verifiers</span>
      </div>

      <WalletButton />
    </header>
  );
}

function Footer() {
  const { stats, error, wallet } = useVisualProof();
  return (
    <footer className="foot">
      <span>
        {stats.attested} attested · {stats.confirmed} confirmed · {stats.refuted} refuted ·{" "}
        {stats.overturned} corrected
      </span>
      {error && <span className="bad">contract unreadable: {error}</span>}
      <span className="mono">GenLayer StudioNet</span>
      {wallet.address ? <span className="mono">{wallet.address.slice(0, 8)}...</span> : null}
    </footer>
  );
}

function Shell() {
  const { wallet } = useVisualProof();
  return (
    <div className="shell">
      <Bar />
      <TxBanner />
      <ChainNotice chainId={wallet.chainId} />
      <main>
        <Routes>
          <Route path="/" element={<Board />} />
          <Route path="/attestations/:id" element={<AttestationPage />} />
          <Route path="/new" element={<NewAttestation />} />
          <Route path="/how" element={<HowItWorks />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}

export default function App() {
  return (
    <VisualProofProvider>
      <Shell />
    </VisualProofProvider>
  );
}
