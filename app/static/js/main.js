/* CSRF helper for fetch-based AJAX (token read from <meta name="csrf-token">) */
(function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  window.getCSRF = function () { return meta ? meta.getAttribute('content') : ''; };
  window.apiFetch = function (url, options) {
    options = options || {};
    options.headers = Object.assign({}, options.headers || {}, {
      'X-CSRFToken': window.getCSRF()
    });
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    options.credentials = 'same-origin';
    return fetch(url, options);
  };
})();