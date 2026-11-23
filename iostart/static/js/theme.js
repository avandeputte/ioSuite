// Applied before the page draws, so it never flashes the wrong theme: the device's by default, or what Settings › Display chose (kept with the account).
(function () { var t = 'system'; try { t = localStorage.getItem('iostart.theme') || 'system'; } catch (e) {} if (t !== 'system') document.documentElement.dataset.theme = t === 'dark' ? 'dark' : 'light'; })();
// The same for the page's colour and the size of its type (Customize › Look; home.js applyLook keeps them here).
(function () { try { var l = JSON.parse(localStorage.getItem('iostart.look') || '{}'), d = document.documentElement.dataset; if (/^[a-z]{2,12}$/.test(l.accent || '')) d.accent = l.accent; if (/^[a-z]{2,12}$/.test(l.text || '')) d.text = l.text; } catch (e) {} })();
