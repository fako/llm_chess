// Tap a piece, then tap its destination. The server decides whether a move is the solution.
(function () {
  "use strict";

  let selected = null;

  function getPuzzle() {
    return document.getElementById("puzzle");
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

  function submit(puzzle, uci) {
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
    const picker = document.createElement("div");
    picker.className = "promotion-picker card fixed inset-x-4 bottom-6 z-50 mx-auto flex max-w-sm justify-around p-3";
    picker.setAttribute("role", "dialog");
    picker.setAttribute("aria-label", "Promote to");
    ["q", "r", "b", "n"].forEach(function (piece) {
      const uci = moves.find(function (move) { return move.slice(4) === piece; });
      if (!uci) {
        return;
      }
      const names = { q: "queen", r: "rook", b: "bishop", n: "knight" };
      const button = document.createElement("button");
      button.type = "button";
      button.className = "h-16 w-16 rounded-lg bg-square-light hover:bg-square-dark";
      button.setAttribute("aria-label", names[piece]);
      button.innerHTML = '<svg viewBox="0 0 45 45" class="h-full w-full"><use href="#piece-' +
        (isWhite ? "white" : "black") + "-" + names[piece] + '"></use></svg>';
      button.dataset.promotion = uci;
      picker.appendChild(button);
    });
    puzzle.appendChild(picker);
  }

  document.addEventListener("click", function (event) {
    const puzzle = getPuzzle();
    if (!puzzle || !puzzle.contains(event.target)) {
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
})();
