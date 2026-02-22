  /* --- Settings Tabs --- */
  document.querySelectorAll('.settings-tab').forEach(function(tab){
    tab.addEventListener('click',function(){
      document.querySelectorAll('.settings-tab').forEach(function(t){t.classList.remove('active')});
      tab.classList.add('active');
      var which=tab.getAttribute('data-settings-tab');
      document.getElementById('settings-general').style.display=which==='general'?'block':'none';
      document.getElementById('settings-features').style.display=which==='features'?'block':'none';
      document.getElementById('settings-model-router').style.display=which==='model-router'?'block':'none';
      document.getElementById('settings-debug').style.display=which==='debug'?'block':'none';
      document.getElementById('settings-logs').style.display=which==='logs'?'block':'none';
      if(which==='features'&&!window._featuresLoaded){window._featuresLoaded=true;loadFeatures()}
      if(which==='model-router'){window._loadModelRouter()}
      if(which==='debug'){window._loadDebug()}
      if(which==='logs'){window._loadLogs()}
    });
  });
