import json
import os
import unittest
from types import SimpleNamespace

import numpy as np

from emulsa import assistant as a
from emulsa.engine import resolve


def reply(payload, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=json.dumps(payload))])


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def full_look(**over):
    look = a.look_to_schema({})
    look.update(over)
    return look


class SanitizeTests(unittest.TestCase):
    def test_values_are_clamped_and_junk_dropped(self):
        out = a.sanitize_look({"contrast": 99, "saturation": -5, "exposure": "nan", "grain": float("inf"),
                               "evil": "__import__('os')", "hsl": [{"color": "blue", "hue": 500, "sat": 9, "lum": -3},
                                                                    {"color": "not-a-colour", "hue": 1}]})
        self.assertEqual(out["contrast"], 1.0)
        self.assertEqual(out["saturation"], 0.0)
        self.assertEqual(out["exposure"], 0.0)
        self.assertEqual(out["grain"], 0.0)
        self.assertNotIn("evil", out)
        self.assertEqual(out["hsl"], {"blue": {"hue": 30.0, "sat": 2.0, "lum": -1.0}})

    def test_garbage_falls_back_to_current_look(self):
        current = {"contrast": 0.3}
        self.assertEqual(a.sanitize_look("rm -rf /", current), resolve(current))
        self.assertEqual(a.sanitize_look(None, current), resolve(current))

    def test_schema_round_trip(self):
        params = resolve({"contrast": 0.2, "hsl": {"red": {"sat": 1.1}}, "split_shadows": [200, 0.3]})
        self.assertEqual(a.sanitize_look(a.look_to_schema(params))["split_shadows"], [200.0, 0.3])

    def test_schema_follows_structured_output_rules(self):
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(sorted(node["required"]), sorted(node["properties"]))
                for bad in ("minimum", "maximum", "minLength", "maxLength"):
                    self.assertNotIn(bad, node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(a.REPLY_SCHEMA)


class ParseTests(unittest.TestCase):
    def test_look_only_applied_when_asked(self):
        msg, look, name = a.parse_reply(json.dumps({"reply": "Need more info?", "apply_look": False,
                                                    "look_name": "x", "look": full_look()}), {})
        self.assertIsNone(look)
        msg, look, name = a.parse_reply(json.dumps({"reply": "Warmer.", "apply_look": True,
                                                    "look_name": "  Golden\nhour  ", "look": full_look(temperature=30)}), {})
        self.assertEqual(look["temperature"], 30.0)
        self.assertEqual(name, "Golden hour")

    def test_non_json_is_shown_as_text_without_a_look(self):
        msg, look, _ = a.parse_reply("<b>hello</b>", {})
        self.assertEqual(msg, "<b>hello</b>")
        self.assertIsNone(look)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.photo = np.random.default_rng(0).random((1500, 1000, 3)).astype(np.float32)

    def test_request_shape(self):
        client = FakeClient([reply({"reply": "Done.", "apply_look": True, "look_name": "Teal",
                                    "look": full_look(split_shadows_hue=190, split_shadows_amount=0.3)})])
        conv = a.Conversation("sk-test", client=client)
        msg, look, name = conv.send("make it teal", self.photo, [self.photo[:500]], {})
        call = client.calls[0]
        self.assertEqual(call["model"], a.DEFAULT_MODEL)
        self.assertEqual(call["output_config"]["format"]["schema"], a.REPLY_SCHEMA)
        images = [b for b in call["messages"][0]["content"] if b["type"] == "image"]
        self.assertEqual(len(images), 2)
        from PIL import Image
        import base64, io
        w, h = Image.open(io.BytesIO(base64.b64decode(images[0]["source"]["data"]))).size
        self.assertLessEqual(max(w, h), a.MAX_SIDE)
        self.assertEqual(look["split_shadows"], [190.0, 0.3])

    def test_failed_request_leaves_history_retryable(self):
        client = FakeClient([RuntimeError("offline"), reply({"reply": "ok", "apply_look": False,
                                                             "look_name": "", "look": full_look()})])
        conv = a.Conversation("sk-test", client=client)
        with self.assertRaises(RuntimeError):
            conv.send("hi", None, [], {})
        self.assertEqual(conv.history, [])
        conv.send("hi", None, [], {})
        self.assertEqual([m["role"] for m in conv.history], ["user", "assistant"])

    def test_refusal(self):
        conv = a.Conversation("k", client=FakeClient([reply({}, stop="refusal")]))
        msg, look, _ = conv.send("x", None, [], {})
        self.assertIsNone(look)
        self.assertEqual(conv.history, [])

    def test_history_is_trimmed(self):
        payload = {"reply": "ok", "apply_look": False, "look_name": "", "look": full_look()}
        client = FakeClient([reply(payload) for _ in range(10)])
        conv = a.Conversation("k", client=client)
        for _ in range(10):
            conv.send("again", None, [], {})
        last = client.calls[-1]["messages"]
        self.assertLessEqual(len(last), a.MAX_TURNS_KEPT)
        self.assertEqual(last[0]["role"], "user")


class KeyTests(unittest.TestCase):
    def test_key_is_masked(self):
        self.assertEqual(a.mask_key("sk-ant-abcdefghijkl1234"), "…1234")
        self.assertEqual(a.mask_key(None), "Not set")

    def test_environment_key_wins(self):
        os.environ["ANTHROPIC_API_KEY"] = "env-key"
        try:
            self.assertEqual(a.KeyStore().get(), "env-key")
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_session_fallback(self):
        ks = a.KeyStore()
        ks._keyring = None
        ks.set("  sk-session  ")
        self.assertEqual(ks.get(), "sk-session")
        ks.clear()
        self.assertIsNone(ks.get())


if __name__ == "__main__":
    unittest.main()


class SafetyTests(unittest.TestCase):
    def test_export_suffix_cannot_escape_the_folder(self):
        from emulsa.imageio import safe_suffix
        for evil in ("../../etc/passwd", "..\\..\\Windows\\x", "/abs", "C:\\x", "a/b", "_ok-name.v2"):
            out = safe_suffix(evil)
            self.assertNotIn("/", out); self.assertNotIn("\\", out); self.assertNotIn("..", out); self.assertNotIn(":", out)
        self.assertEqual(safe_suffix("_kodak-portra-400"), "_kodak-portra-400")

    def test_api_key_never_written_to_settings(self):
        import tempfile
        from emulsa.store import Store
        with tempfile.TemporaryDirectory() as d:
            store = Store(os.path.join(d, "settings.json"))
            ks = a.KeyStore(); ks._keyring = None
            ks.set("sk-ant-secret-value-1234567890")
            store.set("assistant_model", a.DEFAULT_MODEL)
            store.add_custom("x", {}, None)
            self.assertNotIn("sk-ant-secret", open(store.path).read())
