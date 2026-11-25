import { applySections, refreshStatus, render, route } from './core.js';
import { applyTheme, buildNav, loadSettings, loadSuite } from './shell.js';
import { loadMe, me, renderUserMenu, signIn } from './accounts.js';

// the pages: each registers itself in core.pages
import './dashboard.js';
import './metrics.js';
import './correlations.js';
import './workouts.js';
import './sleep.js';
import './glucose.js';
import './records.js';
import './medicines.js';
import './emergency.js';
import './day.js';
import './settings.js';

// ---------- start ----------

loadMe().then(async () => {
  renderUserMenu();
  if (!me.user) { signIn(true); return; }
  buildNav();
  loadSuite();
  await loadSettings();
  applyTheme();
  applySections();
  refreshStatus();
  setInterval(refreshStatus, 60000);
  render();
  // a phone that just synced: the line that says so, and the dashboard or the day shown, are drawn again (the
  // suite's one live stream, iosuite_shared/static/live.js); the pages with a range or a metric picked are left alone
  import(new URL('api/live.js', document.baseURI).href)
    .then((live) => live.keepFresh('iohealth', async () => { refreshStatus(); if (['dashboard', 'day'].includes(route().page)) await render(true); }))
    .catch(() => { /* no stream on this server */ });
});
