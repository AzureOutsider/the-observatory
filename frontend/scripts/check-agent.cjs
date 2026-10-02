// Used by check-manual-refresh.cjs --agent. API and clipboard writes are mocked.
const assert = require('node:assert/strict');
const { writeFileSync } = require('node:fs');
const { join } = require('node:path');

function installAgentFixtures() {
  const reviewPath = 'D:/TestOnly/Observatory/研究档案/每日投资复盘/这是用于验证长路径换行的模拟文件.md';
  const context = {
    date: '2026-09-10', analysis_date: '2026-09-10', generated_at: '2026-09-10T18:00:00+08:00',
    private_portfolio: { holding_count: 34, total_amount: 1234567.89, holdings: [], theme_exposure: [], recent_transactions: [], knowledge: [] },
    market_snapshot: { trading_status: { status: 'closed', message: '已休市，展示最近一次手动刷新时的市场快照' }, market_indices: [], holding_today_changes: [] },
    data_source_health: { sources: [] },
    data_quality_summary: { status_counts: { unavailable: 2 }, holding_count: 34, manual_refresh_required: true, note: '测试数据' },
    internal_news_signals: [{ title: '行业观察' }, { title: '政策观察' }],
    external_research: { required: true, instruction: '核验来源', suggested_queries: ['人工智能 产业资本开支 2026', '半导体先进制造 产业链趋势与风险验证', '中央银行 最新政策声明'], source_priority: [{ type: '官方披露', examples: ['交易所公告', '公司财报', '主管部门文件'] }, { type: '主流财经媒体', examples: ['行业报道', '独立交叉验证来源'] }], verification_rules: [] },
    historical_review: { path: reviewPath, recent_dates: ['2026-09-09', '2026-09-08', '2026-09-07'], open_items: ['需求验证'], follow_up_items: ['盈利变化', '政策窗口'], triggers: [] },
    analysis_contract: { required_output_sections: [], guardrails: [] }, agent_prompt: '模拟分析 Prompt：只读分析，不执行交易。',
  };
  window.__agentTest = { reads: [], writes: [], clipboard: [], failRead: false, failWrite: false, duplicate: false, empty: false };
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async value => {
    if (window.__agentTest.failCopy) throw new Error('模拟剪贴板拒绝');
    window.__agentTest.clipboard.push(value);
  } } });
  const originalFetch = window.fetch;
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const state = window.__agentTest;
    let result;
    let status = 200;
    if (url.pathname === '/api/agent/analysis-package/today') {
      state.reads.push(url.searchParams.get('topic'));
      await new Promise(resolve => setTimeout(resolve, 250));
      status = state.failRead ? 503 : 200;
      result = state.failRead ? { detail: '模拟分析包读取失败' } : { ...context, topic: url.searchParams.get('topic'), ...(state.empty ? { historical_review: undefined } : {}) };
    } else if (url.pathname === '/api/agent/reviews/append' && init.method === 'POST') {
      state.writes.push(JSON.parse(init.body));
      await new Promise(resolve => setTimeout(resolve, 250));
      status = state.failWrite ? 503 : 200;
      result = state.failWrite ? { detail: '模拟写入失败' } : { appended: !state.duplicate, duplicate: state.duplicate, path: reviewPath, fingerprint: 'mock', analysis_date: '2026-09-10' };
    } else return originalFetch(input, init);
    return new Response(JSON.stringify(result), { status, headers: { 'Content-Type': 'application/json' } });
  };
}

