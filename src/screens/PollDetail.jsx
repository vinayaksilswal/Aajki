import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { Poll, Spinner, ErrorBox, Empty } from '../components.jsx';

export default function PollDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [poll, setPoll] = useState(null);
  const [comments, setComments] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setPoll(null); setError(null);
    api.poll(id).then((p) => { if (alive) setPoll(p); }).catch((e) => { if (alive) setError(e); });
    api.pollComments(id).then((c) => { if (alive) setComments(c.items || []); }).catch(() => {});
    return () => { alive = false; };
  }, [id]);

  return (
    <>
      <button className="back" onClick={() => navigate(-1)}>← Back</button>
      {error && <ErrorBox error={error} />}
      {!poll && !error && <Spinner />}
      {poll && (
        <>
          <Poll poll={poll} showDetailLink={false} />
          {poll.description && <p className="note">{poll.description}</p>}
          <h3 style={{ margin: '18px 2px 4px', fontSize: '1rem' }}>Comments</h3>
          {!comments && <Spinner />}
          {comments && comments.length === 0 && <Empty>No comments yet.</Empty>}
          {comments && comments.map((c, i) => (
            <div className="comment" key={c.id || i}>
              <div className="who">{c.author?.name || c.author || 'User'}</div>
              <div>{c.body || c.text}</div>
            </div>
          ))}
        </>
      )}
    </>
  );
}
