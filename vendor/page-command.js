async function pageCommand(command, input) {
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const hash = value => {
    let number = 2166136261;
    for (let i = 0; i < value.length; i++) {
      number ^= value.charCodeAt(i);
      number = Math.imul(number, 16777619);
    }
    return (`00000000${(number >>> 0).toString(16)}`).slice(-8);
  };
  const loginState = () => {
    const text = clean(document.body?.innerText || '');
    const isVisible = node => Boolean(node && (node.offsetWidth || node.offsetHeight || node.getClientRects().length));
    const visibleCredential = [...document.querySelectorAll(
      'input[type=password],input[name*=captcha i],input[id*=captcha i]'
    )].some(isVisible);
    const loginText = /用户登录|账号登录|密码登录|滑块验证|图片验证码/.test(text);
    const markers = ['采购中心','待审批','竞价单审批','服务竞价单审批','请购单审批','退出']
      .filter(marker => text.includes(marker)).length;
    const expired = location.pathname === '/login' || /disable-devtool/i.test(location.href) ||
      (visibleCredential && loginText && markers === 0);
    return expired || markers === 0 ? 'LOGIN_EXPIRED' : 'LOGIN_OK';
  };
  const tableWithActions = () => [...document.querySelectorAll('table')].find(table =>
    [...table.querySelectorAll('thead th')].some(th => clean(th.innerText) === '操作'));
  const auctionRows = () => {
    const table = tableWithActions();
    if (!table) return [];
    return [...table.querySelectorAll('tbody tr')].map((row, index) => {
      let action = [...row.querySelectorAll('a,button,input')]
        .find(node => clean(node.innerText || node.value) === '审批');
      const icon = [...row.querySelectorAll('img')]
        .find(node => /shenpi-(jingjia|queren)/.test(node.getAttribute('src') || ''));
      if (!action && icon) action = icon.closest('a,button') || icon.parentElement;
      if (!action) return null;
      const source = icon?.getAttribute('src') || '';
      const rawKey = `${action.getAttribute('onclick') || ''}|${action.getAttribute('href') || ''}|${clean(row.innerText)}`;
      return { index, key: hash(rawKey), kind: /shenpi-queren/.test(source) ? 'confirm' : 'bid' };
    }).filter(Boolean);
  };
  const procurementRows = () => {
    const table = tableWithActions();
    if (!table) return [];
    return [...table.querySelectorAll('tbody tr')].map((row, index) => {
      const action = [...row.querySelectorAll('a,button,input')].find(node =>
        /agree\s*\(/.test(node.getAttribute('onclick') || '') || clean(node.innerText || node.value) === '同意');
      if (!action) return null;
      const rowText = clean(row.innerText);
      return { index, key: hash(`${action.getAttribute('onclick') || ''}|${rowText}`), kind: 'procurement' };
    }).filter(Boolean);
  };
  const rowsFor = category => category.endsWith('Procurement') ? procurementRows() : auctionRows();

  if (command === 'list') {
    const status = loginState();
    const expectedPath = String(input.expectedPath || '');
    const pathMatches = !expectedPath || location.pathname === expectedPath;
    const rows = status === 'LOGIN_OK' && pathMatches ? rowsFor(input.category) : [];
    return {
      status,
      tableReady: status === 'LOGIN_OK' && pathMatches && Boolean(tableWithActions()),
      rows,
      signature: rows.map(row => row.key).join(',')
    };
  }
  if (command === 'open') {
    const rows = auctionRows();
    const target = rows.find(row => row.key === input.key);
    if (!target) return { ok: false, reason: '页面或接口异常无法判断' };
    const table = tableWithActions();
    const row = [...table.querySelectorAll('tbody tr')][target.index];
    let action = [...row.querySelectorAll('a,button,input')]
      .find(node => clean(node.innerText || node.value) === '审批');
    if (!action) {
      const icon = [...row.querySelectorAll('img')]
        .find(node => /shenpi-(jingjia|queren)/.test(node.getAttribute('src') || ''));
      action = icon && (icon.closest('a,button') || icon.parentElement);
    }
    if (!action) return { ok: false, reason: '页面或接口异常无法判断' };
    action.click();
    return { ok: true };
  }
  if (command === 'detailReady') {
    const status = loginState();
    if (status !== 'LOGIN_OK') return { status, ready: false };
    const path = location.pathname;
    const expectedPath = input.category === 'service'
      ? '/creEnquiryWorkflowNew/forward/100'
      : '/creEnquiryWorkflow/forward/100';
    const hasAgreeAction = [...document.querySelectorAll('a,button,input')]
      .some(node => clean(node.innerText || node.value) === '同意');
    return { status, ready: path.startsWith(expectedPath) && hasAgreeAction };
  }
  if (command === 'next') {
    const before = rowsFor(input.category).map(row => row.key).join(',');
    if (!before) return { clicked: false, before };
    const candidates = [...document.querySelectorAll('a,button,input')];
    const next = candidates.find(node => /^(下一页|下页|>)$/.test(clean(node.innerText || node.value || node.title)));
    const disabled = !next || next.disabled || next.getAttribute('aria-disabled') === 'true' ||
      /disabled/.test(next.className || '') || /javascript:void\(0\)/.test(next.getAttribute('href') || '');
    if (disabled) return { clicked: false, before };
    next.click();
    return { clicked: true, before };
  }
  if (command === 'detail') {
    const text = clean(document.body?.innerText || '');
    if (loginState() !== 'LOGIN_OK') return { status: 'LOGIN_EXPIRED', approved: false, reason: '页面或接口异常无法判断' };
    const rows = [...document.querySelectorAll('tr')];
    const pair = (label, value) => rows.some(row => clean(row.innerText).includes(label) && clean(row.innerText).includes(value));
    const hasValue = labels => rows.some(row => {
      const cells = [...row.querySelectorAll('th,td')];
      return cells.some((cell, index) => {
        const normalized = clean(cell.innerText).replace(/[：:]/g, '');
        return labels.some(label => normalized === label || normalized.startsWith(label)) &&
          cells.slice(index + 1).some(candidate => Boolean(clean(candidate.innerText)));
      });
    });
    const roundText = rows.map(row => clean(row.innerText)).filter(value =>
      /竞价次数|竞价轮次|二次竞价|多轮竞价|第[二三四五六七八九]轮/.test(value));
    const multi = roundText.some(value =>
      /二次竞价|多轮竞价|第[二三四五六七八九]轮|(?:竞价次数|竞价轮次)[^0-9一二三四五六七八九]{0,8}(?:[2-9]|[二三四五六七八九])/.test(value));
    const download = [...document.querySelectorAll('a,button,input')].some(node =>
      /下载/.test(clean(node.innerText || node.value || node.title)) &&
      Boolean(node.getAttribute('href') || node.getAttribute('onclick')));
    const totalPriceLabel = '报价单总价';
    const totalPriceTable = [...document.querySelectorAll('table')].find(table =>
      [...table.querySelectorAll('tr')].some(row =>
        [...row.querySelectorAll('th,td')].some(cell => clean(cell.innerText).includes(totalPriceLabel))));
    let confirmationFirstIsMinimum = false;
    if (totalPriceTable) {
      const headerRow = [...totalPriceTable.querySelectorAll('tr')].find(row =>
        [...row.querySelectorAll('th,td')].some(cell => clean(cell.innerText).includes(totalPriceLabel)));
      const headers = [...(headerRow?.querySelectorAll('th,td') || [])].map(cell => clean(cell.innerText));
      const totalIndex = headers.findIndex(value => value.includes(totalPriceLabel));
      const dataRows = [...totalPriceTable.querySelectorAll('tr')].filter(row =>
        row !== headerRow && row.querySelectorAll('td').length > totalIndex && totalIndex >= 0);
      const amounts = dataRows.map(row => {
        const raw = clean(row.querySelectorAll('td')[totalIndex]?.innerText)
          .replace(/[,，￥¥元\s]/g, '');
        const match = raw.match(/-?\d+(?:\.\d+)?/);
        return match ? Number(match[0]) : NaN;
      });
      confirmationFirstIsMinimum = amounts.length > 0 && amounts.every(Number.isFinite) &&
        Math.abs(amounts[0] - Math.min(...amounts)) < 0.000001;
    }
    const agree = [...document.querySelectorAll('a,button,input')]
      .find(node => clean(node.innerText || node.value) === '同意');
    const match = (agree?.getAttribute('onclick') || '').match(/agreeOrDisAgree\((.*)\)/s);
    let args = [];
    try { args = match ? parseLiteralArgs(match[1]) : []; } catch (_) {}
    const applyType = new URL(location.href).searchParams.get('applyType') || '';
    const scripts = [...document.scripts].map(script => script.text || '').join('\n');
    const names = [...new Set(scripts.match(/creEnquiryApprovalAutting\d+/g) || [])];
    const tokenName = names.find(name => name.endsWith(applyType)) || (names.length === 1 ? names[0] : '');
    const reject = reason => ({ status: 'COMPLETED', approved: false, manual: true, reason });
    const category = input.category;
    const kind = input.kind;
    // Missing download controls alone never prove that attachments are absent.
    const attachmentRows = rows.filter(row => {
      const cells = [...row.querySelectorAll('th,td')];
      return cells.some(cell => /^(?:竞价说明|附件|附件信息|附件列表)[：:]?$/.test(clean(cell.innerText)));
    });
    const attachmentEmpty = attachmentRows.length > 0 && attachmentRows.every(row => {
      const cells = [...row.querySelectorAll('th,td')];
      const labelIndex = cells.findIndex(cell => /^(?:竞价说明|附件|附件信息|附件列表)[：:]?$/.test(clean(cell.innerText)));
      const values = cells.slice(labelIndex + 1);
      return values.length > 0 && values.every(cell =>
        !cell.querySelector('a[href],button,input,iframe') &&
        /^(?:无|暂无附件|无附件|未上传|未上传附件|没有附件)$/.test(clean(cell.innerText)));
    });
    if (multi && kind === 'bid' &&
        ((category === 'material' && applyType === '12') || (category === 'service' && applyType === '4'))) {
      if (!attachmentEmpty || download) return reject(`${category === 'material' ? '物资' : '服务'}多轮竞价需人工审批`);
      const reason = '多轮竞价无附件';
      if (input.dryRun) return { status: 'COMPLETED', approved: false, wouldReject: true, reason };
      const visible = node => Boolean(node && (node.offsetWidth || node.offsetHeight || node.getClientRects().length));
      const rejectionButtons = () => [...document.querySelectorAll('a,button,input')]
        .filter(node => visible(node) && !node.disabled && clean(node.innerText || node.value) === '驳回');
      const buttons = rejectionButtons();
      if (buttons.length !== 1 || !window.jQuery?.ajax) return reject('驳回操作无法确认');
      // Follow the site's own handlers; never invent isAgress values or save parameters.
      buttons[0].click();
      let field, submit;
      for (let attempt = 0; attempt < 20; attempt++) {
        const dialogs = [...document.querySelectorAll('[role="dialog"],.modal,.ui-dialog,.layui-layer,.bootbox')].filter(visible);
        const scopes = dialogs.length ? dialogs : [document];
        const fields = scopes.flatMap(scope => [...scope.querySelectorAll('textarea,input[type="text"]')])
          .filter(node => visible(node) && !node.disabled && !node.readOnly &&
            /驳回原因|驳回意见|审批意见|审核意见/.test(clean(node.getAttribute('placeholder') || '') + clean(node.closest('tr,.form-group')?.innerText || '') +
              clean(node.labels ? [...node.labels].map(label => label.innerText).join(' ') : '')));
        const submits = scopes.flatMap(scope => [...scope.querySelectorAll('a,button,input')])
          .filter(node => visible(node) && !node.disabled && clean(node.innerText || node.value) === '驳回' && node !== buttons[0]);
        if (fields.length === 1 && submits.length === 1) { field = fields[0]; submit = submits[0]; break; }
        await pause(100);
      }
      if (!field || !submit) return reject('驳回原因字段或提交按钮无法确认');
      const setter = Object.getOwnPropertyDescriptor(field.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set;
      setter.call(field, '驳回');
      field.dispatchEvent(new Event('input', { bubbles: true }));
      field.dispatchEvent(new Event('change', { bubbles: true }));
      if (field.value !== '驳回') return reject('驳回原因填写失败');
      return await new Promise(resolve => {
        const original = window.jQuery.ajax;
        let finished = false;
        const finish = result => {
          if (finished) return;
          finished = true;
          clearTimeout(timer);
          if (window.jQuery.ajax === intercept) window.jQuery.ajax = original;
          resolve(result);
        };
        const timer = setTimeout(() => finish(reject('驳回结果未明确，禁止重试')), 25000);
        function intercept(options) {
          // Observe only the verified existing workflow save route.
          const url = typeof options === 'object' ? new URL(options.url || '', location.href) : null;
          if (url?.origin === location.origin && url.pathname === '/creEnquiryWorkflow/save') {
            const success = options.success, error = options.error;
            options = { ...options,
              success: function(data) {
                if (typeof data === 'string') { try { data = JSON.parse(data); } catch (_) {} }
                const rejected = String(data?.resultCode || '') === '00' && /驳回成功|审批驳回|审批已驳回|审批不通过/.test(String(data?.resultMessage || ''));
                finish(rejected ? { status: 'COMPLETED', approved: false, rejected: true, reason } : reject('驳回结果未明确，禁止重试'));
                return success?.apply(this, arguments);
              },
              error: function() { finish(reject('驳回结果未明确，禁止重试')); return error?.apply(this, arguments); }
            };
          }
          return original.call(this, options);
        }
        window.jQuery.ajax = intercept;
        try { submit.click(); } catch (_) { finish(reject('驳回结果未明确，禁止重试')); }
      });
    }
    if (category === 'material' && kind === 'bid') {
      if (applyType !== '12') return reject('页面或接口异常无法判断');
      if (!pair('报价方式', '公开报价')) return reject('报价方式不是公开报价');
      if (!pair('评分规则', '最低价法')) return reject('评分规则不是最低价法');
      if (!hasValue(['包名称','标包名称'])) return reject('包名称为空或无法确认');
      if (!hasValue(['竞价单总限价'])) return reject('竞价单总限价为空或无法确认');
      if (multi) return reject('物资多轮竞价需人工审批');
      const goodsTable = [...document.querySelectorAll('table')].find(table =>
        [...table.querySelectorAll('th')].some(th => clean(th.innerText) === '单价限价'));
      let goodsOk = false;
      if (goodsTable) {
        const headers = [...goodsTable.querySelectorAll('thead th')].map(th => clean(th.innerText));
        const limitIndex = headers.indexOf('单价限价');
        const goods = [...goodsTable.querySelectorAll('tbody tr')].filter(row => row.querySelectorAll('td').length);
        goodsOk = goods.length > 0 && limitIndex >= 0 && goods.every(row => clean(row.querySelectorAll('td')[limitIndex]?.innerText));
      }
      if (!goodsOk) {
        try {
          const url = new URL(location.href);
          // The detail template keeps these values in hidden inputs. Some
          // deployments omit enquirySource (or even enquiryId) from the URL,
          // so prefer the page-owned values and only fall back to query params.
          const hiddenValue = selector => clean(document.querySelector(selector)?.value);
          const enquiryId = hiddenValue('#enquiryId') || url.searchParams.get('enquiryId') || '';
          const enquirySource = hiddenValue('#enquirySource') || url.searchParams.get('enquirySource') || '1';
          let page = 1, pages = 1, count = 0, missing = 0;
          const extractRows = value => {
            if (Array.isArray(value)) return value;
            for (const key of ['rows','list','resultList','dataList','content']) if (Array.isArray(value?.[key])) return value[key];
            if (Array.isArray(value?.result)) return value.result;
            if (Array.isArray(value?.data)) return value.data;
            for (const key of ['data','result','page']) {
              const nested = value?.[key];
              if (Array.isArray(nested)) return nested;
              for (const rowKey of ['rows','list','resultList','dataList','content']) if (Array.isArray(nested?.[rowKey])) return nested[rowKey];
            }
            return [];
          };
          do {
            const body = new URLSearchParams({ pageNo: String(page), enquiryId, enquirySource });
            const response = await fetch('/creEnquiryWorkflow/findGoodsList', {
              method: 'POST', credentials: 'same-origin',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' },
              body: body.toString()
            });
            const data = await response.json();
            const goods = extractRows(data);
            count += goods.length;
            missing += goods.filter(row => !row?.writeLimitPrice).length;
            pages = Number(data?.pageCount || data?.pages || data?.totalPages || data?.data?.pageCount || 1);
            page++;
          } while (page <= pages);
          goodsOk = count > 0 && missing === 0;
        } catch (_) { goodsOk = false; }
      }
      if (!goodsOk) return reject('单价限价缺失或无法抓取');
    } else if (category === 'material' && kind === 'confirm') {
      if (applyType !== '20' || !/确认结果/.test(text)) return reject('确认结果类型不明确');
      if (/取消竞价/.test(text)) return reject('取消竞价或已完成');
      if (!confirmationFirstIsMinimum) return reject('报价单总价排序第一不是最小值或无法确认');
    } else if (category === 'service' && kind === 'bid') {
      if (applyType !== '4') return reject('页面或接口异常无法判断');
      if (multi) return reject('服务多轮竞价需人工审批');
      if (!pair('报价方式', '公开报价')) return reject('报价方式不是公开报价');
      if (!pair('评分规则', '最低价法')) return reject('评分规则不是最低价法');
      if (!hasValue(['包名称','标包名称'])) return reject('包名称为空或无法确认');
      if (!download) return reject('附件下载按钮缺失或无法确认');
    } else if (category === 'service' && kind === 'confirm') {
      if (applyType !== '11' || !/确认结果/.test(text)) return reject('确认结果类型不明确');
      if (/取消竞价/.test(text)) return reject('取消竞价或已完成');
      if (multi) return reject('服务多轮竞价需人工审批');
      if (!confirmationFirstIsMinimum) return reject('报价单总价排序第一不是最小值或无法确认');
    } else return reject('页面或接口异常无法判断');
    const paramsOk = args.length >= 7 && String(args[0]) === '0' && String(args[3]) === applyType && args[1] && args[2];
    const scriptOk = tokenName && scripts.includes('beanValidatorForToken') && scripts.includes('validateEnquiryWorkflow') && scripts.includes('/creEnquiryWorkflow/save');
    if (!paramsOk || !scriptOk) return reject('页面或接口异常无法判断');
    if (input.dryRun) return { status: 'COMPLETED', approved: false, wouldApprove: true };
    try {
      await pause(1000);
      const tokenQuery = new URLSearchParams({ [tokenName]: String(args[2]), applyType });
      const tokenResponse = await fetch(`/creEnquiryWorkflow/beanValidatorForToken?${tokenQuery}`, {
        credentials: 'same-origin', cache: 'no-store', headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      const tokenData = await tokenResponse.json();
      if (!tokenResponse.ok || String(tokenData?.resultCode || '') === '102') return reject('token重复或失效');
      await pause(1500);
      const validateQuery = new URLSearchParams({ enquiryId: String(args[1]), applyType });
      const validateResponse = await fetch(`/creEnquiryWorkflow/validateEnquiryWorkflow?${validateQuery}`, {
        credentials: 'same-origin', cache: 'no-store', headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!validateResponse.ok || !(await validateResponse.json())) return reject('取消竞价或已完成');
      await pause(1000);
      const body = new URLSearchParams({
        isAgress: String(args[0]), enquiryId: String(args[1]), [tokenName]: String(args[2]), opinion: '',
        applyType, gidTypeCount: String(args[4] || ''), workflowStep: String(args[5] || ''),
        winBiddingWorkflowStep: String(args[6] || '')
      });
      if (category === 'service') body.set('inviteList', '[]');
      const saveResponse = await fetch('/creEnquiryWorkflow/save', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' },
        body: body.toString()
      });
      const saveData = await saveResponse.json();
      const approved = saveResponse.ok && String(saveData?.resultCode || '') === '00' &&
        String(saveData?.resultMessage || '').includes('审批通过');
      return approved ? { status: 'COMPLETED', approved: true } : reject('保存返回未明确审批通过');
    } catch (_) { return reject('保存返回未明确审批通过'); }
  }
  if (command === 'procurement') {
    if (loginState() !== 'LOGIN_OK') return { status: 'LOGIN_EXPIRED', approved: false, reason: '页面或接口异常无法判断' };
    const rows = procurementRows();
    const target = rows.find(row => row.key === input.key);
    if (!target) return {
      status: 'COMPLETED', approved: false, manual: true,
      retryable: true, reason: '页面或接口异常无法判断'
    };
    if (input.dryRun) return { status: 'COMPLETED', approved: false, wouldApprove: true };
    const table = tableWithActions();
    const row = [...table.querySelectorAll('tbody tr')][target.index];
    const action = [...row.querySelectorAll('a,button,input')].find(node =>
      /agree\s*\(/.test(node.getAttribute('onclick') || '') || clean(node.innerText || node.value) === '同意');
    if (!action || !window.jQuery?.ajax) return {
      status: 'COMPLETED', approved: false, manual: true,
      retryable: true, reason: '页面或接口异常无法判断'
    };
    return await new Promise(resolve => {
      const oldAjax = window.jQuery.ajax;
      const timer = setTimeout(() => {
        window.jQuery.ajax = oldAjax;
        resolve({ status: 'COMPLETED', approved: false, manual: true, reason: '页面或接口异常无法判断' });
      }, 25000);
      window.jQuery.ajax = function(options) {
        if (options?.url === '/workflowAuditing/saveOrUpdate') {
          const success = options.success;
          const error = options.error;
          options.success = function(data) {
            clearTimeout(timer); window.jQuery.ajax = oldAjax;
            const approved = String(data?.resultCode || '') === '00' && String(data?.resultMessage || '').includes('审批通过');
            resolve(approved ? { status: 'COMPLETED', approved: true } :
              { status: 'COMPLETED', approved: false, manual: true, reason: '保存返回未明确审批通过' });
            return success?.apply(this, arguments);
          };
          options.error = function() {
            clearTimeout(timer); window.jQuery.ajax = oldAjax;
            resolve({ status: 'COMPLETED', approved: false, manual: true, reason: '保存返回未明确审批通过' });
            return error?.apply(this, arguments);
          };
        }
        return oldAjax.apply(this, arguments);
      };
      action.click();
    });
  }
  return { ok: false, reason: 'UNKNOWN_COMMAND' };
}
