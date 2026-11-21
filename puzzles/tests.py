from unittest.mock import patch

import chess
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from puzzles import engine
from puzzles.generation import PuzzleProposal, PuzzleProposals, Rejection, generate_puzzles, verify_proposal
from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle
from puzzles.solver import analyse_mate_puzzle, build_solution_tree


# Rc7+ is the key, after which the king has three squares and Ra8 mates every time.
CHECKING_KEY = "8/5k2/R7/8/8/8/8/1KR5 w - - 0 1"
# Kb6 is a quiet key. After Ka8 both Re8 and Rd8 mate, after Kc8 only Re8 does.
QUIET_KEY = "1k6/8/8/K3R3/8/3R4/8/8 w - - 0 1"
QUIET_KEY_BLACK = chess.Board(QUIET_KEY).mirror().fen()
LEGALS_MATE = "r2qkb1r/pp2nppp/3p4/2pNN1B1/2BnP3/3P4/PPP2PPP/R2bK2R w KQkq - 1 1"
MATE_IN_ONE = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"


def proposal(fen: str, perspective: str = "white", solution: list[list[str]] | None = None) -> PuzzleProposal:
    return PuzzleProposal(fen=fen, perspective=perspective, solution=solution or [["Kb6", "Ka8", "Re8#"]],
                          title="A quiet king", hint="Your king can help.")


class TestSolver(TestCase):

    def test_sound_puzzles(self):
        for fen, key in [(CHECKING_KEY, "c1c7"), (QUIET_KEY, "a5b6"), (LEGALS_MATE, "d5f6"), (QUIET_KEY_BLACK, "a4b3")]:
            analysis = analyse_mate_puzzle(chess.Board(fen), 2)
            self.assertTrue(analysis.is_sound, f"{fen}: {analysis.reason}")
            self.assertEqual(analysis.key_moves, (key,))

    def test_unsound_puzzles(self):
        self.assertEqual(analyse_mate_puzzle(chess.Board(MATE_IN_ONE), 2).reason, "there is already a mate in 1")
        self.assertEqual(analyse_mate_puzzle(chess.Board(), 2).reason, "there is no forced mate in 2")
        illegal = analyse_mate_puzzle(chess.Board("8/8/8/8/8/5K2/7R/7k w - - 0 1"), 2)
        self.assertFalse(illegal.is_sound)
        self.assertTrue(illegal.reason.startswith("illegal position"))
        # Moving the rook from a6 to a7 gives white a second key
        cooked = analyse_mate_puzzle(chess.Board("8/R4k2/8/8/8/8/8/1KR5 w - - 0 1"), 2)
        self.assertFalse(cooked.is_sound)

    def test_solution_tree(self):
        tree = build_solution_tree(chess.Board(QUIET_KEY), 2)
        self.assertEqual(list(tree["moves"]), ["a5b6"])
        key = tree["moves"]["a5b6"]
        self.assertEqual(key["san"], "Kb6")
        self.assertFalse(key["end"])
        self.assertEqual(set(key["replies"]), {"b8a8", "b8c8"})
        self.assertEqual(set(key["replies"]["b8a8"]["moves"]), {"e5e8", "d3d8"})
        self.assertEqual(set(key["replies"]["b8c8"]["moves"]), {"e5e8"})
        self.assertTrue(key["replies"]["b8c8"]["moves"]["e5e8"]["end"])


class TestVerifyProposal(TestCase):

    def setUp(self):
        self.category = ChessPuzzleCategory.objects.get(slug="mate-in-2")

    def test_accepts_sound_proposal(self):
        puzzle = verify_proposal(self.category, proposal(QUIET_KEY))
        self.assertIsInstance(puzzle, ChessPuzzle)
        self.assertEqual(set(puzzle.solution["moves"]["a5b6"]["replies"]), {"b8a8", "b8c8"})
        self.assertTrue(puzzle.generation["llm_was_right"])
        self.assertEqual(puzzle.hint, "Your king can help.")

    def test_keeps_sound_position_with_wrong_llm_solution(self):
        puzzle = verify_proposal(self.category, proposal(QUIET_KEY, solution=[["Re8+", "Kc7"]]))
        self.assertIsInstance(puzzle, ChessPuzzle)
        self.assertFalse(puzzle.generation["llm_was_right"])
        self.assertEqual(puzzle.hint, "", "hints of a wrong solution are misleading")

    def test_rejections(self):
        self.assertIn("invalid FEN", verify_proposal(self.category, proposal("not a fen")).reason)
        self.assertIn("other side is to move", verify_proposal(self.category, proposal(QUIET_KEY, "black")).reason)
        self.assertIn("mate in 1", verify_proposal(self.category, proposal(MATE_IN_ONE)).reason)
        verify_proposal(self.category, proposal(QUIET_KEY)).save()
        duplicate = verify_proposal(self.category, proposal(QUIET_KEY.replace("0 1", "3 9")))
        self.assertEqual(duplicate.reason, "position already exists")


