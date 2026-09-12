# Hanburger-xlh.github.io

个人网站（GitHub Pages），包含 **文章 / 常用网址 / 图片 / B站动态** 四个板块。

## B站动态自动抓取（本地每日方案）

网站“动态”Tab 展示你关注的 B 站 UP 主动态。数据来自仓库里的 `bili.json`，
图片则下载到仓库的 `bili-img/`，由脚本抓取生成并提交到仓库。

> 为什么不用 GitHub Actions 定时抓？
> GitHub 托管 runner 的机房 IP 会被 B 站反爬风控（返回 HTTP 412），**抓不到数据**。
> 因此改为：由本机的游戏日常循环脚本（`daily_loop.py`）在**每天跑完游戏日常后**
> 顺带抓一次（几秒完成），与日常日志一起提交并 `git push`。电脑每天自动开机（约 7 点）、
> 跑完日常即关机，不需要电脑一直开着。
>
> 注：早期做法是用“启动文件夹”在**登录那一刻**抓，现已取消——开机瞬间梯子核心还在
> `mode: direct`（详见下文“网络与代理”），推送容易失败。

### 抓取到的内容

| 字段 | 说明 |
| --- | --- |
| `text` | 动态正文（图文动态取标题 + 摘要） |
| `cover` | **动态首图**。图文取第一张图、图片动态取第一张、视频取视频封面、专栏无图 |
| `avatar` | UP 主头像 |
| `bvid` / `durSec` | **仅视频动态**：稿件号与时长（秒），供视频下载脚本使用 |
| `video` | 已缓存的本地短视频路径（`bili-video/<bvid>.mp4`），未缓存则无此字段 |
| `url` | 动态页链接 `https://t.bilibili.com/<id>` |
| `kind` / `ts` / `author` / `uid` | 类型、发布时间戳、作者、UID |

> **B 站动态接口不提供视频文件地址**，只有视频**封面图**、`bvid` 与动态页链接。
> 要拿到视频文件必须另调 `playurl` 接口，见下节。

`cover` / `avatar` 原本是 B 站图床外链（`i0/i1/i2.hdslb.com`），
`bili-daily/fetch-bili-images.py` 会把它们下载到 `bili-img/` 并改写为站内相对路径，
使网站不依赖外链（外链受 B 站防盗链与可用性影响）。

### 短视频缓存 —— 已关闭

> **当前不下载任何视频。** 动态卡片**只保留封面图**（`cover`，已下载到 `bili-img/`）。
> 关闭开关有两层，任一层都能拦住下载：
> 1. `bili-config.json` → `"videoEnable": false`（脚本层：即便手动运行也只做清理）
> 2. `daily_loop_settings.yaml` → `web_cache_videos: false`（主流程层：根本不调用该脚本）
>
> 想恢复：两处都改回 `true`。下面保留原设计说明备查。

`bili-daily/fetch-bili-videos.py` 会用动态里的 `bvid` 去取播放地址并下载到 `bili-video/`：

```
动态 bvid → x/web-interface/view（取 cid 与真实时长）
          → x/player/playurl?qn=16&fnval=1（360P，audio+video 合一的 mp4）
          → 保存为 bili-video/<bvid>.mp4
```

若该视频拿不到合一的 mp4，则退回 DASH（`fnval=4048`）分别下载 360P 视频轨与音频轨，
再用 **ffmpeg** 合并（需本机有 ffmpeg）。

| 限制 | 值 | 原因 |
| --- | --- | --- |
| 总开关 | **`videoEnable`（当前 false）** | 关闭后脚本只清理旧文件，不下载 |
| 来源 UP | `videoUids`（当前 `["414149787"]`，Phigros官方） | 仅名单内 UP 的动态会下载视频 |
| 清晰度 | **360P** | 匿名即可获取（480P 也行，但体积翻倍） |
| 时长 | **≤5 分钟** | 480P 长视频单条实测可达 80+ MB，合并后超过 GitHub 单文件 **100 MB** 硬上限会被拒收 |
| 本地保留 | **7 天** | 超期文件删除并清空 `video` 字段（条目仍留在 `bili.json`） |
| 单次下载数 | 6 个 | 防止首次运行时突发批量 |

> ⚠️ **git 历史不可回收。** 这也是当初关闭视频下载的关键原因之一：删除 `bili-video/`
> 里的文件只影响工作区，历史中的字节永久保留。按实测频率（约每周 5 条、单条 5–18 MB）
> 曾预计每周增长 50–90 MB。若将来重新开启，建议定期用 `git filter-repo`
> 重写历史并 force push（破坏性操作）。

### 文件说明

