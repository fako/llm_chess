// Tap a piece, then tap its destination. The server decides whether a move is the solution.
// Visitors without an account may look around, but get asked to log in or sign up as soon as they play or take a hint.
// The share button hands the puzzle to the share sheet of the device, or copies its link where there is none.
(function () {
  "use strict";

  let selected = null;

  function getPuzzle() {
    return document.getElementById("puzzle");
  }

  function labels(puzzle) {
    try {
      return JSON.parse(puzzle.dataset.labels || "{}");
    } catch (error) {
      return {};
    }
  }

  function legalMoves(puzzle) {
    try {
      return JSON.parse(puzzle.dataset.legal || "[]");
    } catch (error) {
      return [];
    }
  }

  function clearSelection(puzzle) {
    selected = null;
    puzzle.querySelectorAll(".square.selected, .square.target").forEach(function (square) {
      square.classList.remove("selected", "target");
    });
    closePromotion(puzzle);
  }

  function select(puzzle, square) {
    clearSelection(puzzle);
    const from = square.dataset.square;
    const targets = legalMoves(puzzle).filter(function (uci) { return uci.slice(0, 2) === from; });
    if (!targets.length) {
      return;
    }
    selected = from;
    square.classList.add("selected");
    targets.forEach(function (uci) {
      const target = puzzle.querySelector('[data-square="' + uci.slice(2, 4) + '"]');
      if (target) {
        target.classList.add("target");
      }
    });
  }

  function askAccount() {
    const dialog = document.getElementById("account-dialog");
    if (dialog) {
      dialog.showModal();
    }
  }

  function submit(puzzle, uci) {
    if (puzzle.hasAttribute("data-needs-account")) {
      askAccount();
      return;
    }
    clearSelection(puzzle);
    htmx.ajax("POST", puzzle.dataset.moveUrl, {
      target: "#puzzle",
      swap: "outerHTML",
      values: { move: uci },
    });
  }

  function closePromotion(puzzle) {
    const picker = puzzle.querySelector(".promotion-picker");
    if (picker) {
      picker.remove();
    }
  }

  function askPromotion(puzzle, moves) {
    const isWhite = puzzle.dataset.color === "white";
    const text = labels(puzzle);
    const picker = document.createElement("div");
    picker.className = "promotion-picker card fixed inset-x-4 bottom-6 z-50 mx-auto flex max-w-sm justify-around p-3";
    picker.setAttribute("role", "dialog");
    picker.setAttribute("aria-label", text.promote || "Promote to");
    ["q", "r", "b", "n"].forEach(function (piece) {
      const uci = moves.find(function (move) { return move.slice(4) === piece; });
      if (!uci) {
        return;
      }
      const names = { q: "queen", r: "rook", b: "bishop", n: "knight" };
      const button = document.createElement("button");
      button.type = "button";
      button.className = "h-16 w-16 rounded-lg bg-square-light hover:bg-square-dark";
      button.setAttribute("aria-label", text[piece] || names[piece]);
      button.innerHTML = '<svg viewBox="0 0 45 45" class="h-full w-full"><use href="#piece-' +
        (isWhite ? "white" : "black") + "-" + names[piece] + '"></use></svg>';
      button.dataset.promotion = uci;
      picker.appendChild(button);
    });
    puzzle.appendChild(picker);
  }

  function showCopied(url, copied) {
    const dialog = document.getElementById("share-dialog");
    if (!dialog) {
      return;
    }
    dialog.querySelectorAll("[data-share-copied]").forEach(function (element) { element.hidden = !copied; });
    dialog.querySelectorAll("[data-share-manual]").forEach(function (element) { element.hidden = copied; });
    const link = dialog.querySelector("[data-share-link]");
    link.value = url;
    dialog.showModal();
    if (!copied) {
      link.select();
    }
  }

  function share(button) {
    const url = button.dataset.shareUrl;
    const data = { title: button.dataset.shareTitle, text: button.dataset.shareText, url: url };
    if (navigator.share && (!navigator.canShare || navigator.canShare(data))) {
      navigator.share(data).catch(function (error) {
        if (error.name !== "AbortError") {  // people closing the share sheet themselves is no error
          copy(url);
        }
      });
      return;
    }
    copy(url);
  }

  function copy(url) {
    if (!navigator.clipboard) {  // only available over https
      showCopied(url, false);
      return;
    }
    navigator.clipboard.writeText(url).then(
      function () { showCopied(url, true); },
      function () { showCopied(url, false); }
    );
  }

  document.addEventListener("click", function (event) {
    const puzzle = getPuzzle();
    if (!puzzle || !puzzle.contains(event.target)) {
      return;
    }
    const shareButton = event.target.closest("[data-share-url]");
    if (shareButton) {
      share(shareButton);
      return;
    }
    if (event.target.closest("[data-ask-account]")) {
      askAccount();
      return;
    }
    const promotion = event.target.closest("[data-promotion]");
    if (promotion) {
      submit(puzzle, promotion.dataset.promotion);
      return;
    }
    const square = event.target.closest("[data-square]");
    if (!square || puzzle.dataset.phase !== "move") {
      return;
    }
    if (selected) {
      const to = square.dataset.square;
      const moves = legalMoves(puzzle).filter(function (uci) {
        return uci.slice(0, 2) === selected && uci.slice(2, 4) === to;
      });
      if (moves.length === 1) {
        submit(puzzle, moves[0]);
        return;
      }
      if (moves.length > 1) {
        askPromotion(puzzle, moves);
        return;
      }
    }
    if (square.hasAttribute("data-own") && square.dataset.square !== selected) {
      select(puzzle, square);
    } else {
      clearSelection(puzzle);
    }
  });

  document.addEventListener("htmx:afterSwap", function () {
    selected = null;
  });

  // The board stays as it was when visitors cancel, without the piece they picked up
  document.addEventListener("close", function (event) {
    const puzzle = getPuzzle();
    if (puzzle && event.target.id === "account-dialog") {
      clearSelection(puzzle);
    }
  }, true);
})();
