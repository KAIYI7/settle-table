"""DISPOSABLE domain concurrency experiment; no server, sockets, UI or database.

Questions: Can concurrent diners avoid lost financial edits/overclaims? Can an
organizer finalize stale state? This lock/role model is an explicit scenario,
not a chosen production authorization or realtime architecture.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading


class Rejected(ValueError):
    pass


class Meal:
    def __init__(self):
        self.lock = threading.Lock()
        self.members = {"organizer", "A", "B"}
        self.revision = 0
        self.financial_revision = 0
        self.reviewed = True
        self.finalized = False
        self.items = {"dish": {"revision":0,"quantity":3,"line_sen":1000,"claims":{}},
                      "tea": {"revision":0,"quantity":1,"line_sen":300,"claims":{}}}
        self.operations = {}
        self.events = []

    def snapshot(self):
        return {"revision":self.revision,"financial_revision":self.financial_revision,
                "reviewed":self.reviewed,"finalized":self.finalized,
                "items":deepcopy(self.items)}

    def apply(self, actor, op_id, kind, expected, payload):
        with self.lock:
            # Access checked even on duplicate: revocation is not bypassed by replay.
            if actor not in self.members:
                raise Rejected("membership_revoked_or_unknown")
            operation = (actor, op_id)
            body = json.dumps([kind, expected, payload], sort_keys=True)
            if operation in self.operations:
                before, result = self.operations[operation]
                if before != body:
                    raise Rejected("operation_id_reused_with_different_content")
                return deepcopy(result)
            if self.finalized and kind != "amend":
                raise Rejected("finalized_requires_explicit_amendment")
            if kind == "claim":
                if payload["person"] != actor:
                    raise Rejected("cannot_edit_another_diner_claim")
                item = self.items[payload["item"]]
                if expected != {"item_revision":item["revision"],
                                "financial_revision":self.financial_revision}:
                    raise Rejected("stale_item_or_financial_revision")
                amount = payload["quantity"]
                if type(amount) is not int or amount < 0:
                    raise Rejected("invalid_quantity")
                claims = {**item["claims"], actor:amount}
                if sum(claims.values()) > item["quantity"]:
                    raise Rejected("quantity_capacity_exceeded")
                item["claims"] = claims
                item["revision"] += 1
            elif kind == "amount":
                if actor != "organizer":
                    raise Rejected("organizer_only_financial_edit")
                if expected != self.revision:
                    raise Rejected("stale_meal_revision")
                if type(payload["line_sen"]) is not int or payload["line_sen"] < 0:
                    raise Rejected("money_must_be_nonnegative_integer_sen")
                self.items[payload["item"]]["line_sen"] = payload["line_sen"]
                self.items[payload["item"]]["revision"] += 1
                self.financial_revision += 1
                self.reviewed = False
            elif kind in ("finalize", "review", "amend"):
                if actor != "organizer":
                    raise Rejected("organizer_only_transition")
                if expected != self.revision:
                    raise Rejected("stale_meal_revision")
                if kind == "finalize":
                    if not self.reviewed or any(sum(x["claims"].values()) != x["quantity"] for x in self.items.values()):
                        raise Rejected("review_or_assignment_incomplete")
                    self.finalized = True
                elif kind == "review":
                    self.reviewed = True
                else:
                    self.finalized = False
                    self.reviewed = False
            else:
                raise Rejected("unknown_action")
            self.revision += 1
            event = {"sequence":self.revision,"actor":actor,"op_id":op_id,
                     "kind":kind,"snapshot":self.snapshot()}
            self.events.append(deepcopy(event))
            self.operations[operation] = (body, deepcopy(event))
            return event


def main():
    checks = []
    def reject(name, reason, action):
        try:
            action()
        except Rejected as error:
            assert str(error) == reason, (name, str(error), reason)
            checks.append({"case":name,"result":"expected_rejection","reason":reason})
        else:
            raise AssertionError(name)

    # Baseline: replacing a whole stale claim map loses another diner's edit.
    a, b = {"A":2}, {"B":1}
    naive = a.copy()
    naive = b.copy()
    assert "A" not in naive
    checks.append({"case":"last_writer_wins_counterexample","lost_A_claim":True})

    meal = Meal()
    stale = {"item_revision":0,"financial_revision":0}
    first = meal.apply("A","claim-A","claim",stale,{"item":"dish","person":"A","quantity":2})
    reject("same_item_stale_write", "stale_item_or_financial_revision",
           lambda:meal.apply("B","claim-B","claim",stale,{"item":"dish","person":"B","quantity":1}))
    second = meal.apply("B","fresh-B","claim",{"item_revision":1,"financial_revision":0},
                        {"item":"dish","person":"B","quantity":1})
    assert meal.items["dish"]["claims"] == {"A":2,"B":1}
    # A distinct unchanged item can accept its current item revision despite other edits.
    meal.apply("B","tea","claim",stale,{"item":"tea","person":"B","quantity":1})
    checks.append({"case":"distinct_item_edits_preserved","snapshot":meal.snapshot()})
    before = meal.revision
    assert meal.apply("A","claim-A","claim",stale,{"item":"dish","person":"A","quantity":2}) == first
    assert meal.revision == before
    checks.append({"case":"duplicate_operation_replayed_without_reapply","revision":before})
    reject("duplicate_id_changed_body","operation_id_reused_with_different_content",
           lambda:meal.apply("A","claim-A","claim",stale,{"item":"dish","person":"A","quantity":1}))
    reject("diner_changes_another_claim","cannot_edit_another_diner_claim",
           lambda:meal.apply("A","other","claim",stale,{"item":"tea","person":"B","quantity":0}))
    reject("diner_changes_receipt_amount","organizer_only_financial_edit",
           lambda:meal.apply("A","cost","amount",meal.revision,{"item":"dish","line_sen":999}))
    reject("diner_finalizes","organizer_only_transition",
           lambda:meal.apply("B","final","finalize",meal.revision,{}))
    reject("stale_organizer_finalization","stale_meal_revision",
           lambda:meal.apply("organizer","old-final","finalize",0,{}))
    meal.apply("organizer","edit-cost","amount",meal.revision,{"item":"dish","line_sen":1001})
    reject("stale_financial_basis","stale_item_or_financial_revision",
           lambda:meal.apply("B","stale-tea","claim",{"item_revision":1,"financial_revision":0},
                             {"item":"tea","person":"B","quantity":1}))
    reject("financial_edit_requires_reverification","review_or_assignment_incomplete",
           lambda:meal.apply("organizer","unreviewed-final","finalize",meal.revision,{}))
    meal.apply("organizer","review","review",meal.revision,{})
    meal.apply("organizer","final","finalize",meal.revision,{})
    reject("finalized_claim_mutation","finalized_requires_explicit_amendment",
           lambda:meal.apply("B","after-final","claim",{}, {"item":"tea","person":"B","quantity":0}))
    meal.apply("organizer","amend","amend",meal.revision,{})
    assert not meal.finalized and not meal.reviewed
    checks.append({"case":"explicit_amendment_reopens_review","snapshot":meal.snapshot()})
    # Replay only committed sequence numbers; older/double-delivered events ignored.
    client = {"revision":0}
    for event in reversed(meal.events):
        if event["sequence"] > client["revision"]:
            client = deepcopy(event["snapshot"])
    assert client == meal.snapshot()
    reconnect = [event for event in meal.events if event["sequence"] > second["sequence"]]
    assert reconnect[-1]["snapshot"] == meal.snapshot()
    checks.append({"case":"reconnect_and_out_of_order_snapshots","committed_events":len(meal.events)})
    meal.members.remove("A")
    reject("revocation_blocks_duplicate_replay","membership_revoked_or_unknown",
           lambda:meal.apply("A","claim-A","claim",stale,{"item":"dish","person":"A","quantity":2}))
    # True two-thread race; either winner is allowed, but only one stale write commits.
    raced = Meal()
    barrier = threading.Barrier(2)
    outcomes = []
    def racer(actor):
        barrier.wait()
        try:
            raced.apply(actor,actor,"claim",stale,{"item":"dish","person":actor,"quantity":2})
            outcomes.append("committed")
        except Rejected:
            outcomes.append("rejected")
    threads = [threading.Thread(target=racer,args=(actor,)) for actor in ("A","B")]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(outcomes) == ["committed","rejected"] and raced.revision == 1
    winner = next(iter(raced.items["dish"]["claims"]))
    loser = "B" if winner == "A" else "A"
    reject("fresh_racing_overclaim_rejected","quantity_capacity_exceeded",
           lambda:raced.apply(loser,"retry","claim",{"item_revision":1,"financial_revision":0},
                              {"item":"dish","person":loser,"quantity":2}))
    checks.append({"case":"two_thread_race_single_commit","outcomes":sorted(outcomes),"revision":raced.revision})
    report = {"scope":"DISPOSABLE domain simulation; NOT realtime/network/authentication validation",
              "money":"integer sen","checks":checks,"passed":len(checks),"failed":0,
              "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "limits":["No sockets, invitation tokens, browser clients, Internet latency or persistence",
                        "Lock models a serial authority, not distributed or offline multi-master replication",
                        "Roles are user-confirmed; identity/revocation implementation remains unselected",
                        "No production code or irreversible architecture commitment"]}
    Path(__file__).with_name("results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"passed":len(checks),"failed":0,"scope":report["scope"]}))


if __name__ == "__main__":main()