| 文件 | 作用 |
| --- | --- |
| `.github/scripts/crawl-bili.js` | 爬虫：WBI 签名抓取 UP 主动态，去重合并写入 `bili.json`（视频条目会带上 `bvid`/`durSec`） |
| `bili-daily/fetch-bili-images.py` | 把 `bili.json` 里的图片下载到 `bili-img/`（转 WebP、按显示尺寸缩放），并清理不再引用的旧图 |
| `bili-img/` | 动态图片（`cover/` 封面、`avatar/` 头像）。**刻意不放 `pic/`**：`sync-gallery.js` 会把 `pic/` 的每个子目录当成相册分类 |
| `bili-daily/fetch-bili-videos.py` | 短视频下载（**当前已关闭**，`videoEnable: false`）。开启时下载 360P、≤5 分钟视频到 `bili-video/` 并保留 7 天 |
| `bili-config.json` | 要追踪的 UP 主 UID 列表、视频开关（`videoEnable` / `videoUids`）、每 UP 条数上限 |
| `bili.json` | 抓取结果（自动生成，勿手改） |
| `bili-daily/run-bili.ps1` | 手动/应急入口：同步→抓取→写日志→有更新自动 git push（日常主流程已内置抓取，此脚本仅供手动补跑） |
| `bili-daily/install-startup.cmd` / `.ps1` | 一键把 `run-bili.ps1` 加进“启动”文件夹（**已不推荐**：抓取已并入日常主流程） |
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
     "videoUids": ["414149787"],
     "perUserLimit": 20
   }
   ```
   UID 数字在对应 UP 主空间主页网址的 `/数字` 里能看到。
   `videoUids` 决定**哪些 UP 的动态会下载本地视频**（空/缺省 = 不限）。

2. **确保 git 推送凭据已缓存**：在本仓库目录手动执行一次 `git push`，让它记住凭据，
   之后脚本才能自动推送。

3. 图片缩放依赖 **Pillow**（`pip install pillow`）；缺失时会退回原图保存，不会中断流程。

> 抓取与发布现由游戏日常主流程负责，**不再需要注册启动项**。
> `bili-daily\install-startup.cmd` 保留仅作备用。

### 图片体积

按前端实际显示尺寸缩放（`index.html`：头像 `44x44`、封面 `max-height:220px`）：

| | 缩放前 | 缩放后（默认） |
| --- | --- | --- |
| 单张平均 | ~232 KB | ~40 KB（封面 43.5 / 头像 4.6） |
| 首批 74 张合计 | 16.8 MB | **2.91 MB** |

不缩放会让每天新增的二进制文件永久累积进 git 历史。如需调整，改 `fetch-bili-images.py`
顶部的 `MAX_COVER_PX` / `MAX_AVATAR_PX` / `QUALITY` 即可。

### 之后每天

游戏日常跑完后，由 `daily_loop.py` 自动：抓动态 → 下载图片 → 生成日常摘要 →
一次提交并推送，网站随之更新（详见下节）。

## 日常日志（三月七小助手）

网站“日常”Tab 展示三月七小助手每天跑游戏日常的结果，数据来自 `daily-log.json`。

- **主流程（当天一次跑完）**：`H:\file\March7thAssistant_v2.5.3\March7thAssistant_full\daily_loop.py`
  在跑完当天全部账号的日常后，会自动依次执行：

  1. `node .github/scripts/crawl-bili.js` —— 抓取 B 站动态，更新 `bili.json`
  2. `python bili-daily/fetch-bili-images.py` —— 下载动态图片到 `bili-img/`
  3. ~~`python bili-daily/fetch-bili-videos.py`~~ —— **已关闭**（`web_cache_videos: false`），不再下载视频
  4. `node assistant-logs/parse-and-publish.js --date 今天` —— 生成日常摘要 `daily-log.json`
  5. `git add -- bili.json daily-log.json bili-img bili-video` → `git commit` → `git pull --rebase --autostash` → `git push origin main`

  push 到 `main` 即触发 GitHub Pages 构建，网站当天就能看到结果。
  - 开关与仓库路径在 `daily_loop_settings.yaml`：
    `web_publish_enable` / `web_crawl_bili` / `web_cache_images` / `web_cache_videos` / `web_repo` / `web_branch`。
  - 只想测试发布链路（不跑日常、不关机）：`python daily_loop.py --web-test`
  - 抓取放在**日常跑完之后**，而不是开机登录时。原因：开机瞬间梯子核心
    （`com.vortex.helper` 服务）虽已在 7897 监听，但加载的是 `config.yaml` 的
    `mode: direct`，要等 GUI 客户端 `Cloudupup` 启动后才被切成 `mode: rule`；
    登录那一刻推送很容易撞上这个窗口而失败。日常跑完时（开机约 30 分钟后）代理已就绪。
  - 因此**原先放在启动文件夹的 `B站动态每日抓取.lnk` 已移出**
    （备份在 `%APPDATA%\StartupBackup\`），避免与本次运行重复抓取。
- **网络与代理**：本机 git 全局配置了 `http/https.proxy = 127.0.0.1:7897`，所有 git 操作默认走该代理。
  若代理端口不可达，脚本会自动**改用直连**（`-c http.proxy= -c https.proxy=`）；
  端口可达但推送失败时，每种方式**重试 3 次**（间隔 15 秒），最后再试直连。
  push 失败不影响关机；失败时本地提交会保留，可稍后手动 `git push`。
- 摘要内容：日期 + 每个账号成功/失败（**账号 UID 打码**，如 `109***660`）+ 耗时，
  只保留最近 30 天，避免仓库膨胀。
- 哪天电脑没开机/没跑就没有当天记录，属正常。
- 想手动补某一天：`node assistant-logs\parse-and-publish.js --date 2026-09-05`

> 隐私：网站是公开的，因此只上传打码摘要，不上传含完整账号/密码的原始日志。

## 手动跑一次

```bash
node .github/scripts/crawl-bili.js                       # 只抓取，写 bili.json
python bili-daily/fetch-bili-images.py                   # 只下载图片，写 bili-img/
python bili-daily/fetch-bili-videos.py --dry-run         # 视频已关闭；该命令只会提示"已关闭"
python bili-daily/fetch-bili-videos.py                   # 同上：只做清理，不下载
powershell -File "bili-daily\run-bili.ps1"               # 抓取 + 写日志 + 自动同步推送
```
