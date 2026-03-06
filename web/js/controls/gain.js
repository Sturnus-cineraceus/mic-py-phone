// setupGainControl
(function(){
  function setupGainControl(){
    const gainEl = document.getElementById('gainRange');
    const gainVal = document.getElementById('gainVal');
    if(!gainEl || !gainVal) return;

    const setUI = (v)=>{ gainEl.value = String(v); gainVal.textContent = `${v} dB`; };

    (async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_gain_db){
          const resp = await window.pywebview.api.get_gain_db();
          if(!resp.error && typeof resp.gain_db !== 'undefined'){ setUI(Number(resp.gain_db).toFixed(1)); }
        }
      }catch(e){ }
    })();

    gainEl.oninput = async (e)=>{
      const v = e.target.value;
      gainVal.textContent = `${v} dB`;
      try{ if(window.pywebview && window.pywebview.api && window.pywebview.api.set_gain_db){ await window.pywebview.api.set_gain_db(v); } }catch(err){}
    };
  }

  window.setupGainControl = setupGainControl;

  // auto-init when pywebview ready or DOM ready
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupGainControl(); } else { window.addEventListener('pywebviewready', setupGainControl); } });
  } else {
    if(window.pywebview){ setupGainControl(); } else { window.addEventListener('pywebviewready', setupGainControl); }
  }
})();
