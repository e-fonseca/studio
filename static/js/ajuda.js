/*
 * Ajuda guiada do sistema. F1 (ou o botão Ajuda) abre um tour da própria tela:
 * destaca uma parte de cada vez e explica para que serve.
 *
 * Os passos de cada página vêm de um <script type="application/json" id="passos-ajuda">.
 * Passo sem "seletor", ou cujo elemento não está na tela, aparece como texto solto:
 * serve de abertura e de fechamento.
 *
 * Na primeira vez que a pessoa abre cada tela, o tour aparece sozinho: é a tela se
 * explicando sem ninguém precisar ensinar. Depois disso, só por F1 ou pelo botão.
 *
 * Sem dependência externa, porque o servidor da loja não acessa a internet.
 */
(function () {
  "use strict";

  var PADRAO = [
    {
      titulo: "Ajuda do sistema",
      texto: "Aperte F1 em qualquer tela para abrir esta ajuda. Ela explica o que você está vendo " +
             "na página em que estiver. Use as setas do teclado para avançar e Esc para fechar."
    },
    { seletor: ".menu", titulo: "Menu", texto: "Os módulos liberados para o seu perfil." },
    { seletor: ".usuario", titulo: "Seu usuário", texto: "Use sempre o seu. As ações ficam registradas para conferência." }
  ];

  var passos = PADRAO;
  var indice = 0;
  var aberto = false;
  var caixa, titulo, texto, contador, anterior, proximo, fechar, destacado, focoAnterior;

  function lerPassos() {
    var fonte = document.getElementById("passos-ajuda");
    if (!fonte) { return PADRAO; }
    try {
      var lidos = JSON.parse(fonte.textContent);
      return lidos && lidos.length ? lidos : PADRAO;
    } catch (e) {
      return PADRAO;
    }
  }

  function montar() {
    caixa = document.createElement("div");
    caixa.className = "ajuda-caixa";
    caixa.setAttribute("role", "dialog");
    caixa.setAttribute("aria-modal", "false");
    caixa.setAttribute("aria-labelledby", "ajuda-titulo");
    caixa.hidden = true;
    caixa.innerHTML =
      '<h2 id="ajuda-titulo"></h2>' +
      '<p id="ajuda-texto"></p>' +
      '<div class="ajuda-acoes">' +
      '  <span class="ajuda-contador" aria-live="polite"></span>' +
      '  <button type="button" class="botao secundario" data-ajuda="anterior">Voltar</button>' +
      '  <button type="button" class="botao" data-ajuda="proximo">Avançar</button>' +
      '  <button type="button" class="botao secundario" data-ajuda="fechar">Fechar (Esc)</button>' +
      "</div>";
    document.body.appendChild(caixa);
    titulo = caixa.querySelector("#ajuda-titulo");
    texto = caixa.querySelector("#ajuda-texto");
    contador = caixa.querySelector(".ajuda-contador");
    anterior = caixa.querySelector('[data-ajuda="anterior"]');
    proximo = caixa.querySelector('[data-ajuda="proximo"]');
    fechar = caixa.querySelector('[data-ajuda="fechar"]');
    anterior.addEventListener("click", function () { ir(indice - 1); });
    proximo.addEventListener("click", function () { ir(indice + 1); });
    fechar.addEventListener("click", encerrar);
  }

  function limparDestaque() {
    if (destacado) { destacado.classList.remove("ajuda-destaque"); destacado = null; }
  }

  function ir(novo) {
    if (novo < 0 || novo >= passos.length) { return; }
    indice = novo;
    var passo = passos[indice];
    limparDestaque();
    var alvo = passo.seletor ? document.querySelector(passo.seletor) : null;
    if (alvo) {
      alvo.classList.add("ajuda-destaque");
      destacado = alvo;
      alvo.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    titulo.textContent = passo.titulo || "Ajuda";
    texto.textContent = passo.texto || "";
    contador.textContent = "Passo " + (indice + 1) + " de " + passos.length;
    anterior.disabled = indice === 0;
    proximo.disabled = indice === passos.length - 1;
    (proximo.disabled ? fechar : proximo).focus();
  }

  function abrir() {
    if (aberto) { return; }
    passos = lerPassos();
    if (!caixa) { montar(); }
    focoAnterior = document.activeElement;
    caixa.hidden = false;
    document.body.classList.add("com-ajuda");
    aberto = true;
    ir(0);
  }

  function encerrar() {
    if (!aberto) { return; }
    limparDestaque();
    caixa.hidden = true;
    document.body.classList.remove("com-ajuda");
    aberto = false;
    if (focoAnterior && focoAnterior.focus) { focoAnterior.focus(); }
  }

  // Marca, no próprio navegador, as telas cujo tour já foi visto. Navegador sem
  // armazenamento (ou em janela anônima) simplesmente não abre sozinho.
  function jaViu(chave) {
    try { return window.localStorage.getItem(chave) !== null; } catch (e) { return true; }
  }

  function anotarQueViu(chave) {
    try { window.localStorage.setItem(chave, new Date().toISOString()); } catch (e) { /* sem armazenamento */ }
  }

  function abrirNaPrimeiraVisita() {
    if (!document.getElementById("passos-ajuda")) { return; }
    var chave = "cabana:tour:" + window.location.pathname;
    if (jaViu(chave)) { return; }
    anotarQueViu(chave);
    abrir();
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "F1") { e.preventDefault(); aberto ? encerrar() : abrir(); return; }
    if (!aberto) { return; }
    if (e.key === "Escape") { e.preventDefault(); encerrar(); }
    if (e.key === "ArrowRight") { ir(indice + 1); }
    if (e.key === "ArrowLeft") { ir(indice - 1); }
  });

  document.addEventListener("click", function (e) {
    var botao = e.target.closest ? e.target.closest("#abrir-ajuda") : null;
    if (botao) { e.preventDefault(); aberto ? encerrar() : abrir(); }
  });

  abrirNaPrimeiraVisita();
})();
