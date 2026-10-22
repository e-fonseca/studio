/*
 * Leitura de código de barras e QR pela câmera do celular (contagem de inventário),
 * mais a foto da prateleira.
 *
 * Em 21/10/2026 o Edson testou num Samsung S24 FE e a câmera **não leu uma etiqueta
 * sequer**: *"precisa ajustar melhor para fazer a leitura rápida para fazer sentido o
 * módulo"*. A causa foi medida, não adivinhada, com a câmera de mentira do Chromium
 * mostrando a etiqueta real da loja (VASO GARRAFA M JUNCO, 0000000047463), e a ordem
 * aqui é a do efeito medido:
 *
 *  1. **A RESOLUÇÃO. Era esta.** O pedido era `width: { ideal: 1280 }`, e um EAN-13 tem
 *     95 barras: a etiqueta da prateleira vista de um palmo ocupava cerca de 320 pixels
 *     a 1280, pouco mais de três pixels por barra, abaixo do que qualquer leitor
 *     decifra. Mudando SÓ esta linha para 1920, a mesma cena que não era lida em 15
 *     segundos passou a ser lida em 0,0 s. Tudo o que vem abaixo some perto disto.
 *  2. **Duas tentativas por segundo.** O `decodeFromVideoElementContinuously` espera
 *     500 ms entre uma tentativa e outra. Mão tremendo na prateleira, isso é quase
 *     nenhuma chance de pegar o quadro em que a imagem ficou nítida. Agora o laço é
 *     nosso e roda a cada quadro.
 *  3. **O leitor do próprio Android estava desligado.** Esta tela usava só a biblioteca
 *     ZXing, escolhida porque o Safari do iPhone não tem `BarcodeDetector`. Só que o
 *     Chrome do Android TEM, e o dele é o leitor do Google, melhor em etiqueta pequena,
 *     longe e com pouca luz. "Os dois leem igual" não vale nada quando nenhum dos dois
 *     lê. Agora: o do navegador quando existe, ZXing quando não. Quanto isso melhora no
 *     aparelho dele não dá para medir aqui — o Chromium sem tela não tem
 *     `BarcodeDetector` —, então está escrito na tela qual dos dois está lendo.
 *  4. **Lia o quadro inteiro.** A faixa branca ("Mire a etiqueta") era decoração: o
 *     leitor olhava a imagem toda. Agora a faixa é de verdade. Não é resolução — o
 *     recorte sai dos pixels que a câmera já deu —, é tempo e pontaria: menos pixels
 *     por quadro, mais quadros por segundo, e as linhas que o leitor varre caem todas
 *     onde a pessoa está mirando.
 *  5. **Faltavam lanterna e aproximar.** As etiquetas da loja são pequenas, em peça
 *     escura, muitas vezes no chão ou no alto. Aproximar é o que resolve a etiqueta
 *     distante, que nem a 1920 é lida. Os dois botões só aparecem quando o aparelho tem
 *     o recurso.
 *
 * O que continua sem leitura, e é honesto dizer: etiqueta ocupando menos de um sexto da
 * largura do quadro. Daí o recado na tela mandando encostar, e o botão Aproximar.
 *
 * Duas coisas ainda podem faltar, e cada uma tem o seu recado na tela:
 *  - endereço sem https: o navegador não libera a câmera, nem pede permissão;
 *  - permissão negada pela pessoa.
 * Nos dois casos a digitação do código à mão continua funcionando, que é o caminho
 * que nunca falha. Registrar é por fetch, sem recarregar: recarregar desliga a câmera.
 *
 * Detalhe que custou caro descobrir: um EAN-13 que começa com zero volta do leitor
 * como UPC-A de 12 dígitos, sem o zero. Todos os códigos que o SET gerou para a loja
 * começam com zero, então quem procura o produto no servidor tenta as duas formas
 * (apps/core/barras.py, função variantes).
 */
