# Term Rush — web client

React 19 + Vite + TypeScript + Tailwind v4. Talks to the game service
(`services/game`) via a typed client generated from its OpenAPI schema.

## Development

```bash
npm install
npm run dev
```

The dev server proxies `/sessions` and `/terms` to `localhost:8000` (see
`vite.config.ts`) — run the game service separately.

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
