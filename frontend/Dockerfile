# 前端镜像 —— Next.js 15 多阶段构建
#
# 注意：NEXT_PUBLIC_* 变量在 next build 时内联进客户端产物，
# 必须通过 build arg 注入（服务器部署时改为 http://<服务器IP>:8000）：
#   docker build --build-arg NEXT_PUBLIC_API_BASE_URL=http://your-server:8000 ./frontend

FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# next start 需要 node_modules 中的 next 与生产依赖：按 lock 精确安装 prod 依赖（不含 devDependencies）
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/.next ./.next

EXPOSE 3000
CMD ["npm", "start"]
