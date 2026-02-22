  /* --- Drag highlight --- */
  var ia=document.getElementById('input-area');
  ia.addEventListener('dragenter',function(e){e.preventDefault();ia.classList.add('drag-over')});
  ia.addEventListener('dragover',function(e){e.preventDefault()});
  ia.addEventListener('dragleave',function(){ia.classList.remove('drag-over')});
  ia.addEventListener('drop',function(e){e.preventDefault();ia.classList.remove('drag-over');
    var files=e.dataTransfer.files;if(files.length>0){window.setFile(files[0])}});

  /* --- Scroll to bottom button --- */
  var scrollBtn=document.createElement('button');scrollBtn.id='scroll-bottom';scrollBtn.textContent='↓';
  document.body.appendChild(scrollBtn);
  chat.addEventListener('scroll',function(){
    var atBottom=chat.scrollHeight-chat.scrollTop-chat.clientHeight<100;
    scrollBtn.style.display=atBottom?'none':'flex';
  });
  scrollBtn.addEventListener('click',function(){chat.scrollTop=chat.scrollHeight});

  /* --- Syntax highlighting (pure JS, no external libs) --- */
  var _hlKeywords={
    javascript:'\b(function|const|let|var|if|else|for|while|return|import|from|export|default|class|new|this|typeof|instanceof|try|catch|finally|throw|async|await|yield|switch|case|break|continue|do|in|of|null|undefined|true|false|void|delete)\b',
    python:'\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|raise|with|yield|async|await|lambda|pass|break|continue|and|or|not|in|is|None|True|False|global|nonlocal|del|assert)\b',
    bash:'\b(if|then|else|elif|fi|for|while|do|done|case|esac|function|return|exit|echo|export|source|alias|local|readonly|shift|eval|exec|trap|set|cd|pwd|ls|cat|grep|sed|awk|find|sudo|apt|pip|npm|git|docker|curl|wget)\b',
    html:'\b(html|head|body|div|span|p|a|img|script|style|link|meta|title|ul|ol|li|table|tr|td|th|form|input|button|select|option|textarea|nav|header|footer|section|article|main|class|id|href|src|type|rel)\b',
    css:'\b(color|background|margin|padding|border|font|display|flex|grid|position|width|height|top|left|right|bottom|opacity|transition|transform|animation|overflow|none|auto|inherit|solid|relative|absolute|fixed|block|inline|important)\b',
    json:''
  };
  function highlightCode(){
    document.querySelectorAll('.bubble pre code').forEach(function(el){
      if(el.dataset.hl)return;el.dataset.hl='1';
      var h=el.innerHTML;
      var lang='';
      var lm=h.match(/^\/\*\s*(\w+)\s*\*\/\n?/);
      if(lm){lang=lm[1].toLowerCase();h=h.replace(lm[0],'')}
      var tokens=[];
      h=h.replace(/(\/\*[\s\S]*?\*\/)/g,function(m){tokens.push('<span class="cmt">'+m+'</span>');return '%%TOK'+(tokens.length-1)+'%%'});
      h=h.replace(/(\/\/.*$|#(?![\da-f]{3,8}\b).*$)/gm,function(m){tokens.push('<span class="cmt">'+m+'</span>');return '%%TOK'+(tokens.length-1)+'%%'});
      h=h.replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;|"(?:[^"\\]|\\.)*?"|'(?:[^'\\]|\\.)*?'|`(?:[^`\\]|\\.)*?`)/g,function(m){tokens.push('<span class="str">'+m+'</span>');return '%%TOK'+(tokens.length-1)+'%%'});
      h=h.replace(/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/gi,function(m){return '<span class="num">'+m+'</span>'});
      var kwPattern=_hlKeywords[lang]||_hlKeywords.javascript+'|'+_hlKeywords.python;
      if(kwPattern){h=h.replace(new RegExp(kwPattern,'g'),function(m){return '<span class="kw">'+m+'</span>'})}
      for(var i=0;i<tokens.length;i++){h=h.replace('%%TOK'+i+'%%',tokens[i])}
      el.innerHTML=h;
    });
  }
  var _hlObs=new MutationObserver(highlightCode);
  _hlObs.observe(chat,{childList:true,subtree:true});
