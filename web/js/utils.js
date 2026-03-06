// utilities used by UI scripts
(function(){
  function strengthLabel(percent){
    const p = Number(percent);
    if(p < 34) return `弱(${p}%)`;
    if(p < 67) return `中(${p}%)`;
    return `強(${p}%)`;
  }

  function toPercent01(v){
    const n = Number(v);
    if(Number.isNaN(n)) return 50;
    return Math.max(0, Math.min(100, Math.round(n * 100)));
  }

  // expose as globals for now (simple incremental migration)
  window.strengthLabel = strengthLabel;
  window.toPercent01 = toPercent01;
})();
