#!/usr/bin/env bash
# Generates the v2 puzzles on the hub, writes them to the fixture and commits it, so production can run the
# v2_puzzles command set (migrate + loaddata initial_puzzles) after a deploy.
#
# Safe to run again: every slot only generates what it is missing, so after running out of credits you can top up
# and start this script again. Override the requests per puzzle with MAX_REQUESTS=5 ./generate_v2_puzzles.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=venv/bin/python
MAX_REQUESTS=${MAX_REQUESTS:-3}
FIXTURE=puzzles/fixtures/initial_puzzles.json
PER_CATEGORY=5

if ! git diff --quiet -- "$FIXTURE" || ! git diff --cached --quiet -- "$FIXTURE"; then
    echo "$FIXTURE has uncommitted changes, commit or revert them first" >&2
    exit 1
fi

echo "== Making sure the database is on v2"
$PYTHON manage.py migrate --no-input

# slot <category> <amount> <tags>
# Generates puzzles one at a time, so every puzzle gets its own balanced tags for whatever the given tags leave open.
slot() {
    local category=$1 amount=$2 tags=$3
    for target in $(seq 1 "$amount"); do
        echo
        echo "== $category: puzzle $target of $amount with [$tags]"
        $PYTHON manage.py generate_puzzles "$category" "$target" --tags "$tags" --top-up --max-requests "$MAX_REQUESTS"
    done
}

# Every category: 2 puzzles with few pieces and 3 with a full board
slot mate-in-1 2 few-pieces
slot mate-in-1 3 crowded-board

slot mate-in-2 1 few-pieces,quiet-key
slot mate-in-2 1 few-pieces
slot mate-in-2 3 crowded-board

slot mate-in-3 1 few-pieces,zugzwang
slot mate-in-3 1 few-pieces
slot mate-in-3 1 crowded-board,two-bishops
slot mate-in-3 1 crowded-board,castling
slot mate-in-3 1 crowded-board

slot pin-a-piece 2 few-pieces
slot pin-a-piece 3 crowded-board

echo
echo "== Tags per category"
$PYTHON manage.py puzzle_tags

echo
short=$($PYTHON manage.py shell -c "
from django.db.models import Count
from puzzles.models import ChessPuzzleCategory
for category in ChessPuzzleCategory.objects.annotate(total=Count('puzzles')):
    if category.total < $PER_CATEGORY:
        print(f'{category.slug} has {category.total} of $PER_CATEGORY puzzles')
" 2>/dev/null | grep -v "objects imported" || true)
if [ -n "$short" ]; then
    echo "$short"
    echo "Some puzzles didn't verify within $MAX_REQUESTS requests. Run this script again to top up the missing ones."
    exit 1
fi

echo "== Writing $FIXTURE"
$PYTHON manage.py dumpdata puzzles.chesspuzzlecategory puzzles.chesspuzzle --indent 4 -o "$FIXTURE"
git add "$FIXTURE"
git commit -m "Add the v2 puzzles in English and Dutch with tags" -- "$FIXTURE"

cat <<EOF

Done. To bring the puzzles to production:
  1. git push
  2. Deploy
  3. Run the v2_puzzles command set: it migrates (which deletes the old puzzles and progress) and loads the fixture
EOF
