// setupGateControl
(function(){
  function setupGateControl(){
    const gateEnabled = document.getElementById('gateEnabled');
    const gateRange = document.getElementById('gateRange');
    const gateVal = document.getElementById('gateVal');
    if(!gateEnabled || !gateRange || !gateVal) return;

    const setUI = (s)=>{
      gateEnabled.checked = !!s.enabled;
      const p = window.toPercent01 ? window.toPercent01(s.strength ?? 0.5) : 50;
      gateRange.value = String(p);
      gateVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`;
    };

    (async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
          const resp = await window.pywebview.api.get_easy_settings();
          if(!resp.error && resp.gate){ setUI(resp.gate); }
        } else if(window.pywebview && window.pywebview.api && window.pywebview.api.get_gate_settings){
          const resp = await window.pywebview.api.get_gate_settings();
          if(!resp.error){ setUI(resp); }
        }
      }catch(e){}
    })();

    gateEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_gate_enabled(e.target.checked); }catch(err){} };
    gateRange.oninput = async (e)=>{ const v = e.target.value; gateVal.textContent = window.strengthLabel ? window.strengthLabel(v) : `${v}%`; try{ await window.pywebview.api.set_gate_strength(v); }catch(err){} };
  }

  window.setupGateControl = setupGateControl;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupGateControl(); } else { window.addEventListener('pywebviewready', setupGateControl); } });
  } else { if(window.pywebview){ setupGateControl(); } else { window.addEventListener('pywebviewready', setupGateControl); } }
})();
