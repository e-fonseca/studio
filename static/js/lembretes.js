/*
 * Lembretes do dia: aparecem uma vez por dia, no primeiro acesso, e somem no botão.
 * A marca de "já vi hoje" fica no próprio navegador; sem armazenamento, o aviso
 * simplesmente não abre, para não atrapalhar quem usa o sistema o dia inteiro.
 */
(function () {
  "use strict";

  var caixa = document.getElementById("lembretes-do-dia");
  if (!caixa) { return; }

  var hoje = new Date().toISOString().slice(0, 10);
  var chave = "cabana:lembretes:" + hoje;

  function jaViuHoje() {
    try { return window.localStorage.getItem(chave) !== null; } catch (e) { return true; }
  }

  function anotar() {
    try { window.localStorage.setItem(chave, "1"); } catch (e) { /* sem armazenamento */ }
  }

  function fechar() {
    caixa.hidden = true;
    anotar();
  }

  if (!jaViuHoje()) {
    caixa.hidden = false;
    var botao = caixa.querySelector("[data-fechar-lembretes]");
    if (botao) { botao.focus(); }
  }

  caixa.addEventListener("click", function (e) {
    if (e.target.closest("[data-fechar-lembretes]") || e.target === caixa) { fechar(); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !caixa.hidden) { fechar(); }
  });
})();
