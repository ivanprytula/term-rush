# Term Rush — web client

React 19 + Vite + TypeScript + Tailwind v4. Talks to the game service
(`services/game`) via a typed client generated from its OpenAPI schema.

## Development

```bash
npm install
npm run dev
```

The dev server proxies `/game-rounds` and `/terms` to `localhost:8000` (see
`vite.config.ts`) — run the game service separately.

## UI tests

Playwright specs in `ui/` cover Classic and Sprint mode against a
**mocked** backend (route interception in `ui/mocks.ts`). These are
browser tests, not full end-to-end: the network boundary is faked, so
they prove the frontend's own state machine (mode toggle, round
lifecycle, countdown, play-again) — not that it matches the real API's
contract. A real API shape change (a renamed field, say) would pass here
and still break in production; that gap is open, not covered by any
suite yet.

```bash
npx playwright install chromium   # once
npm run test:ui
```

`playwright.config.ts` builds and serves the production bundle
(`vite preview`) rather than the dev server, so a test failure reflects
what ships.

## Regenerating the API client

After changing an endpoint in `services/game`, refresh `openapi.json` and
regenerate `src/client/`:

```bash
cd ../.. && PYTHONPATH=services/game uv run python -c \
  "from game_service.api.app import app; import json
print(json.dumps(app.openapi()))" \
  > services/web/openapi.json
cd services/web && npm run generate-client
```
