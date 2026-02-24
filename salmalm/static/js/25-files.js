  /* --- File handling (single & multi) --- */
  window.setFile=function(file){
    if(file.type.startsWith('image/')&&file.size>5*1024*1024){alert(t('img-too-large'));return}
    pendingFiles.push(file);pendingFile=pendingFiles[0];
    if(pendingFiles.length>1){
      fileIconEl.textContent='📎×'+pendingFiles.length;
      fileNameEl.textContent=pendingFiles.map(function(f){return f.name}).join(', ');
      fileSizeEl.textContent=(pendingFiles.reduce(function(s,f){return s+f.size},0)/1024).toFixed(1)+'KB';
      imgPrev.style.display='none';
    }else{
      const isImg=file.type.startsWith('image/');
      fileIconEl.textContent=isImg?'🖼️':'📎';
      fileNameEl.textContent=file.name;
      fileSizeEl.textContent=(file.size/1024).toFixed(1)+'KB';
      if(isImg){const r=new FileReader();r.onload=function(e){imgPrev.src=e.target.result;imgPrev.style.display='block'};r.readAsDataURL(file)}
      else{imgPrev.style.display='none'}
    }
    filePrev.style.display='block';
    input.focus();
  };
  window.setFiles=function(files){
    pendingFiles=[];
    for(var i=0;i<files.length;i++){
      var f=files[i];
      if(f.type.startsWith('image/')&&f.size>5*1024*1024)continue;
      pendingFiles.push(f);
    }
    if(!pendingFiles.length)return;
    pendingFile=pendingFiles[0];
    fileIconEl.textContent=pendingFiles.length>1?'📎×'+pendingFiles.length:(pendingFiles[0].type.startsWith('image/')?'🖼️':'📎');
    fileNameEl.textContent=pendingFiles.length>1?pendingFiles.map(function(f){return f.name}).join(', '):pendingFiles[0].name;
    fileSizeEl.textContent=(pendingFiles.reduce(function(s,f){return s+f.size},0)/1024).toFixed(1)+'KB';
    filePrev.style.display='block';
    imgPrev.style.display='none';
    if(pendingFiles.length===1&&pendingFiles[0].type.startsWith('image/')){
      var r=new FileReader();r.onload=function(e){imgPrev.src=e.target.result;imgPrev.style.display='block'};r.readAsDataURL(pendingFiles[0]);
    }
    input.focus();
  };
  window.clearFile=function(){pendingFile=null;pendingFiles=[];filePrev.style.display='none';imgPrev.style.display='none'};
