// Browser regression: run with Vite on 5173. All API calls are mocked in-page;
// this test never refreshes real quotes or edits the user's watchlists.
// Set CHROME_PATH / TEST_BASE_URL to override the local browser / dev URL.
const { spawn } = require('node:child_process');
const { mkdtempSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const assert = require('node:assert/strict');

function installFixtures(longPage = false, newsPage = false, holdingsPage = false, transactionsPage = false, paperPage = false) {
  const point = { time: '2026-09-10T11:30:00', price: 1.23, change_pct: 1, source: 'test' };
  const makeRow = id => ({ watchlist_item_id: id, name: `测试基金${id}`, code: String(id).padStart(6, '0'), asset_type: 'fund', tags: id === 1 ? ['重点'] : [], points: [point], latest: point, quote_status: 'intraday_estimate' });
  const rows = Array.from({ length: longPage ? 35 : 8 }, (_, i) => makeRow(i + 1));
  const news = [
    { title: '产业观察：人工智能基础设施投资与行业需求变化', source: 'source-a', source_label: '观察通讯', importance: 5, tags: ['人工智能'], published_at: '2026-09-10T15:30:00', summary: '从技术进展到企业投入，持续记录产业变化。结合公开信息与持仓关联，区分短期市场波动和长期需求趋势。', url: 'https://example.com/news', related_holdings: [{ code: '000001', name: '人工智能主题基金', latest_change_pct: 1.2, matched_tags: ['人工智能'] }, { code: '000002', name: '科技成长基金', latest_change_pct: -0.8, matched_tags: ['人工智能'] }] },
    { title: '市场观察：银行业政策信息更新', source: 'source-b', source_label: '市场通讯', importance: 4, tags: ['银行'], published_at: '2026-09-10T14:30:00', quality: 'stale', related_holdings: [] },
    { title: '市场简讯：本周经济数据日程', source: 'source-a', source_label: '观察通讯', importance: 3, tags: ['市场'], published_at: '2026-09-10T13:30:00', related_holdings: [] },
  ];
  const holdings = Array.from({length: sessionStorage.getItem('holdings-volume') === 'large' ? 120 : 4}, (_,i)=>({id:i+1,asset:{id:i+1,code:String(i+1).padStart(6,'0'),name:i===0?'长名称测试：全球科技创新成长混合型证券投资基金人民币份额':'持仓测试基金'+(i+1),asset_type:'fund'},amount:'123456.78',profit:i===1?'-1234.56':i===2?null:'3456.78',units:i===2?null:'100000.12',cost_basis:i===2?null:'120000.00',manual_adjusted:i===0,last_valuation_at:'2026-09-10T15:00:00',last_valuation_source:'sina_xincai_estimate',last_manual_adjustment_at:'2026-09-09T12:00:00'}));
  window.__trendTest = { generation: crypto.randomUUID(), refreshes: [], writes: [], cacheReads: 0, failCache: false, failRefresh: false, failRead: sessionStorage.getItem('transactions-read-error') === 'true' };
  const transactions = Array.from({ length: sessionStorage.getItem('transactions-volume') === 'large' ? 120 : 6 }, (_, i) => ({
    id: i + 1, asset: holdings[i % 4].asset, operation: ['buy', 'sell', 'dividend', 'transfer', 'adjustment', 'note'][i % 6],
    trade_date: '2026-09-10', amount: '123456.78', units: i === 2 ? null : '10000.12', price: i === 2 ? null : '1.2345',
    reason: '根据计划分批调整，保留交易事实与对账信息，等待下一次复盘。',
    fee: '0.1',
    retracted_at: i === 5 ? '2026-09-10T12:00:00' : null,
    retraction_reason: i === 5 ? '重复录入，已撤回' : null,
    retraction_effect: i === 5 ? '{"amount_before":"123456.78","amount_after":"0"}' : null,
  }));
  const paperPositions = [
    { id: 41, code: '999001', name: '模拟测试标的', asset_type: 'fund', units: '1000', cost_basis: '1200.1000', realized_profit: '0.0000', market_price: '1.5000', market_value: '1500.0000', unrealized_profit: '299.9000', total_profit: '299.9000', quote_status: 'intraday_estimate', quote_message: '模拟行情，仅作参考', quote_source: 'test', quote_time: '2026-10-14 11:30:00', trade_count: 1, is_open: true },
    { id: 42, code: '600000', name: '已结束的模拟想法', asset_type: 'stock', units: '0.000000', cost_basis: '0.0000', realized_profit: '-20.1000', quote_status: 'closed', trade_count: 2, is_open: false },
  ];
  const paperTrades = [
    { id: 51, asset_id: 41, operation: 'buy', trade_date: '2026-10-14', amount: '1200.1000', units: '1000.000000', price: '1.200000', fee: '0.1000', reason: '浏览器测试：观察行业周期与估值', created_at: '2026-10-14T10:00:00', retracted_at: null, retraction_reason: null },
    { id: 61, asset_id: 42, operation: 'buy', trade_date: '2026-10-13', amount: '20.1000', units: '10.000000', price: '2.000000', fee: '0.1000', reason: 'test', created_at: '2026-10-13T10:00:00', retracted_at: null, retraction_reason: null },
    { id: 62, asset_id: 42, operation: 'sell', trade_date: '2026-10-14', amount: '0.0000', units: '10.000000', price: '2.010000', fee: '0.1000', reason: 'test', created_at: '2026-10-14T10:00:00', retracted_at: null, retraction_reason: null },
  ];
  const paperQuotes = [{ id: 71, asset_id: 41, captured_at: '2026-10-14T03:30:00', price: '1.500000', change_pct: '1.25', quote_status: 'intraday_estimate', quote_time: '2026-10-14 11:30:00', source: 'test', message: 'mock quote' }];
  window.__paperFixture = { positions: paperPositions, trades: paperTrades, quotes: paperQuotes, reads: [], realReads: [], writes: [], refreshes: [], failWrite: false };
  const originalFetch = window.fetch;
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!url.pathname.startsWith('/api/')) return originalFetch(input, init);
    const path = url.pathname.slice(4);
    const state = window.__trendTest;
    let result = [];
    let status = 200;
    if (paperPage && (path === '/holdings' || path === '/transactions' || path.startsWith('/agent/'))) {
      window.__paperFixture.realReads.push(path);
    }
    if (paperPage && path === '/paper/portfolio') {
      window.__paperFixture.reads.push(path);
      result = window.__paperFixture.positions;
    }
    else if (paperPage && path === '/paper/refresh' && init.method === 'POST') {
      window.__paperFixture.refreshes.push(path);
      result = { updated: 1, failed: 0 };
    }
    else if (paperPage && /^\/paper\/assets\/\d+\/quotes$/.test(path)) {
      window.__paperFixture.reads.push(path);
      result = window.__paperFixture.quotes.filter(row => row.asset_id === Number(path.split('/')[3]));
    }
    else if (paperPage && /^\/paper\/assets\/\d+\/trades$/.test(path)) {
      window.__paperFixture.reads.push(path);
      const assetId = Number(path.split('/')[3]);
      result = window.__paperFixture.trades.filter(row => row.asset_id === assetId);
    }
    else if (paperPage && path === '/paper/trades' && init.method === 'POST') {
      const fixture = window.__paperFixture;
      const payload = JSON.parse(init.body);
      fixture.writes.push({ endpoint: path, method: 'POST', payload });
      status = fixture.failWrite ? 503 : 201;
      if (fixture.failWrite) result = { detail: '模拟环境保存失败' };
      else result = { id: 99, asset_id: 41, operation: payload.operation, trade_date: payload.trade_date, amount: String(Number(payload.units) * Number(payload.price) + (payload.operation === 'sell' ? -1 : 1) * Number(payload.fee)), units: payload.units, price: payload.price, fee: payload.fee, reason: payload.reason, created_at: '2026-10-14T12:00:00', retracted_at: null, retraction_reason: null };
    }
    else if (paperPage && /\/paper\/trades\/\d+$/.test(path) && init.method === 'DELETE') {
      const fixture = window.__paperFixture;
      fixture.writes.push({ endpoint: path, method: 'DELETE' });
      const trade = fixture.trades.find(row => path.endsWith('/' + row.id));
      if (trade) {
        trade.retracted_at = '2026-10-14T12:00:00';
        trade.retraction_reason = '用户手动撤回';
        const position = fixture.positions.find(row => row.id === trade.asset_id);
        if (position && trade.operation === 'buy') {
          position.units = '0';
          position.cost_basis = '0';
          position.market_price = null;
          position.market_value = null;
          position.unrealized_profit = null;
          position.total_profit = position.realized_profit;
          position.trade_count -= 1;
          position.is_open = false;
        }
      }
      result = { status: 'ok', id: trade?.id };
    }
    else if (transactionsPage && path === '/transactions') {
      if (init.method === 'POST') {
        status = state.failWrite ? 503 : 200;
        if (state.failWrite) result = { detail: '测试保存失败' };
        else { const payload = JSON.parse(init.body); state.writes.push({ method: 'POST', payload }); result = { ...transactions[0], ...payload, id: 999 }; }
      } else { status = state.failRead ? 503 : 200; result = state.failRead ? { detail: '测试读取失败' } : state.empty ? [] : transactions; }
    }
    else if (transactionsPage && /\/transactions\/\d+$/.test(path) && init.method === 'DELETE') {
      status = state.failWrite ? 503 : 200;
      if (state.failWrite) result = { detail: '测试撤回失败' };
      else { state.writes.push({ method: 'DELETE', path }); const row = transactions.find(row => path.endsWith('/' + row.id)); row.retracted_at = '2026-09-10T12:00:00'; result = { status: 'ok', id: row.id }; }
    }
    else if ((holdingsPage || transactionsPage) && path === '/holdings') result = holdings;
    else if (holdingsPage && /\/holdings\/\d+\/transactions$/.test(path)) {
      state.detailReads = (state.detailReads || 0) + 1;
      status = state.failDetail ? 503 : 200;
      const id = Number(path.split('/')[2]);
      result = state.failDetail ? { detail: '测试详情读取失败' } : state.emptyDetail ? [] : transactions.filter(row => row.asset.id === id);
    }
    else if (holdingsPage && /\/holdings\/\d+$/.test(path) && init.method==='PATCH') {
      const payload=JSON.parse(init.body);
      status=state.failWrite ? 503 : 200;
      if(state.failWrite) result={detail:'测试名称保存失败'};
      else { state.writes.push(payload); const holding=holdings.find(row=>path.endsWith('/'+row.id)); const {custom_name,...fields}=payload; Object.assign(holding,fields); if('custom_name' in payload) holding.asset.custom_name=custom_name; result={...holding}; }
    }
    else if (newsPage && path === '/frontier-news/tags') result = ['全部', '市场', '人工智能', '银行', '黄金'];
    else if (newsPage && path === '/frontier-news') { result = news; if (url.searchParams.get('refresh') === 'true') state.refreshes.push('news'); }
    else if (path === '/watchlists') result = [{ id: 1, name: '测试列表', items: [] }, { id: 2, name: '第二列表', items: [] }];
    else if (/\/trends\/refresh$/.test(path)) {
      const ids = JSON.parse(init.body).item_ids;
      state.refreshes.push(ids);
      status = state.failRefresh ? 503 : 200;
      result = state.failRefresh ? { detail: '测试刷新失败' } : rows.filter(row => ids.includes(row.watchlist_item_id));
    } else if (/\/trends$/.test(path)) {
      state.cacheReads++;
      if (url.searchParams.get('refresh') !== 'false') state.refreshes.push('unsafe GET');
      status = state.failCache ? 503 : 200;
      result = state.failCache ? { detail: '测试缓存读取失败' } : path.includes('/2/') ? [makeRow(20)] : rows;
    } else if (/\/items$/.test(path) && init.method === 'POST') {
      rows.push(makeRow(9)); result = { id: 9 };
    } else if (/\/history$/.test(path)) {
      result = { points: [], start_date: '2026-03-10', end_date: '2026-09-10' };
    } else if (/\/items\/\d+$/.test(path)) {
      result = { id: 1, watchlist_id: 1, display_name: '测试基金1', official_name: '测试基金1', tags: ['重点'], asset: { code: '000001', name: '测试基金1', asset_type: 'fund' } };
    } else if (path === '/market/data-sources/health') result = { sources: [] };
    else if (path === '/system/status') result = { managed_by_launcher: false };
    return new Response(JSON.stringify(result), { status, headers: { 'Content-Type': 'application/json' } });
  };
}

