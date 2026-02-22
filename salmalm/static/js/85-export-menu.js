  /* --- Export menu toggle --- */
  window.toggleExportMenu=function(){var m=document.getElementById('export-menu');m.classList.toggle('open')};
  document.addEventListener('click',function(e){if(!e.target.closest('.export-dropdown')){var m=document.getElementById('export-menu');if(m)m.classList.remove('open')}});
  window.exportMd=function(){document.getElementById('export-menu').classList.remove('open');window.exportChat('md')};
  window.exportJson=function(){document.getElementById('export-menu').classList.remove('open');window.exportChat('json')};
  window.exportServerMd=function(){document.getElementById('export-menu').classList.remove('open');window.open('/api/sessions/'+encodeURIComponent(_currentSession)+'/export?format=md')};
  window.exportServerJson=function(){document.getElementById('export-menu').classList.remove('open');window.open('/api/sessions/'+encodeURIComponent(_currentSession)+'/export?format=json')};
  window.importChat=function(){
    var inp=document.createElement('input');inp.type='file';inp.accept='.json';
    inp.onchange=function(){
      if(!inp.files[0])return;
      var reader=new FileReader();
      reader.onload=function(e){
        try{
          var data=JSON.parse(e.target.result);
          var msgs=data.messages||data;
          if(!Array.isArray(msgs)){alert('Invalid format: messages array not found');return}
          var title=data.title||data.session||'Imported Chat';
          fetch('/api/sessions/import',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({messages:msgs,title:title})})
          .then(function(r){return r.json()}).then(function(d){
            if(d.ok){loadSessions();addMsg('assistant','✅ '+((_lang==='ko')?'대화를 가져왔습니다':'Chat imported')+': '+title)}
            else{alert(d.error||'Import failed')}
          });
        }catch(err){alert('JSON 파싱 오류: '+err.message)}
      };
      reader.readAsText(inp.files[0]);
    };
    inp.click();
  };
