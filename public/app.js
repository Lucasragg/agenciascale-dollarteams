'use strict';
const $ = id => document.getElementById(id);
const baseMetrics = ['spend','impressions','clicks','views','leads','freeTrials','sales','cohortContacts','trialContacts','trialSalesContacts','dateIssues','revenueCents'];
const impactMetrics = ['freeTrials','sales','trialRate','salesRate','cpft','cac'];
const labels = {spend:'Investimento',impressions:'Impressões',clicks:'Cliques',views:'Page views',leads:'Leads',cpm:'CPM',ctr:'CTR',cpc:'CPC',cpl:'CPL',leadRate:'LP → lead',clickRate:'Clique → lead',connectRate:'Connect rate',freeTrials:'Free Trials',trialRate:'Lead → Free Trial',sales:'Vendas · Paid Trial',salesRate:'Free Trial → venda',cpft:'Custo por Free Trial',cac:'CAC'};
const state = {data:null,start:'',end:'',campaign:'',adset:'',ad:'',chart:'leads',media:Object.fromEntries(['campaign','adset','ad'].map(level=>[level,{sort:'spend',direction:-1,search:'',metrics:[],selected:[],comparison:[],rows:[],daily:[]}])),daily:[],previous:[],dailyMetrics:[],loading:false};
const dailyMetricDefs = [
  ['spend','Investimento','#639bff'],['impressions','Impressões','#b89aff'],['clicks','Cliques','#29cbb7'],
  ['cpm','CPM','#7ca8ed'],['ctr','CTR','#b784ff'],['cpc','CPC','#3eded1'],
  ['views','Landing page views','#29c4e0'],['connectRate','Connect rate','#8edbea'],['leads','Leads','#7aeaad'],
  ['cpl','Custo por lead','#e4d35b'],['freeTrials','Free Trials','#38d59b'],['cpft','Custo por Free Trial','#c9dc83'],
  ['sales','Paid Trial','#edb36e'],['cac','Custo por Paid Trial','#ed8daa'],
  ['leadRate','Página → lead','#83caaa'],['trialRate','Lead → Free Trial','#86c3dc'],['salesRate','Free Trial → Paid','#d0a5e8'],
  ['clickRate','Clique → lead','#eca9cf']
];
const money = new Intl.NumberFormat('pt-BR',{style:'currency',currency:'USD',currencyDisplay:'symbol',maximumFractionDigits:2});
const integer = new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0});
const decimal = new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2,minimumFractionDigits:2});
const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ratio = (a,b,m=1) => b>0?a/b*m:null;
const dateValue = s => new Date(`${s}T12:00:00Z`);
const addDays = (s,n) => {const d=dateValue(s);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
const distance = (a,b) => Math.round((dateValue(b)-dateValue(a))/86400000)+1;
const shortDate = s => dateValue(s).toLocaleDateString('pt-BR',{timeZone:'UTC',day:'2-digit',month:'2-digit'});
const longDate = s => dateValue(s).toLocaleDateString('pt-BR',{timeZone:'UTC'});
const today = () => new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const fmt = (key,value) => value==null||!Number.isFinite(value)?'—':['revenue','spend','cpm','cpc','cpl','cpft','cac'].includes(key)?money.format(value):['ctr','leadRate','clickRate','connectRate','trialRate','salesRate'].includes(key)?`${decimal.format(value)}%`:integer.format(value);
function empty(){return Object.fromEntries(baseMetrics.map(m=>[m,0]));}
function sum(rows){return rows.reduce((a,r)=>{baseMetrics.forEach(m=>a[m]+=r[m]??0);return a;},empty());}
function acquisitionMode(){return state.basis!=='event'&&!!state.data?.acquisitionRecords;}
function sourceRecords(){return acquisitionMode()?state.data.acquisitionRecords:state.data.records;}
function revenueCoverage(){return acquisitionMode()?state.data.impact.acquisition:state.data.impact.revenue;}
function revenueComplete(start,end){const s=revenueCoverage();return !!s&&start>=(s.completeStart||s.start)&&end<=(s.completeEnd||s.end);}
function revenueValue(rows,start,end){const s=revenueCoverage();return s&&start<=s.end&&end>=s.start?sum(rows).revenueCents/100:null;}
function impactComplete(start,end,cohort=false){const s=state.data.impact;if(!s)return false;if(acquisitionMode())return start>=s.acquisition.start&&end<=s.acquisition.end;const first=s.completeStart||s.start,last=s.completeEnd||s.end;return start>=(cohort?(s.cohortStart>first?s.cohortStart:first):first)&&end<=last;}
function derive(row,complete=true,start=state.start,end=state.end){const s=acquisitionMode()?state.data.impact.acquisition:state.data.impact,overlap=s&&start<=s.end&&end>=s.start,cohort=impactComplete(start,end,true);return {...row,freeTrials:overlap?row.freeTrials:null,sales:overlap?row.sales:null,cpm:ratio(row.spend,row.impressions,1000),ctr:ratio(row.clicks,row.impressions,100),cpc:ratio(row.spend,row.clicks),cpl:complete?ratio(row.spend,row.leads):null,leadRate:complete?ratio(row.leads,row.views,100):null,clickRate:complete?ratio(row.leads,row.clicks,100):null,connectRate:ratio(row.views,row.clicks,100),trialRate:cohort?ratio(row.trialContacts,row.cohortContacts,100):null,salesRate:cohort?ratio(row.trialSalesContacts,row.trialContacts,100):null,cpft:complete&&impactComplete(start,end)?ratio(row.spend,row.freeTrials):null,cac:complete&&impactComplete(start,end)?ratio(row.spend,row.sales):null};}
function rangeComplete(start,end){const s=state.data.sources;return start>=s.ads.start&&start>=s.leads.start&&end<=s.ads.end&&end<=s.leads.end;}
function impactDetail(key,row){const info={freeTrials:'Ações atribuídas por e-mail · data do evento',sales:'Paid Trial · Pending e Approved',trialRate:`${integer.format(row.trialContacts)} de ${integer.format(row.cohortContacts)} contatos do período`,salesRate:`${integer.format(row.trialSalesContacts)} de ${integer.format(row.trialContacts)} contatos com trial`,cpft:'Investimento ÷ Free Trials atribuídos no período',cac:'Investimento ÷ vendas atribuídas no período'};return info[key];}
function renderImpactNotice(rows){
  const total=sum(rows),assigned=sum(paid(rows)),s=state.data.impact,first=s.completeStart||s.start,last=s.completeEnd||s.end;
  const messages=s.mode==='sheets'?[`Impact + Recuperacao · leitura automática a cada hora. Free Trial e Paid Trial com status Pending ou Approved, atribuídos pelo e-mail e pelas UTMs de CurtoV3DP.`,...Object.entries(s.tabs).map(([name,tab])=>`${name}: eventos de ${longDate(tab.start)} a ${longDate(tab.end)}.`)]:[`Impact · snapshot de ${longDate(s.start)} a ${longDate(s.end)}.`];
  if(acquisitionMode()){
    const a=s.acquisition,excluded=Object.values(a.excluded).reduce((v,x)=>({freeTrials:v.freeTrials+x.freeTrials,sales:v.sales+x.sales,revenueCents:v.revenueCents+x.revenueCents}),{freeTrials:0,sales:0,revenueCents:0});
    messages.unshift('Data do lead: Free Trials, Paid Trials e comissões recebidos depois são contabilizados na primeira inscrição disponível com origem única. CAC e CFT usam o investimento desses dias de captação.');
    messages.push(`Resultado acumulado observado até ${longDate(a.observedThrough)}; cobertura comum das abas até ${longDate(a.commonThrough)}. Períodos recentes ainda podem converter: a comparação não iguala o tempo de maturação.`);
    messages.push(`Na base completa, fora desta visão: ${integer.format(excluded.freeTrials)} Free Trials, ${integer.format(excluded.sales)} Paid Trials e ${money.format(excluded.revenueCents/100)} sem inscrição confiável ou com evento anterior à inscrição. Consulte Data do evento para os totais originais.`);
    if(state.end>a.commonThrough)messages.push('Os inscritos mais recentes têm acompanhamento parcial nas fontes.');
  }else if(state.end>last||state.start<first)messages.push(`Cobertura comum das conversões: ${longDate(first)} a ${longDate(last)}. Custo por Free Trial, CAC e taxas ficam indisponíveis para intervalos que ultrapassam essa cobertura.`);
  messages.push(`Neste filtro: ${integer.format(total.freeTrials-assigned.freeTrials)} Free Trials e ${integer.format(total.sales-assigned.sales)} Paid Trials fora da atribuição paga.`);
  if(s.diagnostics?.duplicatesRemoved)messages.push(`${integer.format(s.diagnostics.duplicatesRemoved)} repetições do mesmo evento removidas na leitura das abas.`);
  if(assigned.dateIssues)messages.push(`${integer.format(assigned.dateIssues)} ações atribuídas têm data anterior à inscrição; entram nas contagens, mas não nas taxas de avanço.`);
  messages.push(`Taxas por contatos inscritos no período, com avanços observados até ${longDate(acquisitionMode()?s.acquisition.observedThrough:last)}. Horários e fusos não são convertidos; atribuição por e-mail não comprova causalidade.`);
  $('impactNotice').textContent=messages.join(' ');
}
function inScope(r){return (!state.campaign||r.campaign===state.campaign)&&(!state.adset||r.adset===state.adset)&&(!state.ad||r.ad===state.ad);}
function periodRows(start,end){return sourceRecords().filter(r=>r.date>=start&&r.date<=end&&inScope(r));}
function paid(rows){return rows.filter(r=>r.campaign);}
function previousRange(){const n=distance(state.start,state.end);return {start:addDays(state.start,-n),end:addDays(state.start,-1)};}
function dates(start,end){const list=[];for(let d=start;d<=end;d=addDays(d,1))list.push(d);return list;}
function daily(rows,start,end){const grouped=new Map(dates(start,end).map(d=>[d,empty()]));for(const r of paid(rows)){const v=grouped.get(r.date);baseMetrics.forEach(k=>v[k]+=r[k]??0);}return [...grouped].map(([date,v])=>({date,...derive(v,rangeComplete(date,date),date,date)}));}
function delta(key,current,previous,complete){if(!complete)return '<span class="delta neutral">Sem base comparável</span>';if(previous==null||current==null)return '<span class="delta neutral">—</span>';if(previous===0)return current===0?'<span class="delta neutral">0%</span>':'<span class="delta neutral">Sem base anterior</span>';const change=(current-previous)/previous*100;const cost=['cpm','cpc','cpl','cpft','cac'].includes(key);const tone=key==='spend'||Math.abs(change)<.05?'neutral':(cost?change<0:change>0)?'':'bad';return `<span class="delta ${tone}">${change>0?'↗':change<0?'↘':'→'} ${decimal.format(Math.abs(change))}%</span>`;}
function setPeriod(value){const end=today();state.end=value==='yesterday'?addDays(end,-1):end;state.start=value==='all'?state.data.coverage.start:['today','yesterday'].includes(value)?state.end:addDays(state.end,-Number(value)+1);$('start').value=state.start;$('end').value=state.end;document.querySelectorAll('#presets button').forEach(b=>b.classList.toggle('active',b.dataset.period===value));render();}
function render(){if(!state.data)return;const rows=periodRows(state.start,state.end),current=derive(sum(paid(rows)),rangeComplete(state.start,state.end)),prev=previousRange(),previousRows=periodRows(prev.start,prev.end),comparison=derive(sum(paid(previousRows)),rangeComplete(prev.start,prev.end),prev.start,prev.end),complete=rangeComplete(state.start,state.end)&&rangeComplete(prev.start,prev.end);
  current.revenue=revenueValue(rows,state.start,state.end);comparison.revenue=revenueValue(previousRows,prev.start,prev.end);
  const revenueScope=state.campaign||state.adset||state.ad?'Comissões atribuídas ao filtro':acquisitionMode()?'Comissões dos leads do período':'Todas as comissões',revenueInfo=revenueCoverage();
  const basisLabel=acquisitionMode()?'Data do lead':'Data do evento';
  $('dateBasis').value=acquisitionMode()?'acquisition':'event';
  $('funnelHint').textContent=acquisitionMode()?'Free Trials e Paid Trials na data de entrada do lead, incluindo conversões recebidas depois. Resultado acumulado; leads recentes ainda podem converter.':'Volumes na data do evento. Taxas de trial e venda acompanham contatos inscritos no período, até a cobertura das abas.';
  const revenueDetail=`${revenueScope} · ${basisLabel} · Pending + Approved${revenueInfo&&!revenueComplete(state.start,state.end)?` · base de ${shortDate(revenueInfo.start)} a ${shortDate(revenueInfo.end)}`:''}`;
  const n=distance(state.start,state.end);$('periodLabel').textContent=`${longDate(state.start)} — ${longDate(state.end)} · ${n} ${n===1?'dia':'dias'} · anterior: ${shortDate(prev.start)} — ${shortDate(prev.end)}`;
  const partial=state.end>=today();const notices=[];if(!rangeComplete(state.start,state.end))notices.push(`Cobertura incompleta: mídia de ${longDate(state.data.sources.ads.start)} a ${longDate(state.data.sources.ads.end)}; leads de ${longDate(state.data.sources.leads.start)} a ${longDate(state.data.sources.leads.end)}. CPL e conversão em leads ficam indisponíveis nesse intervalo.`);if(!rangeComplete(prev.start,prev.end))notices.push('O período anterior não tem cobertura completa das duas fontes; a comparação percentual está desativada.');if(partial)notices.push('Hoje é parcial: os dados refletem a última leitura de cada planilha.');$('coverage').hidden=!notices.length;$('coverage').textContent=notices.join(' ');renderImpactNotice(rows);
  const cards=[
    ['spend','Investimento','$','blue','Valor original em USD'],
    ['impressions','Impressões','◉','purple','Exibições dos anúncios'],
    ['clicks','Cliques','↗','teal','Cliques no link'],
    ['cpm','CPM','M','blue','Custo por mil impressões'],
    ['ctr','CTR','%','purple','Cliques ÷ impressões'],
    ['cpc','CPC','C','teal','Custo por clique no link'],
    ['views','Landing page views','◉','cyan','Páginas de destino carregadas'],
    ['connectRate','Connect rate','ϟ','cyan','Page views ÷ cliques'],
    ['leads','Leads','•','green','Inscrições atribuídas ao tráfego'],
    ['cpl','Custo por lead','L','lime','Investimento ÷ leads'],
    ['freeTrials','Free Trials','↗','green',`Ações atribuídas · ${basisLabel}`],
    ['cpft','Custo por Free Trial','F','lime','Investimento ÷ Free Trials'],
    ['sales','Paid Trial','✓','amber',`Ações atribuídas · ${basisLabel}`],
    ['cac','Custo por Paid Trial','P','rose','Investimento ÷ Paid Trials'],
    ['leadRate','Conversão página → lead','L%','green','Leads ÷ page views'],
    ['trialRate','Conversão lead → Free Trial','F%','teal',`${integer.format(current.trialContacts)} de ${integer.format(current.cohortContacts)} contatos`],
    ['salesRate','Conversão Free Trial → Paid','P%','purple',`${integer.format(current.trialSalesContacts)} de ${integer.format(current.trialContacts)} contatos com trial`],
    ['revenue','Faturamento','$','green',revenueDetail]
  ];
  $('metrics').innerHTML=cards.map(([key,label,symbol,tone,detail])=>`<article class="metric tone-${tone}" data-metric="${key}"><div class="metric-top"><span class="metric-label">${label}</span><span class="symbol" aria-hidden="true">${symbol}</span></div><div class="metric-value">${fmt(key,current[key])}</div><div class="metric-bottom"><span class="metric-detail">${esc(detail)}</span><span class="metric-comparison">${delta(key,current[key],comparison[key],complete&&(!impactMetrics.includes(key)||(impactComplete(state.start,state.end,['trialRate','salesRate'].includes(key))&&impactComplete(prev.start,prev.end,['trialRate','salesRate'].includes(key)))))}<span>vs. anterior</span></span></div></article>`).join('');
  const stages=[['spend','Investimento',null,''],['impressions','Impressões',current.cpm,'CPM'],['clicks','Cliques no link',current.ctr,'CTR'],['views','Page views',current.connectRate,'dos cliques'],['leads','Leads atribuídos',current.leadRate,'das page views'],['freeTrials','Free Trials',current.trialRate,'dos contatos inscritos'],['sales','Vendas · Paid Trial',current.salesRate,'dos contatos com trial']];
  $('funnel').innerHTML=stages.map(([key,label,rate,hint],i)=>{const width=key==='spend'?100:current.impressions?Math.max(3,Math.min(100,current[key]/current.impressions*100)):0;return `<div class="funnel-row"><span class="funnel-number">0${i+1}</span><div><div class="funnel-meta"><span>${label}</span><b>${fmt(key,current[key])}</b></div><div class="funnel-track"><div class="funnel-fill" style="width:${width}%"></div></div></div><div class="funnel-rate"><b>${i===0?'USD':i===1?fmt('cpm',rate):fmt('ctr',rate)}</b>${esc(hint)}</div></div>`;}).join('');
  state.daily=daily(rows,state.start,state.end);state.previous=daily(previousRows,prev.start,prev.end);renderChart();renderEfficiency();renderMediaTables(rows);renderAttribution(rows);renderDailyDetail();
  $('campaign').value=state.campaign;renderBreadcrumb();
}
function dailyValue(row,key){const source=['spend','impressions','clicks','views'].includes(key)?state.data.sources.ads:key==='leads'?state.data.sources.leads:null;return source&&(row.date<source.start||row.date>source.end)?null:row[key];}
function renderDailyDetail(){
  $('dailyMetricsHead').innerHTML='<tr><th scope="col">Data</th>'+dailyMetricDefs.map(([key,label,color])=>`<th scope="col" style="--series:${color}"><button type="button" data-daily-metric="${key}" aria-pressed="${state.dailyMetrics.includes(key)}" aria-controls="dailyMetricChart" title="Adicionar ou remover ${esc(label)} no gráfico">${label}<span class="daily-select-dot" aria-hidden="true"></span></button></th>`).join('')+'</tr>';
  $('dailyBody').innerHTML=[...state.daily].reverse().map(row=>`<tr><th scope="row"><time datetime="${row.date}" title="${longDate(row.date)}">${dateValue(row.date).toLocaleDateString('pt-BR',{timeZone:'UTC',day:'2-digit',month:'short'})}</time></th>${dailyMetricDefs.map(([key])=>`<td${['leads','freeTrials','sales'].includes(key)?' class="daily-count"':''}>${fmt(key,dailyValue(row,key))}</td>`).join('')}</tr>`).join('');
  renderDailyMetricChart();
}
function toggleDailyMetric(key){if(!dailyMetricDefs.some(([k])=>k===key))return;state.dailyMetrics=state.dailyMetrics.includes(key)?state.dailyMetrics.filter(k=>k!==key):[...state.dailyMetrics,key];renderDailyMetricChart();}
function renderDailyMetricChart({efficiency=false,level=null}={}){
  const metricKeys=level?state.media[level].metrics:state.dailyMetrics,points=level?state.media[level].daily:state.daily;
  const chartId=id=>level?`${level}-${id}`:id;
  const el=$(efficiency?'efficiencyChart':chartId('dailyMetricChart')),defs=efficiency?[['cpl','CPL','#7aeaad'],['cpft','CFT','#e4d35b'],['cac','CAC','#b89aff']]:metricKeys.map(key=>dailyMetricDefs.find(([k])=>k===key)).filter(Boolean),normalized=!efficiency&&defs.length>1,comparing=!!level&&state.media[level].selected.length>0;
  if(!efficiency){
  document.querySelectorAll(level?`#${level}-tableHead [data-media-metric]`:'[data-daily-metric]').forEach(button=>button.setAttribute('aria-pressed',String(metricKeys.includes((level?button.dataset.mediaMetric:button.dataset.dailyMetric)))));
  $(chartId('clearDailyMetrics')).hidden=!defs.length;
  $(chartId('dailyMetricLegend')).innerHTML=defs.map(([key,label,color])=>`<button type="button" data-remove-metric="${key}" style="--series:${color}" aria-label="Remover ${esc(label)} do gráfico"><i></i>${label}<span aria-hidden="true">×</span></button>`).join('');
  }
  if(level)$(level+'-comparisonLegend').innerHTML='';
  const emptyChart=(title,message)=>`<div class="daily-metric-empty"><span aria-hidden="true">↗</span><strong>${title}</strong><small>${message}</small></div>`;
  el.onpointermove=el.onpointerleave=el.onpointerdown=el.onkeydown=null;
  if(!defs.length){el.removeAttribute('tabindex');el.removeAttribute('aria-label');$(chartId('dailyMetricChartTitle')).textContent='Selecione métricas na tabela';$(chartId('dailyMetricChartHint')).textContent='Clique em um ou mais cabeçalhos para comparar as séries.';el.innerHTML=emptyChart('Nenhuma métrica selecionada','Escolha quantas colunas quiser na tabela acima.');return;}
  if(comparing&&!state.media[level].comparison.length){el.removeAttribute('tabindex');$(chartId('dailyMetricChartTitle')).textContent='Comparação indisponível';$(chartId('dailyMetricChartHint')).textContent='Os itens selecionados não têm registros no período e nos filtros atuais.';el.innerHTML=emptyChart('Seleção fora do período ou dos filtros','Ajuste os filtros ou limpe os itens selecionados para comparar.');return;}
  const line=(key,label,color,rows,entity='',dash='')=>{const values=rows.map(row=>dailyValue(row,key));return {key,label,color,entity,dash,values,max:Math.max(0,...values.filter(Number.isFinite))};};
  const series=comparing?state.media[level].comparison.flatMap(item=>defs.map(([key,label],i)=>line(key,`${item.label} · ${label}`,item.color,item.days,item.key,['','7 4','2 4','10 3 2 3'][i%4]))):defs.map(([key,label,color])=>line(key,label,color,points));
  // Share a normalization denominator per metric across all entities, so a
  // lower-performing entity cannot become a misleading independent 100% peak.
  if(comparing&&normalized)for(const [key] of defs){const max=Math.max(...series.filter(s=>s.key===key).map(s=>s.max));for(const s of series)if(s.key===key)s.max=max;}
  if(comparing)$(level+'-comparisonLegend').innerHTML=series.map(s=>`<span title="${esc(s.label)}"><svg width="23" height="8" aria-hidden="true"><line x1="0" y1="4" x2="23" y2="4" stroke="${s.color}" stroke-width="2.5" stroke-dasharray="${s.dash}"/></svg><span>${esc(s.label)}</span></span>`).join('');
  if(efficiency){$('efficiencyHint').textContent='Custos em US$ na mesma escala. Investimento do dia ÷ leads, Free Trials ou Paid Trials atribuídos. Dias sem conversões ou cobertura aparecem como lacunas. Passe o mouse ou toque para ver os detalhes.';}else{
    $(chartId('dailyMetricChartTitle')).textContent=comparing?`Comparação · ${state.media[level].comparison.length} ${mediaLevels[level][1].toLocaleLowerCase('pt-BR')} · ${defs.length} ${defs.length===1?'métrica':'métricas'}`:normalized?`Evolução comparativa · ${series.length} métricas`:`Evolução de ${series[0].label}`;
    $(chartId('dailyMetricChartHint')).textContent=`${shortDate(state.start)} — ${shortDate(state.end)} · ${normalized?(comparing?'Escala relativa por métrica: 100% = maior valor entre os itens comparados. Valores reais no detalhe.':'Escala relativa: 100% = maior valor de cada métrica no período. Valores reais no detalhe.'):'Valores reais por dia na mesma escala. Passe o mouse ou toque para ver os detalhes.'}`;
  }
  if(level&&!comparing&&!state.media[level].rows.length){el.removeAttribute('tabindex');el.innerHTML=emptyChart('Nenhum resultado para os filtros','Ajuste a busca ou os filtros da tabela acima.');return;}
  if(!series.some(s=>s.values.some(Number.isFinite))){el.removeAttribute('tabindex');el.innerHTML=emptyChart('Sem base para calcular as métricas','Selecione outro período ou outras colunas.');return;}
  const W=Math.max(280,el.clientWidth),H=el.clientHeight,left=84,right=24,top=efficiency?35:28,bottom=efficiency?48:42,n=points.length,maximum=normalized?100:Math.max(...series.map(s=>s.max*1.1),1);
  const x=i=>left+(W-left-right)*(n===1?.5:i/(n-1)),scaled=(s,v)=>normalized?(s.max?v/s.max*100:0):v,y=v=>H-bottom-v/maximum*(H-top-bottom);
  const path=s=>{let active=false;return s.values.map((v,i)=>{if(v==null){active=false;return '';}const prefix=active?'L':'M';active=true;return `${prefix}${x(i).toFixed(2)},${y(scaled(s,v)).toFixed(2)}`;}).join(' ');};
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolução diária: ${esc(series.map(s=>s.label).join(', '))}">`;
  if(efficiency)svg+=`<text x="${left}" y="16">Custo (US$)</text><text x="${W-right}" y="${H-3}" text-anchor="end">Data</text>`;
  for(let i=0;i<5;i++){const value=maximum*i/4,yy=y(value);svg+=`<line class="gridline" x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}"/><text x="${left-10}" y="${yy+3}" text-anchor="end">${esc(normalized?`${value}%`:fmt(series[0].key,value))}</text>`;}
  for(const s of series){svg+=`<path class="daily-series-line" data-series="${s.key}" data-entity="${esc(s.entity)}" stroke-dasharray="${s.dash}" stroke="${s.color}" d="${path(s)}"/>`;if(n<=60)s.values.forEach((v,i)=>{if(v!=null)svg+=`<circle cx="${x(i)}" cy="${y(scaled(s,v))}" r="${n===1?4:2.5}" fill="${s.color}"><title>${longDate(points[i].date)} · ${esc(s.label)}: ${esc(fmt(s.key,v))}</title></circle>`;});}
  const tickCount=W<550?3:Math.min(8,n),ticks=new Set([0,n-1,...Array.from({length:tickCount},(_,i)=>Math.round((n-1)*i/Math.max(1,tickCount-1)))]);
  for(const i of ticks)svg+=`<text x="${x(i)}" y="${H-(efficiency?25:14)}" text-anchor="middle">${shortDate(points[i].date)}</text>`;
  svg+=`<line class="daily-hover-line" x1="${left}" x2="${left}" y1="${top}" y2="${H-bottom}" visibility="hidden"/></svg><div class="chart-tooltip daily-chart-tooltip" role="status"></div>`;
  el.innerHTML=svg;el.tabIndex=0;el.setAttribute('aria-label','Gráfico das métricas selecionadas. Use as setas esquerda e direita para consultar os dias.');
  const tooltip=el.querySelector('.chart-tooltip'),hover=el.querySelector('.daily-hover-line');let active=0;
  const show=(index,clientX)=>{active=index;const row=points[index];tooltip.innerHTML=`<strong>${longDate(row.date)}</strong>${series.map(s=>`<div class="daily-tooltip-row"><span><i style="background:${s.color}"></i>${esc(s.label)}</span><b>${esc(fmt(s.key,s.values[index]))}</b></div>`).join('')}${efficiency?`<div class="efficiency-tooltip-detail">Investimento: ${fmt('spend',dailyValue(row,'spend'))}<br>Leads: ${fmt('leads',dailyValue(row,'leads'))} · Free Trials: ${fmt('freeTrials',row.freeTrials)} · Paid Trials: ${fmt('sales',row.sales)}</div>`:''}`;tooltip.style.display='block';tooltip.style.left=`${Math.max(4,Math.min(el.clientWidth-tooltip.offsetWidth-4,clientX??x(index)+12))}px`;tooltip.style.top='10px';hover.setAttribute('visibility','visible');hover.setAttribute('x1',x(index));hover.setAttribute('x2',x(index));};
  const pointer=e=>{if(e.target.closest('.chart-tooltip'))return;const chart=el.querySelector('svg'),point=new DOMPoint(e.clientX,e.clientY).matrixTransform(chart.getScreenCTM().inverse());const index=Math.max(0,Math.min(n-1,Math.round((point.x-left)/(W-left-right)*(n-1))));show(index,e.clientX-el.getBoundingClientRect().left+12);};
  const hide=()=>{tooltip.style.display='none';hover.setAttribute('visibility','hidden');};
  el.onpointermove=pointer;el.onpointerdown=pointer;el.onpointerleave=hide;el.onblur=hide;
  el.onkeydown=e=>{if(e.key==='Escape'){hide();return;}if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();show(e.key==='Home'?0:e.key==='End'?n-1:Math.max(0,Math.min(n-1,active+(e.key==='ArrowRight'?1:-1))));};
}
function renderAttribution(rows){const counts={ad:0,adset:0,campaign:0,no_utm:0,unmatched:0,conflict:0};for(const row of rows)counts[row.attribution]=(counts[row.attribution]||0)+row.leads;const total=sum(rows).leads,matched=counts.ad+counts.adset+counts.campaign,percent=ratio(matched,total,100);$('matchRate').textContent=`${fmt('ctr',percent)} atribuídos`;$('attribution').innerHTML=`<div class="match-track"><span style="width:${percent||0}%"></span></div><p class="attribution-summary">${integer.format(matched)} de ${integer.format(total)} inscrições no período${state.campaign?' e no filtro selecionado':''}.</p>`+[['ad','Anúncio identificado'],['adset','Somente conjunto identificado'],['campaign','Somente campanha identificada'],['no_utm','Sem UTM'],['unmatched','UTM sem correspondência'],['conflict','IDs conflitantes']].map(([k,label])=>`<div class="attribution-row"><span>${label}</span><b>${integer.format(counts[k])}</b></div>`).join('');}
function renderBreadcrumb(){let html='<button data-reset="all">Todas as campanhas</button>';for(const level of ['campaign','adset','ad'])if(state[level]){const item=state.data.dimensions[level][state[level]];html+=`<span>›</span><button data-reset="${level}" title="${esc(item?.name)}">${esc(item?.name||state[level])}</button>`;}$('breadcrumb').innerHTML=html;}
function tableRows(rows,level){const grouped=new Map();for(const row of paid(rows)){const id=row[level];const key=id||`partial:${row.campaign}:${level==='ad'?row.adset:''}`;if(!grouped.has(key)){const item=state.data.dimensions[level][id];grouped.set(key,{...empty(),key,id,campaign:row.campaign,adset:row.adset,name:item?.name||(level==='ad'?'Sem anúncio identificado':'Sem conjunto identificado'),partial:!id});}const target=grouped.get(key);baseMetrics.forEach(m=>target[m]+=row[m]??0);}return [...grouped.values()].map(r=>derive(r,rangeComplete(state.start,state.end)));}
const mediaLevels={campaign:['Campanha','Campanhas'],adset:['Conjunto','Conjuntos'],ad:['Anúncio','Anúncios']};
const columns=['name',...dailyMetricDefs.map(([key])=>key)];
function mediaKey(row,level){return row[level]||`partial:${row.campaign}:${level==='ad'?row.adset:''}`;}
function initMediaTables(){
  $('mediaTables').innerHTML=Object.entries(mediaLevels).map(([level,[singular,plural]])=>`<section class="panel optimization" data-media-level="${level}" aria-labelledby="${level}-title">
    <div class="panel-head"><div><p class="eyebrow">DECISÃO DE MÍDIA · ${plural.toLocaleUpperCase('pt-BR')}</p><h2 id="${level}-title">${plural}</h2><p class="daily-selection-hint media-scope" id="${level}-scope"></p></div></div>
    <div class="table-toolbar"><p class="daily-selection-hint">Marque os itens para comparar · Selecione métricas nos cabeçalhos</p><div class="table-actions"><input type="search" id="${level}-search" data-media-search placeholder="Buscar nome ou ID…" aria-label="Buscar ${plural.toLocaleLowerCase('pt-BR')} por nome ou ID"><button data-media-export class="text-button">↓ Exportar CSV</button></div></div>
    <div class="media-comparison-controls"><span id="${level}-selectionCount" role="status"></span><div><button type="button" class="text-button" data-select-visible>Selecionar visíveis</button><button type="button" class="text-button" data-clear-entities>Limpar itens</button></div></div>
    <div class="table-scroll media-table-scroll" tabindex="0" role="region" aria-label="Tabela de ${plural.toLocaleLowerCase('pt-BR')} com rolagem horizontal e vertical"><table class="media-table"><thead id="${level}-tableHead"></thead><tbody id="${level}-tableBody"></tbody><tfoot id="${level}-tableFoot"></tfoot></table></div>
    <div class="table-bottom"><span id="${level}-tableCount"></span><span>Checkbox: comparar no gráfico · Nome: filtrar a dashboard</span></div>
    <div class="daily-evolution"><div class="panel-head"><div><p class="eyebrow">EVOLUÇÃO DAS MÉTRICAS · ${plural.toLocaleUpperCase('pt-BR')}</p><h2 id="${level}-dailyMetricChartTitle">Selecione métricas na tabela</h2><p id="${level}-dailyMetricChartHint" class="daily-selection-hint"></p></div><button id="${level}-clearDailyMetrics" data-media-clear class="text-button" hidden>Limpar seleção</button></div><div id="${level}-dailyMetricLegend" class="daily-metric-legend" aria-label="Métricas selecionadas de ${plural.toLocaleLowerCase('pt-BR')}"></div><div id="${level}-comparisonLegend" class="comparison-legend" aria-label="Itens e séries comparados"></div><div id="${level}-dailyMetricChart" class="chart daily-metric-chart"></div></div>
  </section>`).join('');
}
function renderMediaTables(rows=periodRows(state.start,state.end)){for(const level of Object.keys(mediaLevels))renderMediaTable(level,rows);}
function renderMediaTable(level,rows=periodRows(state.start,state.end)){
  const view=state.media[level],q=view.search.trim().toLocaleLowerCase('pt-BR');
  let list=tableRows(rows,level);
  if(q)list=list.filter(r=>`${r.name} ${r.id}`.toLocaleLowerCase('pt-BR').includes(q));
  list.sort((a,b)=>{const x=a[view.sort],y=b[view.sort];if(x==null)return y==null?0:1;if(y==null)return -1;return (typeof x==='string'?x.localeCompare(y,'pt-BR'):x-y)*view.direction;});
  view.rows=list;
  const selected=new Set(view.selected),groups=new Map();
  for(const row of paid(rows)){const key=mediaKey(row,level);if(selected.has(key)){if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}}
  view.comparison=view.selected.filter(key=>groups.has(key)).map(key=>{const records=groups.get(key),item=state.data.dimensions[level][key],name=item?.name||(level==='ad'?'Sem anúncio identificado':'Sem conjunto identificado'),identity=item?key:state.data.dimensions.campaign[records[0].campaign]?.name||records[0].campaign;return {key,label:`${name} [${identity}]`,color:entityColor(key),days:daily(records,state.start,state.end)};});
  const outside=view.selected.length-view.comparison.length,hiddenBySearch=view.comparison.filter(item=>!list.some(row=>row.key===item.key)).length;
  $(level+'-selectionCount').textContent=view.selected.length?`${view.selected.length} selecionados para comparar${outside?` · ${outside} fora do período/filtros`:''}${hiddenBySearch?` · ${hiddenBySearch} ocultos pela busca, mantidos no gráfico`:''}`:'Gráfico agregado · marque itens para comparar separadamente';
  const panel=document.querySelector(`[data-media-level="${level}"]`);panel.querySelector('[data-clear-entities]').disabled=!view.selected.length;panel.querySelector('[data-select-visible]').disabled=!list.length;

  const keys=new Set(list.map(r=>r.key));
  view.daily=daily(rows.filter(r=>r.campaign&&keys.has(mediaKey(r,level))),state.start,state.end);
  const sortButton=(key,label)=>`<button type="button" class="media-sort" data-media-sort="${key}" aria-label="Ordenar por ${esc(label)}" title="Ordenar por ${esc(label)}">${view.sort===key?(view.direction===1?'↑':'↓'):'↕'}</button>`;
  $(level+'-tableHead').innerHTML='<tr>'+columns.map(key=>{const def=dailyMetricDefs.find(([k])=>k===key),label=def?.[1]||mediaLevels[level][0];return `<th scope="col" aria-sort="${view.sort===key?(view.direction===1?'ascending':'descending'):'none'}" style="--series:${def?.[2]||'#7aeaad'}"><div class="media-column">${key==='name'?`<span>${label}</span>`:`<button type="button" class="media-metric" data-media-metric="${key}" aria-pressed="${view.metrics.includes(key)}" aria-controls="${level}-dailyMetricChart" title="Adicionar ou remover ${esc(label)} no gráfico">${label}<span class="daily-select-dot" aria-hidden="true"></span></button>`}${sortButton(key,label)}</div></th>`;}).join('')+'</tr>';
  $(level+'-tableBody').innerHTML=list.length?list.map(r=>`<tr class="${view.selected.includes(r.key)?'comparison-selected':''}"><td><div class="media-row-choice"><input type="checkbox" data-compare-entity="${esc(r.key)}" aria-label="Comparar ${esc(r.name)} (${esc(r.id||r.key)})" aria-controls="${level}-dailyMetricChart" ${view.selected.includes(r.key)?'checked':''}><div>${r.id?`<button class="row-name" data-drill="${esc(r.id)}" aria-pressed="${state[level]===r.id}">${esc(r.name)}</button>`:`<span class="row-name">${esc(r.name)}</span>`}<span class="row-id">${r.id?esc(r.id):'Atribuição parcial · '+esc(state.data.dimensions.campaign[r.campaign]?.name||r.campaign)}</span></div></div></td>${columns.slice(1).map(k=>`<td>${['cpl','cpft','cac'].includes(k)?`<span class="metric-emphasis">${fmt(k,r[k])}</span>`:fmt(k,r[k])}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${columns.length}" class="empty">Nenhum resultado para os filtros selecionados.</td></tr>`;
  const total=derive(sum(list),rangeComplete(state.start,state.end));
  $(level+'-tableFoot').innerHTML=list.length?`<tr><td>Total ${q?'da busca':'do filtro'}</td>${columns.slice(1).map(k=>`<td>${fmt(k,total[k])}</td>`).join('')}</tr>`:'';
  $(level+'-tableCount').textContent=`${list.length} ${mediaLevels[level][1].toLocaleLowerCase('pt-BR')}${list.some(r=>r.partial)?' · inclui atribuição parcial':''}`;
  const scope=Object.keys(mediaLevels).filter(k=>state[k]).map(k=>state.data.dimensions[k][state[k]]?.name||state[k]);
  $(level+'-scope').textContent=(scope.join(' → ')||'Todas as campanhas')+(q?` · Busca: ${view.search}`:'');
  renderDailyMetricChart({level});
}
const entityColors=new Map();
function entityColor(key){if(!entityColors.has(key))entityColors.set(key,`hsl(${(entityColors.size*137.508+155)%360} 72% 68%)`);return entityColors.get(key);}
function toggleMediaEntity(level,key){const view=state.media[level];view.selected=view.selected.includes(key)?view.selected.filter(k=>k!==key):[...view.selected,key];if(view.selected.length&&!view.metrics.length)view.metrics=['cpl'];renderMediaTable(level);const input=[...$(level+'-tableBody').querySelectorAll('[data-compare-entity]')].find(el=>el.dataset.compareEntity===key);input?.focus({preventScroll:true});}
function toggleMediaMetric(level,key){const view=state.media[level];if(!dailyMetricDefs.some(([k])=>k===key))return;view.metrics=view.metrics.includes(key)?view.metrics.filter(k=>k!==key):[...view.metrics,key];renderDailyMetricChart({level});}
function clearMediaSearch(){for(const level of Object.keys(mediaLevels)){state.media[level].search='';$(level+'-search').value='';}}
function exportMedia(level){
  const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';
  const rows=[['Nome','ID',...dailyMetricDefs.map(([,label])=>label)],...state.media[level].rows.map(r=>[r.name,r.id,...columns.slice(1).map(k=>r[k]==null?'':Number(r[k].toFixed(4)))])];
  const blob=new Blob(['\ufeff'+rows.map(r=>r.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8;'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`dollarteams-${level}-${state.start}-${state.end}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderChart({key=state.chart,target='chart',hint='chartHint',efficiency=false}={}){const W=efficiency?Math.max(320,$(target).clientWidth):800,H=efficiency?$(target).clientHeight:230,left=efficiency?84:62,right=18,top=efficiency?35:20,bottom=efficiency?48:34,n=state.daily.length,valid=(row)=>impactMetrics.includes(key)?row[key]:rangeComplete(row.date,row.date)?row[key]:null;const cur=state.daily.map(valid),prev=state.previous.map(valid);const max=Math.max(1,...cur.filter(v=>v!=null),...prev.filter(v=>v!=null))*1.14;const x=i=>left+(W-left-right)*(n===1?.5:i/(n-1)),y=v=>H-bottom-(v/max)*(H-top-bottom);const path=values=>{let d='',open=false;values.forEach((v,i)=>{if(v==null){open=false;return;}d+=`${open?'L':'M'}${x(i).toFixed(2)},${y(v).toFixed(2)} `;open=true;});return d;};
  const gradient=`${target}-areaFade`;
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(labels[key])}: período atual e anterior. Valores disponíveis na tabela diária."><defs><linearGradient id="${gradient}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#7aeaad" stop-opacity=".16"/><stop offset="100%" stop-color="#7aeaad" stop-opacity="0"/></linearGradient></defs>`;
  if(efficiency)svg+=`<text x="${left}" y="16">CPL (US$)</text><text x="${W-right}" y="${H-4}" text-anchor="end">Data</text>`;
  for(let i=0;i<5;i++){const v=max*i/4,yy=y(v);const label=['spend','cpl','cpc','cpm','cpft','cac'].includes(key)?money.format(v):['ctr','leadRate','clickRate','connectRate','trialRate','salesRate'].includes(key)?`${Math.round(v)}%`:integer.format(v);svg+=`<line class="gridline" x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}"/><text x="${left-10}" y="${yy+3}" text-anchor="end">${esc(label)}</text>`;}
  if(cur.every(v=>v!=null)&&n>1)svg+=`<path d="${path(cur)}L${x(n-1)},${H-bottom} L${x(0)},${H-bottom}Z" fill="url(#${gradient})"/>`;
  svg+=`<path class="prev-line" d="${path(prev)}"/><path class="trend-line" d="${path(cur)}"/>`;
  if(n<=35)cur.forEach((v,i)=>{if(v!=null)svg+=`<circle cx="${x(i)}" cy="${y(v)}" r="${n===1?4:2.5}" fill="#7aeaad"><title>${longDate(state.daily[i].date)} · ${esc(fmt(key,v))}</title></circle>`;});
  const tickCount=efficiency&&W<500?3:5;const tickSet=new Set([0,n-1,...Array.from({length:tickCount},(_,i)=>Math.round((n-1)*i/(tickCount-1)))]);for(const i of tickSet)svg+=`<text x="${x(i)}" y="${H-(efficiency?25:9)}" text-anchor="middle">${shortDate(state.daily[i].date)}</text>`;
  svg+='</svg><div class="chart-tooltip"></div>';$(target).innerHTML=svg;const element=$(target),tooltip=element.querySelector('.chart-tooltip');element.onpointermove=e=>{const rect=element.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W;const i=Math.max(0,Math.min(n-1,Math.round((px-left)/(W-left-right)*(n-1))));const row=state.daily[i];tooltip.innerHTML=`${longDate(row.date)} · <b>${fmt(key,cur[i])}</b>${efficiency?`<br>Investimento: ${fmt('spend',row.spend)}<br>Leads: ${fmt('leads',row.leads)}${cur[i]==null?'<br>CPL indisponível: sem leads ou sem cobertura.':''}`:''}<br>Anterior (${shortDate(state.previous[i].date)}): ${fmt(key,prev[i])}`;tooltip.style.display='block';tooltip.style.left=`${Math.max(0,Math.min(rect.width-tooltip.offsetWidth-8,e.clientX-rect.left+10))}px`;tooltip.style.top='12px';};element.onpointerleave=()=>tooltip.style.display='none';const scope=state.ad?state.data.dimensions.ad[state.ad]?.name:state.adset?state.data.dimensions.adset[state.adset]?.name:state.campaign?state.data.dimensions.campaign[state.campaign]?.name:'Todas as campanhas';$(hint).textContent=efficiency?`${cur.every(v=>v==null)?'Nenhum CPL disponível neste período. ':''}CPL = investimento do dia ÷ leads atribuídos do dia. Dias sem leads ou sem cobertura aparecem como lacunas. Passe o mouse ou toque para ver os valores.`:`${scope} · Passe o mouse ou toque para ver os valores.`;
}
function renderEfficiency(){renderDailyMetricChart({efficiency:true});const scope=['campaign','adset','ad'].filter(level=>state[level]).map(level=>`${{campaign:'Campanha',adset:'Conjunto',ad:'Anúncio'}[level]}: ${state.data.dimensions[level][state[level]]?.name||state[level]}`);$('efficiencyScope').textContent=scope.length?scope.join(' → '):'Todas as campanhas · selecione um nome na tabela acima para detalhar';}
function freshness(){if(!state.data)return;const generated=new Date(state.data.generatedAt),age=(Date.now()-generated)/36e5;$('updatedAt').textContent=`Atualizado ${generated.toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} BRT`;$('statusDot').classList.toggle('stale',age>2);$('freshness').hidden=age<=2;$('freshness').textContent=`A última atualização ocorreu há ${Math.floor(age)} horas. Os dados abaixo são da última publicação válida; a leitura das fontes ou a execução no GitHub pode estar atrasada.`;}
async function load(){if(state.loading)return;state.loading=true;$('refresh').disabled=true;try{const response=await fetch(`data.json?v=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);const data=await response.json();if(data.schema!==2||!data.impact||!Array.isArray(data.records)||!data.sources||!data.dimensions)throw new Error('Formato de dados inválido');state.data=data;$('error').hidden=true;const selected=state.campaign;$('campaign').innerHTML='<option value="">Todas as campanhas</option>'+Object.values(data.dimensions.campaign).sort((a,b)=>a.name.localeCompare(b.name,'pt-BR')).map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');if(selected&&!data.dimensions.campaign[selected])state.campaign=state.adset=state.ad='';if(!state.start)setPeriod('7');else render();freshness();}catch(error){$('error').textContent=`Não foi possível buscar a atualização. ${state.data?'A última versão carregada continua visível.':'Verifique a conexão e clique em ↻ para tentar novamente.'}`;$('error').hidden=false;$('statusDot').classList.add('stale');if(!state.data){$('updatedAt').textContent='Falha ao carregar';$('metrics').innerHTML='<div class="loading">Aguardando dados. Tente atualizar novamente.</div>';}console.error('Dashboard update failed:',error.message);}finally{state.loading=false;$('refresh').disabled=false;}}
$('presets').onclick=e=>{const b=e.target.closest('[data-period]');if(b&&state.data)setPeriod(b.dataset.period);};
$('dateForm').onsubmit=e=>{e.preventDefault();if(!state.data)return;const start=$('start').value,end=$('end').value;if(!start||!end||start>end||distance(start,end)>1096){$('error').textContent='Escolha datas válidas, com início antes do fim e um intervalo de até 3 anos.';$('error').hidden=false;return;}$('error').hidden=true;state.start=start;state.end=end;document.querySelectorAll('#presets button').forEach(b=>b.classList.remove('active'));render();};
$('campaign').onchange=e=>{state.campaign=e.target.value;state.adset=state.ad='';clearMediaSearch();render();};
$('dateBasis').onchange=e=>{state.basis=e.target.value;if(state.data)render();};
initMediaTables();
$('mediaTables').onclick=e=>{
  const section=e.target.closest('[data-media-level]');if(!section||!state.data)return;
  const level=section.dataset.mediaLevel,view=state.media[level],button=e.target.closest('button');if(!button)return;
  if(button.hasAttribute('data-media-sort')){const key=button.dataset.mediaSort;view.direction=view.sort===key?-view.direction:key==='name'?1:-1;view.sort=key;renderMediaTable(level);}
  else if(button.hasAttribute('data-media-metric'))toggleMediaMetric(level,button.dataset.mediaMetric);
  else if(button.hasAttribute('data-remove-metric'))toggleMediaMetric(level,button.dataset.removeMetric);
  else if(button.hasAttribute('data-media-clear')){view.metrics=[];renderDailyMetricChart({level});}
  else if(button.hasAttribute('data-media-export'))exportMedia(level);
  else if(button.hasAttribute('data-select-visible')){view.selected=[...new Set([...view.selected,...view.rows.map(r=>r.key)])];if(view.selected.length&&!view.metrics.length)view.metrics=['cpl'];renderMediaTable(level);}
  else if(button.hasAttribute('data-clear-entities')){view.selected=[];renderMediaTable(level);}
  else if(button.hasAttribute('data-drill')){const id=button.dataset.drill,item=state.data.dimensions[level][id];if(level==='campaign'){state.campaign=id;state.adset=state.ad='';}else if(level==='adset'){state.campaign=item.campaign;state.adset=id;state.ad='';}else{state.campaign=item.campaign;state.adset=item.adset;state.ad=id;}clearMediaSearch();render();}
};
$('mediaTables').onchange=e=>{if(e.target.matches('[data-compare-entity]')&&state.data)toggleMediaEntity(e.target.closest('[data-media-level]').dataset.mediaLevel,e.target.dataset.compareEntity);};
$('mediaTables').oninput=e=>{if(!e.target.matches('[data-media-search]'))return;const level=e.target.closest('[data-media-level]').dataset.mediaLevel;state.media[level].search=e.target.value;if(state.data)renderMediaTable(level);};
$('breadcrumb').onclick=e=>{const b=e.target.closest('[data-reset]');if(!b||!state.data)return;const level=b.dataset.reset;if(level==='all')state.campaign=state.adset=state.ad='';else if(level==='campaign')state.adset=state.ad='';else if(level==='adset')state.ad='';clearMediaSearch();render();};
$('chartMetric').onchange=e=>{state.chart=e.target.value;if(state.data)renderChart();};
$('dailyMetricsHead').onclick=e=>{const button=e.target.closest('[data-daily-metric]');if(button&&state.data)toggleDailyMetric(button.dataset.dailyMetric);};
$('dailyMetricLegend').onclick=e=>{const button=e.target.closest('[data-remove-metric]');if(button)toggleDailyMetric(button.dataset.removeMetric);};
$('clearDailyMetrics').onclick=()=>{state.dailyMetrics=[];renderDailyMetricChart();};
$('refresh').onclick=load;
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
new ResizeObserver(()=>{if(state.data&&state.daily.length)renderEfficiency();}).observe($('efficiencyChart'));
new ResizeObserver(()=>{if(state.data&&state.daily.length)renderDailyMetricChart();}).observe($('dailyMetricChart'));
for(const level of Object.keys(mediaLevels))new ResizeObserver(()=>{if(state.data&&state.media[level].daily.length)renderDailyMetricChart({level});}).observe($(level+'-dailyMetricChart'));
setInterval(load,5*60*1000);setInterval(freshness,60*1000);load();
