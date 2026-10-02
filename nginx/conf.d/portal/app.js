/* Portal BJJ Vetusta · Asturkon — JS minimo, sin dependencias.
 *
 * Unica funcion: reflejar el estado ESTATICO declarado en status.json sobre las
 * etiquetas ya escritas en el HTML. No consulta ninguna API interna, no expone
 * estado del torneo en vivo y no crea enlaces: si status.json no esta disponible
 * (o el navegador no tiene red), la pagina se queda tal cual esta en el HTML.
 */
(function () {
  "use strict";

  var ETIQUETAS = { disponible: "Disponible", proximamente: "Próximamente" };

  function pintar(card, estado) {
    if (!estado || !ETIQUETAS[estado]) return;
    var chip = card.querySelector(".estado");
    if (chip) {
      chip.setAttribute("data-estado", estado);
      chip.textContent = ETIQUETAS[estado];
    }
  }

  function aplicar(cfg) {
    if (!cfg) return;
    var tatamis = cfg.tatamis || {};
    Object.keys(tatamis).forEach(function (n) {
      var card = document.querySelector('[data-tatami="' + n + '"]');
      if (card) pintar(card, tatamis[n].estado);
    });
    var apps = cfg.apps || {};
    Object.keys(apps).forEach(function (nombre) {
      var card = document.querySelector('[data-app="' + nombre + '"]');
      if (card) pintar(card, apps[nombre].estado);
    });
  }

  if (typeof fetch !== "function") return;
  fetch("status.json", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(aplicar)
    .catch(function () { /* sin red: el HTML ya muestra el estado correcto */ });
})();
