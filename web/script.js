document.getElementById('startBtn').addEventListener('click', startBypass);
document.getElementById('stopBtn').addEventListener('click', stopBypass);

// Accordion toggle for audio console: collapsed by default
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
  // initialize collapsed
  setState(false);
}

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

// initialize audio console accordion on DOM ready
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', setupAudioAccordion);
} else {
  setupAudioAccordion();
}

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
  if(!gateEnabled || !gateRange || !gateVal) return;

  const setUI = (s)=>{
    gateEnabled.checked = !!s.enabled;
    const p = toPercent01(s.strength ?? 0.5);
    gateRange.value = String(p);
    gateVal.textContent = strengthLabel(p);
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
    }catch(e){ /* ignore */ }
  })();

  gateEnabled.onchange = async (e)=>{
    try{ await window.pywebview.api.set_gate_enabled(e.target.checked); }catch(err){ /* ignore */ }
  };
  gateRange.oninput = async (e)=>{
    const v = e.target.value;
    gateVal.textContent = strengthLabel(v);
    try{ await window.pywebview.api.set_gate_strength(v); }catch(err){ /* ignore */ }
  };
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
    const p = toPercent01(s.strength ?? 0.5);
    hpfCutoff.value = String(p);
    hpfVal.textContent = strengthLabel(p);
  };

  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
        const resp = await window.pywebview.api.get_easy_settings();
        if(!resp.error && resp.hpf){ setUI(resp.hpf); }
      }
    }catch(e){ /* ignore */ }
  })();

  hpfEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_hpf_enabled(e.target.checked); }catch(err){} };
  hpfCutoff.oninput = async (e)=>{ const v = e.target.value; hpfVal.textContent = strengthLabel(v); try{ await window.pywebview.api.set_hpf_strength(v); }catch(err){} };
}

// initialize HPF controls like others
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){ setupHPFControl(); } else { window.addEventListener('pywebviewready', setupHPFControl); }
  });
} else {
  if(window.pywebview){ setupHPFControl(); } else { window.addEventListener('pywebviewready', setupHPFControl); }
}

// Setup Noise Reduction (noisereduce) UI and bind to backend
function setupNRControl(){
  const nrEnabled = document.getElementById('nrEnabled');
  const nrStrength = document.getElementById('nrStrength');
  const nrStrengthVal = document.getElementById('nrStrengthVal');
  if(!nrEnabled) return;

  const setUI = (s)=>{
    nrEnabled.checked = !!s.enabled;
    if(nrStrength && typeof s.strength !== 'undefined'){
      const p = toPercent01(s.strength);
      nrStrength.value = String(p);
      if(nrStrengthVal) nrStrengthVal.textContent = strengthLabel(p);
    }
  };

  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_nr_settings){
        const resp = await window.pywebview.api.get_nr_settings();
        if(!resp.error){ setUI(resp); }
      }
    }catch(e){ /* ignore */ }
  })();

  nrEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_nr_enabled(e.target.checked); }catch(err){} };
  if(nrStrength){
    nrStrength.oninput = async (e)=>{
      const v = e.target.value;
      if(nrStrengthVal) nrStrengthVal.textContent = strengthLabel(v);
      try{ await window.pywebview.api.set_nr_strength(v); }catch(err){}
    };
  }
}

// initialize NR control
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){ setupNRControl(); } else { window.addEventListener('pywebviewready', setupNRControl); }
  });
} else {
  if(window.pywebview){ setupNRControl(); } else { window.addEventListener('pywebviewready', setupNRControl); }
}

// Setup compressor UI and bind to backend
function setupCompressorControl(){
  const compEnabled = document.getElementById('compEnabled');
  const compRatio = document.getElementById('compRatio');
  const compRatioVal = document.getElementById('compRatioVal');
  if(!compEnabled || !compRatio) return;

  const setUI = (s)=>{
    compEnabled.checked = !!s.enabled;
    const p = toPercent01(s.strength ?? 0.5);
    compRatio.value = String(p);
    if(compRatioVal) compRatioVal.textContent = strengthLabel(p);
  };

  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
        const resp = await window.pywebview.api.get_easy_settings();
        if(!resp.error && resp.compressor){ setUI(resp.compressor); }
      }
    }catch(e){ /* ignore */ }
  })();

  compEnabled.onchange = async (e)=>{ try{ await window.pywebview.api.set_compressor_enabled(e.target.checked); }catch(err){} };
  compRatio.oninput = async (e)=>{
    const v = e.target.value;
    if(compRatioVal) compRatioVal.textContent = strengthLabel(v);
    try{ await window.pywebview.api.set_compressor_strength(v); }catch(err){}
  };
}

// initialize compressor control
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){ setupCompressorControl(); } else { window.addEventListener('pywebviewready', setupCompressorControl); }
  });
} else {
  if(window.pywebview){ setupCompressorControl(); } else { window.addEventListener('pywebviewready', setupCompressorControl); }
}

// Setup final noise adjustment (post-gain de-hiss) UI and bind to backend
function setupFinalNoiseControl(){
  const dehissEnabled = document.getElementById('dehissEnabled');
  const dehissStrength = document.getElementById('dehissStrength');
  const dehissVal = document.getElementById('dehissVal');
  if(!dehissEnabled || !dehissStrength || !dehissVal) return;

  const setUI = (s)=>{
    dehissEnabled.checked = !!s.enabled;
    const p = toPercent01(s.strength ?? 0.5);
    dehissStrength.value = String(p);
    dehissVal.textContent = strengthLabel(p);
  };

  (async ()=>{
    try{
      if(window.pywebview && window.pywebview.api && window.pywebview.api.get_final_noise_settings){
        const resp = await window.pywebview.api.get_final_noise_settings();
        if(!resp.error){ setUI(resp); }
      } else if(window.pywebview && window.pywebview.api && window.pywebview.api.get_easy_settings){
        const resp = await window.pywebview.api.get_easy_settings();
        if(!resp.error && resp.final_noise){ setUI(resp.final_noise); }
      }
    }catch(e){ /* ignore */ }
  })();

  dehissEnabled.onchange = async (e)=>{
    try{ await window.pywebview.api.set_final_noise_enabled(e.target.checked); }catch(err){}
  };
  dehissStrength.oninput = async (e)=>{
    const v = e.target.value;
    dehissVal.textContent = strengthLabel(v);
    try{ await window.pywebview.api.set_final_noise_strength(v); }catch(err){}
  };
}

// initialize final noise adjustment control
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', ()=>{
    if(window.pywebview){ setupFinalNoiseControl(); } else { window.addEventListener('pywebviewready', setupFinalNoiseControl); }
  });
} else {
  if(window.pywebview){ setupFinalNoiseControl(); } else { window.addEventListener('pywebviewready', setupFinalNoiseControl); }
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
