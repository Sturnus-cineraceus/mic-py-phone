// setupNRControl
(function(){
  function setupNRControl(){
    const nrEnabled = document.getElementById('nrEnabled');
    const nrStrength = document.getElementById('nrStrength');
    const nrStrengthVal = document.getElementById('nrStrengthVal');
    if(!nrEnabled) return;

    const setUI = (s)=>{
      nrEnabled.checked = !!s.enabled;
      if(nrStrength && typeof s.strength !== 'undefined'){
        const p = window.toPercent01 ? window.toPercent01(s.strength) : 50;
        nrStrength.value = String(p);
        if(nrStrengthVal) nrStrengthVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`;
      }
    };

    (async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_nr_settings){
          const resp = await window.pywebview.api.get_nr_settings();
          if(!resp.error){ setUI(resp); }
        }
      }catch(e){}
    })();

    nrEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_nr_enabled(e.target.checked); }catch(err){} };
    if(nrStrength){ nrStrength.oninput = async (e)=>{ const v = e.target.value; if(nrStrengthVal) nrStrengthVal.textContent = window.strengthLabel ? window.strengthLabel(v) : `${v}%`; try{ await window.pywebview.api.set_nr_strength(v); }catch(err){} }; }
  }

  window.setupNRControl = setupNRControl;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupNRControl(); } else { window.addEventListener('pywebviewready', setupNRControl); } });
  } else { if(window.pywebview){ setupNRControl(); } else { window.addEventListener('pywebviewready', setupNRControl); } }
})();