(function () {
  "use strict";

  var formulario = document.getElementById("formulario-camera");
  if (!formulario) { return; }

  var campoProduto = document.getElementById("produto");
  var campoQuantidade = document.getElementById("quantidade");
  var video = document.getElementById("camera-video");
  var area = document.getElementById("area-camera");
  var recado = document.getElementById("camera-recado");
  var botaoParar = document.getElementById("camera-parar");
  var botaoFoto = document.getElementById("camera-foto");
  // Marcar a peça que acabou de ser lida. Nascem escondidos: só existem depois de haver
  // uma peça registrada em que prender a marca.
  var botaoSemEtiqueta = document.getElementById("camera-sem-etiqueta");
  var botaoDanificada = document.getElementById("camera-danificada");
  var botaoLanterna = document.getElementById("camera-lanterna");
  var botaoAproximar = document.getElementById("camera-aproximar");
  var qualLeitor = document.getElementById("camera-qual-leitor");
  var lista = document.getElementById("lista-leituras");

  var ESPERA_MESMO_CODIGO = 2500;  // ms: a câmera lê a mesma etiqueta muitas vezes por segundo
  // A faixa que a tela desenha e que o leitor analisa, em fração do que aparece no
  // visor. Os mesmos quatro números estão no .camera-alvo do sistema.css: se um mudar,
  // o outro muda junto, senão a faixa volta a ser decoração e a pessoa mira num lugar
  // em que o sistema não está olhando.
  var ALVO = { esquerda: 0.04, topo: 0.26, largura: 0.92, altura: 0.48 };
  // Formatos que a loja usa. Lista fechada de propósito: formato a mais é leitura
  // errada a mais, e aqui número errado vira contagem errada de estoque.
  var FORMATOS_NAVEGADOR = ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "qr_code"];

  var ultimoCodigo = "";
  var ultimaHora = 0;
  var fluxo = null;
  var trilha = null;
  var lendo = false;
  var decodificar = null;   // função(tela) -> código ou "", conforme o leitor escolhido
  var tela = null;          // canvas do recorte, criado uma vez só
  var pincel = null;
  var aproximado = false;

  function mostrar(id) {
    var bloco = document.getElementById(id);
    if (bloco) { bloco.hidden = false; }
  }

  function avisar(texto, ruim) {
    if (!recado) { return; }
    recado.textContent = texto;
    recado.classList.toggle("camera-recado-ruim", !!ruim);
  }

  function pararCamera() {
    lendo = false;
    if (fluxo) {
      fluxo.getTracks().forEach(function (t) { t.stop(); });
      fluxo = null;
      trilha = null;
    }
    if (area) { area.hidden = true; }
  }

  function aoLer(codigo) {
    if (!codigo) { return; }
    var agora = Date.now();
    if (codigo === ultimoCodigo && agora - ultimaHora < ESPERA_MESMO_CODIGO) { return; }
    ultimoCodigo = codigo;
    ultimaHora = agora;
    campoProduto.value = codigo;
    avisar("Código " + codigo + " lido. Confira as unidades e registre.", false);
    if (navigator.vibrate) { navigator.vibrate(60); }
    if (campoQuantidade) { campoQuantidade.focus(); campoQuantidade.select(); }
  }

  /* O pedaço do vídeo que está dentro da faixa branca, em pixels DA CÂMERA.
   *
   * Não dá para usar a porcentagem direto: a moldura é 4/3, o vídeo costuma ser 16/9 e
   * o `object-fit: cover` do CSS corta as laterais. Quem ignora isso recorta ao lado do
   * que a pessoa está mirando — e o defeito é invisível, porque a imagem continua
   * bonita na tela. */
  function recorteDoAlvo() {
    var larguraVideo = video.videoWidth, alturaVideo = video.videoHeight;
    var larguraTela = video.clientWidth, alturaTela = video.clientHeight;
    if (!larguraVideo || !alturaVideo || !larguraTela || !alturaTela) { return null; }
    var escala = Math.max(larguraTela / larguraVideo, alturaTela / alturaVideo);
    var visivelL = larguraTela / escala, visivelA = alturaTela / escala;
    var sobraL = (larguraVideo - visivelL) / 2, sobraA = (alturaVideo - visivelA) / 2;
    return {
      x: Math.round(sobraL + visivelL * ALVO.esquerda),
      y: Math.round(sobraA + visivelA * ALVO.topo),
      largura: Math.max(1, Math.round(visivelL * ALVO.largura)),
      altura: Math.max(1, Math.round(visivelA * ALVO.altura))
    };
  }

  function desenharORecorte() {
    var corte = recorteDoAlvo();
    if (!corte) { return null; }
    if (!tela) {
      tela = document.createElement("canvas");
      try {
        pincel = tela.getContext("2d", { willReadFrequently: true });
      } catch (e) {
        pincel = tela.getContext("2d");
      }
    }
    if (tela.width !== corte.largura || tela.height !== corte.altura) {
      tela.width = corte.largura;
      tela.height = corte.altura;
    }
    // Sem encolher: cada barra chega ao leitor com os pixels que a câmera capturou, e é
    // a largura da barra em pixels que decide se um EAN-13 é legível ou não.
    pincel.drawImage(video, corte.x, corte.y, corte.largura, corte.altura,
                     0, 0, corte.largura, corte.altura);
    return tela;
  }

  /* ---- Os dois leitores ---------------------------------------------------- */

  function leitorDoNavegador() {
    if (typeof window.BarcodeDetector === "undefined") { return Promise.resolve(null); }
    var suportados = window.BarcodeDetector.getSupportedFormats
      ? window.BarcodeDetector.getSupportedFormats()
      : Promise.resolve(FORMATOS_NAVEGADOR);
    return suportados.then(function (tem) {
      var usar = FORMATOS_NAVEGADOR.filter(function (f) { return tem.indexOf(f) !== -1; });
      // Sem EAN-13 o leitor do navegador não serve para esta loja: toda etiqueta do SET
      // é EAN-13. Melhor cair na biblioteca do que ficar com um leitor meio cego.
      if (usar.indexOf("ean_13") === -1) { return null; }
      var motor = new window.BarcodeDetector({ formats: usar });
      return function (imagem) {
        return motor.detect(imagem).then(function (achados) {
          return achados && achados.length ? String(achados[0].rawValue || "").trim() : "";
        }).catch(function () { return ""; });
      };
    }).catch(function () { return null; });
  }

  function leitorDaBiblioteca() {
    if (typeof window.ZXing === "undefined") { return null; }
    var ajustes = new Map();
    ajustes.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
      ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8,
      ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E,
      ZXing.BarcodeFormat.CODE_128, ZXing.BarcodeFormat.CODE_39,
      ZXing.BarcodeFormat.QR_CODE
    ]);
    // TRY_HARDER faz o ZXing varrer mais linhas e tentar a linha ao contrário. Custa
    // alguns milissegundos por quadro e é a diferença entre ler de primeira e a pessoa
    // ficar balançando o aparelho na frente da etiqueta.
    ajustes.set(ZXing.DecodeHintType.TRY_HARDER, true);
    var motor = new ZXing.MultiFormatReader();
    return function (imagem) {
      var codigo = "";
      try {
        var fonte = new ZXing.HTMLCanvasElementLuminanceSource(imagem);
        var mapa = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(fonte));
        var achado = motor.decode(mapa, ajustes);
        codigo = achado ? String(achado.getText() || "").trim() : "";
      } catch (e) {
        codigo = "";  // quadro sem código é o caso normal, não é erro
      } finally {
        try { motor.reset(); } catch (e) { /* nem toda versão tem */ }
      }
      return Promise.resolve(codigo);
    };
  }

  function escolherLeitor() {
    return leitorDoNavegador().then(function (doNavegador) {
      if (doNavegador) {
        if (qualLeitor) { qualLeitor.textContent = "Lendo com o leitor do próprio aparelho."; }
        return doNavegador;
      }
      var daBiblioteca = leitorDaBiblioteca();
      if (daBiblioteca && qualLeitor) {
        qualLeitor.textContent = "Lendo com o leitor do sistema.";
      }
      return daBiblioteca;
    });
  }

  /* ---- O laço de leitura --------------------------------------------------- */

  function procurar() {
    if (!lendo) { return; }
    if (video.readyState < 2) { requestAnimationFrame(procurar); return; }
    var imagem = desenharORecorte();
    if (!imagem) { requestAnimationFrame(procurar); return; }
    // Um quadro de cada vez: o próximo só é pedido quando este responde. Enfileirar
    // quadros numa promessa que ainda não voltou trava o aparelho e atrasa justamente a
    // leitura que se quer rápida.
    decodificar(imagem).then(function (codigo) {
      if (codigo) { aoLer(codigo); }
      if (lendo) { requestAnimationFrame(procurar); }
    });
  }

  /* ---- Lanterna e aproximar ------------------------------------------------ */

  function prepararControles() {
    if (!trilha || !trilha.getCapabilities) { return; }
    var pode;
    try { pode = trilha.getCapabilities(); } catch (e) { return; }
    // Etiqueta pequena numa peça escura, no chão ou no alto da prateleira: a lanterna é
    // o que faz a diferença entre ler e não ler, e nenhuma luz da loja resolve isso.
    if (pode.torch && botaoLanterna) { botaoLanterna.hidden = false; }
    // Quem está contando fica de pé, a um braço da prateleira, e a etiqueta ocupa um
    // dedo da tela. Aproximar pela câmera dobra a largura das barras em pixels sem
    // ninguém precisar se abaixar.
    if (pode.zoom && pode.zoom.max > pode.zoom.min && botaoAproximar) {
      botaoAproximar.hidden = false;
    }
  }

  function alternarLanterna() {
    if (!trilha) { return; }
    var ligada = botaoLanterna.getAttribute("aria-pressed") === "true";
    trilha.applyConstraints({ advanced: [{ torch: !ligada }] }).then(function () {
      botaoLanterna.setAttribute("aria-pressed", String(!ligada));
      botaoLanterna.textContent = ligada ? "Acender a lanterna" : "Apagar a lanterna";
    }).catch(function () {
      avisar("Este aparelho não deixa o navegador acender a lanterna.", true);
      botaoLanterna.hidden = true;
    });
  }

  function alternarAproximar() {
    if (!trilha) { return; }
    var pode = trilha.getCapabilities();
    // Duas vezes, não o máximo: no máximo o aparelho perde o foco de perto e a imagem
    // vira um borrão, que é pior do que longe e nítido.
    var alvo = aproximado ? pode.zoom.min : Math.min(pode.zoom.max, (pode.zoom.min || 1) * 2);
    trilha.applyConstraints({ advanced: [{ zoom: alvo }] }).then(function () {
      aproximado = !aproximado;
      botaoAproximar.setAttribute("aria-pressed", String(aproximado));
      botaoAproximar.textContent = aproximado ? "Afastar" : "Aproximar";
    }).catch(function () {
      avisar("Este aparelho não deixa o navegador aproximar.", true);
      botaoAproximar.hidden = true;
    });
  }

  /* ---- Ligar --------------------------------------------------------------- */

  function ligarCamera() {
    // A câmera de trás é a que enxerga a etiqueta; a da frente aponta para o rosto.
    // 1920 e não 1280: um EAN-13 tem 95 barras, e a etiqueta da loja ocupa um terço da
    // faixa. A 1280 cada barra cai para menos de dois pixels e nenhum leitor acerta.
    var pedido = {
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1920 },
        height: { ideal: 1080 }
      },
      audio: false
    };
    navigator.mediaDevices.getUserMedia(pedido).then(function (recebido) {
      fluxo = recebido;
      trilha = fluxo.getVideoTracks()[0] || null;
      video.srcObject = fluxo;
      video.play();
      if (area) { area.hidden = false; }
      if (botaoFoto) { botaoFoto.hidden = false; }
      // Foco contínuo: sem isto o Android trava o foco no primeiro quadro, que é a
      // prateleira ao fundo, e a etiqueta fica desfocada a leitura inteira.
      if (trilha && trilha.applyConstraints) {
        trilha.applyConstraints({ advanced: [{ focusMode: "continuous" }] })
          .catch(function () { /* aparelho que não deixa escolher o foco */ });
      }
      prepararControles();
      avisar("Procurando o código…", false);
      lendo = true;
      requestAnimationFrame(procurar);
    }).catch(function () {
      if (area) { area.hidden = false; }
      avisar("A câmera não foi liberada. Autorize a câmera para este endereço nas "
             + "configurações do navegador, ou digite o código aqui embaixo.", true);
    });
  }

  function comecar() {
    // Sem https o navegador não tem nem como pedir a câmera: o recado é outro.
    if (!window.isSecureContext) { mostrar("aviso-sem-https"); return; }
    if (!navigator.mediaDevices) { mostrar("aviso-sem-leitor"); return; }
    escolherLeitor().then(function (lido) {
      if (!lido) { mostrar("aviso-sem-leitor"); return; }
      decodificar = lido;
      ligarCamera();
    });
  }

  function anotarNaLista(produto) {
    if (!lista) { return null; }
    var vazia = document.getElementById("leitura-vazia");
    if (vazia) { vazia.remove(); }
    var linha = document.createElement("li");
    linha.className = produto.bate ? "leitura-bate" : "leitura-difere";
    linha.id = "leitura-" + produto.id;
    var nome = document.createElement("strong");
    nome.textContent = produto.descricao;
    var detalhe = document.createElement("span");
    detalhe.textContent = produto.contado + " contado, " + produto.saldo_set + " no SET · " + produto.recado;
    linha.appendChild(nome);
    linha.appendChild(detalhe);
    lista.insertBefore(linha, lista.firstChild);
    return linha;
  }

  var ultimoItem = null;  // o último produto registrado, que é onde a foto se prende

  function mostrarBotoesDaPeca(mostrar) {
    [botaoSemEtiqueta, botaoDanificada].forEach(function (botao) {
      if (botao) { botao.hidden = !mostrar; }
    });
  }

  function marcarEstado(estado, rotuloCurto) {
    if (!ultimoItem || !ultimoItem.estado_em) {
      avisar("Registre a peça primeiro: a marca fica guardada junto dela.", true);
      return;
    }
    var dados = new FormData();
    dados.append("estado", estado);
    dados.append("csrfmiddlewaretoken", formulario.querySelector("[name=csrfmiddlewaretoken]").value);
    var peca = ultimoItem;
    fetch(peca.estado_em, { method: "POST", body: dados, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (corpo) {
        if (!corpo.ok) { avisar(corpo.erro, true); return; }
        peca.estado = corpo.estado;
        avisar(peca.descricao + ": " + corpo.rotulo.toLowerCase() + ".", !corpo.perfeito);
        var linha = document.getElementById("leitura-" + peca.id);
        if (linha) {
          var marca = linha.querySelector(".leitura-estado");
          if (!marca) {
            marca = document.createElement("span");
            marca.className = "leitura-estado";
            linha.appendChild(marca);
          }
          // Vazio quando a peça volta a perfeita: deixar "perfeito" escrito faria a
          // lista parecer cheia de peça marcada.
          marca.textContent = corpo.perfeito ? "" : rotuloCurto;
        }
      })
      .catch(function () { avisar("Não deu para marcar agora. Tente outra vez.", true); });
  }

  function tirarFoto() {
    if (!ultimoItem) {
      avisar("Registre um produto primeiro: a foto fica guardada junto dele.", true);
      return;
    }
    if (!fluxo) { avisar("A câmera está desligada.", true); return; }
    var papel = document.createElement("canvas");
    papel.width = video.videoWidth || 1280;
    papel.height = video.videoHeight || 960;
    papel.getContext("2d").drawImage(video, 0, 0, papel.width, papel.height);
    avisar("Guardando a foto…", false);
    papel.toBlob(function (imagem) {
      if (!imagem) { avisar("Não deu para tirar a foto neste aparelho.", true); return; }
      var dados = new FormData();
      dados.append("foto", imagem, "prateleira.jpg");
      dados.append("csrfmiddlewaretoken", formulario.querySelector("[name=csrfmiddlewaretoken]").value);
      fetch(ultimoItem.foto, { method: "POST", body: dados, credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (corpo) {
          if (!corpo.ok) { avisar(corpo.erro, true); return; }
          avisar("Foto guardada em " + ultimoItem.descricao + ".", false);
          var linha = document.getElementById("leitura-" + ultimoItem.id);
          if (linha && !linha.querySelector("img")) {
            var miniatura = document.createElement("img");
            miniatura.src = corpo.endereco;
            miniatura.alt = "Foto da prateleira de " + ultimoItem.descricao;
            miniatura.className = "leitura-foto";
            linha.appendChild(miniatura);
          }
        })
        .catch(function () { avisar("Não deu para guardar a foto agora.", true); });
    }, "image/jpeg", 0.8);
  }

  formulario.addEventListener("submit", function (evento) {
    var destino = formulario.getAttribute("data-destino");
    if (!destino || !window.fetch) { return; }  // sem fetch, o envio normal recarrega e funciona
    evento.preventDefault();
    fetch(destino, {
      method: "POST",
      body: new FormData(formulario),
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    }).then(function (resposta) {
      return resposta.json();
    }).then(function (corpo) {
      if (!corpo.ok) { avisar(corpo.erro, true); return; }
      ultimoItem = corpo.produto;
      mostrarBotoesDaPeca(true);
      anotarNaLista(corpo.produto);
      avisar(corpo.produto.descricao + ": " + corpo.produto.contado + " contado, "
             + corpo.produto.recado + ".", !corpo.produto.bate);
      campoProduto.value = "";
      campoQuantidade.value = "1";
      ultimoCodigo = "";
      campoProduto.focus();
    }).catch(function () {
      avisar("Não deu para registrar agora. Confira o wi-fi da loja e tente outra vez.", true);
    });
  });

  if (botaoParar) { botaoParar.addEventListener("click", pararCamera); }
  if (botaoFoto) { botaoFoto.addEventListener("click", tirarFoto); }
  if (botaoSemEtiqueta) {
    botaoSemEtiqueta.addEventListener("click", function () {
      marcarEstado("sem_etiqueta", "sem etiqueta");
    });
  }
  if (botaoDanificada) {
    botaoDanificada.addEventListener("click", function () {
      marcarEstado("danificado", "danificada");
    });
  }
  if (botaoLanterna) { botaoLanterna.addEventListener("click", alternarLanterna); }
  if (botaoAproximar) { botaoAproximar.addEventListener("click", alternarAproximar); }
  // Câmera ligada numa aba escondida gasta bateria e não lê nada.
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { pararCamera(); }
  });
  comecar();
})();
