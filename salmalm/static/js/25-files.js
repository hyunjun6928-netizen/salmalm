  /* --- File handling --- */
  window.setFile=function(file){
    if(file.type.startsWith('image/')&&file.size>5*1024*1024){alert(t('img-too-large'));return}
    pendingFile=file;
    const isImg=file.type.startsWith('image/');
    fileIconEl.textContent=isImg?'🖼️':'📎';
    fileNameEl.textContent=file.name;
    fileSizeEl.textContent=(file.size/1024).toFixed(1)+'KB';
    filePrev.style.display='block';
    if(isImg){const r=new FileReader();r.onload=function(e){imgPrev.src=e.target.result;imgPrev.style.display='block'};r.readAsDataURL(file)}
    else{imgPrev.style.display='none'}
    input.focus();
  };
  window.clearFile=function(){pendingFile=null;filePrev.style.display='none';imgPrev.style.display='none'};