(async () => {
  const browser = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--disable-gpu', '--remote-debugging-port=0',
    '--user-data-dir=' + mkdtempSync(join(tmpdir(), 'finance-manual-refresh-')),
    'about:blank',
  ], { windowsHide: true });
  let ws;
  try {
    const endpoint = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Chrome startup timeout')), 15000);
      browser.once('error', error => { clearTimeout(timer); reject(error); });
      browser.stderr.on('data', data => {
        const match = data.toString().match(/DevTools listening on (ws:\/\/[^\s]+)/);
        if (match) { clearTimeout(timer); resolve(match[1]); }
      });
    });
    const targets = await (await fetch('http://127.0.0.1:' + new URL(endpoint).port + '/json')).json();
    ws = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
    await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
    let id = 0;
    const pending = new Map();
    ws.addEventListener('message', ({ data }) => {
      const message = JSON.parse(data);
      const call = pending.get(message.id);
      if (!call) return;
      pending.delete(message.id); clearTimeout(call.timer);
      message.error ? call.reject(new Error(call.method + ': ' + JSON.stringify(message.error))) : call.resolve(message.result);
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const requestId = ++id;
      const timer = setTimeout(() => { pending.delete(requestId); reject(new Error(method + ' timeout')); }, 15000);
      pending.set(requestId, { method, resolve, reject, timer });
      ws.send(JSON.stringify({ id: requestId, method, params }));
    });
    const evaluate = async expression => {
      try {
        const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
        if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
        return result.result.value;
      } catch (error) {
        throw new Error('Runtime expression failed: ' + expression + ' (' + error.message + ')');
      }
    };
    const until = async expression => {
      for (let i = 0; i < 80; i++) {
        if (await evaluate(expression)) return;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      throw new Error('Timed out: ' + expression);
    };
    const settled = async () => {
      await until("!!document.querySelector('.chartsRefreshActions button:not(:disabled)') || !!document.querySelector('.chartsWorkspace .notice')");
      await new Promise(resolve => setTimeout(resolve, 250));
    };
    const count = () => evaluate('window.__trendTest.refreshes.length');
    const assertNoRefresh = async label => { assert.equal(await count(), 0, label); console.log('PASS:', label); };
    await send('Page.enable');
    const sidebarMode = process.argv.includes('--sidebar');
    const frontierMode = process.argv.includes('--frontier');
    const holdingsMode = process.argv.includes('--holdings');
    const transactionsMode = process.argv.includes('--transactions');
    const agentMode = process.argv.includes('--agent');
    const paperMode = process.argv.includes('--paper');
    await send('Page.addScriptToEvaluateOnNewDocument', { source: '(' + installFixtures.toString() + ')(' + sidebarMode + ',' + frontierMode + ',' + holdingsMode + ',' + transactionsMode + ',' + paperMode + ')' });
    if (agentMode) await send('Page.addScriptToEvaluateOnNewDocument', { source: '(' + require('./check-agent.cjs').installAgentFixtures.toString() + ')()' });
    await send('Emulation.setDeviceMetricsOverride', { width: 1660, height: 1272, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: (process.env.TEST_BASE_URL || 'http://127.0.0.1:5173') + (agentMode ? '/#agent' : paperMode ? '/#paper' : transactionsMode ? '/#transactions' : holdingsMode ? '/#holdings' : frontierMode ? '/#frontierNews' : '/#charts') });
    if (agentMode) {
      await require('./check-agent.cjs').checkAgent({ send, evaluate, until });
      await send('Browser.close');
      return;
    }
    if (paperMode) {
      await until("document.querySelectorAll('.paperTable tbody tr').length===2");
      const capture = async name => { if(process.env.TEST_SCREENSHOT_DIR){const result=await send('Page.captureScreenshot',{format:'png'});writeFileSync(join(process.env.TEST_SCREENSHOT_DIR,'paper-'+name+'.png'),Buffer.from(result.data,'base64'));} };
      await new Promise(resolve=>setTimeout(resolve,350));
      assert(await evaluate("document.querySelector('.paperCaution').textContent.includes('不改变真实持仓') && document.querySelector('.paperCaution').textContent.includes('Agent 分析')"),'paper ledger isolation is explicit');
      assert.equal(await evaluate("document.querySelector('.paperMetrics').textContent.includes('2 个')"),true,'position totals render');
      assert(await evaluate("[...document.querySelectorAll('.paperFormGrid input,.paperFormGrid select,.paperFormGrid textarea')].every(el=>el.labels.length>0)"),'paper form controls have visible labels');
      assert.equal(await evaluate("document.querySelector('.searchTrigger')===null"),true,'real holding search is not exposed on paper page');
      await evaluate("window.dispatchEvent(new KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}))");
      assert.equal(await evaluate("document.querySelector('.searchDialog')===null"),true,'real holding search shortcut is disabled on paper page');
      assert.deepEqual(await evaluate('window.__paperFixture.realReads'),[],'paper page never reads real holdings, transactions or agent context');
      assert.equal(await evaluate("document.querySelector('.paperTable tbody tr:first-child td:nth-child(6)').textContent.trim().startsWith('¥1,500.00')"),true,'market value displays from read-only quote fixture');
      await capture('desktop');
      const setField = async (selector,value) => evaluate(`(() => {const el=document.querySelector('${selector}');const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,'${value}');el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
      const paperToday = await evaluate("document.querySelector('[name=trade_date]').value");
      await setField('[name=asset_code]','999002');
      await setField('[name=asset_name]','测试虚拟标的');
      await setField('[name=units]','1000000');
      await setField('[name=price]','2.5');
      await until("document.querySelector('.paperAmountPreview strong').textContent==='¥2,500,000.10'");
      await evaluate("document.querySelector('.paperTradeForm').requestSubmit()");
      await until("window.__paperFixture.writes.length===1 && !document.querySelector('.paperTradeForm button').disabled");
      const firstTradeWrite = await evaluate('window.__paperFixture.writes[0]');
      const { idempotency_key: buyRetryKey, ...firstTradePayload } = firstTradeWrite.payload;
      assert.match(buyRetryKey,/^[0-9a-f-]{36}$/i,'new paper operation carries a retry key');
      assert.deepEqual({ endpoint:firstTradeWrite.endpoint,method:firstTradeWrite.method,payload:firstTradePayload },{endpoint:'/paper/trades',method:'POST',payload:{asset_code:'999002',asset_name:'测试虚拟标的',asset_type:'fund',operation:'buy',trade_date:paperToday,units:'1000000',price:'2.5',fee:'0.1'}});
      assert.equal(await evaluate("document.querySelector('[name=units]').value"),'','successful virtual trade resets form');
      await evaluate("document.querySelector('.paperRefreshButton').click()");
      await until("window.__paperFixture.refreshes.length===1 && !document.querySelector('.paperRefreshButton').disabled");
      await evaluate("document.querySelector('.paperTable tbody tr:first-child .compactAction').click()");
      await until("!!document.querySelector('.paperDetailDialog') && document.querySelectorAll('.paperHistoryTable tbody tr').length===1 && document.querySelectorAll('.paperQuotePoint').length===1");
      assert(await evaluate("document.querySelector('.paperQuoteHistory').textContent.includes('1.5000')"),'quote refresh snapshot is visible in detail');
      assert(await evaluate("document.querySelector('.paperHistoryTable').textContent.includes('浏览器测试：观察行业周期与估值')"),'virtual trade thesis is available in detail');
      await capture('detail');
      await evaluate("document.querySelector('.paperSellFromDetail').click()");
      await until("!document.querySelector('.paperDetailDialog') && document.querySelector('[name=operation]').value==='sell'");
      assert.equal(await evaluate("document.querySelector('[name=asset_code]').value"),'999001','sell action pre-fills paper asset');
      assert.equal(await evaluate("document.querySelector('[name=price]').value"),'1.5000','sell action uses latest paper quote as an editable suggestion');
      await setField('[name=units]','100');
      await until("document.querySelector('.paperAmountPreview strong').textContent==='¥149.90'");
      await evaluate("window.__paperFixture.failWrite=true;document.querySelector('.paperTradeForm').requestSubmit()");
      await until("!!document.querySelector('[data-sonner-toast][data-type=error]')");
      await until("!!document.querySelector('.paperTradeError') && document.activeElement.classList.contains('paperTradeError')");
      assert.equal(await evaluate("document.querySelector('[name=units]').value"),'100','failed save retains simulated input');
      await evaluate("window.__paperFixture.failWrite=false");
      assert.equal(await evaluate("window.__paperFixture.writes[1].payload.operation"),'sell','sell operation is recorded independently');
      await evaluate("document.querySelector('.paperTradeForm').requestSubmit()");
      await until("window.__paperFixture.writes.length===3 && !document.querySelector('.paperTradeForm button').disabled");
      assert.equal(await evaluate('window.__paperFixture.writes[2].payload.idempotency_key'),await evaluate('window.__paperFixture.writes[1].payload.idempotency_key'),'retry reuses the original operation key');
      await evaluate("document.querySelector('.paperTable tbody tr:first-child .compactAction').click()");
      await until("!!document.querySelector('.paperDetailDialog')");
      await evaluate("document.querySelector('.paperDetailDialog .modalCloseButton').click()");
      await evaluate("document.querySelector('[name=operation]').value='buy';document.querySelector('[name=operation]').dispatchEvent(new Event('change',{bubbles:true}))");
      await evaluate("document.querySelector('[name=units]').value='';document.querySelector('[name=units]').dispatchEvent(new Event('input',{bubbles:true}))");
      await evaluate("document.querySelector('.paperTable tbody tr:first-child .compactAction').click()");
      await until("!!document.querySelector('.paperDetailDialog') && !!document.querySelector('.paperHistoryTable .retractButton')");
      await evaluate("document.querySelector('.paperHistoryTable .retractButton').click()");
      await until("!!document.querySelector('.confirmDialog')");
      await evaluate("document.querySelector('.confirmDialog .secondaryButton').click()");
      assert.equal(await evaluate('window.__paperFixture.writes.length'),3,'cancel retraction does not write');
      await evaluate("document.querySelector('.paperHistoryTable .retractButton').click()");
      await until("!!document.querySelector('.confirmDialog')");
      await evaluate("document.querySelector('.confirmDialog .dangerButton').click()");
      await until("window.__paperFixture.writes.length===4 && !document.querySelector('.confirmDialog')");
      assert.equal(await evaluate("window.__paperFixture.writes[3].endpoint"),'/paper/trades/51');
      await until("document.querySelector('.paperDetailMetrics').textContent.includes('0.00') && !document.querySelector('.paperSellFromDetail')");
      assert(await evaluate("!!document.querySelector('.paperHistoryTable .paperRetractedLabel')"),'retracted history stays visible in the open detail');
      await send('Emulation.setDeviceMetricsOverride',{width:390,height:1100,deviceScaleFactor:1,mobile:false});
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'paper page fits narrow viewport');
      await evaluate("document.querySelector('.paperLedger').scrollIntoView();document.querySelector('.paperTableWrap').scrollLeft=99999");
      assert(await evaluate("document.querySelector('.paperTableWrap').scrollLeft>0"),'paper ledger scrolls horizontally on mobile');
      await evaluate("document.querySelector('.paperTable tbody tr:first-child .compactAction').click()");
      await until("!!document.querySelector('.paperDetailDialog')");
      await new Promise(resolve=>setTimeout(resolve,200));
      assert(await evaluate("(() => {const r=document.querySelector('.paperDetailDialog').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight})()"),'paper detail dialog fits mobile viewport');
      await capture('mobile-detail');
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'paper detail does not overflow page');
      assert(await evaluate("window.__paperFixture.writes.every(write=>write.endpoint.startsWith('/paper/'))"),'all simulated writes use isolated paper endpoints');
      console.log('PASS: paper isolation, unlimited amounts, buy/sell formulas, form errors, thesis details, retraction, mobile layout; writes isolated and mocked');
      await send('Browser.close');
      return;
    }
    if (transactionsMode) {
      await until("document.querySelectorAll('.transactionTable tbody tr').length===6");
      await new Promise(resolve => setTimeout(resolve, 350));
      const capture = async name => { if (process.env.TEST_SCREENSHOT_DIR) { const result = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(join(process.env.TEST_SCREENSHOT_DIR, 'transactions-' + name + '.png'), Buffer.from(result.data, 'base64')); } };
      const columnsAligned = async () => {
        assert(await evaluate(`(() => {const headers=[...document.querySelectorAll('.transactionTable th')];const cells=[...document.querySelector('.transactionTable tbody tr').children];return headers.every((h,i)=>Math.abs(h.getBoundingClientRect().left-cells[i].getBoundingClientRect().left)<2)})()`), 'transaction columns align');
      };
      assert(await evaluate("[...document.querySelectorAll('.formGrid input,.formGrid select,.formGrid textarea')].every(el=>el.labels.length>0 && parseFloat(getComputedStyle(el).fontSize)>=17)"), 'all transaction fields have visible labels and larger type');
      assert(await evaluate("[...document.querySelectorAll('.operationBadge,.retractedBadge')].every(el=>getComputedStyle(el).backgroundColor==='rgba(0, 0, 0, 0)')"), 'no pale operation badges');
      assert(await evaluate("[...document.querySelectorAll('.transactionTable td small,.correctionIdentity small')].every(el=>parseFloat(getComputedStyle(el).fontSize)>=15)"), 'readable audit and correction text');
      await columnsAligned();
      await capture('desktop');
      await evaluate("document.querySelector('.transactionHistoryPanel').scrollIntoView()");
      await capture('ledger');
      assert.equal(await evaluate('window.__trendTest.writes.length'), 0, 'opening transactions does not write');
      await evaluate("document.querySelector('.formPanel').requestSubmit()");
      assert.equal(await evaluate('window.__trendTest.writes.length'), 0, 'required fields prevent empty submission');
      assert.equal(await evaluate("document.querySelector('[name=amount]') === null"), true, 'no editable amount');
      const today = await evaluate("(() => { const d=new Date(); return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-') })()");
      assert.equal(await evaluate("document.querySelector('[name=trade_date]').value"), today, 'local date defaults to today');
      assert.equal(await evaluate("document.querySelector('[name=fee]').value"), '0.1', 'default fee');
      await evaluate(`Object.entries({asset_code:'000001',asset_name:'测试基金',asset_type:'fund',operation:'buy',trade_date:'2026-09-10',units:'10.12',price:'1.234567',fee:'0.10',reason:'浏览器测试，不写真实数据'}).forEach(([key,value])=>{const el=document.querySelector('.formPanel [name="'+key+'"]'); const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));})`);
      await until("document.querySelector('.transactionAmountPreview output').textContent==='¥12.59'");
      const setTradeField = async (name, value) => evaluate(`(() => { const el=document.querySelector('.formPanel [name="${name}"]'); const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(el,'${value}'); el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true})); })()`);
      await setTradeField('operation', 'sell');
      await until("document.querySelector('.transactionAmountPreview output').textContent==='¥12.39'");
      assert.equal(await evaluate("document.querySelector('.transactionAmountPreview small').textContent"), '份额 × 价格 − 手续费');
      await setTradeField('fee', '0.25');
      await until("document.querySelector('.transactionAmountPreview output').textContent==='¥12.24'");
      await setTradeField('fee', '0');
      await until("document.querySelector('.transactionAmountPreview output').textContent==='¥12.49'");
      await setTradeField('operation', 'buy');
      await setTradeField('fee', '0.10');
      await until("document.querySelector('.transactionAmountPreview output').textContent==='¥12.59'");
      assert.equal(await evaluate("document.querySelector('.transactionAmountPreview small').textContent"), '份额 × 价格 + 手续费');
      await evaluate("window.__trendTest.failWrite=true; document.querySelector('.formPanel').requestSubmit()");
      await until("!!document.querySelector('.transactionToast[data-type=error]')");
      assert.equal(await evaluate("document.querySelector('[name=units]').value"), '10.12', 'failed submission retains input');
      await evaluate("window.__trendTest.failWrite=false; document.querySelector('.formPanel').requestSubmit()");
      await until("window.__trendTest.writes.length===1 && !document.querySelector('.formPanel button').disabled");
      assert.deepEqual(await evaluate('window.__trendTest.writes[0].payload'), { asset_code:'000001', asset_name:'测试基金', asset_type:'fund', operation:'buy', trade_date:'2026-09-10',  units:'10.12', price:'1.234567', fee:'0.10', reason:'浏览器测试，不写真实数据' });
      assert.equal(await evaluate("document.querySelector('[name=units]').value"), '', 'successful submission resets form');
      assert.equal(await evaluate("document.querySelector('.transactionAmountPreview output').textContent"), '¥--', 'preview resets');
      assert.equal(await evaluate("document.querySelector('[name=fee]').value"), '0.1', 'fee resets');
      assert.equal(await evaluate("document.querySelector('[name=trade_date]').value"), today, 'date resets');
      await evaluate("document.querySelector('.retractButton').click()");
      await until("!!document.querySelector('.confirmDialog')");
      assert(await evaluate("(() => {const r=document.querySelector('.confirmDialog').getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight})()"), 'retraction confirmation stays in viewport after page scroll');
      await capture('confirm');
      await evaluate("document.querySelector('.confirmDialog .secondaryButton').click()");
      assert.equal(await evaluate('window.__trendTest.writes.length'), 1, 'cancel retraction never writes');
      await evaluate("document.querySelector('.retractButton').click(); window.__trendTest.failWrite=true");
      await until("!!document.querySelector('.confirmDialog')");
      await evaluate("document.querySelector('.confirmDialog .dangerButton').click()");
      await until("[...document.querySelectorAll('.transactionToast')].some(el=>el.textContent.includes('测试撤回失败'))");
      assert(await evaluate("!!document.querySelector('.confirmDialog')"), 'failed retraction leaves confirmation available');
      await evaluate("window.__trendTest.failWrite=false; document.querySelector('.confirmDialog .dangerButton').click()");
      await until("window.__trendTest.writes.length===2 && !document.querySelector('.confirmDialog')");
      assert.equal(await evaluate('window.__trendTest.writes[1].path'), '/transactions/1');
      assert.equal(await evaluate("document.querySelectorAll('.retractedTransaction').length"), 2);
      await evaluate("document.querySelector('.correctionRow .compactAction').click()");
      await until("!!document.querySelector('.holdingEditor')");
      assert(await evaluate("document.querySelector('.holdingEditor').getBoundingClientRect().top>=0"), 'correction editor opens from transactions');
      await evaluate("document.querySelector('.holdingEditorActions .iconButton').click()");
      await setTradeField('asset_code', '000001');
      await setTradeField('operation', 'sell');
      await setTradeField('units', '300');
      await setTradeField('price', '1.462');
      await until("document.querySelector('.transactionAmountPreview output').textContent==='¥438.50'");
      await evaluate("document.querySelector('.formPanel').requestSubmit()");
      await until("window.__trendTest.writes.length===3 && !document.querySelector('.formPanel button').disabled");
      assert.equal(await evaluate('window.__trendTest.writes[2].payload.operation'), 'sell');
      assert.equal(await evaluate('window.__trendTest.writes[2].payload.fee'), '0.1');
      assert.equal(await evaluate("document.querySelector('[name=operation]').value"), 'buy', 'sell submission resets operation');
      for (const [width,height] of [[375,900],[844,390]]) {
        await send('Emulation.setDeviceMetricsOverride', { width,height,deviceScaleFactor:1,mobile:false });
        await evaluate("document.querySelector('.formPanel').scrollIntoView()");
        await new Promise(resolve=>setTimeout(resolve,250));
        assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'no page overflow at ' + width);
        assert(await evaluate("[...document.querySelectorAll('.formGrid input,.formGrid select,.formGrid textarea')].every(el=>el.getBoundingClientRect().right<=document.documentElement.clientWidth)"), 'fields fit narrow viewport');
        await capture('mobile-' + width);
        await evaluate("document.querySelector('.transactionTableWrap').scrollLeft=99999; document.querySelector('.retractButton').click()");
        await until("!!document.querySelector('.confirmDialog')");
        assert(await evaluate("(() => {const r=document.querySelector('.confirmDialog').getBoundingClientRect();return r.left>=0 && r.right<=document.documentElement.clientWidth && r.top>=0 && r.bottom<=innerHeight})()"), 'confirmation fits narrow/landscape viewport');
        await evaluate("document.querySelector('.confirmDialog .secondaryButton').click()");
      }
      await send('Emulation.setDeviceMetricsOverride', { width:1660,height:1272,deviceScaleFactor:1,mobile:false });
      await evaluate("sessionStorage.setItem('transactions-volume','large')");
      await send('Page.reload');
      await until("!!document.querySelector('.virtualTableBody tr')");
      await new Promise(resolve=>setTimeout(resolve,350));
      await columnsAligned();
      await evaluate("document.querySelector('.transactionTableWrap').scrollTop=999999");
      await until("!!document.querySelector('tr[data-index=\"119\"]')");
      await columnsAligned();
      assert(await evaluate("(() => {const rows=[...document.querySelectorAll('.virtualTableBody tr')].map(el=>el.getBoundingClientRect());return rows.slice(1).every((r,i)=>r.top>=rows[i].bottom-1)})()"), '120-row virtual ledger does not overlap');
      await evaluate("sessionStorage.setItem('transactions-read-error','true')");
      await send('Page.reload');
      await until("!!document.querySelector('.transactionsView .notice')");
      await evaluate("window.__trendTest.failRead=false; window.__trendTest.empty=true; document.querySelector('.refreshRetryButton').click()");
      await until("!!document.querySelector('.transactionsView .holdingsEmpty')");
      console.log('PASS: transactions labels, palette, create/failure/reset, retraction/cancel/failure, correction dialog, empty/error, narrow layouts and 120-row virtualization; all writes mocked');
      await send('Browser.close');
      return;
    }
    if (holdingsMode) {
      await until("document.querySelectorAll('.holdingIdentity').length===4");
      const capture = async name => { if(process.env.TEST_SCREENSHOT_DIR) { const result=await send('Page.captureScreenshot',{format:'png'}); writeFileSync(join(process.env.TEST_SCREENSHOT_DIR,'holdings-'+name+'.png'),Buffer.from(result.data,'base64')); } };
      await new Promise(resolve=>setTimeout(resolve,500));
      const fonts = await evaluate(`Object.fromEntries(['.holdingIdentity strong','.holdingAudit','.holdingsTable td.numberCell','.holdingsTable th','.holdingsMetric span','.holdingsFooter'].map(q=>[q,getComputedStyle(document.querySelector(q)).fontSize]))`);
      for(const [selector,size] of Object.entries(fonts)) assert(parseFloat(size)>=15,selector+' must be readable');
      assert.equal(fonts['.holdingIdentity strong'],'19px');
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.assetTypeBadge')).backgroundColor"),'rgba(0, 0, 0, 0)');
      const columnsAligned = async () => {
        const offsets=await evaluate(`(() => {const headers=[...document.querySelectorAll('.holdingsTable th')];const cells=[...document.querySelector('.holdingsTable tbody tr').children];return headers.map((h,i)=>Math.abs(h.getBoundingClientRect().left-cells[i].getBoundingClientRect().left))})()`);
        assert(offsets.every(value=>value<2),'header and row columns align: '+offsets);
      };
      await columnsAligned();
      await capture('desktop');
      await evaluate("document.querySelector('.compactAction').click()");
      await until("!!document.querySelector('.holdingEditor')");
      await new Promise(resolve=>setTimeout(resolve,300));
      const editor=await evaluate(`(() => {const el=document.querySelector('.holdingEditor');const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom,font:getComputedStyle(el.querySelector('input')).fontSize}})()`);
      assert(editor.top>=0 && editor.bottom<=1272,'editor fits viewport');
      assert.equal(editor.font,'17px');
      await capture('editor');
      await evaluate("document.querySelector('.holdingEditorActions .primaryButton').click()");
      await until("!!document.querySelector('.holdingEditorError')");
      assert.equal(await evaluate('window.__trendTest.writes.length'),0,'unchanged form must not save');
      await evaluate("(() => {const el=document.querySelector('.holdingEditor [name=amount]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'123456.79');el.dispatchEvent(new Event('input',{bubbles:true}));})()");
      await evaluate("document.querySelector('.holdingEditorActions .primaryButton').click()");
      await until("document.querySelector('.holdingEditorError').textContent.includes('修正原因')");
      assert.equal(await evaluate('window.__trendTest.writes.length'),0,'missing correction reason must not save');
      await evaluate("document.querySelector('.holdingEditorReason textarea').focus()");
      await send('Input.insertText',{text:'浏览器测试，仅模拟保存'});
      await evaluate("document.querySelector('.holdingEditorActions .primaryButton').click()");
      await until("!document.querySelector('.holdingEditor')");
      assert.equal(await evaluate('window.__trendTest.writes.length'),1);
      assert.equal(await evaluate('window.__trendTest.writes[0].amount'),'123456.79');
      await evaluate("document.querySelector('.holdingEditButton').click()");
      await until("!!document.querySelector('.holdingEditor [name=custom_name]')");
      await evaluate("(() => {const el=document.querySelector('[name=custom_name]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'示例半导体ETF');el.dispatchEvent(new Event('input',{bubbles:true}));})()");
      await evaluate("window.__trendTest.failWrite=true;document.querySelector('.holdingEditorActions .primaryButton').click()");
      await until("!!document.querySelector('.holdingEditorError')");
      assert.equal(await evaluate("document.querySelector('[name=custom_name]').value"),'示例半导体ETF','failed rename retains input');
      await evaluate("window.__trendTest.failWrite=false;document.querySelector('.holdingEditorActions .primaryButton').click()");
      await until("!document.querySelector('.holdingEditor') && document.querySelector('.holdingIdentity strong').textContent==='示例半导体ETF'");
      assert.deepEqual(await evaluate('window.__trendTest.writes[1]'),{custom_name:'示例半导体ETF'},'name-only save never submits position fields or reason');
      assert.equal(await evaluate('window.__trendTest.detailReads || 0'),0,'history fetched only when opened');
      await evaluate("document.querySelector('.holdingDetailButton').focus();document.querySelector('.holdingDetailButton').click()");
      await until("document.querySelectorAll('.holdingDetailTable tbody tr').length===2");
      await new Promise(resolve=>setTimeout(resolve,350));
      assert.equal(await evaluate("document.querySelector('#holding-detail-title').textContent"),'示例半导体ETF');
      assert(await evaluate("document.querySelector('.holdingDetailTable').textContent.includes('买入') && document.querySelector('.holdingDetailTable').textContent.includes('调整')"),'matching asset operations displayed');
      assert(await evaluate("document.querySelector('.holdingDetailTable').textContent.includes('2026-09-10') && document.querySelector('.holdingDetailTable').textContent.includes('1.2345')"),'trade date and price displayed');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',modifiers:8});
      assert(await evaluate("document.activeElement.classList.contains('holdingDetailTableWrap')"),'shift-tab stays in dialog');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab'});
      assert(await evaluate("document.activeElement.classList.contains('modalCloseButton')"),'tab wraps to dialog close button');
      await capture('detail');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
      await until("!document.querySelector('.holdingDetail')");
      assert(await evaluate("document.activeElement.classList.contains('holdingDetailButton')"),'detail restores focus');
      await evaluate("window.__trendTest.failDetail=true;document.querySelectorAll('.holdingDetailButton')[1].click()");
      await until("!!document.querySelector('.holdingDetailError')");
      await evaluate("window.__trendTest.failDetail=false;document.querySelector('.holdingDetailError button').click()");
      await until("!!document.querySelector('.holdingDetailRetracted')");
      assert(await evaluate("document.querySelector('.holdingDetailRetracted').textContent.includes('已撤回')"),'retracted record retained and labeled');
      await evaluate("document.querySelector('.holdingDetail .modalCloseButton').click(); window.__trendTest.emptyDetail=true;document.querySelectorAll('.holdingDetailButton')[2].click()");
      await until("!!document.querySelector('.holdingDetail .holdingsEmpty')");
      await evaluate("document.querySelector('.holdingDetail .modalCloseButton').click();window.__trendTest.emptyDetail=false");
      await send('Emulation.setDeviceMetricsOverride',{width:390,height:1100,deviceScaleFactor:1,mobile:false});
      await evaluate("document.querySelector('.holdingsView').scrollIntoView()");
      await new Promise(resolve=>setTimeout(resolve,250));
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'only table may scroll horizontally');
      await capture('mobile');
      await evaluate("document.querySelector('.holdingsTableWrap').scrollLeft=99999");
      assert(await evaluate("document.querySelector('.holdingsTableWrap').scrollLeft>0"),'table can reach right-hand actions');
      await evaluate("document.querySelector('.compactAction').click()");
      await until("!!document.querySelector('.holdingEditor')");
      await new Promise(resolve=>setTimeout(resolve,250));
      await capture('mobile-editor');
      assert(await evaluate("document.querySelector('.holdingEditor').scrollWidth<=document.querySelector('.holdingEditor').clientWidth"),'editor has no horizontal overflow');
      assert(await evaluate("(() => {const r=document.querySelector('.holdingEditor').getBoundingClientRect();return r.left>=0 && r.right<=document.documentElement.clientWidth && document.documentElement.scrollWidth<=innerWidth})()"),'mobile editor fits within viewport without page overflow');
      assert(await evaluate("[...document.querySelectorAll('.holdingsMetric strong')].every(el=>el.getBoundingClientRect().height<=parseFloat(getComputedStyle(el).lineHeight)+1)"),'mobile summary values stay on one line');
      await evaluate("document.querySelector('.holdingEditorActions .iconButton').click()");
      assert.equal(await evaluate('window.__trendTest.writes.length'),2,'cancel never saves');
      await evaluate("document.querySelector('.holdingDetailButton').click()");
      await until("!!document.querySelector('.holdingDetailTable')");
      await new Promise(resolve=>setTimeout(resolve,350));
      assert(await evaluate("(() => {const r=document.querySelector('.holdingDetail').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight})()"),'detail fits narrow viewport');
      assert(await evaluate("document.documentElement.scrollWidth<=innerWidth"),'detail does not overflow page');
      await capture('mobile-detail');
      await send('Emulation.setDeviceMetricsOverride',{width:844,height:390,deviceScaleFactor:1,mobile:false});
      assert(await evaluate("(() => {const r=document.querySelector('.holdingDetail').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight})()"),'detail fits landscape viewport');
      await evaluate("document.querySelector('.holdingDetail .modalCloseButton').click()");
      await send('Emulation.setDeviceMetricsOverride',{width:1660,height:1272,deviceScaleFactor:1,mobile:false});
      await evaluate("sessionStorage.setItem('holdings-volume','large')");
      await send('Page.reload');
      await until("!!document.querySelector('.virtualTableBody tr')");
      await new Promise(resolve=>setTimeout(resolve,500));
      await columnsAligned();
      await evaluate("document.querySelector('.holdingsTableWrap').scrollTop=999999");
      await until("!!document.querySelector('tr[data-index=\"119\"]')");
      const overlap=await evaluate(`(() => {const rows=[...document.querySelectorAll('.virtualTableBody tr')].map(r=>r.getBoundingClientRect());return rows.slice(1).some((r,i)=>r.top<rows[i].bottom-1)})()`);
      assert(!overlap,'larger virtual rows do not overlap');
      await columnsAligned();
      console.log('PASS: holdings rename/failure, correction validation/save/cancel, asset history/retractions/error/retry/empty/focus, mobile dialogs, columns and 120-row virtualization; all writes mocked');
      await send('Browser.close');
      return;
    }
    if (frontierMode) {
      await until("document.querySelectorAll('.frontierNewsItem').length===3");
      const visual = await evaluate(`(() => {
        const s=q=>getComputedStyle(document.querySelector(q));
        return {card:s('.frontierNewsItem').backgroundColor,title:s('.frontierNewsItem a').color,tag:s('.tagFilter.active').color,up:s('.relatedHoldings .upText').color,down:s('.relatedHoldings .downText').color,checkbox:document.querySelector('.newsToggle input').getBoundingClientRect().width};
      })()`);
      assert.equal(visual.card, 'rgba(7, 14, 29, 0.36)');
      assert.equal(visual.title, 'rgb(244, 242, 220)');
      assert.equal(visual.tag, 'rgb(225, 189, 114)');
      assert.notEqual(visual.up, visual.down);
      assert.equal(visual.checkbox, 16);
      const capture = async name => {
        if (!process.env.TEST_SCREENSHOT_DIR) return;
        const result = await send('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(process.env.TEST_SCREENSHOT_DIR, 'frontier-' + name + '.png'), Buffer.from(result.data, 'base64'));
      };
      await capture('desktop');
      await evaluate("document.querySelectorAll('.tagFilter')[2].click()");
      await until("document.querySelectorAll('.frontierNewsItem').length===1");
      assert.equal(await evaluate("document.querySelectorAll('.tagFilter')[2].getAttribute('aria-pressed')"), 'true');
      await evaluate("document.querySelector('.tagFilter').click()");
      await until("document.querySelectorAll('.frontierNewsItem').length===3");
      await evaluate("var newsSelect=document.querySelector('.newsFilterBar select'); newsSelect.value='source-b'; newsSelect.dispatchEvent(new Event('change',{bubbles:true}))");
      await until("document.querySelectorAll('.frontierNewsItem').length===1");
      await evaluate("var newsSelect=document.querySelector('.newsFilterBar select'); newsSelect.value=''; newsSelect.dispatchEvent(new Event('change',{bubbles:true})); document.querySelector('.newsToggle input').click()");
      await until("document.querySelectorAll('.frontierNewsItem').length===1 && !!document.querySelector('.relatedHoldings')");
      await evaluate("document.querySelector('.newsToggle input').click(); var newsSelect=document.querySelectorAll('.newsFilterBar select')[1]; newsSelect.value='5'; newsSelect.dispatchEvent(new Event('change',{bubbles:true}))");
      await until("document.querySelectorAll('.frontierNewsItem').length===1");
      await evaluate("var newsSelect=document.querySelectorAll('.newsFilterBar select')[1]; newsSelect.value='0'; newsSelect.dispatchEvent(new Event('change',{bubbles:true})); document.querySelectorAll('.tagFilter')[4].click()");
      await until("!!document.querySelector('.frontierLayout .trackingEmpty')");
      await evaluate("document.querySelector('.impactStrip button').click()");
      await until("document.querySelectorAll('.frontierNewsItem').length===1");
      await assertNoRefresh('news filters do not trigger source refresh');
      await evaluate("document.querySelector('.frontierNewsPanel > .sectionHeader .iconButton').click()");
      await until('window.__trendTest.refreshes.length===1');
      await until("!!document.querySelector('[data-sonner-toast].frontierToast')");
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.frontierToast')).backgroundColor"), 'rgb(12, 22, 43)', 'refresh toast uses navy instead of green');
      await evaluate("document.querySelector('.tagFilter').click()");
      await until("document.querySelectorAll('.frontierNewsItem').length===3");
      await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 1500, deviceScaleFactor: 1, mobile: false });
      await evaluate("document.querySelector('.frontierLayout').scrollIntoView()");
      await new Promise(resolve=>setTimeout(resolve,250));
      const mobile = await evaluate('({page:document.documentElement.scrollWidth,viewport:innerWidth})');
      assert(mobile.page<=mobile.viewport, 'news page has no mobile horizontal overflow');
      await capture('mobile');
      console.log('PASS: newsroom palette, tags, sources, importance, related-only, empty state, manual refresh, mobile layout');
      await send('Browser.close');
      return;
    }
    await settled();
    if (sidebarMode) {
      const geometry = () => evaluate(`(() => {
        const sidebar = document.querySelector('.sidebar');
        const box = sidebar.getBoundingClientRect();
        return { top: box.top, left: box.left, right: box.right, height: box.height, scroll: scrollY, mainLeft: document.querySelector('.mainPanel').getBoundingClientRect().left, position: getComputedStyle(sidebar).position };
      })()`);
      for (const y of [0, 650, 99999]) {
        await evaluate(`window.scrollTo(0, ${y})`);
        await new Promise(resolve => setTimeout(resolve, 150));
        const box = await geometry();
        console.log('Sidebar geometry:', JSON.stringify(box));
        if (y) assert(box.scroll > 0, 'long-page fixture actually scrolls');
        assert.equal(box.top, 0, 'sidebar stays at viewport top');
        assert.equal(box.left, 0, 'sidebar stays at viewport left');
        assert.equal(box.height, 1272, 'sidebar fills viewport height');
        assert(box.mainLeft >= box.right, 'main content is not obscured');
      }
      await send('Emulation.setDeviceMetricsOverride', { width: 1200, height: 500, deviceScaleFactor: 1, mobile: false });
      await evaluate("document.querySelector('.sidebar').scrollTop=99999");
      const compact = await evaluate(`(() => { const s=document.querySelector('.sidebar'); const b=document.querySelector('.shutdownButton').getBoundingClientRect(); return {scrolled:s.scrollTop,top:b.top,bottom:b.bottom,navHeight:document.querySelector('.navButton').getBoundingClientRect().height}; })()`);
      assert(compact.scrolled > 0, 'short-window sidebar scrolls independently');
      assert(compact.top >= 0 && compact.bottom <= 500, 'exit remains reachable');
      assert(compact.navHeight >= 42, 'navigation does not shrink');
      await send('Emulation.setDeviceMetricsOverride', { width: 800, height: 900, deviceScaleFactor: 1, mobile: false });
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.nav')).gridTemplateColumns.split(' ').length"),8,'tablet navigation keeps all eight pages visible');
      await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
      await evaluate('window.scrollTo(0,0)');
      await new Promise(resolve => setTimeout(resolve, 150));
      const mobile = await evaluate(`({ position:getComputedStyle(document.querySelector('.sidebar')).position, width:document.documentElement.scrollWidth, viewport:innerWidth })`);
      assert.equal(mobile.position, 'relative', 'mobile keeps existing stacked navigation');
      assert.equal(await evaluate("document.querySelectorAll('.navButton').length"),8,'mobile navigation keeps all eight pages visible');
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.nav')).gridTemplateColumns.split(' ').length"),4,'mobile navigation uses compact icon grid');
      assert(mobile.width <= mobile.viewport, 'mobile has no horizontal overflow');
      await assertNoRefresh('scrolling and resizing never refresh quotes');
      console.log('PASS: fixed sidebar at top/middle/bottom; short-window controls and mobile layout');
      await send('Browser.close');
      return;
    }
    await assertNoRefresh('enter charts reads cache only');
    const previousGeneration = await evaluate('window.__trendTest.generation');
    await send('Page.reload');
    await until(`window.__trendTest && window.__trendTest.generation !== ${JSON.stringify(previousGeneration)}`);
    await settled();
    await assertNoRefresh('browser reload reads cache only');
    await until("!!document.querySelector('.removeWatchButton')");
    await evaluate("document.querySelector('.removeWatchButton').click()");
    await until("!!document.querySelector('.trackingDetailModalBar button')");
    await evaluate("document.querySelector('.trackingDetailModalBar button').click()");
    await until("!document.querySelector('.trackingDetail')");
    await settled();
    await assertNoRefresh('detail open and close never refresh list');
    await evaluate("window.dispatchEvent(new Event('focus')); window.dispatchEvent(new Event('online'))");
    await settled();
    await assertNoRefresh('focus and reconnect never refresh quotes');
    await evaluate("document.querySelectorAll('.tagFilterOptions button')[1].click()");
    await settled();
    await assertNoRefresh('tag filter never refreshes quotes');
    await evaluate("document.querySelector('.chartsRefreshActions button').click()");
    await until("!!document.querySelector('.refreshStatusStrip.complete')");
    assert.deepEqual(await evaluate('window.__trendTest.refreshes'), [[1]], 'manual click refreshes selected tag only');
    console.log('PASS: manual click refreshes selected tag only');
    await evaluate("document.querySelector('.tagFilterOptions button').click(); window.__trendTest.refreshes=[]");
    await evaluate("document.querySelector('.chartsRefreshActions button').click()");
    await until("!!document.querySelector('.refreshStatusStrip.complete')");
    assert.deepEqual(await evaluate('window.__trendTest.refreshes'), [[1,2,3,4,5,6,7],[8]], 'manual click preserves batching');
    console.log('PASS: manual click preserves batching');
    await evaluate("window.__trendTest.refreshes=[]; const field=document.querySelector('input[aria-label=\"股票或基金代码\"]'); field.focus()");
    await send('Input.insertText', { text: '000009' });
    await evaluate("document.querySelector('.watchlistAddButton').click()");
    await until("document.querySelectorAll('.fundTrendCard').length===9");
    await settled();
    await assertNoRefresh('adding a tracking item reads cache only');
    await evaluate("const select=document.querySelector('.watchlistSelect'); select.value='2'; select.dispatchEvent(new Event('change',{bubbles:true}))");
    await until("document.querySelectorAll('.fundTrendCard').length===1");
    await settled();
    await assertNoRefresh('switching watchlist reads cache only');
    await evaluate("window.__trendTest.failCache=true; location.hash='holdings'");
    await until("!document.querySelector('.chartsWorkspace')");
    await evaluate("location.hash='charts'");
    await until("!!document.querySelector('.chartsWorkspace .notice')");
    await assertNoRefresh('cache failure never falls through to refresh');
    await evaluate("window.__trendTest.failCache=false; location.hash='holdings'");
    await until("!document.querySelector('.chartsWorkspace')");
    await evaluate("location.hash='charts'");
    await settled();
    await assertNoRefresh('re-entering charts reads cache only');
    await evaluate("window.__trendTest.failRefresh=true; document.querySelector('.chartsRefreshActions button').click()");
    await until("!!document.querySelector('.refreshStatusStrip.failed')");
    const failedCount = await count();
    await new Promise(resolve => setTimeout(resolve, 600));
    assert.equal(await count(), failedCount, 'failed refresh has no automatic retry');
    assert.equal(await evaluate("document.querySelectorAll('.refreshRetryButton,.secondaryRefreshButton').length"), 0, 'only refresh-current initiates updates');
    console.log('PASS: failed refresh does not retry automatically; single refresh entry point');
    await send('Browser.close');
  } finally { if (ws) ws.close(); browser.kill(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
