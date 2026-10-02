// Browser regression: run with Vite on 5173. All API calls are mocked in-page;
// this test never refreshes real quotes or edits the user's watchlists.
// Set CHROME_PATH / TEST_BASE_URL to override the local browser / dev URL.
const { spawn } = require('node:child_process');
const { mkdtempSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const assert = require('node:assert/strict');

function installFixtures(longPage = false, newsPage = false, holdingsPage = false, transactionsPage = false) {
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
    retracted_at: i === 5 ? '2026-09-10T12:00:00' : null,
    retraction_reason: i === 5 ? '重复录入，已撤回' : null,
    retraction_effect: i === 5 ? '{"amount_before":"123456.78","amount_after":"0"}' : null,
  }));
  const originalFetch = window.fetch;
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!url.pathname.startsWith('/api/')) return originalFetch(input, init);
    const path = url.pathname.slice(4);
    const state = window.__trendTest;
    let result = [];
    let status = 200;
    if (transactionsPage && path === '/transactions') {
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
    else if (holdingsPage && /\/holdings\/\d+$/.test(path) && init.method==='PATCH') { const payload=JSON.parse(init.body); state.writes.push(payload); result={...holdings[0],...payload}; }
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
      message.error ? call.reject(new Error(JSON.stringify(message.error))) : call.resolve(message.result);
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const requestId = ++id;
      const timer = setTimeout(() => { pending.delete(requestId); reject(new Error(method + ' timeout')); }, 15000);
      pending.set(requestId, { resolve, reject, timer });
      ws.send(JSON.stringify({ id: requestId, method, params }));
    });
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
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
    await send('Page.addScriptToEvaluateOnNewDocument', { source: '(' + installFixtures.toString() + ')(' + sidebarMode + ',' + frontierMode + ',' + holdingsMode + ',' + transactionsMode + ')' });
    if (agentMode) await send('Page.addScriptToEvaluateOnNewDocument', { source: '(' + require('./check-agent.cjs').installAgentFixtures.toString() + ')()' });
    await send('Emulation.setDeviceMetricsOverride', { width: 1660, height: 1272, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: (process.env.TEST_BASE_URL || 'http://127.0.0.1:5173') + (agentMode ? '/#agent' : transactionsMode ? '/#transactions' : holdingsMode ? '/#holdings' : frontierMode ? '/#frontierNews' : '/#charts') });
    if (agentMode) {
      await require('./check-agent.cjs').checkAgent({ send, evaluate, until });
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
      await evaluate(`Object.entries({asset_code:'000001',asset_name:'测试基金',asset_type:'fund',operation:'buy',trade_date:'2026-09-10',amount:'123.45',units:'10.12',price:'1.234567',fee:'0.10',reason:'浏览器测试，不写真实数据'}).forEach(([key,value])=>document.querySelector('.formPanel [name="'+key+'"]').value=value)`);
      await evaluate("window.__trendTest.failWrite=true; document.querySelector('.formPanel').requestSubmit()");
      await until("!!document.querySelector('.transactionToast[data-type=error]')");
      assert.equal(await evaluate("document.querySelector('[name=amount]').value"), '123.45', 'failed submission retains input');
      await evaluate("window.__trendTest.failWrite=false; document.querySelector('.formPanel').requestSubmit()");
      await until("window.__trendTest.writes.length===1 && !document.querySelector('.formPanel button').disabled");
      assert.deepEqual(await evaluate('window.__trendTest.writes[0].payload'), { asset_code:'000001', asset_name:'测试基金', asset_type:'fund', operation:'buy', trade_date:'2026-09-10', amount:'123.45', units:'10.12', price:'1.234567', fee:'0.10', reason:'浏览器测试，不写真实数据' });
      assert.equal(await evaluate("document.querySelector('[name=amount]').value"), '', 'successful submission resets form');
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
      assert.equal(await evaluate('window.__trendTest.writes.length'),0,'missing reason must not save');
      await evaluate("document.querySelector('.holdingEditorReason textarea').focus()");
      await send('Input.insertText',{text:'浏览器测试，仅模拟保存'});
      await evaluate("document.querySelector('.holdingEditorActions .primaryButton').click()");
      await until("!document.querySelector('.holdingEditor')");
      assert.equal(await evaluate('window.__trendTest.writes.length'),1);
      assert.equal(await evaluate('window.__trendTest.writes[0].amount'),'123456.78');
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
      assert.equal(await evaluate('window.__trendTest.writes.length'),1,'cancel never saves');
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
      console.log('PASS: holdings typography, columns, correction validation/save/cancel, mobile scrolling, 120-row virtualization; all writes mocked');
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
      await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
      await evaluate('window.scrollTo(0,0)');
      await new Promise(resolve => setTimeout(resolve, 150));
      const mobile = await evaluate(`({ position:getComputedStyle(document.querySelector('.sidebar')).position, width:document.documentElement.scrollWidth, viewport:innerWidth })`);
      assert.equal(mobile.position, 'relative', 'mobile keeps existing stacked navigation');
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
