from utils.config import GROQ_API_KEY  

from runner import resolve_one_conflict
from agent import get_merge_conflict_agent

conflict = {
    "filename": "discounts.py",

    "ancestor":
'''def get_discount(user, cart_total):
    if user.is_member:
        return 0.10
    return 0.0
''',

    "main_version":
'''def get_discount(user, cart_total):
    if cart_total > 100:
        return 0.15
    if user.is_member:
        return 0.10
    return 0.0
''',

    "incoming_version":
'''def get_discount(user, cart_total):
    if user.is_member and user.days_as_member < 30:
        return 0.20
    if user.is_member:
        return 0.10
    return 0.0
''',

    "extra_context":
'''# discounts.py -- pricing rules for checkout
# get_discount returns a fraction (0.0 - 1.0) applied to the cart total.
# user has: .is_member (bool), .days_as_member (int)
# cart_total is a float (dollars).

def get_discount(user, cart_total):
    ...

def apply_discount(user, cart_total):
    return cart_total * (1 - get_discount(user, cart_total))
''',
}

agent = get_merge_conflict_agent()
result = resolve_one_conflict(agent, conflict)

if result is None:
    print("Resolution failed -- check the error printed above.")
else:
    print("MERGED CODE:\n", result.merged_code)
    print("\nMAIN INTENT:\n", result.main_intent)
    print("\nINCOMING INTENT:\n", result.incoming_intent)
    print("\nREASONING:\n", result.reasoning)
    print("\nCONFIDENCE:", result.confidence)
    print("CONFIDENCE NOTE:", result.confidence_note)
    print("\nALTERNATIVES:\n", result.alternatives)
