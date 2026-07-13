# 自建 RSSHub 指南（获取实时 Twitter/X feed）

公共 RSS 源的痛点：

- **Nitter 镜像**（xcancel、nitter.net 等）：免费无需部署，但 RSS 端同步有延迟，
  实测约 **15 分钟**，且公共实例时常限流或下线。
- **rsshub.app 公共实例**：Twitter 路由已下线（404），且官方声明仅供测试、
  不可用于生产（403）。

想要**低延迟、稳定、可控**的 Twitter feed，最可靠的方式是自建 RSSHub 实例。
本文用 Docker 部署，并配置 Twitter 路由所需的认证。

## 前置条件

- 一台能常年运行的机器（本地、NAS 或 VPS 均可）
- 已安装 Docker 与 Docker Compose
- 一个**可用于抓取的 X(Twitter) 账号**（建议用小号，有被限制风险）

## 一、获取 Twitter auth_token

RSSHub 的 Twitter 路由需要登录态 Cookie 中的 `auth_token`：

1. 用浏览器登录 [x.com](https://x.com)（建议用小号）。
2. 打开开发者工具（F12）→ **Application/应用** → **Cookies** → `https://x.com`。
3. 找到名为 `auth_token` 的 Cookie，复制它的值（一长串十六进制字符）。
4. 如需多个账号轮换以降低被限流概率，可准备多个 `auth_token`，用逗号分隔。

> 注意：`auth_token` 等同于该账号的登录凭证，务必妥善保管，不要泄露或提交到 git。

## 二、docker-compose 配置

在任意目录创建 `docker-compose.yml`：

```yaml
services:
  rsshub:
    image: diygod/rsshub:latest
    restart: unless-stopped
    ports:
      - "1200:1200"
    environment:
      NODE_ENV: production
      # 缓存时间（秒）。调小可降低延迟，但会增加对上游的请求频率
      CACHE_EXPIRE: 300
      # Twitter 认证：填你的 auth_token，多个用逗号分隔
      TWITTER_AUTH_TOKEN: "在此填入你的_auth_token"
      # 可选：用 Redis 做缓存（不配则用内存缓存，重启丢失）
      REDIS_URL: "redis://redis:6379/"
    depends_on:
      - redis

  redis:
    image: redis:alpine
    restart: unless-stopped
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

启动：

```bash
docker compose up -d
```

查看日志确认正常：

```bash
docker compose logs -f rsshub
```

## 三、验证 Twitter 路由

在浏览器或用 curl 访问（本机部署时用 localhost）：

```bash
curl -s "http://localhost:1200/twitter/user/elonmusk" | head -c 500
```

看到 `<?xml ... <rss ...` 开头的内容即成功。若返回错误，多为 `auth_token`
失效或被限流，换一个账号的 token 重试。

## 四、接入 X_monitor

编辑项目根目录的 `.env`，把 `RSS_BASE_URL` 指向你的 RSSHub 实例：

```dotenv
# 本机部署
RSS_BASE_URL=http://localhost:1200/twitter/user/{username}

# 部署在其它主机（换成实际地址/域名）
# RSS_BASE_URL=https://rsshub.你的域名.com/twitter/user/{username}
```

也可以把自建实例与 Nitter 镜像一起配置，形成多级备援（自建优先，失败回退到公共镜像）：

```dotenv
RSS_BASE_URL=http://localhost:1200/twitter/user/{username},https://xcancel.com/{username}/rss
```

> X_monitor 会按顺序尝试各镜像，第一个成功返回内容的即被采用（见 `rss_monitor.py` 的
> `fetch_first_available`）。

保存后重启监听：

```bash
python3 rss_monitor.py
```

## 五、降低延迟与被限流的建议

- **`CACHE_EXPIRE`**：RSSHub 默认缓存较长。设为 300（5 分钟）可兼顾实时性与请求压力；
  想更实时可再调小，但过小会增加被 X 限流的风险。
- **X_monitor 的 `POLL_INTERVAL`**：轮询间隔应 ≥ RSSHub 的缓存时间，否则拿到的还是缓存。
- **多 token 轮换**：`TWITTER_AUTH_TOKEN` 配多个（逗号分隔）可分摊单账号的限流。
- **用小号**：抓取账号有被 X 风控的可能，不要用主力账号。

## 六、安全提醒

- `auth_token` 和 `.env` 都含敏感凭证，**切勿提交到 git**。
- 若把 RSSHub 暴露到公网，务必加访问控制（如反向代理 + Basic Auth，或
  RSSHub 的 `ACCESS_KEY` 环境变量），否则会被他人白嫖甚至滥用你的抓取账号。
- 参考官方文档：<https://docs.rsshub.app/>
