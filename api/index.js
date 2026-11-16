// Vercel serverless entry. The whole Express backend runs as one function; vercel.json
// routes /api/* and /admin here, while the static frontend (dist/) is served by Vercel.
import { createApp } from '../server/app.mjs';

const app = createApp();
export default app;
