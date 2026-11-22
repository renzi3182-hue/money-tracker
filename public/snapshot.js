/* Copia privata della dashboard, associata alla sessione Ricordami del dispositivo. */
const dashboardSnapshot = (() => {
  const key = 'mt-dashboard-v1';
  const marker = () => document.cookie.split('; ').find(c => c.startsWith('mt_snapshot='))?.slice(12);
  const clear = () => { try { localStorage.removeItem(key); } catch (_) {} };
  function read() {
    try {
      const saved = JSON.parse(localStorage.getItem(key));
      if (!marker() || saved?.session !== marker() || !saved.data?.auth_required ||
          !Number.isFinite(saved.at) || saved.at > Date.now() || Date.now() - saved.at > 7 * 86400000) {
        clear(); return null;
      }
      return saved;
    } catch (_) { clear(); return null; }
  }
  function save(data) {
    const session = marker();
    if (!session || !data.auth_required) { clear(); return; }
    try { localStorage.setItem(key, JSON.stringify({session, at: Date.now(), data})); } catch (_) { clear(); }
  }
  return {key, read, save, clear, session: marker};
})();
