const $ = id => document.getElementById(id);
let chartEvolucao, chartSC;

const JT_RED = '#df171f';
const JT_BLUE = '#2e9ddd';
const OK = '#17a05e';
const BAD = '#df171f';
const GRID = '#e8ebef';
const MUTED = '#718096';
let availableDates = [];

async function json(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}
function opt(sel, values){
  values.forEach(v => {
    const o = document.createElement('option');
    o.value = v; o.textContent = v; sel.appendChild(o);
  });
}
function fmt(n){ return new Intl.NumberFormat('pt-BR').format(n || 0); }
function pct(n){ return `${Number(n || 0).toFixed(2).replace('.', ',')}%`; }
function shortDate(iso){ if(!iso) return ''; const [y,m,d]=iso.split('-'); return `${d}/${m}`; }
function fullDate(iso){ if(!iso) return ''; const [y,m,d]=iso.split('-'); return `${d}/${m}/${y}`; }

async function init(){
  const [datas, filtros] = await Promise.all([json('/api/datas'), json('/api/filtros')]);
  availableDates = datas;
  if(datas.length){ $('dataIni').value = datas[0]; $('dataFim').value = datas[0]; }
  opt($('rm'), filtros.rm); opt($('sc'), filtros.sc); opt($('uf'), filtros.uf); opt($('base'), filtros.base);
  $('aplicar').onclick = load;
  $('limpar').onclick = clearFilters;
  await load();
}

function clearFilters(){
  ['rm','sc','uf','base'].forEach(id => $(id).value = '');
  if(availableDates.length){ $('dataIni').value = availableDates[0]; $('dataFim').value = availableDates[0]; }
  load();
}

function params(){
  const p = new URLSearchParams();
  [['data_ini','dataIni'],['data_fim','dataFim'],['rm','rm'],['sc','sc'],['uf','uf'],['base','base']]
    .forEach(([k,id]) => { if($(id).value) p.set(k,$(id).value); });
  return p.toString();
}

function setKpis(d){
  const taxa = d.kpis.taxa;
  const atingiu = taxa >= d.meta;
  const gap = taxa - d.meta;
  $('taxa').textContent = pct(taxa);
  $('total').textContent = fmt(d.kpis.total);
  $('ok').textContent = fmt(d.kpis.t0_ok);
  $('perdido').textContent = fmt(d.kpis.t0_perdido);

  $('status').textContent = atingiu ? 'META ATINGIDA' : 'ABAIXO DA META';
  $('status').className = `status-badge ${atingiu ? 'good' : 'bad'}`;
  $('gap').textContent = `${gap >= 0 ? '+' : ''}${gap.toFixed(2).replace('.', ',')} p.p.`;
  $('gap').className = `gap-number ${atingiu ? 'good' : 'bad'}`;
  $('insightText').textContent = atingiu
    ? `O T0 consolidado está ${Math.abs(gap).toFixed(2).replace('.', ',')} p.p. acima da meta de ${d.meta.toFixed(0)}%.`
    : `O T0 consolidado está ${Math.abs(gap).toFixed(2).replace('.', ',')} p.p. abaixo da meta de ${d.meta.toFixed(0)}%.`;
  const meter = $('meterFill');
  meter.style.width = `${Math.min(100, Math.max(0, taxa))}%`;
  meter.className = atingiu ? 'good' : '';
}

function buildEvolution(d){
  if(chartEvolucao) chartEvolucao.destroy();
  chartEvolucao = new Chart($('evolucao'), {
    type:'line',
    data:{
      labels:d.evolucao.map(x=>shortDate(x.nome)),
      datasets:[
        {label:'T0',data:d.evolucao.map(x=>x.taxa),borderColor:JT_BLUE,backgroundColor:'rgba(46,157,221,.07)',pointBackgroundColor:'#fff',pointBorderColor:JT_BLUE,pointBorderWidth:2.3,pointRadius:3.7,pointHoverRadius:5,borderWidth:3,fill:false,tension:.24},
        {label:'Meta',data:d.evolucao.map(()=>d.meta),borderColor:JT_RED,pointRadius:0,borderDash:[6,5],borderWidth:1.7,fill:false,tension:0}
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{backgroundColor:'#171b23',padding:12,titleFont:{weight:'700'},callbacks:{
          title:items=>fullDate(d.evolucao[items[0].dataIndex]?.nome),
          label:ctx=>ctx.dataset.label==='T0'?` T0: ${pct(ctx.parsed.y)} • ${fmt(d.evolucao[ctx.dataIndex]?.total)} pedidos`:` Meta: ${pct(ctx.parsed.y)}`
        }}
      },
      scales:{
        x:{grid:{display:false},border:{display:false},ticks:{color:MUTED,maxRotation:0,minRotation:0,autoSkip:true,maxTicksLimit:18,font:{size:10}}},
        y:{min:0,max:100,border:{display:false},grid:{color:GRID},ticks:{color:MUTED,callback:v=>`${v}%`,stepSize:10,font:{size:10}}}
      }
    }
  });
}

function buildSC(d){
  if(chartSC) chartSC.destroy();
  const sc=d.sc;
  chartSC=new Chart($('scChart'),{
    type:'bar',
    data:{labels:sc.map(x=>x.nome),datasets:[{label:'T0',data:sc.map(x=>x.taxa),backgroundColor:sc.map(x=>x.taxa>=d.meta?OK:BAD),borderRadius:6,borderSkipped:false,barThickness:20}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>` T0: ${pct(ctx.parsed.x)} • ${fmt(sc[ctx.dataIndex]?.total)} pedidos`}}},scales:{x:{min:0,max:100,border:{display:false},grid:{color:GRID},ticks:{color:MUTED,callback:v=>`${v}%`,stepSize:20,font:{size:10}}},y:{border:{display:false},grid:{display:false},ticks:{color:'#394355',autoSkip:false,font:{size:10,weight:'600'}}}}}
  });
}

function buildTable(d){
  $('tbody').innerHTML=d.piores_bases.map(x=>{
    const good=x.taxa>=d.meta;
    const gap=x.taxa-d.meta;
    return `<tr>
      <td><strong>${x.nome}</strong></td>
      <td>${fmt(x.total)}</td>
      <td>${fmt(x.ok)}</td>
      <td>${fmt(x.perdido)}</td>
      <td class="${good?'good-txt':'bad-txt'}">${pct(x.taxa)}</td>
      <td class="${gap>=0?'good-txt':'bad-txt'}">${gap>=0?'+':''}${gap.toFixed(2).replace('.',',')} p.p.</td>
      <td><span class="table-status ${good?'table-good':'table-bad'}">${good?'Na meta':'Abaixo'}</span></td>
    </tr>`;
  }).join('');
}

async function load(){
  const d=await json('/api/dashboard?'+params());
  setKpis(d); buildEvolution(d); buildSC(d); buildTable(d);
}
init().catch(e=>{console.error(e);alert('Erro ao carregar dashboard T0. Veja o console.');});
