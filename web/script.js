document.getElementById('audioBtn').addEventListener('click', loadAudioDevices);
document.getElementById('startBtn').addEventListener('click', startBypass);
document.getElementById('stopBtn').addEventListener('click', stopBypass);

async function loadAudioDevices(){
  const statusEl = document.getElementById('status');
  statusEl.textContent = '状態: デバイス取得中...';
  try{
    const resp = await window.pywebview.api.get_audio_devices();
    if(resp.error){
      statusEl.textContent = 'エラー: ' + resp.error;
      return;
    }
    const devices = resp.devices || [];
    const hostapis = resp.hostapis || [];
    const defaultDev = resp.default_device;
    if(devices.length === 0){
      statusEl.textContent = 'デバイスが見つかりません。';
      return;
    }

    const inputSelect = document.getElementById('inputSelect');
    const outputSelect = document.getElementById('outputSelect');
    inputSelect.innerHTML = '';
    outputSelect.innerHTML = '';

    // Prefer grouping by hostapi where possible, otherwise use flat list
    let candidateDevices = devices;
    if(hostapis.length > 0){
      // flatten hostapi devices to avoid duplicates
      const seen = new Set();
      const flat = [];
      hostapis.forEach(h => { (h.devices||[]).forEach(d => { if(!seen.has(d.index)){ seen.add(d.index); flat.push(d); } }); });
      if(flat.length > 0) candidateDevices = flat;
    }

    candidateDevices.forEach(d => {
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

    // set defaults if provided by backend
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

    inputSelect.onchange = async (e) => {
      const idx = e.target.value;
      try{ await window.pywebview.api.set_input_device(idx); statusEl.textContent = '状態: 入力選択 ' + idx; }catch(err){ statusEl.textContent = '設定失敗: ' + err; }
    };
    outputSelect.onchange = async (e) => {
      const idx = e.target.value;
      try{ await window.pywebview.api.set_output_device(idx); statusEl.textContent = '状態: 出力選択 ' + idx; }catch(err){ statusEl.textContent = '設定失敗: ' + err; }
    };

    statusEl.textContent = '状態: デバイス読み込み完了';
  }catch(e){
    document.getElementById('status').textContent = '取得失敗: ' + e;
  }
}

async function startBypass(){
  const statusEl = document.getElementById('status');
  statusEl.textContent = '状態: バイパス開始中...';
  try{
    const resp = await window.pywebview.api.start_bypass();
    if(resp.error){ statusEl.textContent = '開始失敗: ' + resp.error; return; }
    statusEl.textContent = '状態: 実行中';
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
  }catch(e){ statusEl.textContent = '開始失敗: ' + e; }
}

async function stopBypass(){
  const statusEl = document.getElementById('status');
  statusEl.textContent = '状態: 停止中...';
  try{
    const resp = await window.pywebview.api.stop_bypass();
    if(resp.error){ statusEl.textContent = '停止失敗: ' + resp.error; return; }
    statusEl.textContent = '状態: 停止';
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
  }catch(e){ statusEl.textContent = '停止失敗: ' + e; }
}
