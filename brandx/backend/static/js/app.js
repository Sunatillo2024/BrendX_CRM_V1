/* BrandX SSR UI runtime: theme, sidebar, profile menu, i18n, toasts, confirm.
   Vanilla JS only. No framework, no build step. */
(function () {
  'use strict';

  var STORAGE = {
    theme: 'brandx_theme',
    sidebar: 'brandx_sidebar',
    lang: 'brandx_lang',
  };

  var dict = window.BRANDX_TRANSLATIONS || { uz: {}, ru: {} };

  var BrandX = {
    lang: (document.documentElement.getAttribute('lang') || 'uz'),

    t: function (key) {
      var table = dict[BrandX.lang] || dict.uz || {};
      return table[key] != null ? table[key] : (dict.uz && dict.uz[key]) != null ? dict.uz[key] : key;
    },

    applyTranslations: function (root) {
      root = root || document;
      root.querySelectorAll('[data-i18n]').forEach(function (el) {
        el.textContent = BrandX.t(el.getAttribute('data-i18n'));
      });
      root.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
        el.setAttribute('placeholder', BrandX.t(el.getAttribute('data-i18n-placeholder')));
      });
      root.querySelectorAll('[data-i18n-title]').forEach(function (el) {
        el.setAttribute('title', BrandX.t(el.getAttribute('data-i18n-title')));
      });
    },

    /* ── Theme ─────────────────────────────────────────────────── */
    themeMode: function () { return localStorage.getItem(STORAGE.theme) || 'system'; },
    resolvedTheme: function () {
      var mode = BrandX.themeMode();
      if (mode === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      return mode;
    },
    setTheme: function (mode) {
      localStorage.setItem(STORAGE.theme, mode);
      BrandX.applyTheme();
    },
    applyTheme: function () {
      document.documentElement.setAttribute('data-theme', BrandX.resolvedTheme());
      document.querySelectorAll('[data-theme-opt]').forEach(function (btn) {
        btn.classList.toggle('active', btn.getAttribute('data-theme-opt') === BrandX.themeMode());
      });
      var icon = document.querySelector('[data-theme-icon]');
      if (icon) icon.textContent = BrandX.resolvedTheme() === 'dark' ? 'light_mode' : 'dark_mode';
    },
    toggleTheme: function () {
      BrandX.setTheme(BrandX.resolvedTheme() === 'dark' ? 'light' : 'dark');
    },

    /* ── Toast ─────────────────────────────────────────────────── */
    toast: function (msg, type) {
      var host = document.querySelector('.toast-host');
      if (!host) return;
      type = type || 'info';
      var icons = { success: 'check_circle', error: 'error', warn: 'warning', info: 'info' };
      var el = document.createElement('div');
      el.className = 'toast ' + type;
      el.innerHTML = '<span class="material-icons-round lead">' + (icons[type] || 'info') + '</span>' +
        '<span class="toast-msg"></span>';
      el.querySelector('.toast-msg').textContent = msg;
      host.appendChild(el);
      setTimeout(function () {
        el.style.transition = 'opacity .2s'; el.style.opacity = '0';
        setTimeout(function () { el.remove(); }, 220);
      }, 3000);
    },

    /* ── Confirm (for data-confirm forms/links) ────────────────── */
    confirm: function (message, onOk) {
      var wrap = document.createElement('div');
      wrap.className = 'modal-backdrop';
      wrap.innerHTML =
        '<div class="modal">' +
        '<div class="modal-head"><h3></h3></div>' +
        '<div class="modal-body"><p class="muted"></p></div>' +
        '<div class="modal-foot">' +
        '<button class="btn" data-cancel></button>' +
        '<button class="btn danger" data-ok></button>' +
        '</div></div>';
      wrap.querySelector('h3').textContent = BrandX.t('common.confirm');
      wrap.querySelector('p').textContent = message;
      wrap.querySelector('[data-cancel]').textContent = BrandX.t('common.cancel');
      wrap.querySelector('[data-ok]').textContent = BrandX.t('common.confirm');
      function close() { wrap.remove(); }
      wrap.querySelector('[data-cancel]').onclick = close;
      wrap.querySelector('[data-ok]').onclick = function () { close(); onOk(); };
      wrap.addEventListener('click', function (e) { if (e.target === wrap) close(); });
      document.body.appendChild(wrap);
    },
  };

  window.BrandX = BrandX;

  document.addEventListener('DOMContentLoaded', function () {
    BrandX.applyTheme();
    BrandX.applyTranslations();

    /* Sidebar */
    var shell = document.querySelector('.app-shell');
    if (shell && localStorage.getItem(STORAGE.sidebar) === 'collapsed') {
      shell.classList.add('collapsed');
    }
    var collapseBtn = document.querySelector('[data-collapse]');
    if (collapseBtn) {
      collapseBtn.addEventListener('click', function () {
        if (window.innerWidth <= 820) {
          document.querySelector('.sidebar') &&
            document.querySelector('.sidebar').classList.toggle('mobile-open');
          var ov = document.querySelector('.overlay');
          if (ov) ov.style.display = ov.style.display === 'block' ? 'none' : 'block';
        } else {
          shell.classList.toggle('collapsed');
          localStorage.setItem(STORAGE.sidebar, shell.classList.contains('collapsed') ? 'collapsed' : 'expanded');
        }
      });
    }
    var overlay = document.querySelector('.overlay');
    if (overlay) overlay.addEventListener('click', function () {
      document.querySelector('.sidebar').classList.remove('mobile-open');
      overlay.style.display = 'none';
    });

    /* Theme buttons */
    document.querySelectorAll('[data-theme-toggle]').forEach(function (b) {
      b.addEventListener('click', BrandX.toggleTheme);
    });
    document.querySelectorAll('[data-theme-opt]').forEach(function (b) {
      b.addEventListener('click', function () { BrandX.setTheme(b.getAttribute('data-theme-opt')); });
    });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (BrandX.themeMode() === 'system') BrandX.applyTheme();
    });

    /* Profile dropdown */
    var profileBtn = document.querySelector('[data-profile-toggle]');
    var profileMenu = document.querySelector('[data-profile-menu]');
    if (profileBtn && profileMenu) {
      profileBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        profileMenu.hidden = !profileMenu.hidden;
      });
      document.addEventListener('click', function () { profileMenu.hidden = true; });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') profileMenu.hidden = true;
      });
    }

    /* Generic confirm handlers */
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        var msg = el.getAttribute('data-confirm');
        var form = el.closest('form');
        var href = el.getAttribute('href');
        e.preventDefault();
        BrandX.confirm(msg, function () {
          if (form) form.submit();
          else if (href) window.location.href = href;
        });
      });
    });

    /* Auto-dismiss Django messages already rendered server-side */
    document.querySelectorAll('.toast[data-autohide]').forEach(function (el) {
      setTimeout(function () {
        el.style.transition = 'opacity .2s'; el.style.opacity = '0';
        setTimeout(function () { el.remove(); }, 220);
      }, 3200);
    });
  });
})();
