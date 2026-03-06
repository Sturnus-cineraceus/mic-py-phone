// setupCompressorControl
(function(){
  function setupCompressorControl(){
    const compEnabled = document.getElementById('compEnabled');
    const compRatio = document.getElementById('compRatio');
    const compRatioVal = document.getElementById('compRatioVal');
    if(!compEnabled || !compRatio) return;

    const setUI = (s)=>{
      compEnabled.checked = !!s.enabled;
      const p = window.toPercent01 ? window.toPercent01(s.strength ?? 0.5) : 50;
      compRatio.value = String(p);
      if(compRatioVal) compRatioVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`;
    };

    (async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
          const resp = await window.pywebview.api.get_easy_settings();
          if(!resp.error && resp.compressor){ setUI(resp.compressor); }
        }
      }catch(e){}
    })();

    compEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_compressor_enabled(e.target.checked); }catch(err){} };
    compRatio.oninput = async (e)=>{ const v = e.target.value; if(compRatioVal) compRatioVal.textContent = window.strengthLabel ? window.strengthLabel(v) : `${v}%`; try{ await window.pywebview.api.set_compressor_strength(v); }catch(err){} };
  }

  window.setupCompressorControl = setupCompressorControl;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupCompressorControl(); } else { window.addEventListener('pywebviewready', setupCompressorControl); } });
  } else { if(window.pywebview){ setupCompressorControl(); } else { window.addEventListener('pywebviewready', setupCompressorControl); } }
})();
