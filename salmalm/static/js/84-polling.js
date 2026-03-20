  /* --- Notification polling (30s) --- */
  setInterval(async()=>{
    if(!_tok)return;
    try{
      var r=await fetch('/api/notifications',{headers:{'X-Session-Token':_tok}});
      if(!r.ok)return;
      var d=await r.json();
      if(d.notifications&&d.notifications.length){
        d.notifications.forEach(n=>addMsg('assistant',n.text,'⏰ cron'));
        /* Clear after showing to prevent duplicates on next poll */
        fetch('/api/notifications/clear',{method:'POST',headers:{'X-Session-Token':_tok}}).catch(()=>{});
      }
    }catch(e){}
  },30000);