async function checkAgent({ send, evaluate, until }) {
  const ready = () => until("!!document.querySelector('.agentPayloadPanel') && !document.querySelector('.agentHeroActions button').disabled");
  const screenshot = async name => {
    if (!process.env.TEST_SCREENSHOT_DIR) return;
    const result = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(process.env.TEST_SCREENSHOT_DIR, 'agent-' + name + '.png'), Buffer.from(result.data, 'base64'));
  };
  await ready();
  assert.equal(await evaluate('window.__agentTest.writes.length'), 0, 'opening Agent never appends reviews');
  assert(await evaluate("document.querySelector('.agentReviewField textarea').labels.length>0"), 'review has visible label');
  for (const selector of ['.agentTopicField span', '.agentMetric small', '.agentFacts strong', '.continuityPath', '.queryList button', '.agentReviewField textarea', '.jsonBox']) {
    assert(await evaluate(`parseFloat(getComputedStyle(document.querySelector('${selector}')).fontSize)>=15`), selector + ' readable type');
  }
  assert(await evaluate("getComputedStyle(document.querySelector('.agentHero')).backgroundColor==='rgba(0, 0, 0, 0)'"), 'unboxed hero');
  await screenshot('desktop');
  await evaluate("document.querySelector('.agentGrid').scrollIntoView()");
  await screenshot('research');
  for (const [selector, expected] of [['.agentEndpointBox button', '/api/agent/analysis-package/today'], ['.agentCommandBox button', 'investment-observatory-review'], ['.queryList button', '人工智能'], ['.agentPayloadPanel button', '模拟分析 Prompt']]) {
    await evaluate(`document.querySelector('${selector}').click()`);
    await until(`window.__agentTest.clipboard.at(-1)?.includes(${JSON.stringify(expected)})`);
  }
  await evaluate("document.querySelectorAll('.agentPayloadPanel button')[1].click()");
  await until("window.__agentTest.clipboard.at(-1)?.startsWith('{')");
  assert.equal(await evaluate("JSON.parse(window.__agentTest.clipboard.at(-1)).analysis_date"), '2026-09-10');
  await evaluate("window.__agentTest.failCopy=true; document.querySelector('.agentEndpointBox button').click()");
  await until("[...document.querySelectorAll('.agentToast')].some(el=>el.textContent.includes('模拟剪贴板拒绝'))");
  await evaluate("window.__agentTest.failCopy=false; document.querySelector('.agentTopicField input').focus(); document.querySelector('.agentTopicField input').select()");
  await send('Input.insertText', { text: '新能源 / 全球' });
  await evaluate("document.querySelector('.agentHeroActions button').click()");
  await ready();
  assert.equal(await evaluate('window.__agentTest.reads.at(-1)'), '新能源 / 全球', 'topic is passed intact');
  const reads = await evaluate('window.__agentTest.reads.length');
  await evaluate("document.querySelector('.agentHeroActions button').click()");
  await ready();
  assert.equal(await evaluate('window.__agentTest.reads.length'), reads + 1, 'same topic button refetches');
  assert(await evaluate("document.querySelector('.appendFooter button').disabled"), 'empty review cannot append');
  const review = '# 测试复盘\n\n只验证界面，不写入真实复盘文件。';
  await evaluate("document.querySelector('.agentReviewField textarea').focus()");
  await send('Input.insertText', { text: review });
  await evaluate("window.__agentTest.failWrite=true; document.querySelector('.appendFooter button').click()");
  await until("[...document.querySelectorAll('.agentToast')].some(el=>el.textContent.includes('模拟写入失败'))");
  assert.equal(await evaluate("document.querySelector('.agentReviewField textarea').value"), review, 'failure retains draft');
  await evaluate("window.__agentTest.failWrite=false; window.__agentTest.duplicate=true; document.querySelector('.appendFooter button').click()");
  await until("!!document.querySelector('.agentAppendPanel .notice')");
  assert.equal(await evaluate("document.querySelector('.agentReviewField textarea').value"), review, 'duplicate retains draft');
  await evaluate("window.__agentTest.duplicate=false; document.querySelector('.appendFooter button').click()");
  await until("!!document.querySelector('.agentAppendPanel .successNotice')");
  assert.equal(await evaluate("document.querySelector('.agentReviewField textarea').value"), '', 'success clears draft');
  assert.deepEqual(await evaluate('window.__agentTest.writes.at(-1)'), { analysis_date: '2026-09-10', content: review });
  await evaluate("document.querySelector('.agentAppendPanel').scrollIntoView()");
  await screenshot('append');
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  for (const [width, height] of [[375, 900], [844, 390], [1222, 1114]]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
    await evaluate('window.scrollTo(0,0)');
    await new Promise(resolve => setTimeout(resolve, 200));
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'no horizontal overflow at ' + width);
    assert(await evaluate("[...document.querySelectorAll('.agentEndpointBox button,.agentCommandBox button,.agentHeroActions button,.appendFooter button')].every(el=>{const r=el.getBoundingClientRect();return r.left>=0 && r.right<=document.documentElement.clientWidth})"), 'actions stay in viewport');
    await screenshot('width-' + width);
    if (width === 375) {
      await evaluate("document.querySelector('.agentControlPanel').scrollIntoView()");
      await screenshot('mobile-controls');
      await evaluate("document.querySelector('.agentAppendPanel').scrollIntoView()");
      await screenshot('mobile-append');
    }
  }
  await evaluate("window.__agentTest.failRead=true; document.querySelector('.agentHeroActions button').click()");
  await until("!!document.querySelector('.agentErrorNotice')");
  await evaluate("window.__agentTest.failRead=false; window.__agentTest.empty=true; document.querySelector('.refreshRetryButton').click()");
  await ready();
  assert(await evaluate("document.querySelector('.continuityDates').textContent.includes('尚无历史日期')"), 'missing review history fallback');
  assert.equal(await evaluate('window.__agentTest.writes.length'), 3, 'reading and resizing never append reviews');
  console.log('PASS: Agent palette, typography, topic reload, copy controls, append failure/duplicate/success, long paths, narrow layouts and read retry; API and clipboard writes mocked');
}

module.exports = { installAgentFixtures, checkAgent };
