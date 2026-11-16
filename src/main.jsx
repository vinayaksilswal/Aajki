import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import './styles.css';
import App from './App.jsx';
import Feed from './screens/Feed.jsx';
import Home from './screens/Home.jsx';
import Stories from './screens/Stories.jsx';
import Leaderboards from './screens/Leaderboards.jsx';
import PollDetail from './screens/PollDetail.jsx';
import Topic from './screens/Topic.jsx';
import Story from './screens/Story.jsx';
import Board from './screens/Board.jsx';
import Login from './screens/Login.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Feed />} />
          <Route path="home" element={<Home />} />
          <Route path="stories" element={<Stories />} />
          <Route path="leaderboards" element={<Leaderboards />} />
          <Route path="poll/:id" element={<PollDetail />} />
          <Route path="topic/:id" element={<Topic />} />
          <Route path="story/:id" element={<Story />} />
          <Route path="board/:id" element={<Board />} />
          <Route path="login" element={<Login />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  </React.StrictMode>
);
