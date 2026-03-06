// setupAudioAccordion: controls the audio console accordion
(function(){
  function setupAudioAccordion(){
    const toggle = document.getElementById('audioToggle');
    const panel = document.getElementById('audioControls');
    if(!toggle || !panel) return;
    const setState = (expanded)=>{
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      if(expanded){ panel.removeAttribute('hidden'); toggle.textContent = '音声コンソール ▾'; }
      else { panel.setAttribute('hidden',''); toggle.textContent = '音声コンソール ▸'; }
    };
    toggle.addEventListener('click', ()=>{ const expanded = toggle.getAttribute('aria-expanded') === 'true'; setState(!expanded); });
    setState(false);
  }

  window.setupAudioAccordion = setupAudioAccordion;
})();
