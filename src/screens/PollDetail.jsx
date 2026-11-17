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
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    let alive = true;
    setPoll(null); setError(null); setComments(null); setDraft('');
    api.poll(id).then((p) => { if (alive) setPoll(p); }).catch((e) => { if (alive) setError(e); });
    api.pollComments(id).then((c) => { if (alive) setComments(c.items || []); }).catch(() => {});
    return () => { alive = false; };
  }, [id]);

  async function postComment(e) {
    e.preventDefault();
    const body = draft.trim();
    if (!body || posting) return;
    setPosting(true);
    try {
      const added = await api.addComment(id, body);
      setComments((prev) => [added, ...(prev || [])]);
      setDraft('');
    } catch (err) {
      setError(err);
    } finally {
      setPosting(false);
    }
  }

  return (
    <>
      <button className="back" onClick={() => navigate(-1)}>← Back</button>
      {error && <ErrorBox error={error} />}
      {!poll && !error && <Spinner />}
      {poll && (
        <>
          <Poll poll={poll} showDetailLink={false} />
          {poll.description && <p className="note">{poll.description}</p>}
          <h3 style={{ margin: '18px 2px 8px', fontSize: '1rem' }}>Comments</h3>
          <form className="comment-form" onSubmit={postComment}>
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)}
              placeholder="Add a comment…" rows={2} maxLength={1000} />
            <button className="btn" type="submit" disabled={posting || !draft.trim()}>
              {posting ? 'Posting…' : 'Post'}
            </button>
          </form>
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
