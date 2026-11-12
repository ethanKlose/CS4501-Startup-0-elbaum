/* Run with npm run test:e2e after make setup and npx playwright install chromium. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

const repo = path.resolve(__dirname, '../..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platejoy-e2e-'));
const port = Number(process.env.E2E_PORT || 8123);
const baseURL = `http://127.0.0.1:${port}`;
const python = process.env.PYTHON || (fs.existsSync(path.join(repo, '.venv/bin/python')) ? path.join(repo, '.venv/bin/python') : 'python');
const server = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)], {
  cwd: repo, env: {...process.env, DATABASE_URL: 'sqlite:///' + path.join(temp, 'test.db'), ANTHROPIC_API_KEY: '', SECRET_KEY: 'isolated-e2e-only'}
});
let serverLog = '', browser, context, page;
server.stdout.on('data', d => { serverLog += d; });
server.stderr.on('data', d => { serverLog += d; });
const pageErrors = [];
function pass(message) { console.log('PASS ' + message); }

async function planReady(previousId) {
  await page.waitForFunction(old => {
    const el = document.getElementById('meals-data');
    return el && Object.keys(JSON.parse(el.textContent)).length === 21 && Object.keys(JSON.parse(el.textContent))[0] !== old;
  }, previousId || '', {timeout: 90000});
}
async function mealData() { return JSON.parse(await page.locator('#meals-data').textContent()); }
async function confirmClick(button, accept) {
  const event = page.waitForEvent('dialog');
  const clicked = button.click();
  const dialog = await event;
  assert.equal(dialog.type(), 'confirm');
  if (accept) await dialog.accept(); else await dialog.dismiss();
  await clicked;
}

(async () => {
  server.on('error', e => { serverLog += String(e); });
  let healthy = false;
  for (let i = 0; i < 150; i++) {
    if (server.exitCode !== null) throw new Error('App exited before becoming healthy: ' + serverLog);
    try { healthy = (await fetch(baseURL + '/health')).ok; } catch (_) {}
    if (healthy) break;
    await new Promise(r => setTimeout(r, 100));
  }
  assert.ok(healthy, 'App did not start: ' + serverLog);
  browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {}),
    args: JSON.parse(process.env.PLAYWRIGHT_CHROMIUM_ARGS || '[]')
  });
  context = await browser.newContext({baseURL, viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
  await context.route('https://fonts.googleapis.com/**', route => route.abort());
  page = await context.newPage();
  page.on('pageerror', e => pageErrors.push(e.message));
  await page.goto('/');
  assert.match(await page.getByTestId('planner-mode').innerText(), /Demo mode/);
  await page.getByRole('link', {name: 'Get started', exact: true}).first().click();
  await page.locator('input[name=email]').fill('browser@example.test');
  await page.locator('input[name=password]').fill('TestPass123!');
  await page.locator('form button[type=submit], form button:not([type])').last().click();
  await page.waitForURL('**/survey');
  await page.locator('input[name=budget]').fill('150');
  await page.locator('[data-next]').click();
  await page.locator('textarea[name=free_text]').fill("no fish. I can't cook on Wednesdays");
  await page.locator('[data-next]').click();
  await page.locator('input[name=minutes_2]').fill('0');
  await page.locator('[data-next]').click();
  await page.locator('[data-save]').click();
  await planReady();
  assert.equal(await page.locator('a[data-meal]').count(), 21);
  pass('signup, survey, automatic generation, demo label');

  await page.getByRole('button', {name: 'Agenda', exact: true}).click();
  assert.ok(await page.locator('.gcal').evaluate(e => e.classList.contains('is-agenda')));
  await page.reload();
  assert.ok(await page.locator('.gcal').evaluate(e => e.classList.contains('is-agenda')));
  await page.getByRole('button', {name: 'Calendar', exact: true}).click();
  const first = await page.locator('a[data-meal]').first().getAttribute('data-meal');
  await page.locator('a[data-meal]').first().click();
  assert.ok(await page.locator('#meal-dialog').evaluate(e => e.open));
  await page.getByRole('link', {name: 'Full recipe'}).click();
  const pinnedName = await page.locator('h1').innerText();
  await page.getByRole('button', {name: 'Pin this meal'}).click();
  await page.locator('a.backlink').click();
  await confirmClick(page.getByRole('button', {name: 'Regenerate week', exact: true}), false);
  assert.equal(Object.keys(await mealData())[0], first);
  await confirmClick(page.getByRole('button', {name: 'Regenerate week', exact: true}), true);
  await planReady(first);
  assert.ok(Object.values(await mealData()).some(m => m.pinned && m.name === pinnedName));
  pass('agenda persistence, quick view, pin preservation, cancel/confirm regeneration');

  let cards = await mealData();
  const cookedId = Object.keys(cards)[0];
  await page.goto('/meals/' + cookedId);
  await page.getByRole('button', {name: 'Mark cooked', exact: true}).click();
  await page.getByLabel('Rating', {exact: true}).selectOption('5');
  await page.getByRole('button', {name: 'Save rating', exact: true}).click();
  assert.equal(await page.getByRole('button', {name: 'Swap meal', exact: true}).count(), 0);
  const blocked = await context.request.post('/meals/' + cookedId + '/swap', {headers: {'X-CSRF-Token': await page.locator('meta[name=csrf-token]').getAttribute('content')}});
  assert.match(await blocked.text(), /Only planned, unrated meals/);
  await page.goto('/');
  cards = await mealData();
  const swapId = Object.keys(cards).at(-1), oldName = cards[swapId].name;
  await page.goto('/meals/' + swapId);
  await page.getByRole('button', {name: 'Swap meal', exact: true}).click();
  await page.waitForFunction(({id, name}) => {
    const el = document.getElementById('meals-data');
    return el && JSON.parse(el.textContent)[id].name !== name;
  }, {id: swapId, name: oldName}, {timeout: 90000});
  assert.equal((await mealData())[cookedId].rating, 5);
  pass('completed history protected; planned meal swap works');

  await page.locator('.skipform[action="/plan/days/3/skip"] button').click();
  assert.equal(await page.locator('a[data-meal]').count(), 18);
  await page.locator('.skipform[action="/plan/days/3/skip"] button').click();
  const previous = Object.keys(await mealData())[0];
  await confirmClick(page.getByRole('button', {name: 'Regenerate week', exact: true}), true);
  await planReady(previous);
  pass('skip and restore day');

  await page.goto('/grocery');
  assert.equal(await page.locator('#grocery-error').isVisible(), false);
  let box = page.locator('ul.grocery input[type=checkbox]').first();
  await Promise.all([page.waitForResponse(r => r.url().endsWith('/grocery/toggle') && r.status() === 204), box.check()]);
  await page.reload();
  assert.ok(await page.locator('ul.grocery input').first().isChecked());
  const countBefore = await page.locator('#remaining').innerText();
  const widthBefore = await page.locator('#gbar').evaluate(e => e.style.width);
  await page.route('**/grocery/toggle', route => route.fulfill({status: 500, body: 'intentional failure'}));
  await page.locator('ul.grocery input').first().uncheck();
  await page.locator('#grocery-error').waitFor({state: 'visible'});
  assert.ok(await page.locator('ul.grocery input').first().isChecked());
  assert.equal(await page.locator('#remaining').innerText(), countBefore);
  assert.equal(await page.locator('#gbar').evaluate(e => e.style.width), widthBefore);
  await page.unroute('**/grocery/toggle');
  pass('grocery persistence and complete rollback on failed save');

  await page.goto('/survey#pantry');
  await page.getByLabel('Item name', {exact: true}).fill('rice');
  await page.getByLabel('Quantity', {exact: true}).fill('2');
  await page.getByLabel('Unit', {exact: true}).fill('cup');
  await page.locator('.pantry-add button').click();
  assert.match(await page.locator('.pantry').innerText(), /rice/);
  await page.locator('input[name=budget]').fill('25');
  await page.locator('[data-save]').click();
  assert.match(await page.getByRole('alert').innerText(), /at least \$30/);
  await page.locator('input[name=budget]').fill('150');
  await page.locator('[data-save]').click();
  pass('pantry editing and survey validation');

  await page.getByRole('button', {name: 'Toggle dark mode'}).click();
  const theme = await page.locator('html').getAttribute('data-theme');
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
  for (const width of [1024, 390]) {
    await page.setViewportSize({width, height: 844});
    for (const url of ['/', '/grocery', '/checkin', '/survey']) {
      await page.goto(url);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), url + ' overflow at ' + width);
    }
  }
  await page.goto('/');
  await page.locator('a[data-meal]').first().click();
  assert.ok(await page.locator('#meal-dialog').evaluate(e => e.open));
  await page.locator('[data-close]').click();
  pass('theme, tablet and phone layouts, mobile dialog');

  await page.goto('/checkin');
  await page.getByRole('button', {name: 'Save check-in', exact: true}).click();
  assert.ok(await page.getByText('Thanks! Your next plan will take this into account.', {exact: true}).isVisible());
  await page.goto('/grocery');
  assert.equal(await page.locator('ul.grocery input:not(:disabled)').count(), 0);
  await page.getByLabel('Account menu', {exact: true}).click();
  await page.getByRole('button', {name: 'Log out', exact: true}).click();
  await page.waitForURL('**/login');
  await page.locator('input[name=email]').fill('browser@example.test');
  await page.locator('input[name=password]').fill('TestPass123!');
  await page.locator('form button[type=submit], form button:not([type])').last().click();
  await page.waitForURL(baseURL + '/');
  await page.goto('/plans');
  assert.ok(await page.getByRole('heading', {name: 'Plan history', exact: true}).isVisible());
  await page.goto('/checkin');
  await page.getByRole('button', {name: 'Undo check-in and reopen', exact: true}).click();
  assert.equal(await page.getByRole('button', {name: 'Undo check-in and reopen', exact: true}).count(), 0);
  await page.goto('/prices');
  await page.locator('select[name=key]').selectOption('rice|cup');
  await page.locator('input[name=quantity]').fill('4');
  await page.locator('input[name=price]').fill('2');
  await page.locator('input[name=source]').fill('Local test receipt');
  await page.locator('input[name=observed_on]').fill('2026-11-01');
  await page.getByRole('button', {name: 'Save local price', exact: true}).click();
  assert.match(await page.locator('body').innerText(), /Local test receipt/);
  await page.goto('/survey');
  await page.locator('[data-goto="3"]').click();
  await page.locator('select[name=cooking_skill]').selectOption('beginner');
  await page.getByRole('button', {name: 'Save changes', exact: true}).click();
  await page.goto('/survey#schedule-windows');
  await page.locator('input[name=windows_0]').fill('07:00-08:00,17:00-19:00');
  await page.getByRole('button', {name: 'Save changes', exact: true}).click();
  await page.goto('/survey#schedule-windows');
  assert.equal(await page.locator('input[name=windows_0]').inputValue(), '07:00-08:00, 17:00-19:00');
  const csrfRejected = await context.request.post('/plan/generate');
  assert.equal(csrfRejected.status(), 403);
  await page.goto('/feedback');
  await page.locator('input[name=actual_spend]').fill('50');
  await page.locator('input[name=actual_minutes]').fill('10');
  await page.locator('input[name=baseline_minutes]').fill('30');
  await page.locator('input[name=ease]').fill('4');
  await page.getByRole('button', {name: 'Save feedback', exact: true}).click();
  assert.match(await page.locator('body').innerText(), /10 planning minutes/);
  await page.goto('/forgot-password');
  assert.ok(await page.getByRole('button', {name: 'Send reset link', exact: true}).isVisible());
  await page.goto('/');
  const calendarHref = await page.getByRole('link', {name: 'Export calendar', exact: true}).getAttribute('href');
  const exported = await context.request.get(calendarHref);
  assert.equal(exported.status(), 200);
  assert.match(await exported.text(), /BEGIN:VCALENDAR/);
  pass('history, undo, price provenance, kitchen/windows forms, CSRF, feedback and calendar export');
  const oldWeek = await page.locator('h1').innerText();
  const oldId = Object.keys(await mealData())[0];
  await confirmClick(page.getByRole('button', {name: 'Plan next week', exact: true}), true);
  await planReady(oldId);
  assert.notEqual(await page.locator('h1').innerText(), oldWeek);
  pass('explicit next-week action advances the calendar');
  assert.deepEqual(pageErrors, []);
  pass('check-in closes inventory once, logout/login, no browser exceptions');
})().catch(async e => {
  console.error(e);
  console.error(serverLog.slice(-5000));
  if (page && !page.isClosed()) {
    const results = path.join(repo, 'test-results');
    fs.mkdirSync(results, {recursive: true});
    await page.screenshot({path: path.join(results, 'e2e-failure.png'), fullPage: true}).catch(() => {});
  }
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
  if (server.exitCode === null) {
    const exited = new Promise(resolve => server.once('exit', resolve));
    server.kill('SIGTERM');
    await exited;
  }
  fs.rmSync(temp, {recursive: true, force: true});
});
