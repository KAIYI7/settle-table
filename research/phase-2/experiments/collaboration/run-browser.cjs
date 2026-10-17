// DISPOSABLE automated application test, two isolated real Chromium contexts.
// Set NODE_PATH to a Playwright installation; no external network is needed.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const contexts=await Promise.all([browser.newContext(),browser.newContext()]);
 const [a,b]=await Promise.all(contexts.map(c=>c.newPage()));
 const errors=[];for(const p of [a,b])p.on('pageerror',e=>errors.push(e.message));
 const started=Date.now();
 try{
  await Promise.all([a.goto('http://127.0.0.1:8766/?actor=A'),b.goto('http://127.0.0.1:8766/?actor=B')]);
  await Promise.all([a.locator('#race').click(),b.locator('#race').click()]);
  // Wait for report POST, rather than assuming the last displayed check means its response arrived.
  async function stage(p,id,name){let report=p.waitForResponse(r=>r.url().endsWith('/report')&&r.request().postDataJSON().stage===name);await p.locator(id).click();await report;let log=await p.locator('#log').innerText();if(log.includes('FAILED:'))throw Error(log);}
  // Both race stages must be present; ordinary browser fetch reads fixture evidence only.
  await a.waitForFunction(async()=>{const d=await(await fetch('/results')).json();return ['A','B'].every(actor=>d.reports.some(r=>r.actor===actor&&r.stage==='race'));});
  await stage(a,'#organizer','organizer');
  await stage(b,'#reconnect','reconnect');
  await stage(a,'#revoke','revoke');
  await stage(b,'#revoked','revoked');
  const result=await a.evaluate(async()=>await(await fetch('/results')).json());
  const latest=new Map(result.reports.map(r=>[r.actor,r]));
  const checks=[...latest.values()].flatMap(r=>r.checks.map(c=>({actor:r.actor,...c})));
  const raceStatuses=checks.filter(c=>c.name==='simultaneous_same_revision_commit_or_conflict').map(c=>c.detail.status).sort();
  checks.push({actor:'independent-runner',name:'exactly_one_same_revision_race_commit',pass:JSON.stringify(raceStatuses)==='[200,409]',detail:raceStatuses});
  result.automation={browser:await browser.version(),playwright:require('playwright/package.json').version,
   independent_contexts:2,elapsed_ms:Date.now()-started,page_errors:errors,
   passed:checks.filter(c=>c.pass).length,failed:checks.filter(c=>!c.pass).length,checks};
  fs.writeFileSync(path.join(__dirname,'results.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({browser:result.automation.browser,contexts:2,passed:result.automation.passed,failed:result.automation.failed,elapsed_ms:result.automation.elapsed_ms,page_errors:errors}));
  if(result.automation.failed||errors.length)process.exitCode=1;
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
