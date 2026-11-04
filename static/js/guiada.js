/*
 * Compra guiada (1.45.0): o que a tela faz na hora, sem esperar o servidor.
 *
 * A tela funciona inteira sem este arquivo: cada resposta vai ao servidor no "Continuar"
 * e volta com a conta feita lá (apps/compras/guiada.py). Aqui só mora o conforto:
 *   - o cartão da resposta escolhida fica aceso (para navegador sem :has());
 *   - escrever no campo de "Outro" já marca a opção dele;
 *   - as teclas 1 a 9 escolhem a resposta pelo número que aparece no cartão;
 *   - os tipos marcados somam na hora quantos produtos cada "o que entra" dá;
 *   - a quantidade digitada mostra quanto custa e quanto tempo dura;
 *   - na conferência, o total, os produtos e as unidades acompanham o que se digita.
 *
 * As contas daqui repetem as do Python (valor ao centavo, a mesma frase de duração de
 * apps/compras/lista_de_compra.duracao). O número que vale é o do servidor: ao salvar,
 * a tela volta com ele.
 */
(function () {
  "use strict";

  function numero(texto) {
    var limpo = String(texto || "").replace(/\s/g, "");
    if (!limpo) { return null; }
    if (limpo.indexOf(",") >= 0) { limpo = limpo.replace(/\./g, "").replace(",", "."); }
    if (!/^\d*\.?\d*$/.test(limpo)) { return NaN; }
    var valor = parseFloat(limpo);
    return isNaN(valor) ? NaN : valor;
  }

  function reais(valor) {
    var centavos = Math.round(valor * 100);
    var inteiro = Math.floor(centavos / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    var resto = ("0" + (centavos % 100)).slice(-2);
    return "R$ " + inteiro + "," + resto;
  }

  function quantidade(valor) {
    var texto = (Math.round(valor * 1000) / 1000).toString();
    return texto.replace(".", ",");
  }

  // round() do Python arredonda o meio para o par: 4,5 meses vira 4, e não 5.
  function arredondarComoPython(x) {
    var baixo = Math.floor(x), parte = x - baixo;
    if (parte > 0.5) { return baixo + 1; }
    if (parte < 0.5) { return baixo; }
    return baixo % 2 === 0 ? baixo : baixo + 1;
  }

  function duracao(dias) {
    if (dias === null) { return ""; }
    if (dias < 90) { return dias + (dias === 1 ? " dia" : " dias"); }
    if (dias < 730) {
      var meses = arredondarComoPython(dias / 30);
      return meses + (meses === 1 ? " mês" : " meses");
    }
    return (dias / 365).toFixed(1).replace(".", ",").replace(/,0$/, "") + " anos";
  }

  function diasQueCobre(unidades, porDia) {
    if (!porDia || porDia <= 0) { return null; }
    return Math.floor(unidades / porDia);
  }

  // ------------------------------------------------------------ a opção escolhida
  function acender(grupo) {
    if (!grupo) { return; }
    grupo.querySelectorAll(".guiada-opcao").forEach(function (cartao) {
      var campo = cartao.querySelector("input[type=radio], input[type=checkbox]");
      cartao.classList.toggle("marcada", !!(campo && campo.checked));
    });
  }

  document.querySelectorAll(".guiada-opcoes").forEach(acender);
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches(".guiada-opcao input")) {
      acender(e.target.closest(".guiada-opcoes"));
      if (e.target.closest("[data-tipos]")) { somarTipos(); }
    }
  });

  // Escrever no campo do "Outro" é escolher o "Outro".
  function marcarAOpcaoDoCampo(campo) {
    var cartao = campo.closest(".guiada-opcao");
    var bolinha = cartao && cartao.querySelector("input[type=radio]");
    if (bolinha && !bolinha.checked) {
      bolinha.checked = true;
      acender(cartao.closest(".guiada-opcoes"));
    }
  }
  document.addEventListener("focusin", function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute("data-marca-a-opcao")) { marcarAOpcaoDoCampo(e.target); }
  });

  // ------------------------------------------------------------ as teclas 1 a 9
  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || !/^[1-9]$/.test(e.key)) { return; }
    var ativo = document.activeElement;
    if (ativo && (/^(INPUT|TEXTAREA|SELECT)$/.test(ativo.tagName) && ativo.type !== "radio" && ativo.type !== "checkbox")) { return; }
    if (document.body.classList.contains("com-ajuda")) { return; }
    var formulario = document.getElementById("guiada-respostas") || document.getElementById("guiada-comecar");
    if (!formulario) { return; }
    var primeira = formulario.querySelector(".guiada-opcao input[type=radio]");
    if (!primeira) { return; }
    var mesmas = formulario.querySelectorAll('.guiada-opcao input[type=radio][name="' + primeira.name + '"]');
    var escolhida = mesmas[parseInt(e.key, 10) - 1];
    if (!escolhida || escolhida.disabled) { return; }
    e.preventDefault();
    escolhida.checked = true;
    acender(escolhida.closest(".guiada-opcoes"));
    var campo = escolhida.closest(".guiada-opcao").querySelector("[data-marca-a-opcao]");
    (campo || escolhida).focus();
  });

  // ------------------------------------------------------------ os tipos de produto
  function somarTipos() {
    var caixas = document.querySelectorAll("[data-tipos] input[type=checkbox]");
    if (!caixas.length) { return; }
    var soma = { tudo: 0, faltando: 0, carro_chefe: 0 };
    caixas.forEach(function (caixa) {
      if (!caixa.checked) { return; }
      Object.keys(soma).forEach(function (chave) {
        soma[chave] += parseInt(caixa.getAttribute("data-" + chave) || "0", 10);
      });
    });
    Object.keys(soma).forEach(function (chave) {
      var alvo = document.querySelector('[data-conta-entra="' + chave + '"]');
      if (alvo) { alvo.textContent = soma[chave] + (soma[chave] === 1 ? " produto" : " produtos"); }
    });
  }

  // ------------------------------------------------------------ "Outra quantidade"
  document.querySelectorAll("input[name=quantidade_outro]").forEach(function (campo) {
    var saida = campo.parentNode.querySelector("[data-conta-viva]");
    function mostrar() {
      var valor = numero(campo.value);
      if (!saida) { return; }
      if (valor === null || isNaN(valor)) { saida.textContent = ""; return; }
      var custo = numero(campo.getAttribute("data-custo"));
      var porDia = numero(campo.getAttribute("data-por-dia"));
      var partes = [];
      if (custo !== null && !isNaN(custo)) { partes.push(reais(valor * custo)); }
      var dura = duracao(diasQueCobre(valor, porDia));
      if (dura) { partes.push("dura " + dura); }
      saida.textContent = partes.join(" · ");
    }
    campo.addEventListener("input", mostrar);
    mostrar();
  });

  // ------------------------------------------------------------ a conferência
  var campos = document.querySelectorAll("[data-quantidade]");
  function eraDe(campo) {
    var irmao = campo.form && campo.form.elements["era-" + campo.name.slice(2)];
    return irmao ? irmao.value : campo.defaultValue;
  }
  function refazerTotais() {
    var total = 0, produtos = 0, unidades = 0, mudou = false;
    campos.forEach(function (campo) {
      var linha = campo.closest("[data-linha]");
      var valor = numero(campo.value);
      var custo = numero(campo.getAttribute("data-custo"));
      var porDia = numero(campo.getAttribute("data-por-dia"));
      var valido = valor !== null && !isNaN(valor);
      var unidadesDaLinha = valido ? valor : 0;
      var valorDaLinha = (custo !== null && !isNaN(custo)) ? Math.round(unidadesDaLinha * custo * 100) / 100 : 0;
      if (unidadesDaLinha > 0) { produtos += 1; unidades += unidadesDaLinha; total += valorDaLinha; }
      var celulaTotal = linha && linha.querySelector("[data-total-da-linha]");
      if (celulaTotal) { celulaTotal.textContent = reais(valorDaLinha); }
      var celulaDura = linha && linha.querySelector("[data-dura]");
      if (celulaDura) { celulaDura.textContent = duracao(diasQueCobre(unidadesDaLinha, porDia)) || "—"; }
      var diferente = numero(eraDe(campo)) !== (valido ? valor : null);
      if (linha) { linha.classList.toggle("guiada-mudou", diferente); }
      campo.setAttribute("aria-invalid", valido || valor === null ? "false" : "true");
      mudou = mudou || diferente;
    });
    document.querySelectorAll("[data-total-do-pedido]").forEach(function (el) { el.textContent = reais(total); });
    document.querySelectorAll("[data-produtos-do-pedido]").forEach(function (el) { el.textContent = produtos; });
    document.querySelectorAll("[data-unidades-do-pedido]").forEach(function (el) { el.textContent = quantidade(unidades); });
    var aviso = document.querySelector("[data-aviso-folha]");
    if (aviso) { aviso.hidden = !mudou; }
  }
  if (campos.length) {
    campos.forEach(function (campo, i) {
      campo.addEventListener("input", refazerTotais);
      // Enter desce para a quantidade de baixo, como numa planilha. Sem isto, o Enter
      // mandaria o formulário pelo primeiro botão dele (que só salva, mas tira a pessoa
      // do lugar em que estava na tabela).
      campo.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" || e.isComposing) { return; }
        e.preventDefault();
        // A linha escondida pela procura (1.47.0) é pulada: foco nela não vai a lugar nenhum.
        var proximo = null;
        for (var j = i + 1; j < campos.length && !proximo; j += 1) {
          var linhaDele = campos[j].closest("[data-linha]");
          if (!linhaDele || !linhaDele.hidden) { proximo = campos[j]; }
        }
        if (proximo) { proximo.focus(); proximo.select(); } else { campo.blur(); }
      });
    });
    // A conferência de um fornecedor grande tem centenas de linhas e dois campos por linha.
    // Só vai ao servidor o que a pessoa mudou: o resto continua seguindo a conta de lá.
    var formulario = campos[0].form;
    formulario.addEventListener("submit", function () {
      campos.forEach(function (campo) {
        if (numero(campo.value) === numero(eraDe(campo))) {
          campo.disabled = true;
          var irmao = formulario.elements["era-" + campo.name.slice(2)];
          if (irmao) { irmao.disabled = true; }
        }
      });
    });
    // Voltar pelo navegador devolve a página como ela estava ao sair, com os campos travados.
    window.addEventListener("pageshow", function () {
      formulario.querySelectorAll("input:disabled").forEach(function (campo) { campo.disabled = false; });
    });
  }

  // ------------------------------------------------------------ procurar nos outros
  // Fornecedor grande tem centenas de produtos na tabela dos outros (1.47.0). O campo
  // esconde as linhas que não têm o que se digitou, sem ir ao servidor; a quantidade já
  // escrita numa linha escondida continua no formulário. Sem acento dos dois lados:
  // "ceramica" acha CERÂMICA.
  var procurar = document.querySelector("[data-procurar-outros]");
  if (procurar) {
    var campoProcura = procurar.querySelector("input");
    var contaProcura = procurar.querySelector("[data-procurar-conta]");
    var outras = Array.prototype.slice.call(document.querySelectorAll("[data-tabela-outros] tbody tr"));
    var semAcento = function (texto) {
      return String(texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    };
    var textos = outras.map(function (linha) { return semAcento(linha.getAttribute("data-procura")); });
    procurar.hidden = false;
    campoProcura.addEventListener("input", function () {
      var termo = semAcento(campoProcura.value).trim();
      var vistas = 0;
      outras.forEach(function (linha, i) {
        var mostra = !termo || textos[i].indexOf(termo) >= 0;
        linha.hidden = !mostra;
        if (mostra) { vistas += 1; }
      });
      contaProcura.textContent = termo ? (vistas + " de " + outras.length) : "";
    });
    // Enter aqui é "procurar", e não "salvar": o formulário inteiro está em volta.
    campoProcura.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); }
    });
  }
})();
