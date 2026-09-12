# Hanburger-xlh.github.io

个人网站（GitHub Pages），包含 **文章 / 常用网址 / 图片 / B站动态** 四个板块。

## B站动态自动抓取（本地每日方案）

网站“动态”Tab 展示你关注的 B 站 UP 主动态。数据来自仓库里的 `bili.json`，
由脚本抓取生成并提交到仓库。

> 为什么不用 GitHub Actions 定时抓？
> GitHub 托管 runner 的机房 IP 会被 B 站反爬风控（返回 HTTP 412），**抓不到数据**。
> 因此改为：在本机放一个“开机登录自动运行”的启动项，**电脑每天自动开机（约 7 点，配合
> 游戏日常）登录那一刻抓一次**（几秒完成），抓完写日志并自动 `git push` 更新 `bili.json`。
> 之后关机即可，不需要电脑一直开着。

### 文件说明

| 文件 | 作用 |
| --- | --- |
| `.github/scripts/crawl-bili.js` | 爬虫：WBI 签名抓取 UP 主动态，去重合并写入 `bili.json` |
| `bili-config.json` | 要追踪的 UP 主 UID 列表（在此增删） |
| `bili.json` | 抓取结果（自动生成，勿手改） |
| `bili-daily/run-bili.ps1` | 每日运行入口：同步→抓取→写日志→有更新自动 git push |
| `bili-daily/install-startup.cmd` | 一键把 `run-bili.ps1` 加进“启动”文件夹（**无需管理员/UAC**） |
| `bili-daily/install-startup.ps1` | 被上面的 .cmd 调用的建自启脚本 |
| `logs/bili-crawl.log` | 运行日志（自动生成，已被 `.gitignore` 排除，不入库） |
| `assistant-logs/parse-and-publish.js` | 解析三月七小助手日常日志，生成精简摘要写 `daily-log.json`（默认解析昨天，日常循环脚本会带 `--date 今天` 调用） |
| `daily-log.json` | 日常结果摘要（自动生成，账号 UID 已打码，保留最近 30 天） |
| `index.html` | “动态”“日常”Tab 与渲染逻辑 |

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

2. **注册开机自启（不用管理员，不用管 UAC）**：双击 `bili-daily\install-startup.cmd`。
   它把 `run-bili.ps1` 加入当前用户的**启动文件夹**，之后每次开机登录自动运行。
   验证：启动文件夹里出现 `B站动态每日抓取.lnk`。

3. **确保 git 推送凭据已缓存**：在本仓库目录手动执行一次 `git push`，让它记住凭据，
   之后自启脚本才能自动推送。

4. **手动测试一次**：
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File "bili-daily\run-bili.ps1"
   ```
   再打开 `logs/bili-crawl.log`，应看到 `[ok] uid=... 抓取 N 条`。

### 之后每天

电脑自动开机登录时，启动项会自动：拉取最新 → 抓 B 站动态 → 有新动态就提交并推送，
网站随之更新。运行过程都记在 `logs/bili-crawl.log`（无需电脑常开，跑完即关机）。

- 卸载：删除启动文件夹里的 `B站动态每日抓取.lnk`
  （启动文件夹：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`）

> 提示：B 站按 IP 风控，本机偶尔某账号返回 0 条属正常波动，多跑会收敛；脚本只在
> 真正抓到新动态时才提交，不会产生无意义的空提交。

## 日常日志（三月七小助手）

网站“日常”Tab 展示三月七小助手每天跑游戏日常的结果，数据来自 `daily-log.json`。

- **主流程（当天发布）**：`H:\file\March7thAssistant_v2.5.3\March7thAssistant_full\daily_loop.py`
  在跑完当天全部账号的日常后，会自动调用本仓库的
  `assistant-logs\parse-and-publish.js --date 今天` 生成 `daily-log.json`，
  然后 `git add daily-log.json` → `git commit` → `git pull --rebase --autostash` → `git push origin main`。
  push 到 `main` 即触发 GitHub Pages 构建，网站当天就能看到结果，不必等第二天开机。
  - 开关与仓库路径在 `daily_loop_settings.yaml`：`web_publish_enable` / `web_repo` / `web_branch`。
  - 只想测试发布链路（不跑日常、不关机）：
    `python daily_loop.py --web-test`
- **网络与代理**：本机 git 全局配置了 `http/https.proxy = 127.0.0.1:7897`，所有 git 操作默认走该代理。
  开机时若梯子没启动，推送会失败。因此 `daily_loop.py` 与 `run-bili.ps1` 都会先探测该代理端口：
  - 端口不可达 → 自动**改用直连**（`-c http.proxy= -c https.proxy=`）；
  - 端口可达但推送失败 → 每种方式**重试 3 次**（间隔 15 秒），最后再试直连。
  push 失败不影响关机；失败时本地提交会保留，可稍后手动 `git push`。
- **兜底**：每天早晨的 `run-bili.ps1` 仍会顺带重新解析**昨天**的
  `daily_loop_YYYYMMDD.log`（三月七小助手 logs 目录，见脚本顶部 `ASSISTANT_LOGS_DIR`）。
  同一日期会被覆盖重算，因此重复执行是安全的。
- 摘要内容：日期 + 每个账号成功/失败（**账号 UID 打码**，如 `109***660`）+ 耗时，
  只保留最近 30 天，避免仓库膨胀。
- 哪天电脑没开机/没跑就没有当天记录，属正常。
- 想手动补某一天：`node assistant-logs\parse-and-publish.js --date 2026-09-05`

> 隐私：网站是公开的，因此只上传打码摘要，不上传含完整账号/密码的原始日志。

## 手动抓一次

```bash
node .github/scripts/crawl-bili.js          # 只抓取，写 bili.json
powershell -File "bili-daily\run-bili.ps1"  # 抓取 + 写日志 + 自动同步推送
```
