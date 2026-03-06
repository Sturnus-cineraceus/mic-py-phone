// save/load/reset settings and refreshAllControls
(function(){
  async function refreshAllControls(){
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_gain_db){
        const resp = await window.pywebview.api.get_gain_db();
        if(!resp.error && typeof resp.gain_db !== 'undefined'){
          const gainEl = document.getElementById('gainRange');
          const gainValEl = document.getElementById('gainVal');
          if(gainEl && gainValEl){ const v = Number(resp.gain_db).toFixed(1); gainEl.value = String(v); gainValEl.textContent = `${v} dB`; }
        }
      }
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
        const resp = await window.pywebview.api.get_easy_settings();
        if(!resp.error){
          if(resp.gate){ const gateEnabled = document.getElementById('gateEnabled'); const gateRange = document.getElementById('gateRange'); const gateVal = document.getElementById('gateVal'); if(gateEnabled) gateEnabled.checked = !!resp.gate.enabled; if(gateRange && gateVal){ const p = window.toPercent01 ? window.toPercent01(resp.gate.strength ?? 0.5) : 50; gateRange.value = String(p); gateVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`; } }
          if(resp.hpf){ const hpfEnabled = document.getElementById('hpfEnabled'); const hpfCutoff = document.getElementById('hpfCutoff'); const hpfVal = document.getElementById('hpfVal'); if(hpfEnabled) hpfEnabled.checked = !!resp.hpf.enabled; if(hpfCutoff && hpfVal){ const p = window.toPercent01 ? window.toPercent01(resp.hpf.strength ?? 0.5) : 50; hpfCutoff.value = String(p); hpfVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`; } }
          if(resp.compressor){ const compEnabled = document.getElementById('compEnabled'); const compRatio = document.getElementById('compRatio'); const compRatioVal = document.getElementById('compRatioVal'); if(compEnabled) compEnabled.checked = !!resp.compressor.enabled; if(compRatio && compRatioVal){ const p = window.toPercent01 ? window.toPercent01(resp.compressor.strength ?? 0.5) : 50; compRatio.value = String(p); compRatioVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`; } }
          if(resp.final_noise){ const dehissEnabled = document.getElementById('dehissEnabled'); const dehissStrength = document.getElementById('dehissStrength'); const dehissVal = document.getElementById('dehissVal'); if(dehissEnabled) dehissEnabled.checked = !!resp.final_noise.enabled; if(dehissStrength && dehissVal){ const p = window.toPercent01 ? window.toPercent01(resp.final_noise.strength ?? 0.5) : 50; dehissStrength.value = String(p); dehissVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`; } }
        }
      }
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_nr_settings){
        const resp = await window.pywebview.api.get_nr_settings();
        if(!resp.error){ const nrEnabled = document.getElementById('nrEnabled'); const nrStrength = document.getElementById('nrStrength'); const nrStrengthVal = document.getElementById('nrStrengthVal'); if(nrEnabled) nrEnabled.checked = !!resp.enabled; if(nrStrength && typeof resp.strength !== 'undefined'){ const p = window.toPercent01 ? window.toPercent01(resp.strength) : 50; nrStrength.value = String(p); if(nrStrengthVal) nrStrengthVal.textContent = window.strengthLabel ? window.strengthLabel(p) : `${p}%`; } }
      }
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_selected_devices){
        const resp = await window.pywebview.api.get_selected_devices();
        if(!resp.error){ const inputSelect = document.getElementById('inputSelect'); const outputSelect = document.getElementById('outputSelect'); if(inputSelect && resp.input !== null && resp.input !== undefined){ const opt = inputSelect.querySelector(`option[value="${resp.input}"]`); if(opt) opt.selected = true; } if(outputSelect && resp.output !== null && resp.output !== undefined){ const opt2 = outputSelect.querySelector(`option[value="${resp.output}"]`); if(opt2) opt2.selected = true; } }
      }
      try{ if(window.pywebview && window.pywebview.api && window.pywebview.api.get_transcribe_settings){ const t = await window.pywebview.api.get_transcribe_settings(); if(!t.error){ const cb = document.getElementById('transcribeEnabled'); const st = document.getElementById('transcribeStatus'); if(cb) cb.checked = !!t.enabled; if(st) st.textContent = t.enabled ? '文字起こし: ON' : '文字起こし: OFF'; } } }catch(e){}
    }catch(e){}
  }

  async function saveSettings(){ try{ const resp = await window.pywebview.api.save_settings(); if(resp.error){ window.showToast && window.showToast('設定の保存に失敗しました。', 'error'); } else { window.showToast && window.showToast('設定を保存しました。', 'success'); } }catch(e){ window.showToast && window.showToast('設定の保存に失敗しました。', 'error'); } }

  async function loadSettings(){ try{ const resp = await window.pywebview.api.load_settings(); if(resp.error){ window.showToast && window.showToast('設定読み込み失敗: ' + resp.error, 'error'); } else { await refreshAllControls(); window.showToast && window.showToast('設定を読み込みました。'); } }catch(e){ window.showToast && window.showToast('設定読み込み失敗: ' + e, 'error'); } }

  async function resetSettings(){ try{ const resp = await window.pywebview.api.reset_settings(); if(resp.error){ window.showToast && window.showToast('デフォルトリセット失敗: ' + resp.error, 'error'); } else { await refreshAllControls(); window.showToast && window.showToast('デフォルト設定に戻しました。'); } }catch(e){ window.showToast && window.showToast('デフォルトリセット失敗: ' + e, 'error'); } }

  window.refreshAllControls = refreshAllControls;
  window.saveSettings = saveSettings;
  window.loadSettings = loadSettings;
  window.resetSettings = resetSettings;
})();
