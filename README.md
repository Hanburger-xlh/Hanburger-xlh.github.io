# Hanburger-xlh.github.io

个人网站（GitHub Pages），包含 **文章 / 常用网址 / 图片 / B站动态** 四个板块。

## B站动态自动抓取

网站新增“动态”Tab：通过 **GitHub Actions 每小时** 抓取你关注的 B 站 UP 主动态，
结果写入 `bili.json`，前端读取展示。由于 GitHub Pages 是纯静态站，爬取必须在服务端
（GitHub Actions）完成，浏览器里无法定时爬 B 站。

### 工作原理

```
GitHub Actions(cron 每小时)
      │  node .github/scripts/crawl-bili.js
      ▼
B站空间动态接口(带 WBI 签名) ──► 合并去重 ──► 写回 bili.json ──(自动 commit)──► 仓库
                                                                              │
网站首页 JS 读取 bili.json ◄─────────────────────────────────────────────────┘
```

涉及文件：

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/bili.yml` | 每小时定时触发 + 手动触发，跑爬虫并提交 |
| `.github/scripts/crawl-bili.js` | 爬虫脚本：WBI 签名请求、抓取/去重/写入 |
| `bili-config.json` | 要追踪的 UP 主 UID 列表（在这里增删） |
| `bili.json` | 抓取结果（自动生成，勿手改） |
| `index.html` | 新增“动态”Tab 与渲染/筛选逻辑 |

### 配置要追踪的 UP 主

编辑仓库根目录的 `bili-config.json`，把想关注的 UP 主 UID 填进 `users`：

```json
{
  "users": [
    { "uid": "2127596945", "name": "（可选，不填会自动取昵称）" }
  ],
  "perUserLimit": 20
}
```

UID 数字在对应 UP 主空间主页网址的 `/数字` 里能找到。

### 首次部署步骤

1. 把本仓库改动提交并 `git push` 到 GitHub（默认分支 `main`）。
2. 到仓库 **Actions** 页面，手动运行一次 **Fetch Bilibili Dynamics**
   （右侧 *Run workflow*），确认日志显示 `[ok]` 且自动 commit 生成 `bili.json`。
3. 之后会每小时整点自动跑一次；无新动态时不产生空提交。

### 关于 B 站风控（重要）

B 站会拦截匿名/机房 IP（返回 `-352`/`412`）。脚本已用 **WBI 签名**处理，绝大多数情况下
匿名也能抓到（本仓库就是匿名测试成功的）。但若某个账号持续返回 `-352`、抓不到数据，
推荐添加两个 **仓库 Secrets**（`Settings → Secrets and variables → Actions`），用你自己
浏览器登录 bilibili.com 后的 cookie 值：

- `BILI_SESSDATA`：cookie 里的 `SESSDATA` 值（最关键）
- `BILI_BUVID3`：cookie 里的 `buvid3`（可选，不填会自动申请）

> 隐私提示：`SESSDATA` 等同你账号的登录凭证，仅存进 GitHub Secret 即可，不要写进代码或
> `bili.json`。建议用一个不太重要的账号。此实现不依赖登录也能跑，加它是为更稳。

### 抓取频率

`cron: '0 * * * *'` 表示每小时整点一次。注意 GitHub 只对“近 60 天有活动”的仓库执行定时任务；
平时页面有人访问即算活动，正常不会停。想临时改频，编辑 `.github/workflows/bili.yml` 里的
`schedule` 即可（GitHub 定时最小间隔约 5 分钟）。

## 本地开发

```bash
node .github/scripts/crawl-bili.js   # 本地手动抓一次（会自动更新 bili.json）
```
