from utils.config import GROQ_API_KEY  

from detector import find_all_conflicts          
from runner import resolve_all_conflicts   

from json_writer import write_resolutions_to_json

import sys

repo_path = sys.argv[1] if len(sys.argv) > 1 else "."


conflicts = find_all_conflicts(repo_path)
print(f"Found {len(conflicts)} conflict(s).\n")


resolutions = resolve_all_conflicts(conflicts)


for i, res in enumerate(resolutions, start=1):
    print(f"\n===== Resolution {i} =====")
    if res is None:
        print("(failed to resolve this conflict)")
        continue
    print("MERGED CODE:\n", res.merged_code)
    print("\nMAIN INTENT:\n", res.main_intent)
    print("\nINCOMING INTENT:\n", res.incoming_intent)
    print("\nREASONING:\n", res.reasoning)
    print("\nCONFIDENCE:", res.confidence)
    print("CONFIDENCE NOTE:", res.confidence_note)
    print("\nALTERNATIVES:\n", res.alternatives)


write_resolutions_to_json(resolutions, "resolutions.json")
print("Wrote resolutions to resolutions.json")