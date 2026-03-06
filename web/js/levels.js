// setupLevelMeters
(function(){
  function setupLevelMeters(){
    const inBar = document.getElementById('inputLevelBar');
    const outBar = document.getElementById('outputLevelBar');
    if(!inBar || !outBar) return;

    const update = async ()=>{
      try{
        if(window.pywebview && window.pywebview.api && window.pywebview.api.get_levels){
          const resp = await window.pywebview.api.get_levels();
          if(!resp.error){
            const mapDbToPct = (db)=>{
              const v = Number(db);
              if(Number.isNaN(v)) return 0;
              const pct = Math.max(0, Math.min(100, Math.round((v + 60) * (100/60))));
              return pct;
            };
            const inPct = mapDbToPct(resp.input_db);
            const outPct = mapDbToPct(resp.output_db);
            inBar.style.width = `${inPct}%`;
            outBar.style.width = `${outPct}%`;
          }
        }
      }catch(e){}
    };

    setInterval(update, 150);
  }

  window.setupLevelMeters = setupLevelMeters;

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', ()=>{ if(window.pywebview){ setupLevelMeters(); } else { window.addEventListener('pywebviewready', setupLevelMeters); } });
  } else { if(window.pywebview){ setupLevelMeters(); } else { window.addEventListener('pywebviewready', setupLevelMeters); } }
})();
