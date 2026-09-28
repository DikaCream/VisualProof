# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Smoke test: does web screenshot rendering plus multimodal judgement reach
consensus on Studionet? Kept deliberately tiny so a failure is cheap to read.
"""

import json

from genlayer import *  # noqa: F401
import genlayer.gl as gl


class VisionSmoke(gl.Contract):
    last: str
    shots: u256

    def __init__(self):
        self.last = ""
        self.shots = u256(0)

    @gl.public.write
    def probe(self, url: str) -> str:
        """Screenshot the page, read it with a vision prompt, store the result."""

        def read_shot() -> str:
            shot = gl.nondet.web.render(url, mode="screenshot")
            prompt = (
                "You are looking at a screenshot of a web page. "
                "Answer with STRICT JSON only, no prose, no fences: "
                '{"heading": "<the main visible heading text>", "has_links": true or false}'
            )
            raw = gl.nondet.exec_prompt(prompt, images=[shot], response_format="json")
            if isinstance(raw, str):
                return raw
            return json.dumps(raw, sort_keys=True)

        principle = (
            "Both answers describe the same web page screenshot. They are "
            "equivalent if and only if both identify the same main heading "
            "text (case and surrounding whitespace ignored) and agree on "
            "has_links."
        )
        out = gl.eq_principle.prompt_comparative(read_shot, principle)
        self.last = str(out)
        self.shots = u256(int(self.shots) + 1)
        return self.last

    @gl.public.view
    def get_state(self) -> dict:
        return {"last": self.last, "shots": int(self.shots)}
