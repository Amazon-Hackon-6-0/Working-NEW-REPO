FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
ARG NEXT_PUBLIC_CAMPUSBUDDY_API_BASE_URL=http://127.0.0.1:8000

ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_CAMPUSBUDDY_API_BASE_URL=$NEXT_PUBLIC_CAMPUSBUDDY_API_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
