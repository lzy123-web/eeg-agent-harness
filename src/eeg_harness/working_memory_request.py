"""Small request-delivery account, not an independent intent parser or planner.

The existing LLM proposes quoted requirements alongside a goal and reviews
coverage alongside its final answer. The program checks declared associations
against real results. Omitted natural-language intent still needs evaluation.
"""
from .working_memory import clone


class RequestProgress:
    def __init__(self, controller):
        self.controller = controller
        self.frames = []

    def begin_turn(self, text):
        self.frames.append({"turn": self.controller.store.turn, "original_request": text,
                            "requirements": [], "coverage_review": None})

    def related_goals(self):
        c = self.controller
        return [g for g in c.store.subgoals if g.turn == c.store.turn or
                g.subgoal_id in c.touched_goals or g.subgoal_id in c.restored]

    def valid_quote(self, quote):
        c = self.controller
        turns = {c.store.turn} | {g.turn for g in self.related_goals()}
        return (isinstance(quote, str) and bool(quote.strip()) and
                any(quote in c.requests[t-1] for t in turns))

    def validate_requirements(self, requirements, deliveries):
        if not isinstance(requirements, list):
            return "requirements must be a list"
        keys = {d.get("key") for d in deliveries}
        for item in requirements:
            if (not isinstance(item, dict) or set(item) != {"quote", "delivery_keys"} or
                    not self.valid_quote(item["quote"]) or not isinstance(item["delivery_keys"], list) or
                    not item["delivery_keys"] or any(k not in keys for k in item["delivery_keys"])):
                return "Each requirement needs an exact relevant user quote and existing local delivery_keys"
        return None

    def bind(self, requirements, proposed, goal):
        # Equivalent renamed deliveries may have reused an older completed goal.
        mapping = {}
        for d in proposed:
            matches = [x["key"] for x in goal.deliveries if x["tool"] == d["tool"] and x["scope"] == d["scope"]]
            if len(matches) == 1:
                mapping[d["key"]] = matches[0]
        for item in requirements:
            row = {"quote": item["quote"], "subgoal_id": goal.subgoal_id,
                   "delivery_keys": [mapping.get(k, k) for k in item["delivery_keys"]],
                   "interpretation_origin": "model_proposed_not_independent_intent_proof"}
            if row not in self.frames[-1]["requirements"]:
                self.frames[-1]["requirements"].append(row)

    def view(self):
        c = self.controller
        goals = []
        for g in self.related_goals():
            check = c.store.completion_check(g)
            goals.append({"subgoal_id": g.subgoal_id, "originating_turn": g.turn, "record": g.record,
                          "status": g.status, "declared_contract_valid": check["valid"],
                          "deliveries": check.get("deliveries", []), "unresolved": clone(g.unresolved)})
        return {**clone(self.frames[-1]), "related_scientific_goals": goals,
                "unrelated_pending_goal_ids": [g.subgoal_id for g in c.store.subgoals
                    if g.status != "completed" and g.subgoal_id not in {r["subgoal_id"] for r in goals}],
                "next": "Deliver an evidence-grounded answer if the ORIGINAL request is covered; otherwise continue its missing items or clarify. Do not restart completed equivalent analysis.",
                "coverage_is_model_review": True}

    def review(self, status, coverage, complete):
        c, store = self.controller, self.controller.store
        if not isinstance(coverage, list) or not coverage or type(complete) is not bool:
            return "Supply coverage and coverage_complete alongside the final answer, not a separate control round"
        if status == "completed" and not complete:
            return "A claimed incomplete original request cannot finish as completed"
        seen = set()
        for item in coverage:
            if (not isinstance(item, dict) or set(item)-{"quote", "result_ids", "unresolved"} or
                    not self.valid_quote(item.get("quote")) or not isinstance(item.get("result_ids"), list)):
                return "Coverage needs a relevant literal user quote and actual result_ids"
            if status == "completed" and (item.get("unresolved") or not item["result_ids"]):
                return "A missing or unresolved covered item requires partial/clarification delivery"
            for ident in item["result_ids"]:
                entry = store.find_entry(ident)
                if entry is None or not store._binding_valid(entry):
                    return "Coverage references an unavailable or invalid scientific result"
                mentioned = store._mentioned_records(item["quote"])
                if mentioned and entry.record not in mentioned:
                    return "The quoted requested record and the cited scientific result disagree"
                if ident not in c.visible_evidence_ids:
                    return "Read the actual result before answering; a locator or same-batch unseen result is insufficient"
                seen.add(ident)
        if status == "completed":
            relevant = {g.subgoal_id for g in self.related_goals()}
            for frame in self.frames:
                for req in frame["requirements"]:
                    if req["subgoal_id"] not in relevant:
                        continue
                    g = store.find_subgoal(req["subgoal_id"])
                    if g.status == "completed" and g.turn != store.turn:
                        # Restoring completed history supplies context, not an
                        # obligation to re-answer the whole earlier question.
                        continue
                    states = store.completion_check(g)["deliveries"]
                    for key in req["delivery_keys"]:
                        row = next((s for s in states if s["key"] == key), None)
                        if not row or row["status"] != "satisfied" or row["result_id"] not in seen:
                            return "Declared request output has not been delivered and covered by a real visible result"
        self.frames[-1]["coverage_review"] = {"coverage": clone(coverage), "coverage_complete": complete,
            "status": status, "accepted": False, "meaning": "Model's original-request review; program verifies declared real evidence, not all natural-language semantics"}
        return None
