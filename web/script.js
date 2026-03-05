document.getElementById('startBtn').addEventListener('click', startBypass);
document.getElementById('stopBtn').addEventListener('click', stopBypass);

// 自動読み込み: 起動時にデバイス一覧を取得してプルダウンを埋める
function scheduleLoadAudioDevices(){
  const runLoad = () => {
    if(window.pywebview && window.pywebview.api){
      loadAudioDevices();
    } else {
      window.addEventListener('pywebviewready', loadAudioDevices);
    }
  };

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', runLoad);
  } else {
    runLoad();
  }
}

// 起動時に一度だけ実行
scheduleLoadAudioDevices();

// Setup gain control UI and bind to backend
function setupGainControl(){
  const gainEl = document.getElementById('gainRange');
  const gainVal = document.getElementById('gainVal');
  if(!gainEl || !gainVal) return;

  const setUI = (v)=>{ gainEl.value = String(v); gainVal.textContent = `${v} dB`; };

  // initialize from backend if available
  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_gain_db){
        const resp = await window.pywebview.api.get_gain_db();
        if(!resp.error && typeof resp.gain_db !== 'undefined'){
          setUI(Number(resp.gain_db).toFixed(1));
        }
      }
    }catch(e){ /* ignore */ }
  })();

  gainEl.oninput = async (e)=>{
    const v = e.target.value;
    gainVal.textContent = `${v} dB`;
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.set_gain_db){
        await window.pywebview.api.set_gain_db(v);
      }
    }catch(err){ /* ignore */ }
  };
}
// also setup gain control once pywebview is ready
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){
      setupGainControl();
    } else {
      window.addEventListener('pywebviewready', setupGainControl);
    }
  });
} else {
  if(window.pywebview){
    setupGainControl();
  } else {
    window.addEventListener('pywebviewready', setupGainControl);
  }
}

// Setup noise gate UI and bind to backend
function setupGateControl(){
  const gateEnabled = document.getElementById('gateEnabled');
  const gateRange = document.getElementById('gateRange');
  const gateVal = document.getElementById('gateVal');
  const gateAttack = document.getElementById('gateAttack');
  const gateRelease = document.getElementById('gateRelease');
  if(!gateEnabled || !gateRange || !gateVal) return;

  const setUI = (s)=>{
    gateEnabled.checked = !!s.enabled;
    gateRange.value = String(s.threshold_db);
    gateVal.textContent = `${s.threshold_db} dB`;
    if(gateAttack) gateAttack.value = String(s.attack_ms);
    if(gateRelease) gateRelease.value = String(s.release_ms);
  };

  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_gate_settings){
        const resp = await window.pywebview.api.get_gate_settings();
        if(!resp.error){ setUI(resp); }
      }
    }catch(e){ /* ignore */ }
  })();

  gateEnabled.onchange = async (e)=>{
    try{ await window.pywebview.api.set_gate_enabled(e.target.checked); }catch(err){ /* ignore */ }
  };
  gateRange.oninput = async (e)=>{
    const v = e.target.value; gateVal.textContent = `${v} dB`;
    try{ await window.pywebview.api.set_gate_threshold_db(v); }catch(err){ /* ignore */ }
  };
  if(gateAttack){ gateAttack.onchange = async (e)=>{ try{ await window.pywebview.api.set_gate_attack_ms(e.target.value); }catch(err){} }; }
  if(gateRelease){ gateRelease.onchange = async (e)=>{ try{ await window.pywebview.api.set_gate_release_ms(e.target.value); }catch(err){} }; }
}

// initialize gate controls like gain controls
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){ setupGateControl(); } else { window.addEventListener('pywebviewready', setupGateControl); }
  });
} else {
  if(window.pywebview){ setupGateControl(); } else { window.addEventListener('pywebviewready', setupGateControl); }
}

// Setup HPF control UI and bind to backend
function setupHPFControl(){
  const hpfEnabled = document.getElementById('hpfEnabled');
  const hpfCutoff = document.getElementById('hpfCutoff');
  const hpfVal = document.getElementById('hpfVal');
  if(!hpfEnabled || !hpfCutoff || !hpfVal) return;

  const setUI = (s)=>{
    hpfEnabled.checked = !!s.enabled;
    hpfCutoff.value = String(s.cutoff_hz);
    hpfVal.textContent = `${s.cutoff_hz} Hz`;
  };

  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_hpf_settings){
        const resp = await window.pywebview.api.get_hpf_settings();
        if(!resp.error){ setUI(resp); }
      }
    }catch(e){ /* ignore */ }
  })();

  hpfEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_hpf_enabled(e.target.checked); }catch(err){} };
  hpfCutoff.oninput = async (e)=>{ const v = e.target.value; hpfVal.textContent = `${v} Hz`; try{ await window.pywebview.api.set_hpf_cutoff_hz(v); }catch(err){} };
}

// initialize HPF controls like others
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){ setupHPFControl(); } else { window.addEventListener('pywebviewready', setupHPFControl); }
  });
} else {
  if(window.pywebview){ setupHPFControl(); } else { window.addEventListener('pywebviewready', setupHPFControl); }
}

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

    // Ensure backend has the currently-selected values even if the user didn't change the selects
    try{
      const curIn = inputSelect.value;
      const curOut = outputSelect.value;
      if(curIn !== undefined && curIn !== null && curIn !== ''){
        try{ await window.pywebview.api.set_input_device(curIn); }catch(e){ /* ignore */ }
      }
      if(curOut !== undefined && curOut !== null && curOut !== ''){
        try{ await window.pywebview.api.set_output_device(curOut); }catch(e){ /* ignore */ }
      }
    }catch(e){ /* ignore */ }

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