class FakeResource:
    """
    Stands in for AnthropicPromptResource, so tests don't make requests.
    """
    status = 200
    success = True
    served_by = "claude-opus-5"
    signature = None
    result = None

    requests = []

    def __init__(self, llm=None):
        self.llm = llm

    def extract(self, *args, **kwargs):
        self.context = kwargs["context"]
        FakeResource.requests.append((self.llm.value, kwargs["options"]["effort"]))
        return self

    def close(self):
        return self

    def get_token_usage(self):
        return {"prompt": 10, "completion": 20, "total": 30}

    @property
    def content(self):
        return "application/json", PuzzleProposals(puzzles=[
            proposal(MATE_IN_ONE), proposal(CHECKING_KEY, solution=[["Rc7+", "Kf8", "Ra8#"]]), proposal(QUIET_KEY),
        ])


class TestGeneratePuzzles(TestCase):

    @patch("puzzles.generation.AnthropicPromptResource", FakeResource)
    def test_generate_puzzles(self):
        report = generate_puzzles("mate-in-2", 2)
        self.assertEqual(report.requests, 1)
        self.assertEqual([puzzle.fen for puzzle in report.created], [CHECKING_KEY, QUIET_KEY])
        self.assertEqual([rejection.reason for rejection in report.rejected], ["there is already a mate in 1"])
        self.assertEqual(report.tokens["total"], 30)
        self.assertEqual(ChessPuzzle.objects.count(), 2)
        puzzle = ChessPuzzle.objects.get(fen=CHECKING_KEY)
        self.assertEqual(puzzle.generation["served_by"], "claude-opus-5")
        self.assertEqual((puzzle.model, puzzle.effort), ("claude-opus-5", "low"))

    @patch("puzzles.generation.AnthropicPromptResource", FakeResource)
    def test_model_and_effort(self):
        FakeResource.requests = []
        report = generate_puzzles("mate-in-3", 1, max_requests=1)
        self.assertEqual((report.model, report.effort), ("claude-opus-5", "high"), "category defaults")
        generate_puzzles("mate-in-2", 1, model="claude-sonnet-5", effort="medium")
        self.assertEqual(FakeResource.requests, [
            ("anthropic/claude-opus-5", "high"),
            ("anthropic/claude-sonnet-5", "medium"),
        ])
        puzzle = ChessPuzzle.objects.get(category__slug="mate-in-2")
        self.assertEqual((puzzle.model, puzzle.effort), ("claude-sonnet-5", "medium"), "command overrides")

    @patch("puzzles.generation.AnthropicPromptResource", FakeResource)
    def test_stops_at_max_requests(self):
        report = generate_puzzles("mate-in-2", 5, max_requests=2)
        self.assertEqual(report.requests, 2)
        self.assertEqual(len(report.created), 2, "the second request only proposes existing positions")
        self.assertTrue(all(isinstance(rejection, Rejection) for rejection in report.rejected))


class EngineTestCase(TestCase):

    def setUp(self):
        self.category = ChessPuzzleCategory.objects.get(slug="mate-in-2")
        self.user = User.objects.create_user("solver", password="secret-password")
        self.puzzle = verify_proposal(self.category, proposal(QUIET_KEY))
        self.puzzle.save()


def end(san: str) -> dict:
    return {"san": san, "end": True}


# A made up tree: after the key the opponent has two replies that hold out for two more moves and one that doesn't.
# After "b" the user may mate right away or take the long way around.
BRANCHING_TREE = {"moves": {"k": {"san": "K", "end": False, "replies": {
    "a": {"san": "a", "moves": {"x": {"san": "x", "end": False, "replies": {"r": {"san": "r", "moves": {"m": end("m")}}}}}},
    "b": {"san": "b", "moves": {"m": end("m"), "y": {"san": "y", "end": False, "replies": {
        "r": {"san": "r", "moves": {"m": end("m")}},
    }}}},
    "c": {"san": "c", "moves": {"z": {"san": "z", "end": False, "replies": {"r": {"san": "r", "moves": {"m": end("m")}}}}}},
}}}}


