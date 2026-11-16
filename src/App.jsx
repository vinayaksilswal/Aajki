import { useEffect, useState } from 'react';
import { Outlet, NavLink, Link } from 'react-router-dom';
import { api, getToken } from './api.js';

const tabs = [
  { to: '/', ic: '🗳️', label: 'Polls', end: true },
  { to: '/home', ic: '🏠', label: 'Home' },
  { to: '/stories', ic: '📰', label: 'Stories' },
  { to: '/leaderboards', ic: '🏆', label: 'Boards' },
  { to: '/login', ic: '👤', label: 'Account' },
];

export default function App() {
  const [balance, setBalance] = useState(null);

  useEffect(() => {
    // Show the coin balance when logged in (home payload carries it).
    if (!getToken()) return;
    api.home().then((h) => setBalance(h?.balance ?? null)).catch(() => {});
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="logo" style={{ textDecoration: 'none', color: 'inherit' }}>
          <span className="dot">A</span> Aajki
        </Link>
        <span className="coin-pill"><span className="c">◎</span> {balance ?? 0}</span>
      </header>

      <main className="content"><Outlet /></main>

      <nav className="nav">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end}
            className={({ isActive }) => (isActive ? 'active' : '')}>
            <span className="ic">{t.ic}</span>{t.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
