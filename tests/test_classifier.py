from utils.config import GROQ_API_KEY  # triggers load_dotenv()
 
from classifier import get_classifier_agent, classify_reply
 
agent = get_classifier_agent()
 
# the alternatives that were "offered" -- so numbered/described references resolve
alternatives = [
    "Apply the new-member discount first, then the cart-total discount.",
    "Always apply the cart-total discount before considering membership.",
]
 
# (reply text, what we EXPECT the decision to be)
cases = [
    ("Yes, looks good, merge it.",                              "approve"),
    ("lgtm",                                                    "approve"),
    ("No problem, ship it.",                                    "approve"),   # tricky: contains "no"
    ("No, flip the precedence -- cart total should win.",       "reject"),
    ("go with alternative 2",                                   "reject"),    # numbered reference
    ("do the cumulative one instead",                           "reject"),    # described reference
    ("Don't bother, I'll handle this conflict myself.",         "abort"),
    ("leave it, I'll sort it out manually",                     "abort"),
]
 
print("Testing classifier on sample replies:\n")
for reply_text, expected in cases:
    result = classify_reply(agent, reply_text, alternatives)
    got = result.decision if result else "FAILED"
    mark = "OK " if got == expected else "XX "
    print(f"[{mark}] expected={expected:8} got={got:8}  reply={reply_text!r}")
    if result and result.decision == "reject" and result.feedback:
        print(f"       feedback captured: {result.feedback!r}")
    print()