class TestEngine(EngineTestCase):

    def test_longest_replies(self):
        self.assertEqual(engine.moves_to_solve(BRANCHING_TREE), 3)
        self.assertEqual(engine.longest_replies(BRANCHING_TREE["moves"]["k"]), ["a", "c"],
                         "b doesn't count as long, because the user can mate right away")
        self.assertEqual(engine.moves_to_solve(BRANCHING_TREE["moves"]["k"]["replies"]["b"]), 1)

    @patch("puzzles.engine.random.choice", lambda options: options[-1])
    def test_solve(self):
        progress = engine.get_progress(self.user, self.puzzle)
        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.MOVE)
        self.assertEqual(state.moves_left, 2)
        self.assertIn("a5b6", state.legal_moves)

        self.assertEqual(engine.play_move(progress, "e5e8"), engine.Outcome.WRONG)
        self.assertEqual(engine.play_move(progress, "a1a2"), engine.Outcome.ILLEGAL)
        self.assertEqual(progress.wrong_moves, 1)
        self.assertEqual(engine.play_move(progress, "a5b6"), engine.Outcome.CORRECT)
        self.assertEqual(progress.line, ["a5b6", "b8c8"], "the opponent replies right away")

        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.MOVE)
        self.assertEqual(state.moves_left, 1)
        self.assertEqual(state.last_move, chess.Move.from_uci("b8c8"))
        self.assertEqual(engine.play_move(progress, "d3d8"), engine.Outcome.WRONG, "Rd8+ doesn't mate against Kc8")
        self.assertEqual(engine.play_move(progress, "e5e8"), engine.Outcome.SOLVED)
        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.SOLVED)
        self.assertEqual(state.moves_left, 0)
        self.assertTrue(progress.is_solved)
        self.assertEqual(progress.wrong_moves, 2)

        solved_at = progress.solved_at
        engine.restart(progress)
        engine.play_move(progress, "a5b6")
        engine.play_move(progress, "e5e8")
        self.assertEqual(progress.solved_at, solved_at, "only the first solve counts")

    def test_any_mating_move_is_accepted(self):
        progress = engine.get_progress(self.user, self.puzzle)
        progress.line = ["a5b6", "b8a8"]
        progress.save()
        self.assertEqual(engine.play_move(progress, "d3d8"), engine.Outcome.SOLVED)

    def test_replies_are_random(self):
        replies = set()
        for _ in range(30):
            progress = engine.get_progress(self.user, self.puzzle)
            engine.restart(progress)
            engine.play_move(progress, "a5b6")
            replies.add(progress.line[1])
        self.assertEqual(replies, {"b8a8", "b8c8"})

    def test_hints(self):
        progress = engine.get_progress(self.user, self.puzzle)
        engine.take_hint(progress)
        self.assertEqual(engine.get_state(progress).hint_squares, ["a5"])
        engine.take_hint(progress)
        engine.take_hint(progress)
        self.assertEqual(engine.get_state(progress).hint_squares, ["a5", "b6"])
        self.assertEqual(progress.hints_used, 2)
        engine.play_move(progress, "a5b6")
        self.assertEqual(progress.hint_level, 0, "hints are per position")

    def test_line_outside_of_solution_resets(self):
        progress = engine.get_progress(self.user, self.puzzle)
        for line in (["e5e8"], ["a5b6"]):  # a wrong move, and a line that waits for a reply
            progress.line = line
            progress.save()
            state = engine.get_state(progress)
            self.assertEqual(progress.line, [])
            self.assertEqual(state.phase, engine.Phase.MOVE)

    def test_next_puzzle(self):
        other = verify_proposal(self.category, proposal(CHECKING_KEY))
        other.save()
        self.assertIn(engine.next_puzzle(self.user, self.category), [self.puzzle, other])

        # A started puzzle comes first
        progress = engine.get_progress(self.user, other)
        self.assertEqual(engine.next_puzzle(self.user, self.category), other)

        # Once solved, unsolved puzzles remain
        engine.play_move(progress, "c1c7")
        engine.play_move(progress, "a6a8")
        self.assertTrue(progress.is_solved)
        self.assertEqual(engine.next_puzzle(self.user, self.category), self.puzzle)

        UserChessPuzzle.objects.create(user=self.user, puzzle=self.puzzle, solved_at=timezone.now())
        self.assertIsNone(engine.next_puzzle(self.user, self.category))


