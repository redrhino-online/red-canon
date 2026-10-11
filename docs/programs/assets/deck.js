/* Shared RED Method program deck boot script. Viewport-native canvas. */

(function () {
  "use strict";

  var deck = new Reveal({
    hash: true,
    hashOneBasedIndex: false,
    slideNumber: "c/t",
    transition: "fade",
    transitionSpeed: "fast",
    progress: true,
    controls: true,
    touch: true,
    keyboard: true,
    overview: true,
    margin: 0,
    minScale: 1,
    maxScale: 1,
    width: window.innerWidth || 1240,
    height: window.innerHeight || 700,
  });

  deck.initialize();

  function fitDeck() {
    deck.configure({
      width: window.innerWidth,
      height: window.innerHeight,
    });
  }

  window.addEventListener("resize", fitDeck);
  window.addEventListener("orientationchange", fitDeck);
})();
