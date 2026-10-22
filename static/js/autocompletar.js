/* Autopreenchimento das caixas de busca.
 *
 * Qualquer campo com data-sugestoes="<endereço>" ganha uma lista que aparece enquanto a
 * pessoa digita. O endereço devolve JSON do próprio sistema; nada vem da internet, que o
 * servidor da loja não acessa.
 *
 * Duas regras de uso que moldaram o código:
 * - O leitor de código de barras digita tudo de uma vez e manda Enter. A lista não pode
 *   atrapalhar isso, então ela só abre com duas letras ou mais e some ao enviar.
 * - Quem está no balcão usa o teclado: setas para escolher, Enter para aceitar, Esc para
 *   fechar sem escolher nada.
 */
(function () {
  "use strict";

  var ESPERA = 180; // tempo sem digitar antes de perguntar ao servidor

  function criarLista(campo) {
    var lista = document.createElement("ul");
    lista.className = "sugestoes";
    lista.setAttribute("role", "listbox");
    lista.hidden = true;
    campo.parentNode.insertBefore(lista, campo.nextSibling);
    return lista;
  }

  function ligar(campo) {
    var endereco = campo.dataset.sugestoes;
    if (!endereco) return;
    var caixa = document.createElement("div");
    caixa.className = "campo-com-sugestoes";
    campo.parentNode.insertBefore(caixa, campo);
    caixa.appendChild(campo);
    var lista = criarLista(campo);
    var itens = [];
    var escolhido = -1;
    var relogio = null;

    campo.setAttribute("autocomplete", "off");
    campo.setAttribute("role", "combobox");
    campo.setAttribute("aria-expanded", "false");
    campo.setAttribute("aria-autocomplete", "list");

    function fechar() {
      lista.hidden = true;
      lista.innerHTML = "";
      itens = [];
      escolhido = -1;
      campo.setAttribute("aria-expanded", "false");
    }

    function marcar(indice) {
      var filhos = lista.querySelectorAll("li");
      for (var i = 0; i < filhos.length; i++) {
        filhos[i].classList.toggle("sugestao-ativa", i === indice);
        filhos[i].setAttribute("aria-selected", i === indice ? "true" : "false");
      }
      escolhido = indice;
    }

    function aceitar(indice) {
      if (indice < 0 || indice >= itens.length) return false;
      campo.value = itens[indice].descricao;
      fechar();
      return true;
    }

    function desenhar(dados) {
      itens = dados || [];
      lista.innerHTML = "";
      if (!itens.length) {
        fechar();
        return;
      }
      itens.forEach(function (item, indice) {
        var linha = document.createElement("li");
        linha.setAttribute("role", "option");
        linha.setAttribute("aria-selected", "false");
        var nome = document.createElement("span");
        nome.className = "sugestao-nome";
        nome.textContent = item.descricao;
        linha.appendChild(nome);
        // A segunda linha explica a sugestão, e o que explica depende do que se procura:
        // um produto se reconhece pelo código e pelo grupo, um fornecedor pelo quanto a
        // loja comprou dele. Quem responde o endereço manda a frase pronta em "ajuda";
        // sem ela, vale a linha de produto, que foi a primeira a existir.
        var texto = item.ajuda || ("código " + item.codigo + (item.grupo ? " · " + item.grupo : ""));
        if (texto) {
          var ajuda = document.createElement("span");
          ajuda.className = "sugestao-ajuda";
          ajuda.textContent = texto;
          linha.appendChild(ajuda);
        }
        linha.addEventListener("mousedown", function (evento) {
          evento.preventDefault();
          aceitar(indice);
          campo.form && campo.form.submit();
        });
        lista.appendChild(linha);
      });
      lista.hidden = false;
      campo.setAttribute("aria-expanded", "true");
      marcar(-1);
    }

    function perguntar() {
      var termo = campo.value.trim();
      if (termo.length < 2) {
        fechar();
        return;
      }
      fetch(endereco + "?q=" + encodeURIComponent(termo), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      })
        .then(function (resposta) {
          return resposta.ok ? resposta.json() : { itens: [] };
        })
        .then(function (dados) {
          // Enquanto a resposta vinha, a pessoa pode ter apagado tudo.
          if (campo.value.trim().length >= 2) desenhar(dados.itens);
        })
        .catch(function () {
          fechar();
        });
    }

    campo.addEventListener("input", function () {
      window.clearTimeout(relogio);
      relogio = window.setTimeout(perguntar, ESPERA);
    });

    campo.addEventListener("keydown", function (evento) {
      if (lista.hidden) return;
      if (evento.key === "ArrowDown") {
        evento.preventDefault();
        marcar(escolhido + 1 >= itens.length ? 0 : escolhido + 1);
      } else if (evento.key === "ArrowUp") {
        evento.preventDefault();
        marcar(escolhido - 1 < 0 ? itens.length - 1 : escolhido - 1);
      } else if (evento.key === "Enter") {
        if (aceitar(escolhido)) evento.preventDefault();
      } else if (evento.key === "Escape") {
        fechar();
      }
    });

    campo.addEventListener("blur", function () {
      window.setTimeout(fechar, 120);
    });
    if (campo.form) campo.form.addEventListener("submit", fechar);
  }

  var campos = document.querySelectorAll("[data-sugestoes]");
  for (var i = 0; i < campos.length; i++) ligar(campos[i]);
})();
