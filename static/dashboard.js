const grid=document.getElementById('panelGrid');
const empty=document.getElementById('emptyState');
const summary=document.getElementById('connectionSummary');
const modal=document.getElementById('detailModal');
let panels=[];

function gasStatus(key,value,alarm){
  if(!alarm)return 'NORMAL';
  if(key==='vacuum')return 'LOW PRESSURE';
  return Number(value)<30?'LOW PRESSURE':'HIGH PRESSURE';
}
function gasMarkup(key,label,value,unit,alarm){
  const classes=['gas',key]; if(alarm)classes.push('alarm');
  const blink=alarm?' blink':'';
  return `<div class="${classes.join(' ')}"><div class="gas-name">${label}</div><div class="gas-value${blink}">${value}</div><div class="gas-unit">${unit}</div><div class="gas-status${blink}">${gasStatus(key,value,alarm)}</div></div>`;
}
function panelMarkup(panel){
  return `<article class="panel-card${panel.alarm_active?' alarm-card':''}" data-id="${panel.id}"><div class="panel-heading"><h2>${escapeHtml(panel.name)}</h2><span class="panel-state${panel.alarm_active?' alarm blink':''}">${panel.alarm_active?'ALARM':'ONLINE'}</span></div><div class="gas-row">${gasMarkup('oxygen','OXYGEN',panel.oxygen,'PSI',panel.oxygen_alarm)}${gasMarkup('air','AIR 4 BAR',panel.air,'PSI',panel.air_alarm)}${gasMarkup('vacuum','VACUUM',panel.vacuum,'mmHg',panel.vacuum_alarm)}</div></article>`;
}
function escapeHtml(value){const node=document.createElement('div');node.textContent=String(value);return node.innerHTML;}
function render(){
  empty.classList.toggle('hidden',panels.length>0);
  grid.innerHTML=panels.map(panelMarkup).join('');
  const alarms=panels.filter(p=>p.alarm_active).length;
  summary.textContent=`${panels.length} CONNECTED | ${alarms} ALARM`;
  summary.style.color=alarms?'var(--red-ink)':'var(--green-ink)';
  grid.querySelectorAll('.panel-card').forEach(card=>card.addEventListener('click',()=>openDetail(card.dataset.id)));
}
function openDetail(id){
  const p=panels.find(item=>item.id===id); if(!p)return;
  document.getElementById('detailName').textContent=p.name;
  document.getElementById('detailGases').innerHTML=gasMarkup('oxygen','OXYGEN',p.oxygen,'PSI',p.oxygen_alarm)+gasMarkup('air','AIR 4 BAR',p.air,'PSI',p.air_alarm)+gasMarkup('vacuum','VACUUM',p.vacuum,'mmHg',p.vacuum_alarm);
  document.getElementById('detailFlags').textContent=`${p.muted?'MUTED':'AUDIBLE'}${p.test_active?' | TEST ACTIVE':''} | READ ONLY`;
  modal.classList.remove('hidden');
}
document.getElementById('closeDetail').addEventListener('click',()=>modal.classList.add('hidden'));
modal.addEventListener('click',event=>{if(event.target===modal)modal.classList.add('hidden')});
document.addEventListener('keydown',event=>{if(event.key==='Escape')modal.classList.add('hidden')});
async function refresh(){
  try{
    const response=await fetch('/api/panels',{cache:'no-store'});
    if(response.status===401){location.href='/login';return}
    if(!response.ok)throw new Error('server error');
    const data=await response.json(); panels=data.panels; render();
  }catch(error){summary.textContent='SERVER CONNECTION LOST';summary.style.color='var(--red-ink)'}
}
refresh();setInterval(refresh,1000);
