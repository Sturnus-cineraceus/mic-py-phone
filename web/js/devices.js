// loadAudioDevices and scheduleLoadAudioDevices
(function(){
  async function loadAudioDevices(){
    window.showToast && window.showToast('デバイス取得中...');
    try{
      const resp = await window.pywebview.api.get_audio_devices();
      if(resp.error){ window.showToast && window.showToast('エラー: ' + resp.error, 'error'); return; }
      const devices = resp.devices || [];
      const hostapis = resp.hostapis || [];
      const defaultDev = resp.default_device;
      if(devices.length === 0){ window.showToast && window.showToast('デバイスが見つかりません。', 'error'); return; }

      const inputSelect = document.getElementById('inputSelect');
      const outputSelect = document.getElementById('outputSelect');
      if(inputSelect) inputSelect.innerHTML = '';
      if(outputSelect) outputSelect.innerHTML = '';

      let candidateDevices = devices;
      if(hostapis.length > 0){
        const seen = new Set();
        const flat = [];
        hostapis.forEach(h => { (h.devices||[]).forEach(d => { if(!seen.has(d.index)){ seen.add(d.index); flat.push(d); } }); });
        if(flat.length > 0) candidateDevices = flat;
      }

      candidateDevices.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.index;
        opt.text = `${d.name} (idx:${d.index})`;
        if(d.max_input_channels && d.max_input_channels > 0){ inputSelect && inputSelect.appendChild(opt.cloneNode(true)); }
        if(d.max_output_channels && d.max_output_channels > 0){ outputSelect && outputSelect.appendChild(opt.cloneNode(true)); }
      });

      if(Array.isArray(defaultDev)){
        const inIdx = defaultDev[0];
        const outIdx = defaultDev[1];
        if(inIdx !== null && inIdx !== undefined){ const opt = inputSelect.querySelector(`option[value="${inIdx}"]`); if(opt) opt.selected = true; }
        if(outIdx !== null && outIdx !== undefined){ const opt2 = outputSelect.querySelector(`option[value="${outIdx}"]`); if(opt2) opt2.selected = true; }
      }

      if(inputSelect){
        inputSelect.onchange = async (e) => {
          const idx = e.target.value;
          try{ await window.pywebview.api.set_input_device(idx); window.showToast && window.showToast('入力を選択しました: ' + idx); }catch(err){ window.showToast && window.showToast('入力設定失敗: ' + err, 'error'); }
        };
      }
      if(outputSelect){
        outputSelect.onchange = async (e) => {
          const idx = e.target.value;
          try{ await window.pywebview.api.set_output_device(idx); window.showToast && window.showToast('出力を選択しました: ' + idx); }catch(err){ window.showToast && window.showToast('出力設定失敗: ' + err, 'error'); }
        };
      }

      try{
        const curIn = inputSelect && inputSelect.value;
        const curOut = outputSelect && outputSelect.value;
        if(curIn !== undefined && curIn !== null && curIn !== ''){ try{ await window.pywebview.api.set_input_device(curIn); }catch(e){} }
        if(curOut !== undefined && curOut !== null && curOut !== ''){ try{ await window.pywebview.api.set_output_device(curOut); }catch(e){} }
      }catch(e){}

      window.showToast && window.showToast('デバイス読み込み完了', 'success');
    }catch(e){ window.showToast && window.showToast('取得失敗: ' + e, 'error'); }
  }

  function scheduleLoadAudioDevices(){
    const runLoad = () => {
      if(window.pywebview && window.pywebview.api){ loadAudioDevices(); }
      else { window.addEventListener('pywebviewready', loadAudioDevices); }
    };
    if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', runLoad); } else { runLoad(); }
  }

  window.loadAudioDevices = loadAudioDevices;
  window.scheduleLoadAudioDevices = scheduleLoadAudioDevices;

  // run once on load
  scheduleLoadAudioDevices();
})();
