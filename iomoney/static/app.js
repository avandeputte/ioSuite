/* ioMoney web app: no build step. The modules in js/: core.js (the helpers, numbers and dates, the app's state),
   shell.js (the sidebar, the menus) and main.js (the routes and the start); charts.js (inline SVG); then a module per
   page: overview.js (the net worth, its history, the accounts by kind, the Monarch sync), account.js (one account
   with its history, transactions, holdings or values), transactions.js (to search and correct), categories.js (with
   spending by category and month), recurring.js, rules.js (with transfers), tidy.js and reconcile.js (putting the
   data in order, a bank's own file), portfolio.js (the portfolio with its quotes, the house and the cars with their
   loans) and settings.js (account, display, and for admins Money, and for suite admins the suite's panel), laid out
   as in the other ioSuite apps. */
import './js/main.js';
