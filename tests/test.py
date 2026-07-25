from utils.config import GROQ_API_KEY

from runner import resolve_one_conflict
from agent import get_merge_conflict_agent

conflict = {
    "filename": "story.py",
    "ancestor":
'''def story():
    print("Once upon a time, under a starry night, there lived a lion in his den.")
''',
    "main_version":
'''def story():
    print("Once upon a time, under a starry night, there lived a lion in his den.")
    print("That morning, a fierce storm rolled in over the jungle.")
''',
    "incoming_version":
'''def story():
    print("Once upon a time, under a starry night, there lived a lion in his den.")
    print("A wise old owl watched silently from a nearby tree.")
''',
    "extra_context":
'''# story.py -- prints a short fable

def story():
    ...

if __name__ == "__main__":
    story()
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