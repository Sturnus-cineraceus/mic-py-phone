// setupFinalNoiseControl
(function(){
  function setupFinalNoiseControl(){
    const dehissEnabled = document.getElementById('dehissEnabled');
    const dehissStrength = document.getElementById('dehissStrength');
    const dehissVal = document.getElementById('dehissVal');
    if(!dehissEnabled || !dehissStrength || !dehissVal) return;

    const setUI = (s)=>{
      dehissEnabled.checked = !!s.enabled;
      const p = window.toPercent01 ? window.toPercent01(s.strength ?? 0.5) : 50;
      dehissStrength.value = String(p);
      dehissVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`;
    };

    (async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_final_noise_settings){
          const resp = await window.pywebview.api.get_final_noise_settings();
          if(!resp.error){ setUI(resp); }
        } else if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
          const resp = await window.pywebview.api.get_easy_settings();
          if(!resp.error && resp.final_noise){ setUI(resp.final_noise); }
        }
      }catch(e){}
    })();

    dehissEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_final_noise_enabled(e.target.checked); }catch(err){} };
    dehissStrength.oninput = async (e)=>{ const v = e.target.value; dehissVal.textContent = window.strengthLabel ? window.strengthLabel(v) : `${v}%`; try{ await window.pywebview.api.set_final_noise_strength(v); }catch(err){} };
  }

  window.setupFinalNoiseControl = setupFinalNoiseControl;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupFinalNoiseControl(); } else { window.addEventListener('pywebviewready', setupFinalNoiseControl); } });
  } else { if(window.pywebview){ setupFinalNoiseControl(); } else { window.addEventListener('pywebviewready', setupFinalNoiseControl); } }
})();
