"""多人类局（#2609）：发牌、私有发词、人类节点绑定与公开参数的隔离。

单人类局走原流程，由 flow_baseline 与其余测试覆盖；这里只测两名及以上人类。
偷看者视角的断言（T1/T2/T4/T5/T10/T11）以"任何公开出口里都不能出现某个词"表达：
主持人命令输出、群里的副屏参数、run.input、人类节点的 instruction。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "undercover.py"
spec = importlib.util.spec_from_file_location("undercover_multi_human", SCRIPT)
assert spec and spec.loader
uc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uc)

SESSION = "group:game"
HUMANS = ("human_a", "human_b", "human_c")
BOTS = ("bot-1", "bot-2", "bot-3", "bot-4", "bot-5")


def human_nodes(yaml_text: str) -> dict[str, str]:
    """Split a rendered definition into node blocks and keep the human_input ones."""
    blocks: dict[str, str] = {}
    current = None
    for line in yaml_text.splitlines():
        if line.startswith("      ") and not line.startswith("       ") and line.strip().endswith(":"):
            current = line.strip()[:-1]
            blocks[current] = ""
        elif current:
            blocks[current] += line + "\n"
    return {k: v for k, v in blocks.items() if "kind: human_input" in v}


class MultiHumanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"BOT_DATA_DIR": self.temp.name}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.humans = list(HUMANS[:2])
        self.contexts: list[list[str]] = []
        self.context_result = (0, '{"ok":true}', "")

    def session(self):
        participants = [{"bot_uuid": "host-id", "bot_name": "主持人", "actor_kind": "bot", "role": "manager"}]
        participants += [{"bot_uuid": b, "bot_name": f"玩家{b}", "actor_kind": "bot", "role": "worker"} for b in BOTS]
        participants += [{"bot_uuid": h, "bot_name": h.upper(), "actor_kind": "human", "mode": "present"} for h in self.humans]
        return {"id": SESSION, "group_id": "group", "participants": participants}

    def cli(self, *args, **kwargs):
        if args[:2] == ("session", "get"):
            return 0, json.dumps(self.session()), ""
        if args[:2] == ("group-context", "add"):
            self.contexts.append(list(args))
            return self.context_result
        return 0, '{"allowed":true}', ""

    def invoke(self, *args):
        out = io.StringIO()
        with patch("sys.argv", [str(SCRIPT), *args]), contextlib.redirect_stdout(out):
            try:
                uc.main()
            except SystemExit as exc:
                self.assertIn(exc.code, (0, 2))
        return json.loads(out.getvalue())

    def deal(self, players: int = 5, seed: int = 7, undercover: int = 1):
        with patch.object(uc, "bcs_cli", side_effect=self.cli):
            begin = self.invoke("begin", "--session", SESSION, "--group", "group", "--referee-uuid", "host-id",
                                "--players", str(players), "--undercover", str(undercover))
            self.assertTrue(begin["human_present"], begin)
            args = shlex.split(begin["init_command"])[1:] + ["--seed", str(seed)]
            return begin, self.invoke(*args)

    def assert_no_words(self, payload, state, where: str):
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        for word in state["words"].values():
            self.assertNotIn(word, text, f"word leaked through {where}")

    # --- 发牌 ---------------------------------------------------------------

    def test_begin_lists_every_human_and_passes_players(self):
        begin, init = self.deal()
        self.assertEqual(begin["human_actor_ids"], list(HUMANS[:2]))
        args = shlex.split(begin["init_command"])
        self.assertEqual([args[i + 1] for i, a in enumerate(args) if a == "--human"], list(HUMANS[:2]))
        self.assertEqual(args[args.index("--players") + 1], "5")
        self.assertTrue(init["ok"], init)

    def test_two_humans_three_bots_and_three_humans_three_bots(self):
        for humans, players in ((2, 5), (3, 6)):
            with self.subTest(humans=humans):
                self.humans = list(HUMANS[:humans])
                self.contexts.clear()
                _, init = self.deal(players=players)
                state = uc.load_state(SESSION)
                kinds = [s["kind"] for s in state["seats"]]
                self.assertEqual((kinds.count("human"), kinds.count("bot")), (humans, players - humans))
                self.assertEqual(sorted(s["actor_id"] for s in state["seats"] if s["kind"] == "human"), self.humans)
                self.assertEqual(len(self.contexts), humans)
                uc.state_path(SESSION).unlink()

    def test_init_output_and_status_never_carry_a_word(self):
        _, init = self.deal()
        state = uc.load_state(SESSION)
        self.assertNotIn("human_word", init)
        self.assertEqual(init["word_delivery"], "group_context")
        self.assert_no_words(init, state, "init output")
        with patch.object(uc, "bcs_cli", side_effect=self.cli):
            status = self.invoke("status", "--session", SESSION, "--full")
            my_word = self.invoke("my-word", "--session", SESSION)
        self.assert_no_words(status, state, "status")
        self.assert_no_words(my_word, state, "my-word")
        self.assertEqual(sorted(status["human_seats"]), sorted(s["seat"] for s in state["seats"] if s["kind"] == "human"))

    def test_private_word_entries_are_visible_to_referee_and_owner_only(self):
        """T10：每个人类一条 session 级条目，visible_to 恰好是 [主持人, 本人]，不设 collect_from。"""
        self.deal()
        state = uc.load_state(SESSION)
        key = state["word_context_key"]
        self.assertRegex(key, r"^[0-9a-f]{16}$")
        by_name = {}
        for call in self.contexts:
            opts = dict(zip(call[2::2], call[3::2]))
            by_name[opts["--name"]] = opts
            self.assertEqual(opts["--scope-level"], "session")
            self.assertEqual(opts["--session-id"], SESSION)
            self.assertNotIn("--collect-from", opts)
        for seat in (s for s in state["seats"] if s["kind"] == "human"):
            opts = by_name[uc.word_context_name(key, seat["seat"])]
            self.assertEqual(json.loads(opts["--visible-to"]), {"userIds": ["host-id", seat["actor_id"]]})
            self.assertEqual(opts["--content"], f"你的词语是：{seat['word']}")

    def test_conflict_or_failure_stops_dealing_without_state(self):
        for result, code in (((1, "", "HTTP 409 conflict"), "WORD_CONTEXT_CONFLICT"),
                             ((1, "", "HTTP 500"), "WORD_DEAL_FAILED")):
            with self.subTest(code=code):
                self.context_result = result
                _, init = self.deal()
                self.assertEqual(init["error"], code)
                self.assertFalse(uc.state_path(SESSION).exists())

    def test_absent_or_unlisted_human_cannot_be_dealt(self):
        with patch.object(uc, "bcs_cli", side_effect=self.cli):
            result = self.invoke("init", "--session", SESSION, "--group", "group", "--referee-uuid", "host-id",
                                 "--human", "human_a", *[x for b in BOTS for x in ("--bot", f"玩家{b}={b}")])
        self.assertEqual(result["error"], "ROSTER_MISMATCH")
        self.assertFalse(uc.state_path(SESSION).exists())

    def test_player_count_bounds(self):
        for players in (3, 9, 2):
            with self.subTest(players=players):
                _, init = self.deal(players=players)
                self.assertEqual(init["error"], "BAD_CONFIG")

    # --- 节点与公开参数 -------------------------------------------------------

    def rendered(self):
        self.deal()
        speak = uc.prepare_speak_run(SESSION, False)
        state = uc.load_state(SESSION)
        vote_yaml, vote_bindings = uc.render_vote_yaml(state)
        return state, speak, vote_yaml, vote_bindings

    def test_human_nodes_are_bound_and_carry_no_word(self):
        """T2 的定义侧：人类节点绑定到本人；instruction 与 UI 上下文都不含词。"""
        state, speak, vote_yaml, _ = self.rendered()
        speak_yaml = Path(speak["yaml_path"]).read_text(encoding="utf-8")
        for yaml_text in (speak_yaml, vote_yaml):
            nodes = human_nodes(yaml_text)
            self.assertEqual(len(nodes), 2)
            for node_id, body in nodes.items():
                seat = uc.seat_of(state, int(node_id.split("_")[1]))
                self.assertIn(f"type: runtime_actor\n          actor: \"{seat['actor_id']}\"", body)
                self.assert_no_words(body, state, f"instruction of {node_id}")
                self.assertNotIn('"word"', body)
        # Bot 节点仍按原方式拿到自己的词（Bot 收不到群广播，T7 由运行局检查）。
        self.assertTrue(any(word in speak_yaml for word in state["words"].values()))

    def test_public_outputs_never_carry_a_word_or_viewer_specific_fields(self):
        """T4/T5：群里的副屏参数和 run.input 只有公共信息。"""
        state, speak, _, _ = self.rendered()
        panel = json.loads(Path(speak["panel_params_path"]).read_text(encoding="utf-8"))
        run_input = json.loads(Path(speak["input_path"]).read_text(encoding="utf-8"))
        vote_panel = uc.public_panel_projection(state, "vote", 1)
        for name, payload in (("speak panel", panel), ("vote panel", vote_panel), ("run.input", run_input),
                              ("announcement", speak["announcement"])):
            self.assert_no_words(payload, state, name)
        for params in (panel, vote_panel):
            self.assertNotIn("currentViewerActorId", params)
            self.assertNotIn("currentAction", params)
            self.assertEqual(params["privateWord"], {"contextKey": state["word_context_key"], "scopeLevel": "session"})
        living = {uc.actor_id_for(s, state) for s in uc.alive_seats(state)}
        self.assertEqual({c["actorId"] for c in vote_panel["voteCandidates"]}, living)

    def test_vote_starter_falls_back_to_an_eliminated_bot(self):
        self.deal()
        uc.prepare_speak_run(SESSION, False)
        state = uc.load_state(SESSION)
        for seat in state["seats"]:
            if seat["kind"] == "bot":
                seat["alive"] = False
        yaml_text, bindings = uc.render_vote_yaml(state)
        starter = min((s for s in state["seats"] if s["kind"] == "bot"), key=lambda s: s["seat"])
        self.assertIn(f"binding: {starter['binding']}", yaml_text.split("vote_start:")[1].split("vote_")[0])
        self.assertIn(f"{starter['binding']}={starter['bot_uuid']}", bindings)
        self.assertEqual(len(human_nodes(yaml_text)), 2)

    def test_structured_ballots_resolve_each_human_by_actor_id(self):
        self.deal()
        uc.prepare_speak_run(SESSION, False)
        state = uc.load_state(SESSION)
        a, b = (s for s in state["seats"] if s["kind"] == "human")
        ballot = json.dumps({"kind": "vote", "target_actor_id": b["actor_id"]})
        self.assertEqual(uc.parse_ballot(state, a["seat"], ballot), (b["seat"], None))
        self.assertEqual(uc.parse_ballot(state, b["seat"], ballot), (None, "投了自己"))

    def test_injected_leak_is_caught(self):
        """T11：把词塞回人类节点的 UI 上下文，上面的断言必须失败。"""
        original = uc.append_ui_context

        def leaky(instruction, context):
            return original(instruction, {**context, "word": "LEAK"})

        state, speak, _, _ = self.rendered()
        speak_yaml = Path(speak["yaml_path"]).read_text(encoding="utf-8")
        self.assertNotIn('"word"', "".join(human_nodes(speak_yaml).values()))
        uc.state_path(SESSION).unlink()
        self.contexts.clear()
        with patch.object(uc, "append_ui_context", side_effect=leaky):
            _, speak, _, _ = self.rendered()
        leaked = "".join(human_nodes(Path(speak["yaml_path"]).read_text(encoding="utf-8")).values())
        with self.assertRaises(AssertionError):
            self.assertNotIn('"word"', leaked)


if __name__ == "__main__":
    unittest.main()
