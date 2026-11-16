import { useEffect, useState, useCallback } from 'react';
import { api, categoryPolls, listCategories } from '../api.js';
import { Poll, Spinner, ErrorBox, Empty } from '../components.jsx';

export default function Feed() {
  const [cats, setCats] = useState(['all']);
  const [category, setCategory] = useState('all');
  const [polls, setPolls] = useState(null);
  const [cursor, setCursor] = useState(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { listCategories().then((c) => setCats(['all', ...c])).catch(() => {}); }, []);

  useEffect(() => {
    let alive = true;
    setPolls(null); setError(null); setCursor(null);
    const load = category === 'all'
      ? api.feed().then((r) => { if (alive) { setPolls((r.items || []).map((i) => i.poll).filter(Boolean)); setCursor(r.next_cursor || null); } })
      : categoryPolls(category).then((ps) => { if (alive) { setPolls(ps); setCursor(null); } });
    load.catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [category]);

  const loadMore = useCallback(() => {
    if (!cursor || more || category !== 'all') return;
    setMore(true);
    api.feed(undefined, cursor)
      .then((r) => { setPolls((prev) => [...(prev || []), ...(r.items || []).map((i) => i.poll).filter(Boolean)]); setCursor(r.next_cursor || null); })
      .catch(setError).finally(() => setMore(false));
  }, [cursor, more, category]);

  return (
    <>
      <h1 className="page-title">Polls</h1>
      <div className="chips">
        {cats.map((c) => (
          <button key={c} className={`chip ${c === category ? 'active' : ''}`} onClick={() => setCategory(c)}>{c}</button>
        ))}
      </div>
      {error && <ErrorBox error={error} />}
      {!polls && !error && <Spinner />}
      {polls && polls.length === 0 && <Empty>No polls in “{category}”.</Empty>}
      {polls && polls.map((p, i) => <Poll key={p.id || i} poll={p} />)}
      {polls && cursor && category === 'all' && (
        <button className="load-more" onClick={loadMore} disabled={more}>{more ? 'Loading…' : 'Load more'}</button>
      )}
    </>
  );
}
