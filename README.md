# Hanburger-xlh.github.io

个人网站（GitHub Pages），包含 **文章 / 常用网址 / 图片 / B站动态** 四个板块。

## B站动态自动抓取（本地每日方案）

网站“动态”Tab 展示你关注的 B 站 UP 主动态。数据来自仓库里的 `bili.json`，
由脚本抓取生成并提交到仓库。

> 为什么不用 GitHub Actions 定时抓？
> GitHub 托管 runner 的机房 IP 会被 B 站反爬风控（返回 HTTP 412），**抓不到数据**。
> 因此改为：在本机注册一个“开机登录即运行”的计划任务，**每天开机（约 7 点，配合电脑
> 自动开机跑游戏日常）时抓一次**，抓完写日志并自动 `git push` 更新 `bili.json`。

### 文件说明

| 文件 | 作用 |
| --- | --- |
| `.github/scripts/crawl-bili.js` | 爬虫：WBI 签名抓取 UP 主动态，去重合并写入 `bili.json` |
| `bili-config.json` | 要追踪的 UP 主 UID 列表（在此增删） |
| `bili.json` | 抓取结果（自动生成，勿手改） |
| `bili-daily/run-bili.ps1` | 每日运行入口：同步→抓取→写日志→有更新自动 git push |
| `bili-daily/install-bili-task.bat` | 把 `run-bili.ps1` 注册成开机计划任务 |
| `logs/bili-crawl.log` | 运行日志（自动生成，已被 `.gitignore` 排除，不入库） |
| `index.html` | “动态”Tab 与渲染/筛选逻辑 |

### 一次性配置（只需做一次）

1. **配置要追踪的 UP 主**：编辑根目录 `bili-config.json` 的 `users`，填 UID。
   例：
   ```json
   {
     "users": [
       { "uid": "2127596945", "name": "（可选，不填自动取昵称）" }
     ],
     "perUserLimit": 20
   }
   ```
   UID 数字在对应 UP 主空间主页网址的 `/数字` 里能看到。

2. **注册每日计划任务**：右键 `bili-daily/install-bili-task.bat` → **以管理员身份运行**。
   它注册一个 `BiliCrawlDaily` 任务（`ONLOGON`，开机登录即触发）。

3. **确保 git 推送凭据已缓存**：在本仓库目录手动执行一次 `git push`，让它记住凭据，
   之后计划任务才能自动推送。

4. **手动测试一次**：
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File "bili-daily\run-bili.ps1"
   ```
   再打开 `logs/bili-crawl.log`，应看到 `[ok] uid=... 抓取 N 条`。

### 之后每天

电脑开机自动登录时，计划任务会自动：拉取最新 → 抓 B 站动态 → 有新动态就提交并推送，
网站随之更新。运行过程都记在 `logs/bili-crawl.log`。

- 查看任务：`schtasks /Query /TN BiliCrawlDaily /V /FO LIST`
- 卸载任务：管理员运行 `bili-daily\install-bili-task.bat uninstall`，
  或 `schtasks /Delete /TN BiliCrawlDaily /F`

> 提示：B 站按 IP 风控，本机偶尔某账号返回 0 条属正常波动，多跑会收敛；脚本只在
> 真正抓到新动态时才提交，不会产生无意义的空提交。

## 手动抓一次

```bash
node .github/scripts/crawl-bili.js          # 只抓取，写 bili.json
powershell -File "bili-daily\run-bili.ps1"  # 抓取 + 写日志 + 自动同步推送
```
