import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* ── Usage Cost Chart (pure CSS bars, no external lib) ── */
  window._loadUsageChart=function(){
    var el=document.getElementById('usage-chart-content');if(!el)return;
    var kr=document.documentElement.lang==='kr';
    el.innerHTML='<div style="color:var(--text2);text-align:center;padding:12px">⏳...</div>';
    Promise.all([
      fetch('/api/usage/daily',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}),
      fetch('/api/usage/models',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()})
    ]).then(function(res){
      var daily=res[0].report||[];var models=res[1].breakdown||{};
      if(!daily.length&&!Object.keys(models).length){
        el.innerHTML='<div style="color:var(--text2);text-align:center;padding:20px">'+(kr?'사용 기록이 없습니다':'No usage data yet')+'</div>';
        return;
      }
      /* Aggregate daily by date */
      var byDate={};
      daily.forEach(function(r){
        if(!byDate[r.date])byDate[r.date]={cost:0,calls:0,inp:0,out:0};
        byDate[r.date].cost+=r.cost;
        byDate[r.date].calls+=r.calls;
        byDate[r.date].inp+=r.input_tokens;
        byDate[r.date].out+=r.output_tokens;
      });
      var dates=Object.keys(byDate).sort();
      var maxCost=Math.max.apply(null,dates.map(function(d){return byDate[d].cost}))||0.01;
      /* Daily bar chart */
      var h='<div style="font-weight:600;font-size:13px;margin-bottom:10px">'+(kr?'📊 일별 비용 (최근 7일)':'📊 Daily Cost (Last 7 Days)')+'</div>';
      h+='<div style="display:flex;align-items:flex-end;gap:4px;height:120px;padding:0 4px;margin-bottom:16px">';
      dates.slice(-7).forEach(function(d){
        var pct=Math.max((byDate[d].cost/maxCost)*100,2);
        var label=d.slice(5);/* MM-DD */
        h+='<div style="flex:1;display:flex;flex-direction:column;align-items:center;height:100%">';
        h+='<div style="flex:1;width:100%;display:flex;align-items:flex-end">';
        h+='<div style="width:100%;height:'+pct+'%;background:linear-gradient(180deg,var(--accent),var(--accent-dim));border-radius:4px 4px 0 0;min-height:2px" title="$'+byDate[d].cost.toFixed(4)+'"></div>';
        h+='</div>';
        h+='<div style="font-size:10px;color:var(--text2);margin-top:4px">'+label+'</div>';
        h+='<div style="font-size:9px;color:var(--accent2)">$'+byDate[d].cost.toFixed(3)+'</div>';
        h+='</div>';
      });
      h+='</div>';
      /* Total summary */
      var totalCost=0;var totalCalls=0;var totalIn=0;var totalOut=0;
      dates.forEach(function(d){totalCost+=byDate[d].cost;totalCalls+=byDate[d].calls;totalIn+=byDate[d].inp;totalOut+=byDate[d].out});
      h+='<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:16px">';
      h+='<div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;border:1px solid var(--border)"><div style="font-size:18px;font-weight:700;color:var(--accent2)">$'+totalCost.toFixed(4)+'</div><div style="font-size:10px;color:var(--text2)">'+(kr?'총 비용':'Total Cost')+'</div></div>';
      h+='<div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;border:1px solid var(--border)"><div style="font-size:18px;font-weight:700">'+totalCalls+'</div><div style="font-size:10px;color:var(--text2)">'+(kr?'총 호출':'Total Calls')+'</div></div>';
      h+='<div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;border:1px solid var(--border)"><div style="font-size:18px;font-weight:700">'+(totalIn/1000).toFixed(1)+'K</div><div style="font-size:10px;color:var(--text2)">'+(kr?'입력 토큰':'Input Tok')+'</div></div>';
      h+='<div style="text-align:center;padding:10px;background:var(--bg);border-radius:8px;border:1px solid var(--border)"><div style="font-size:18px;font-weight:700">'+(totalOut/1000).toFixed(1)+'K</div><div style="font-size:10px;color:var(--text2)">'+(kr?'출력 토큰':'Output Tok')+'</div></div>';
      h+='</div>';
      /* Model breakdown */
      var modelEntries=Object.entries(models).sort(function(a,b){return b[1]-a[1]});
      if(modelEntries.length){
        var modelMax=modelEntries[0][1]||0.01;
        h+='<div style="font-weight:600;font-size:13px;margin-bottom:8px">'+(kr?'🤖 모델별 비용':'🤖 Cost by Model')+'</div>';
        modelEntries.forEach(function(e){
          var pct=Math.max((e[1]/modelMax)*100,2);
          var name=e[0].split('/').pop();
          h+='<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px"><span>'+name+'</span><span style="color:var(--accent2)">$'+e[1].toFixed(4)+'</span></div>';
          h+='<div style="height:6px;background:var(--bg);border-radius:3px;overflow:hidden"><div style="height:100%;width:'+pct+'%;background:var(--accent);border-radius:3px"></div></div></div>';
        });
      }
      el.innerHTML=h;
    }).catch(function(e){
      el.innerHTML='<div style="color:var(--red)">Error: '+e+'</div>';
    });
  };

