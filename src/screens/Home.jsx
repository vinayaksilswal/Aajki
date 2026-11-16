import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Spinner, ErrorBox, Empty, TopicCard } from '../components.jsx';

export default function Home() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.home().then(setData).catch(setError);
  }, []);

  if (error) return <><h1 className="page-title">Home</h1><ErrorBox error={error} /></>;
  if (!data) return <><h1 className="page-title">Home</h1><Spinner /></>;

  const topics = data.topics || [];
  const goal = data.goal;
  return (
    <>
      <h1 className="page-title">Today</h1>

      {(data.daily_remaining != null || goal) && (
        <div className="tile">
          <div className="kicker">Daily</div>
          <h3>{data.daily_remaining != null ? `${data.daily_remaining} polls left today` : 'Daily goal'}</h3>
          {goal && (
            <>
              <p>{goal.label || `${goal.current ?? 0} / ${goal.target ?? 0} coins`}</p>
              <div className="bar"><div className="bar-fill"
                style={{ width: `${goal.target ? Math.min(100, Math.round((goal.current || 0) * 100 / goal.target)) : 0}%` }} /></div>
            </>
          )}
        </div>
      )}

      <div className="section-label">TRENDING TOPICS</div>
      {topics.length === 0 && <Empty>No topics right now.</Empty>}
      {topics.map((t) => <TopicCard key={t.id} topic={t} />)}
    </>
  );
}
