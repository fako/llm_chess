{{ prompt }}

Answer with exactly {{ count }} puzzles. For every puzzle give:
- fen: the position in Forsyth-Edwards Notation, with the solving side to move.
- perspective: "white" or "black", the side that solves the puzzle. It must match the side to move in the FEN.
- solution: the main variations as lists of SAN moves, each starting with the first move of the solving side.
  Include the most important defences of the opponent as separate variations.
- title: a short title that doesn't give away the solution.
- hint: one sentence that nudges towards the idea without naming the first move.

Every position must be legal: exactly one king per side, kings not on adjacent squares, no pawns on the first or
last rank, and the side that is not to move can't be in check. Castling rights and en passant squares in the FEN
must be consistent with the position.

A chess engine checks every puzzle afterwards and rejects unsound ones, so there is no need to verify every
defence yourself. Spend your effort on placing the pieces correctly in the FEN: most rejected puzzles have a
piece on the wrong square, an extra piece that spoils the mate, or a second first move that also mates.
Prefer puzzles you are confident about over ambitious ones.
{% if excluded_positions %}

These positions exist already, don't propose them again:
{% for fen in excluded_positions %}- {{ fen }}
{% endfor %}{% endif %}
Request reference: {{ nonce }}
