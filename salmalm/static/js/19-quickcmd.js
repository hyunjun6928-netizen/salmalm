  /* --- Quick command from sidebar --- */
  window.quickCmd=function(msg){
    input.value=msg;input.focus();
    input.dispatchEvent(new Event('input'));
    /* close sidebar on mobile */
    var sb=document.getElementById('sidebar');if(sb.classList.contains('open'))toggleSidebar();
  };
