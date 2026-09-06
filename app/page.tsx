import Link from 'next/link';

export default function Home() {
  return (
    <main className="shell">
      <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>XAU/USD GOLD INTELLIGENCE</h1><div className="muted">Live market analysis + VCPR + broadcast control</div></div></div></div>
      <div className="panel card">
        <h2 style={{marginTop:0}}>Dashboard routes</h2>
        <div className="nav"><Link href="/dashboard">Dashboard</Link><Link href="/broadcast">OBS Broadcast</Link><Link href="/control">Control</Link></div>
        <p className="muted">The first version uses a demo feed. The MT4 bridge will replace the feed without changing the dashboard routes or VCPR rendering model.</p>
      </div>
    </main>
  );
}
