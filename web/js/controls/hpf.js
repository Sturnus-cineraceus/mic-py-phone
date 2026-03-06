// setupHPFControl
(function(){
  function setupHPFControl(){
    const hpfEnabled = document.getElementById('hpfEnabled');
    const hpfCutoff = document.getElementById('hpfCutoff');
    const hpfVal = document.getElementById('hpfVal');
    if(!hpfEnabled || !hpfCutoff || !hpfVal) return;

    const setUI = (s)=>{
      hpfEnabled.checked = !!s.enabled;
      const p = window.toPercent01 ? window.toPercent01(s.strength ?? 0.5) : 50;
      hpfCutoff.value = String(p);
      hpfVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`;
    };

    (async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
          const resp = await window.pywebview.api.get_easy_settings();
          if(!resp.error && resp.hpf){ setUI(resp.hpf); }
        }
      }catch(e){}
    })();

    hpfEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_hpf_enabled(e.target.checked); }catch(err){} };
    hpfCutoff.oninput = async (e)=>{ const v = e.target.value; hpfVal.textContent = window.strengthLabel ? window.strengthLabel(v) : `${v}%`; try{ await window.pywebview.api.set_hpf_strength(v); }catch(err){} };
  }

  window.setupHPFControl = setupHPFControl;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupHPFControl(); } else { window.addEventListener('pywebviewready', setupHPFControl); } });
  } else { if(window.pywebview){ setupHPFControl(); } else { window.addEventListener('pywebviewready', setupHPFControl); } }
})();
