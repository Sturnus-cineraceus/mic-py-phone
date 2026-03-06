// startBypass / stopBypass
(function(){
  let statusEl = null;
  function setupStatusElement(){ statusEl = document.getElementById('bypassStatus'); if(statusEl) statusEl.textContent = 'ステータス: 停止中'; }
  if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', setupStatusElement); } else { setupStatusElement(); }

  async function startBypass(){
    window.showToast && window.showToast('バイパスを開始中...');
    try{
      const resp = await window.pywebview.api.start_bypass();
      if(resp.error){ if(statusEl) statusEl.textContent = '開始失敗: ' + resp.error; return; }
      window.showToast && window.showToast('バイパスを開始しました。', 'success');
      document.getElementById('startBtn').disabled = true;
      document.getElementById('stopBtn').disabled = false;
      if(statusEl) statusEl.textContent = 'ステータス: バイパス中';
    }catch(e){ statusEl && (statusEl.textContent = '開始失敗: ' + e); }
  }

  async function stopBypass(){
    window.showToast && window.showToast('停止中...');
    try{
      const resp = await window.pywebview.api.stop_bypass();
      if(resp.error){ if(statusEl) statusEl.textContent = '停止失敗: ' + resp.error; return; }
      window.showToast && window.showToast('停止しました。', 'success');
      document.getElementById('startBtn').disabled = false;
      document.getElementById('stopBtn').disabled = true;
      if(statusEl) statusEl.textContent = 'ステータス: 停止中';
    }catch(e){ statusEl && (statusEl.textContent = '停止失敗: ' + e); }
  }

  window.startBypass = startBypass;
  window.stopBypass = stopBypass;
})();
