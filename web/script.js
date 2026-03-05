document.getElementById('themeBtn').addEventListener('click', ()=>{
  document.body.classList.toggle('dark');
});

document.getElementById('calcBtn').addEventListener('click', onCalculate);
document.getElementById('sysBtn').addEventListener('click', onGetSys);
document.getElementById('audioBtn').addEventListener('click', onGetAudio);

async function onCalculate(){
  const op = document.getElementById('op').value;
  const val = document.getElementById('value').value;
  const resEl = document.getElementById('result');
  resEl.textContent = '処理中...';
  try{
    const resp = await window.pywebview.api.calculate(op, val);
    if(resp.error) resEl.textContent = 'エラー: ' + resp.error;
    else resEl.textContent = '結果: ' + resp.result;
  }catch(e){
    resEl.textContent = '呼び出し失敗: ' + e;
  }
}

async function onGetSys(){
  const infoEl = document.getElementById('sysinfo');
  infoEl.textContent = '取得中...';
  try{
    const info = await window.pywebview.api.get_system_info();
    infoEl.textContent = `Platform: ${info.platform} | Python: ${info.python}`;
  }catch(e){
    infoEl.textContent = '取得失敗: ' + e;
  }
}

async function onGetAudio(){
  const el = document.getElementById('audiolist');
  el.textContent = '取得中...';
  try{
    const resp = await window.pywebview.api.get_audio_devices();
    if(resp.error){
      el.textContent = 'エラー: ' + resp.error;
      return;
    }
    const devices = resp.devices || [];
    const hostapis = resp.hostapis || [];
    const defaultDev = resp.default_device;
    if(devices.length === 0){
      el.textContent = 'デバイスが見つかりませんでした。';
      return;
    }

    const inputSelect = document.getElementById('inputSelect');
    const outputSelect = document.getElementById('outputSelect');
    inputSelect.innerHTML = '';
    outputSelect.innerHTML = '';

    // Show only WASAPI hostapi devices (flat list). If none, fall back to flat devices list.
    let wasapiDevices = [];
    if(hostapis.length > 0){
      hostapis.forEach(h => {
        const name = (h.name || '').toString().toUpperCase();
        if(name.includes('WASAPI')){
          (h.devices || []).forEach(d => {
            // avoid duplicates
            if(!wasapiDevices.find(x => x.index === d.index)) wasapiDevices.push(d);
          });
        }
      });
    }

    const listToUse = (wasapiDevices.length > 0) ? wasapiDevices : devices;
    listToUse.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.index;
      opt.text = `${d.name} (idx:${d.index})`;
      if(d.max_input_channels && d.max_input_channels > 0){
        inputSelect.appendChild(opt.cloneNode(true));
      }
      if(d.max_output_channels && d.max_output_channels > 0){
        outputSelect.appendChild(opt.cloneNode(true));
      }
    });

    // set defaults if available
    if(Array.isArray(defaultDev)){
      const inIdx = defaultDev[0];
      const outIdx = defaultDev[1];
      if(inIdx !== null && inIdx !== undefined){
        const opt = inputSelect.querySelector(`option[value="${inIdx}"]`);
        if(opt) opt.selected = true;
      }
      if(outIdx !== null && outIdx !== undefined){
        const opt2 = outputSelect.querySelector(`option[value="${outIdx}"]`);
        if(opt2) opt2.selected = true;
      }
    }

    // use onchange to avoid duplicate handlers on repeated loads
    inputSelect.onchange = async (e) => {
      const idx = e.target.value;
      try{ await window.pywebview.api.set_input_device(idx); el.textContent = 'マイク選択: ' + idx; }catch(err){ el.textContent = '設定失敗: ' + err; }
    };
    outputSelect.onchange = async (e) => {
      const idx = e.target.value;
      try{ await window.pywebview.api.set_output_device(idx); el.textContent = 'スピーカー選択: ' + idx; }catch(err){ el.textContent = '設定失敗: ' + err; }
    };

    el.textContent = 'デバイスが読み込まれました。ホストAPIごとにグループ表示しています。';
  }catch(e){
    el.textContent = '取得失敗: ' + e;
  }
}

function showMessage(){
  const el = document.getElementById('message');
  el.textContent = 'こんにちは！ pywebview サンプルです。';
}
