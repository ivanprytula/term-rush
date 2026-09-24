FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

RUN npm ci --prefer-offline --no-audit || npm install

COPY . .

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD wget -q -O- http://127.0.0.1:5173/ || exit 1

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
