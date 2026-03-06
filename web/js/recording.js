// startRecording / stopRecording
(function(){
  async function startRecording(){
    try{
      const dlg = await window.pywebview.api.open_save_file_dialog();
      if(!dlg || dlg.path === null || typeof dlg.path === 'undefined'){
        window.showToast && window.showToast('保存がキャンセルされました。');
        return;
      }
      const path = dlg.path;
      window.showToast && window.showToast('録音を開始します。');
      const resp = await window.pywebview.api.start_record(path);
      if(resp && resp.ok){
        const recBtnEl = document.getElementById('recBtn');
        const recStopBtnEl = document.getElementById('recStopBtn');
        if(recBtnEl) recBtnEl.disabled = true;
        if(recStopBtnEl) recStopBtnEl.disabled = false;
        if(recBtnEl) recBtnEl.classList.add('recording');
        const st = document.getElementById('recordStatus'); if(st) st.textContent = '録音: 録音中';
        window.showToast && window.showToast('録音中...');
      } else { window.showToast && window.showToast('録音開始に失敗しました: ' + (resp && resp.error ? resp.error : '不明なエラー'), 'error'); }
    }catch(e){ window.showToast && window.showToast('録音開始に失敗しました: ' + e, 'error'); }
  }

    async function stopRecording(){
    try{
      window.showToast && window.showToast('保存を開始します。');
      const resp = await window.pywebview.api.stop_record();
      if(resp && resp.ok){
        const recBtnEl = document.getElementById('recBtn');
        const recStopBtnEl = document.getElementById('recStopBtn');
        if(recBtnEl) recBtnEl.disabled = false;
        if(recStopBtnEl) recStopBtnEl.disabled = true;
        if(recBtnEl) recBtnEl.classList.remove('recording');
        const st = document.getElementById('recordStatus');
        if(st){
          if(resp.converting){
            st.textContent = '録音: 変換中';
          } else {
            st.textContent = '録音: 停止中';
          }
        }
        if(resp.converting){
          window.showToast && window.showToast('録音ファイルを変換しています。処理が完了したら出力ファイルに保存されます。', 'info');
        } else {
          window.showToast && window.showToast('録音を保存しました。', 'success');
        }
      } else { window.showToast && window.showToast('録音停止に失敗しました: ' + (resp && resp.error ? resp.error : '不明なエラー'), 'error'); }
    }catch(e){ window.showToast && window.showToast('録音停止に失敗しました: ' + e, 'error'); }
  }

  window.startRecording = startRecording;
  window.stopRecording = stopRecording;
})();
