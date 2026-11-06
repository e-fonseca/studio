/* A faixa do topo (1.50.0): o relógio anda a cada segundo, e o dólar e as ações são
   pedidos ao PRÓPRIO sistema a cada minuto (nunca à internet: quem vai buscar lá fora é o
   servidor, em segundo plano). Esse pedido não conta como uso do sistema: a sessão parada
   continua acabando em 30 minutos, e quando acaba a tela vai sozinha para a entrada. */
(function () {
  "use strict";
  var faixa = document.getElementById("cotacao-faixa");
  if (!faixa) { return; }
  var relogio = document.getElementById("cotacao-relogio");
  var conteudo = document.getElementById("cotacao-conteudo");
  var endereco = faixa.getAttribute("data-endereco");
  var entrar = faixa.getAttribute("data-entrar");
  var lugar = { timeZone: "America/Sao_Paulo" };
  function formato(extra) {
    var opcoes = { timeZone: lugar.timeZone };
    for (var chave in extra) { opcoes[chave] = extra[chave]; }
    return new Intl.DateTimeFormat("pt-BR", opcoes);
  }
  var dia = formato({ weekday: "short" });
  var data = formato({ day: "2-digit", month: "2-digit", year: "numeric" });
  var hora = formato({ hour: "2-digit", minute: "2-digit", second: "2-digit" });

  function andarRelogio() {
    var agora = new Date();
    relogio.textContent = dia.format(agora).replace(".", "") + ", " + data.format(agora) +
      " · " + hora.format(agora);
    relogio.setAttribute("datetime", agora.toISOString());
  }

  function emendar() {
    // O rolo leva o trecho duas vezes: quando a primeira volta acaba, a segunda está no
    // mesmo lugar e a emenda não aparece. A cópia é só enfeite para quem lê a tela.
    var rolo = conteudo.querySelector(".cotacao-rolo");
    if (!rolo) { return; }
    var trecho = rolo.querySelector(".cotacao-trecho");
    var copia = trecho.cloneNode(true);
    copia.setAttribute("aria-hidden", "true");
    rolo.appendChild(copia);
    rolo.style.setProperty("--cotacao-duracao", Math.max(20, Math.round(trecho.scrollWidth / 40)) + "s");
    rolo.classList.add("cotacao-rolando");
  }

  function buscar() {
    if (document.visibilityState === "hidden") { return; }
    fetch(endereco, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (resposta) {
        if (resposta.status === 401 || resposta.redirected) {
          window.location.href = entrar;
          return null;
        }
        return resposta.ok ? resposta.json() : null;
      })
      .then(function (dados) {
        if (!dados || typeof dados.html !== "string") { return; }
        conteudo.innerHTML = dados.html;
        emendar();
      })
      .catch(function () { /* sem resposta, fica o que estava na tela */ });
  }

  andarRelogio();
  window.setInterval(andarRelogio, 1000);
  // Sem endereço é a faixa de quem não vê número da loja: só o relógio.
  if (!endereco) { return; }
  emendar();
  window.setInterval(buscar, 60000);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") { buscar(); }
  });
})();
