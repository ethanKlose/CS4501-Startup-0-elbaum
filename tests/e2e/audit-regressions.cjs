/* Additional real-browser checks for the local audit findings. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');const {chromium}=require('playwright');
const repo=path.resolve(__dirname,'../..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'platejoy-audit-fixes-'));
const base='http://127.0.0.1:8139';
const python=process.env.PYTHON || path.join(repo,fs.existsSync(path.join(repo,'.venv/Scripts/python.exe'))?'.venv/Scripts/python.exe':'.venv/bin/python');
const server=spawn(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8139'],{cwd:repo,env:{...process.env,DATABASE_URL:'sqlite:///'+path.join(temp,'audit.db'),ANTHROPIC_API_KEY:'',INSTACART_API_KEY:'',SECRET_KEY:'audit-regressions-only'}});
let log='',browser;server.stdout.on('data',d=>log+=d);server.stderr.on('data',d=>log+=d);
(async()=>{
  let healthy=false;for(let i=0;i<150;i++){try{if((await fetch(base+'/health')).ok){healthy=true;break}}catch{}await new Promise(r=>setTimeout(r,100));}assert.ok(healthy,log);
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{}),args:JSON.parse(process.env.PLAYWRIGHT_CHROMIUM_ARGS||'[]')});
  const errors=[];
  async function account(name,values={}){
    const ctx=await browser.newContext({baseURL:base,viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    await ctx.route('https://fonts.googleapis.com/**',r=>r.abort());await ctx.request.get('/health');
    const token=(await ctx.cookies()).find(c=>c.name==='csrf_token').value;
    const post=(url,form)=>ctx.request.post(url,{form,headers:{'X-CSRF-Token':token},maxRedirects:0});
    assert.equal((await post('/register',{email:name+'@example.test',password:'AuditPassword123!'})).status(),303);
    assert.equal((await post('/survey',{budget:'150',...values})).status(),303);
    const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));return {ctx,post,page};
  }
  const diet=await account('diet',{free_text:'No peanuts or shellfish'});
  await diet.post('/plan/generate',{start_mode:'next_week'});await diet.page.goto('/');
  const meals=JSON.parse(await diet.page.locator('#meals-data').textContent());
  assert.equal(Object.keys(meals).length,21);
  assert.ok(Object.values(meals).every(m=>!m.ingredients.some(i=>/\b(peanuts?|shrimp|crab|shellfish)\b/i.test(i))));
  console.log('PASS original dietary note survives browser signup and generation');
  const low=await account('budget',{budget:'40'});await low.post('/plan/generate',{start_mode:'next_week'});await low.page.goto('/');
  assert.equal(await low.page.locator('a[data-meal]').count(),21);
  assert.match(await low.page.getByTestId('plan-verification').innerText(),/Checks passed/);
  console.log('PASS feasible $40 budget generates a checked plan');
  await low.page.goto('/grocery');
  await low.page.getByRole('button',{name:'Send to Instacart',exact:true}).click();
  assert.match(await low.page.locator('.alert[role=status]').innerText(),/not configured yet/);
  const reject=await low.post('/survey',{minutes_0:'15.9'});assert.equal(reject.status(),400);
  const unknown=await low.post('/survey',{restrictions_present:'1',restrictions:'made_up'});assert.equal(unknown.status(),400);
  await low.page.goto('/');
  const recipeId=Object.keys(JSON.parse(await low.page.locator('#meals-data').textContent()))[0];
  await low.post('/checkin',{});await low.page.goto('/meals/'+recipeId);
  assert.equal(await low.page.locator('form[action$="/pin"]').count(),0);
  assert.equal((await low.post('/meals/'+recipeId+'/pin',{})).status(),409);
  console.log('PASS serialized Instacart unavailable handoff, input format errors and closed-history pin controls');
  const cal=await account('calendar');
  await cal.post('/preferences/lifestyle',{equipment:['stove','oven','fridge','freezer','toaster','blender'],external_0_lunch:'on'});
  await cal.post('/preferences/schedule',{time_breakfast:'06:00',time_lunch:'13:00',time_dinner:'22:00'});
  await cal.post('/plan/generate',{start_mode:'next_week'});await cal.page.goto('/');
  await cal.page.addStyleTag({content:'*, *::before, *::after { animation: none !important; transition: none !important; }'});
  const geometry=await cal.page.evaluate(()=>{
    const ex=document.querySelector('[data-testid=external-event]'),col=ex.closest('.gcol');
    const firstLabel=document.querySelector('.gutter span').textContent;
    const firstHour=Number(firstLabel.match(/\d+/)[0]);
    const r=e=>e.getBoundingClientRect();
    return {offset:r(ex).top-r(col).top,expected:(13-firstHour)*75,
      within:[...document.querySelectorAll('.event')].every(e=>r(e).top>=r(e.closest('.gcol')).top-.5&&r(e).bottom<=r(e.closest('.gcol')).bottom+.5)};
  });assert.ok(Math.abs(geometry.offset-geometry.expected)<1,JSON.stringify(geometry));assert.ok(geometry.within,JSON.stringify(geometry));
  for(const width of [390,1024]){await cal.page.setViewportSize({width,height:844});assert.ok(await cal.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
  console.log('PASS outside-meal positions, early/late calendar bounds, phone and tablet widths');
  const goal=await account('goal',{goal:'calorie_target',calorie_target:'4500'});await goal.post('/plan/generate',{start_mode:'next_week'});await goal.page.goto('/');
  assert.match(await goal.page.getByTestId('plan-verification').innerText(),/Needs review/);
  await goal.page.goto('/feedback');await goal.page.locator('[name=plan_correct]').selectOption('no');
  await goal.page.locator('[name=failed_constraints][value=nutrition]').check();
  await goal.page.getByRole('button',{name:'Save feedback',exact:true}).click();
  assert.match(await goal.page.locator('body').innerText(),/Constraint review: no/);
  assert.match(await goal.page.locator('body').innerText(),/Unrecorded planning minutes/);
  assert.deepEqual(errors,[]);console.log('PASS unmet goal label, correctness feedback and zero browser exceptions');
})().catch(e=>{console.error(e);console.error(log.slice(-3000));process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server.exitCode===null){const stopped=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await stopped;}fs.rmSync(temp,{recursive:true,force:true});});
