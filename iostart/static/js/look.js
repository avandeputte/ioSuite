// The page's colour and the size of its type, as each person picks them (Customize › Look; home.js applyLook keeps
// them here), applied before the page draws so the next visit opens in them at once. The theme itself is the suite's
// one choice (api/auth/theme.js).
(function () { try { var l = JSON.parse(localStorage.getItem('iostart.look') || '{}'), d = document.documentElement.dataset; if (/^[a-z]{2,12}$/.test(l.accent || '')) d.accent = l.accent; if (/^[a-z]{2,12}$/.test(l.text || '')) d.text = l.text; } catch (e) {} })();