class TestViews(EngineTestCase):

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_signup(self):
        self.client.logout()
        response = self.client.post("/accounts/signup/", {
            "username": "newcomer", "password1": "a-long-passphrase-42", "password2": "a-long-passphrase-42",
        })
        self.assertRedirects(response, "/")
        self.assertIsInstance(User.objects.get(username="newcomer").pk.hex, str)

    def test_home_and_category(self):
        response = self.client.get("/")
        self.assertContains(response, "Mate in 2")
        response = self.client.get("/categories/mate-in-2/")
        self.assertRedirects(response, f"/puzzles/{self.puzzle.pk}/")

    def test_play_through_htmx(self):
        url = f"/puzzles/{self.puzzle.pk}/"
        response = self.client.get(url)
        self.assertContains(response, 'data-phase="move"')
        self.assertContains(response, "piece-white-king")

        headers = {"HX-Request": "true"}
        response = self.client.post(url + "move/", {"move": "e5e8"}, headers=headers)
        self.assertContains(response, "not it")
        self.assertContains(response, "square dark occupied wrong")
        self.assertNotContains(response, "<html")

        with patch("puzzles.engine.random.choice", lambda options: "b8c8"):
            response = self.client.post(url + "move/", {"move": "a5b6"}, headers=headers)
        self.assertContains(response, 'data-phase="move"')
        self.assertContains(response, "mate now")
        response = self.client.post(url + "hint/", headers=headers)
        self.assertContains(response, "hint")
        response = self.client.post(url + "move/", {"move": "e5e8"}, headers=headers)
        self.assertContains(response, "Checkmate!")
        self.assertContains(response, "Next puzzle")

        response = self.client.post(url + "restart/")
        self.assertRedirects(response, url)

    def test_board_orientation_for_black(self):
        puzzle = verify_proposal(self.category, proposal(QUIET_KEY_BLACK, "black", [["Kb3"]]))
        puzzle.save()
        response = self.client.get(f"/puzzles/{puzzle.pk}/")
        content = response.content.decode()
        self.assertLess(content.index('data-square="h1"'), content.index('data-square="a8"'))
        self.assertContains(response, "Black to play")

    def test_category_after_everything_is_solved(self):
        UserChessPuzzle.objects.create(user=self.user, puzzle=self.puzzle, solved_at=timezone.now())
        response = self.client.get("/categories/mate-in-2/")
        self.assertContains(response, "All done")


MATE_IN_THREE = "r1b1kb1r/pppp1ppp/5q2/4n3/3KP3/2N3PN/PPP4P/R1BQ1B1R b kq - 0 1"
BISHOP_PIN = "4k3/8/2n5/8/8/8/8/3BK3 w - - 0 1"
UNSAFE_PIN = "4k3/8/2n5/1p6/8/8/8/3BK3 w - - 0 1"


class TestOtherCategories(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("solver", password="secret-password")

    def solve(self, puzzle, line):
        progress = engine.get_progress(self.user, puzzle)
        outcome = None
        for uci in line:
            outcome = engine.play_move(progress, uci)
        return progress, outcome

    def test_mate_in_one(self):
        category = ChessPuzzleCategory.objects.get(slug="mate-in-1")
        puzzle = verify_proposal(category, proposal(MATE_IN_ONE, solution=[["Rd8#"]]))
        self.assertIsInstance(puzzle, ChessPuzzle)
        puzzle.save()
        progress, outcome = self.solve(puzzle, ["d1d8"])
        self.assertEqual(outcome, engine.Outcome.SOLVED)
        self.assertTrue(progress.is_solved)
        self.assertIsNone(engine.next_puzzle(self.user, category))
        self.assertEqual(verify_proposal(category, proposal(QUIET_KEY)).reason, "there is no forced mate in 1")

    def test_mate_in_three(self):
        category = ChessPuzzleCategory.objects.get(slug="mate-in-3")
        self.assertIn("mate in 2", verify_proposal(category, proposal(QUIET_KEY)).reason)
        puzzle = verify_proposal(category, proposal(MATE_IN_THREE, "black", [["Qf2+"]]))
        self.assertIsInstance(puzzle, ChessPuzzle)
        puzzle.save()
        progress = engine.get_progress(self.user, puzzle)
        key = next(iter(puzzle.solution["moves"]))
        self.assertGreater(len(puzzle.solution["moves"][key]["replies"]), 1)
        self.assertEqual(engine.play_move(progress, key), engine.Outcome.CORRECT)
        self.assertEqual(engine.get_state(progress).moves_left, 2, "the opponent picks a reply that holds out longest")

    def test_pin(self):
        category = ChessPuzzleCategory.objects.get(slug="pin-a-piece")
        self.assertEqual(category.depth, 1)
        self.assertEqual(verify_proposal(category, proposal(UNSAFE_PIN)).reason, "no move creates a safe pin")
        self.assertEqual(verify_proposal(category, proposal(MATE_IN_ONE)).reason, "there is a mate in 1")
        puzzle = verify_proposal(category, proposal(BISHOP_PIN, solution=[["Ba4"]]))
        self.assertIsInstance(puzzle, ChessPuzzle)
        self.assertTrue(puzzle.generation["llm_was_right"])
        puzzle.save()
        progress, outcome = self.solve(puzzle, ["d1b3"])
        self.assertEqual(outcome, engine.Outcome.WRONG)
        progress, outcome = self.solve(puzzle, ["d1a4"])
        self.assertEqual(outcome, engine.Outcome.SOLVED)
        self.assertEqual(engine.get_state(progress).final_move["pin"]["pinned"], "c6")

        self.client.force_login(self.user)
        response = self.client.get(f"/puzzles/{puzzle.pk}/")
        self.assertContains(response, "Pinned!")
        self.assertContains(response, "The knight on c6 is pinned to the king on e8.")
