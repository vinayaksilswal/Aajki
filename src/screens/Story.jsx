import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../api.js';
import { Poll, Spinner, ErrorBox, Empty } from '../components.jsx';
import { cacheStories, getCachedStory } from './storyCache.js';

export default function Story() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [story, setStory] = useState(() => getCachedStory(id));
  const [error, setError] = useState(null);

  useEffect(() => {
    if (story) return;
    // Cold cache (direct link): refetch the daily edition and find this story.
    api.storiesDaily()
      .then((d) => { cacheStories(d.stories || []); const s = (d.stories || []).find((x) => x.id === id);
        if (s) setStory(s); else setError(new Error('Story not in the current edition.')); })
      .catch(setError);
  }, [id, story]);

  if (error) return <><button className="back" onClick={() => navigate(-1)}>← Back</button><ErrorBox error={error} /></>;
  if (!story) return <><button className="back" onClick={() => navigate(-1)}>← Back</button><Spinner /></>;

  const cover = story.cover || {};
  const sections = Array.isArray(story.context) ? story.context : [];
  return (
    <>
      <button className="back" onClick={() => navigate(-1)}>← Back</button>
      <div className="kicker" style={{ color: 'var(--accent)' }}>{(story.desk || story.shelf || '').replace(/_/g, ' ')}</div>
      <h1 className="page-title" style={{ marginTop: 4 }}>{cover.hook || cover.alt || story.path}</h1>
      {cover.image_key && <img className="cover" src={cover.image_key} alt={cover.alt || ''} />}

      {sections.map((sec, i) => (
        <div className="tile" key={i}>
          {sec.label && <div className="kicker">{sec.label}</div>}
          {sec.visual?.image_key && <img className="cover" src={sec.visual.image_key} alt={sec.visual.alt || ''} loading="lazy" style={{ marginTop: 8 }} />}
          {sec.body && <p style={{ color: 'var(--text)', lineHeight: 1.5 }}>{sec.body}</p>}
        </div>
      ))}

      <div className="section-label">QUESTIONS</div>
      {(!story.questions || story.questions.length === 0) && <Empty>No questions on this story.</Empty>}
      {story.questions?.map((q) => <Poll key={q.id} poll={{ ...q, category: null }} />)}
    </>
  );
}
