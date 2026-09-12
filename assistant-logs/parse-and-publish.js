/**
 * parse-and-publish.js
 * 解析三月七小助手(日常循环)的 daily_loop_YYYYMMDD.log，生成"精简摘要"并写入 daily-log.json。
 *
 * 设计：
 *  - 每次只处理一个日期(默认"昨天"，因为当天早晨跑时今天的日志还没写完)。
 *  - 账号 UID 一律打码(如 109***660)，避免公开页面泄露完整账号。
 *  - 只统计"真正开始运行"的账号(出现 `---------- 账号 X ----------` 标记)，
 *    完成/失败以对应标记为准；无实际运行的日期(如当天已完成过委托)会跳过。
 *  - 只保留最近 keepDays 天。
 *
 * 用法：
 *   node assistant-logs/parse-and-publish.js                # 处理昨天
 *   node assistant-logs/parse-and-publish.js --date 2026-09-05
 */

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..'); // assistant-logs 在仓库根，上一级即仓库根
// ↓ 改成三月七小助手(日常循环)的 logs 目录
const ASSISTANT_LOGS_DIR = 'H:/file/March7thAssistant_v2.5.3/March7thAssistant_full/logs';
const OUT_FILE = path.join(ROOT, 'daily-log.json');
const KEEP_DAYS = 30;

function log(...a) { console.log(new Date().toISOString(), ...a); }

function maskUid(u) {
  const s = String(u || '');
  if (s.length <= 4) return '***';
  return s.slice(0, 3) + '***' + s.slice(-3);
}

function readJsonSafe(f) {
  try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; }
}

function parseTime(str) {
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/.exec(str.trim());
  if (!m) return null;
  return new Date(m[1] + 'T' + m[2] + ':' + m[3] + ':' + m[4]).getTime();
}

function splitList(body) {
  return (body.match(/'([^']*)'/g) || []).map((s) => s.slice(1, -1));
}

function parseDailyFile(filePath, dateStr) {
  let lines;
  try { lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/); }
  catch { return null; }

  const firstStart = {};   // uid -> 首次开始 ts(ms)
  const lastStart = {};    // uid -> 最近一次开始 ts(ms)，补跑会覆盖
  const durMap = {};       // uid -> 最后一次尝试的耗时(秒)
  const outcomeTs = {};    // uid -> 完成/失败 ts(ms)
  const outcome = {};      // uid -> true/false
  const order = [];        // 真正出现的账号顺序
  const inOrder = {};
  let discovered = [];
  let successList = [];
  let failedList = [];
  let haveRun = false;

  const addOrder = (uid) => { if (!inOrder[uid]) { inOrder[uid] = true; order.push(uid); } };
  // 记录一次「完成/失败」结果，耗时按最近一次尝试（补跑）计算
  const markOutcome = (uid, ok, ts) => {
    outcome[uid] = ok;
    addOrder(uid);
    haveRun = true;
    if (ts === null) return;
    outcomeTs[uid] = ts;
    const s = lastStart[uid];
    if (s !== undefined) durMap[uid] = Math.max(0, Math.round((ts - s) / 1000));
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const tsM = /^\[([\d\- :]+)\]/.exec(line);
    const ts = tsM ? parseTime(tsM[1]) : null;

    let m = line.match(/发现\s+\d+\s+个账号:\s*\[([^\]]*)\]/);
    if (m && !discovered.length) { discovered = splitList(m[1]); haveRun = true; continue; }

    // `---------- 账号 X ----------`，补跑时为 `---------- 账号 X (补跑) ----------`
    m = line.match(/账号\s+(\d+)\s*(?:[(（][^)）]*[)）])?\s*-+\s*$/);
    if (m) {
      const uid = m[1];
      addOrder(uid);
      if (ts !== null) {
        if (firstStart[uid] === undefined) firstStart[uid] = ts;
        lastStart[uid] = ts;
      }
      haveRun = true;
      continue;
    }

    m = line.match(/\[账号\s+(\d+)\]\s*(?:\[[^\]]*\])?\s*日常执行完成/);          // 完成
    if (m) { markOutcome(m[1], true, ts); continue; }

    m = line.match(/\[账号\s+(\d+)\]\s*(?:\[[^\]]*\])?\s*日常执行失败/);          // 失败（含超时强杀）
    if (m) { markOutcome(m[1], false, ts); continue; }

    m = line.match(/成功\s+(\d+)\s+个:\s*\[([^\]]*)\]\s*[；;]?\s*失败\s+(\d+)\s+个:\s*\[([^\]]*)\]/);
    if (m) { successList = splitList(m[2]); failedList = splitList(m[4]); haveRun = true; continue; }
  }

  if (!haveRun || order.length === 0) return { empty: true };   // 无实际运行，跳过

  const okSet = new Set(successList);
  const accounts = order.map((uid) => {
    const ok = outcome[uid] !== undefined ? outcome[uid] : okSet.has(uid);
    const s = firstStart[uid];
    const e = outcomeTs[uid];
    let durSec = durMap[uid];
    if (durSec === undefined) {
      durSec = (s !== undefined && e !== undefined) ? Math.max(0, Math.round((e - s) / 1000)) : null;
    }
    return { uid: maskUid(uid), ok, start: s !== undefined ? new Date(s).toISOString() : null, durSec };
  });

  return {
    date: dateStr,
    success: accounts.filter((a) => a.ok).length,
    fail: accounts.filter((a) => !a.ok).length,
    accounts,
  };
}

function fmtLocal(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

async function main() {
  const args = process.argv.slice(2);
  let dateStr = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--date' && args[i + 1]) dateStr = args[i + 1];
  }
  if (!dateStr) { const y = new Date(); y.setDate(y.getDate() - 1); dateStr = fmtLocal(y); }

  const compact = dateStr.replace(/-/g, '');
  const filePath = path.join(ASSISTANT_LOGS_DIR, `daily_loop_${compact}.log`);
  if (!fs.existsSync(filePath)) {
    log(`[skip] ${dateStr} 无 daily_loop 日志(${filePath})，跳过。`);
    return 0;
  }

  const entry = parseDailyFile(filePath, dateStr);
  if (!entry || entry.empty) {
    log(`[skip] ${dateStr} 日志无实际运行记录。`);
    return 0;
  }
  log(`[ok] ${dateStr} 成功 ${entry.success} / 失败 ${entry.fail}`);

  const data = readJsonSafe(OUT_FILE) || { logs: [] };
  let logs = Array.isArray(data.logs) ? data.logs : [];
  logs = logs.filter((x) => x.date !== dateStr);
  logs.unshift(entry);
  logs.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  logs = logs.slice(0, KEEP_DAYS);

  fs.writeFileSync(OUT_FILE, JSON.stringify({ updatedAt: new Date().toISOString(), keepDays: KEEP_DAYS, logs }, null, 2), 'utf8');
  log(`已写入 ${OUT_FILE}，共 ${logs.length} 天`);
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => { log('[error]', e); process.exit(0); });
