/*
 * Telas de entrada (1.43.0): mostrar a senha e avisar do Caps Lock.
 *
 * Duas causas comuns de "a senha não entra" que a pessoa não enxerga: a letra que saiu
 * errada atrás das bolinhas, e a tecla de maiúsculas ligada. O botão Mostrar troca as
 * bolinhas pelas letras e volta; o aviso aparece enquanto o Caps Lock estiver ligado.
 *
 * Tudo aqui é acréscimo: sem JavaScript a tela entra igual, só sem os dois recursos. Por
 * isso o botão nasce escondido no HTML e só aparece daqui.
 */
(function () {
  "use strict";

  document.querySelectorAll(".mostrar-senha").forEach(function (botao) {
    var campo = document.getElementById(botao.getAttribute("aria-controls"));
    if (!campo) { return; }
    botao.hidden = false;
    botao.addEventListener("click", function () {
      var mostrando = campo.type === "text";
      campo.type = mostrando ? "password" : "text";
      botao.textContent = mostrando ? "Mostrar" : "Esconder";
      botao.setAttribute("aria-pressed", mostrando ? "false" : "true");
      campo.focus();
    });
  });

  // Antes de enviar, a senha volta às bolinhas: o navegador não oferece guardar a senha
  // de campo de texto, e quem está ao lado não lê a senha na tela que fica parada.
  document.querySelectorAll("form").forEach(function (formulario) {
    formulario.addEventListener("submit", function () {
      formulario.querySelectorAll(".campo-senha input").forEach(function (campo) {
        campo.type = "password";
      });
    });
  });

  var aviso = document.getElementById("aviso-maiusculas");
  if (aviso) {
    var conferir = function (evento) {
      if (typeof evento.getModifierState !== "function") { return; }
      aviso.hidden = !evento.getModifierState("CapsLock");
    };
    document.querySelectorAll('input[type="password"], .campo-senha input').forEach(function (campo) {
      campo.addEventListener("keydown", conferir);
      campo.addEventListener("keyup", conferir);
      campo.addEventListener("blur", function () { aviso.hidden = true; });
    });
  }
})();
