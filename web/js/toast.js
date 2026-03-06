// simple toast helper (keeps behavior identical to original)
(function(){
  function showToast(message, type){
    try{
      const area = document.getElementById('toastArea');
      if(!area) return;
      const t = document.createElement('div');
      t.className = 'toast' + (type ? ' ' + type : '');
      t.textContent = message;
      area.appendChild(t);
      // trigger show animation
      window.requestAnimationFrame(()=> t.classList.add('show'));
      // auto-dismiss
      setTimeout(()=>{
        t.classList.remove('show');
        setTimeout(()=>{ if(t.parentNode) t.parentNode.removeChild(t); }, 300);
      }, 3000);
    }catch(e){ /* no-op */ }
  }

  window.showToast = showToast;
})();
