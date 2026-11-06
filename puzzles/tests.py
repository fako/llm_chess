from unittest.mock import patch

import chess
from django.test import TestCase

from accounts.models import User
from puzzles import engine
from puzzles.generation import PuzzleProposal, PuzzleProposals, Rejection, generate_puzzles, verify_proposal
from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle
from puzzles.solver import analyse_mate_puzzle, build_solution_tree, list_branches


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
        self.assertFalse(key["mate"])
        self.assertEqual(set(key["replies"]), {"b8a8", "b8c8"})
        self.assertEqual(set(key["replies"]["b8a8"]["moves"]), {"e5e8", "d3d8"})
        self.assertEqual(set(key["replies"]["b8c8"]["moves"]), {"e5e8"})
        self.assertTrue(key["replies"]["b8c8"]["moves"]["e5e8"]["mate"])
        self.assertEqual(list_branches(tree), ["b8a8", "b8c8"])


class TestVerifyProposal(TestCase):

    def setUp(self):
        self.category = ChessPuzzleCategory.objects.get(slug="mate-in-2")

    def test_accepts_sound_proposal(self):
        puzzle = verify_proposal(self.category, proposal(QUIET_KEY))
        self.assertIsInstance(puzzle, ChessPuzzle)
        self.assertEqual(puzzle.branches, ["b8a8", "b8c8"])
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

    def __init__(self, llm=None):
        pass

    def extract(self, *args, **kwargs):
        self.context = kwargs["context"]
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
        self.assertEqual(ChessPuzzle.objects.get(fen=CHECKING_KEY).generation["model"], "claude-opus-5")

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


class TestEngine(EngineTestCase):

    def test_solve_branches(self):
        progress = engine.get_progress(self.user, self.puzzle)
        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.MOVE)
        self.assertEqual(state.moves_left, 2)
        self.assertIn("a5b6", state.legal_moves)

        self.assertEqual(engine.play_move(progress, "e5e8"), engine.Outcome.WRONG)
        self.assertEqual(engine.play_move(progress, "a1a2"), engine.Outcome.ILLEGAL)
        self.assertEqual(progress.wrong_moves, 1)
        self.assertEqual(engine.play_move(progress, "a5b6"), engine.Outcome.CORRECT)

        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.REPLY)
        self.assertEqual([(reply.san, reply.is_completed) for reply in state.replies], [("Ka8", False), ("Kc8", False)])
        self.assertFalse(engine.choose_reply(progress, "b8b7"))
        self.assertTrue(engine.choose_reply(progress, "b8a8"))

        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.MOVE)
        self.assertEqual(state.moves_left, 1)
        self.assertEqual(engine.play_move(progress, "d3d8"), engine.Outcome.MATE, "any mating move is accepted")
        state = engine.get_state(progress)
        self.assertEqual(state.phase, engine.Phase.SOLVED)
        self.assertEqual(state.branch, "b8a8")
        self.assertEqual(progress.completed_branches, ["b8a8"])
        self.assertEqual(progress.open_branches, ["b8c8"])

        engine.restart(progress)
        engine.play_move(progress, "a5b6")
        state = engine.get_state(progress)
        self.assertEqual([(reply.san, reply.is_completed) for reply in state.replies], [("Kc8", False), ("Ka8", True)])
        engine.choose_reply(progress, "b8c8")
        self.assertEqual(engine.play_move(progress, "d3d8"), engine.Outcome.WRONG, "Rd8+ doesn't mate against Kc8")
        self.assertEqual(engine.play_move(progress, "e5e8"), engine.Outcome.MATE)
        self.assertTrue(progress.is_fully_solved)
        self.assertEqual(progress.wrong_moves, 2)

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
        progress.line = ["e5e8"]
        progress.save()
        state = engine.get_state(progress)
        self.assertEqual(progress.line, [])
        self.assertEqual(state.phase, engine.Phase.MOVE)

    def test_next_puzzle(self):
        other = verify_proposal(self.category, proposal(CHECKING_KEY))
        other.save()
        self.assertIn(engine.next_puzzle(self.user, self.category), [self.puzzle, other])

        # A started puzzle without solved branches comes first
        progress = engine.get_progress(self.user, other)
        self.assertEqual(engine.next_puzzle(self.user, self.category), other)

        # Once a branch is solved, puzzles without solved branches remain
        for uci in ["c1c7", "f7f8", "a6a8"]:
            engine.play_move(progress, uci) if uci != "f7f8" else engine.choose_reply(progress, uci)
        self.assertEqual(progress.completed_branches, ["f7f8"])
        self.assertEqual(engine.next_puzzle(self.user, self.category), self.puzzle)

        # Without new puzzles the user picks a puzzle with open branches
        UserChessPuzzle.objects.create(user=self.user, puzzle=self.puzzle, completed_branches=["b8a8", "b8c8"])
        self.assertIsNone(engine.next_puzzle(self.user, self.category))
        self.assertEqual(engine.puzzles_with_open_branches(self.user, self.category), [progress])


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

        response = self.client.post(url + "move/", {"move": "a5b6"}, headers=headers)
        self.assertContains(response, 'data-phase="reply"')
        self.assertContains(response, "Kc8")
        response = self.client.post(url + "reply/", {"move": "b8c8"}, headers=headers)
        self.assertContains(response, "mate now")
        response = self.client.post(url + "hint/", headers=headers)
        self.assertContains(response, "hint")
        response = self.client.post(url + "move/", {"move": "e5e8"}, headers=headers)
        self.assertContains(response, "Checkmate!")
        self.assertContains(response, "Try another defence")

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
        UserChessPuzzle.objects.create(user=self.user, puzzle=self.puzzle, completed_branches=["b8a8"])
        response = self.client.get("/categories/mate-in-2/")
        self.assertContains(response, "1 / 2 lines")
        UserChessPuzzle.objects.filter(puzzle=self.puzzle).update(completed_branches=["b8a8", "b8c8"])
        response = self.client.get("/categories/mate-in-2/")
        self.assertContains(response, "All done")
