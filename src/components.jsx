import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getVote, setVote } from './vote.js';

export function Spinner() { return <div className="spinner" />; }
export function ErrorBox({ error }) {
  return <div className="err">{error?.message || 'Something went wrong.'}{error?.status ? ` (${error.status})` : ''}</div>;
}
export function Empty({ children }) { return <div className="state">{children}</div>; }
export const rupees = (paise) => (paise == null ? null : `₹${(paise / 100).toLocaleString('en-IN')}`);

// Interactive poll: results (percentages + bars) stay hidden until the viewer picks an
// option. Their choice is stored locally and counts toward the shown totals.
export function Poll({ poll, showDetailLink = true, compact = false }) {
  const [choice, setChoice] = useState(() => getVote(poll.id));
  const answered = choice != null;

  const base = (o) => (o.votes != null ? o.votes : (o.pct != null ? o.pct : 0));
  const rawTotal = poll.total_votes || poll.options?.reduce((s, o) => s + base(o), 0) || 0;
  // Count the viewer's own vote in the revealed numbers.
  const bump = answered ? 1 : 0;
  const total = rawTotal + bump;

  function pick(id) {
    if (answered) return;
    setChoice(id);
    setVote(poll.id, id);
  }

  return (
    <div className={`card${compact ? ' compact' : ''}`}>
      <div className="cat">{poll.category || poll.beat || 'poll'}{poll.trending ? ' · 🔥 trending' : ''}</div>
      <div className="q">{poll.question}</div>
      {poll.image_url && <img className="cover" src={poll.image_url} alt="" loading="lazy" />}

      <div className="options">
        {poll.options?.map((o) => {
          const mine = choice === o.id;
          const votes = base(o) + (mine ? 1 : 0);
          const pct = answered ? (total ? Math.round(votes * 100 / total) : 0) : 0;
          const tone = o.id === 'yes' ? 'yes' : o.id === 'no' ? 'no' : '';
          return (
            <button key={o.id} type="button" className={`opt ${tone}${answered ? ' revealed' : ''}${mine ? ' mine' : ''}`}
              onClick={() => pick(o.id)} disabled={answered}>
              {answered && <div className="fill" style={{ width: `${pct}%` }} />}
              <div className="row">
                <span className="label">{o.emoji ? `${o.emoji} ` : ''}{o.label}{mine ? ' ✓' : ''}</span>
                {answered && <span className="pct">{pct}%</span>}
              </div>
            </button>
          );
        })}
      </div>

      <div className="foot">
        {answered
          ? <span><b>{total}</b> votes</span>
          : <span className="tap-hint">Tap an option to see results</span>}
        {poll.comment_count != null && <span><b>{poll.comment_count || 0}</b> comments</span>}
        {poll.is_prediction && <span>🔮 prediction</span>}
        {poll.reward?.coins ? <span>◎ {poll.reward.coins}</span> : null}
        {showDetailLink && poll.id && <Link className="detail-link" to={`/poll/${poll.id}`}>Details →</Link>}
      </div>
    </div>
  );
}

// Topic card with cover image.
export function TopicCard({ topic }) {
  return (
    <Link to={`/topic/${topic.id}`} className="tile" style={{ display: 'block', textDecoration: 'none', color: 'inherit' }}>
      <div className="kicker">{topic.short_label || topic.category || 'Topic'}</div>
      {topic.image_url && <img className="cover" src={topic.image_url} alt="" loading="lazy" style={{ marginTop: 8 }} />}
      <h3>{topic.title}</h3>
      {topic.blurb && <p>{topic.blurb}</p>}
    </Link>
  );
}
