/* Single-select loan cards + dynamic Apply button (amount re-validated server-side) */
(function () {
  var form = document.getElementById('loan-form');
  if (!form) return;
  var hidden = document.getElementById('selected-amount');
  var btn = document.getElementById('apply-btn');
  var cards = Array.prototype.slice.call(document.querySelectorAll('.loan-card'));
  var applyHint = document.querySelector('.apply-hint');

  function fmt(n) { return 'KSH ' + Number(n).toLocaleString('en-KE'); }

  function select(card) {
    cards.forEach(function (c) {
      c.classList.remove('selected');
      c.setAttribute('aria-pressed', 'false');
      c.setAttribute('aria-checked', 'false');
    });
    card.classList.add('selected');
    card.setAttribute('aria-pressed', 'true');
    card.setAttribute('aria-checked', 'true');
    hidden.value = card.getAttribute('data-amount');
    btn.textContent = 'Apply for ' + fmt(card.getAttribute('data-amount'));
    btn.disabled = false;
    if (applyHint) applyHint.style.display = 'none';
  }

  cards.forEach(function (card) {
    card.setAttribute('tabindex', '0');
    card.setAttribute('role', 'radio');
    card.setAttribute('aria-checked', 'false');
    card.addEventListener('click', function () { select(card); });
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(card); }
    });
  });

  /* Prevent submitting with no selection */
  form.addEventListener('submit', function (e) {
    if (!hidden.value) e.preventDefault();
  });
})();