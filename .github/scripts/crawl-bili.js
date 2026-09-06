/**
 * crawl-bili.js
 * 抓取 B 站(哔哩哔哩)用户空间动态，合并写入 bili.json。
 * 由 .github/workflows/bili.yml 每小时在 GitHub Actions 上运行。
 *
 * 设计要点：
 *  - 使用现行接口 /x/polymer/web-dynamic/v1/feed/space，带 WBI 签名参数。
 *  - 匿名(仅 buvid3)请求经常被 B 站风控返回 -352/412，此时若在仓库 Secrets
 *    配置了 BILI_SESSDATA(你自己的账号 cookie 值)，会带上 SESSDATA 重试。
 *  - 任何一次抓取失败都不会覆盖已有数据、不会让工作流报错：脚本以 0 退出，
 *    只在确实拿到新数据时才改写 bili.json，从而避免每个小时产生空提交。
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..', '..');
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// ---------- 工具 ----------
function log(...a) { console.log(new Date().toISOString(), ...a); }

function readJsonSafe(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch { return null; }
}

async function httpJson(url, cookieHeader) {
  const headers = {
    'User-Agent': UA,
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
  };
  if (cookieHeader) headers['Cookie'] = cookieHeader;

  const res = await fetch(url, { headers });
  const text = await res.text();
  if (!res.ok) throw new Error('HTTP ' + res.status);
  let json;
  try { json = JSON.parse(text); }
  catch { throw new Error('非 JSON 响应(可能被风控/拦截): ' + text.slice(0, 120)); }
  return json;
}

// ---------- Cookie 获取 ----------
async function getCookies() {
  // 1) 先看仓库 Secrets 里有没有显式给出 buvid3/SESSDATA
  const env = process.env;
  let buvid3 = env.BILI_BUVID3 || '';
  let buvid4 = env.BILI_BUVID4 || '';
  const sessdata = env.BILI_SESSDATA || '';

  // 2) 否则向官方 spi 接口要一个真实的 buvid3/buvid4
  if (!buvid3) {
    try {
      const spi = await httpJson('https://api.bilibili.com/x/frontend/finger/spi', '');
      if (spi && spi.data) { buvid3 = spi.data.b_3 || ''; buvid4 = spi.data.b_4 || ''; }
    } catch (e) { log('[warn] 获取 buvid 失败:', e.message); }
  }

  const parts = [];
  if (buvid3) parts.push('buvid3=' + buvid3);
  if (buvid4) parts.push('buvid4=' + buvid4);
  if (sessdata) parts.push('SESSDATA=' + sessdata);
  return { header: parts.join('; '), sessdata: !!sessdata };
}

// ---------- WBI 签名 ----------
const MIXIN_KEY_ENC_TAB = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
  27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
  37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
  22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
];

function getMixinKey(orig) {
  let res = '';
  for (const i of MIXIN_KEY_ENC_TAB) res += orig[i];
  return res.slice(0, 32);
}

async function getWbiKeys(cookieHeader) {
  const nav = await httpJson('https://api.bilibili.com/x/web-interface/nav', cookieHeader);
  const wbi = nav.data && nav.data.wbi_img;
  if (!wbi) throw new Error('取不到 wbi_img');
  const key = (u) => u.slice(u.lastIndexOf('/') + 1).split('.')[0];
  return { img_key: key(wbi.img_url), sub_key: key(wbi.sub_url) };
}

function signedParams(params, img_key, sub_key) {
  const mixinKey = getMixinKey(img_key + sub_key);
  params.wts = Math.round(Date.now() / 1000);
  const query = Object.keys(params)
    .filter((k) => /^[a-zA-Z0-9_.-]+$/.test(k))
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&');
  params.w_rid = crypto.createHash('md5').update(query + mixinKey).digest('hex');
  return params;
}

// ---------- 抓取单个 UP 主动态 ----------
async function fetchSpaceDynamics(uid, cookieHeader, imgKey, subKey) {
  const base = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space';
  const params = {
    host_mid: uid,
    platform: 'web',
    timezone_offset: -480,
    features: 'itemOpusStyle',
  };
  if (imgKey && subKey) signedParams(params, imgKey, subKey); // 原地补上 wts/w_rid
  const qs = new URLSearchParams(params).toString();
  const json = await httpJson(base + '?' + qs, cookieHeader);
  if (json.code !== 0) {
    const err = new Error(`B站返回 code=${json.code} ${json.message || ''}`);
    err.code = json.code;
    throw err;
  }
  return (json.data && json.data.items) || [];
}

function normalizeItem(raw, configName) {
  const modules = raw.modules || {};
  const author = modules.module_author || {};
  const md = modules.module_dynamic || {};
  const major = md.major || {};
  const desc = (md.desc && md.desc.text) || '';

  const id = String(raw.id || raw.id_str || '');
  if (!id) return null;

  let title = '';
  let kind = '';
  let cover = '';
  if (major.archive) {
    title = major.archive.title || '';
    cover = major.archive.cover || '';
    kind = '动态·视频';
  } else if (major.opus) {
    title = major.opus.title || (major.opus.summary && major.opus.summary.text) || '';
    const pics = major.opus.pics || [];
    if (pics.length && pics[0].url) cover = pics[0].url;
    kind = '动态·图文';
  } else if (major.draw) {
    const items = major.draw.items || [];
    if (items.length) cover = items[0].src || '';
    kind = '动态·图片';
  } else if (major.article) {
    title = (major.article.title) || '';
    kind = '动态·专栏';
  } else if (major.live_rcmd) {
    title = '正在直播';
    kind = '动态·直播';
  } else if (md.orig) {
    // 转发内容
    kind = '动态·转发';
  } else {
    kind = '动态';
  }

  const textParts = [];
  if (title && title !== desc) textParts.push(title);
  if (desc && desc !== title) textParts.push(desc);
  const text = textParts.join('\n') || '（无文字内容）';

  return {
    id,
    uid: author.mid ? String(author.mid) : raw.config && raw.config.uid ? String(raw.config.uid) : configName,
    author: author.name || '',
    avatar: up(author.face),
    kind,
    text,
    cover: up(cover),
    url: 'https://t.bilibili.com/' + id,
    ts: author.pub_ts || 0,
  };
}

// 有些图片地址是 http://，GitHub Pages 是 https，浏览器会拦掉 http 图片(混合内容)，统一升成 https
function up(u) {
  return typeof u === 'string' && /^http:\/\//.test(u) ? 'https://' + u.slice(7) : u;
}

// ---------- 主流程 ----------
async function main() {
  const cfg = readJsonSafe(path.join(ROOT, 'bili-config.json'));
  if (!cfg || !Array.isArray(cfg.users) || cfg.users.length === 0) {
    log('[error] bili-config.json 缺少 users');
    return 0;
  }

  const outFile = path.join(ROOT, cfg.output || 'bili.json');
  const existing = readJsonSafe(outFile) || { items: [] };
  const seen = new Set((existing.items || []).map((i) => i.id));
  const merged = [...(existing.items || [])];
  const perLimit = cfg.perUserLimit || 20;
  let changed = false;

  let cookie;
  try { cookie = await getCookies(); }
  catch (e) { cookie = { header: '', sessdata: false }; }
  log('cookie: sessdata=' + cookie.sessdata + '  buvid=' + (cookie.header.includes('buvid3') ? 'yes' : 'no'));

  let imgKey = null, subKey = null;
  try { const k = await getWbiKeys(cookie.header); imgKey = k.img_key; subKey = k.sub_key; }
  catch (e) { log('[warn] WBI keys 获取失败，将尝试不带签名:', e.message); }

  for (const user of cfg.users) {
    const uid = String(user.uid);
    const name = user.name || '';
    try {
      const items = await fetchSpaceDynamics(uid, cookie.header, imgKey, subKey);
      let fresh = 0;
      for (const raw of items) {
        const norm = normalizeItem(raw, name || uid);
        if (!norm) continue;
        if (!seen.has(norm.id)) { seen.add(norm.id); merged.push(norm); changed = true; fresh++; }
      }
      log(`[ok] uid=${uid} 抓取 ${items.length} 条，新增 ${fresh} 条`);
    } catch (e) {
      if (e.code === -352 || e.code === -412) {
        log(`[skip] uid=${uid} 触发风控(${e.code})。若未配置 BILI_SESSDATA，请在仓库 Secrets 添加自己的 SESSDATA cookie 后再试。`);
      } else {
        log(`[skip] uid=${uid} 抓取失败: ${e.message}`);
      }
      continue;
    }
    // 抓取间隔，避免过快触发风控
    await new Promise((r) => setTimeout(r, 800));
  }

  // 按 uid 分组截断到 perLimit，再整体按时间倒序
  const byUid = {};
  for (const it of merged) (byUid[it.uid] = byUid[it.uid] || []).push(it);
  let trimmed = [];
  for (const uid of Object.keys(byUid)) {
    byUid[uid].sort((a, b) => b.ts - a.ts);
    trimmed = trimmed.concat(byUid[uid].slice(0, perLimit));
  }
  trimmed.sort((a, b) => b.ts - a.ts);
  // 统一把所有历史条目的图片地址也升到 https，避免混入 http://(会被浏览器拦)
  trimmed = trimmed.map((it) => ({ ...it, avatar: up(it.avatar), cover: up(it.cover) }));

  if (!changed) { log('无新动态，无需更新'); return 0; }

  const output = {
    source: cfg.source || 'bilibili',
    updatedAt: new Date().toISOString(),
    note: '由 .github/scripts/crawl-bili.js 通过 GitHub Actions 每小时自动生成，勿手工编辑。',
    items: trimmed,
  };
  fs.writeFileSync(outFile, JSON.stringify(output, null, 2), 'utf8');
  log(`已写入 ${outFile}，共 ${trimmed.length} 条`);
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => { log('[error]', e); process.exit(0); });
