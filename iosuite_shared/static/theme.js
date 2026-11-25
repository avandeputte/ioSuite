// One appearance choice for the whole suite, kept with the account and mirrored in this browser, applied before the
// page draws so it never flashes the wrong theme: the device's unless Settings › Appearance chose light or dark.
// Every app serves this at <app>/api/auth/theme.js and names it in its page; frame.js keeps the same key.
(function () { var t = 'system'; try { t = localStorage.getItem('iosuite.theme') || 'system'; } catch (e) {} if (t !== 'system') document.documentElement.dataset.theme = t === 'dark' ? 'dark' : 'light'; })();
